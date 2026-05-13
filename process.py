"""HLI 商品画像後処理ツール - Phase 1 (v1)

CLI で対話的にカテゴリ／シリーズ名を聞き、input/ 配下の画像を
カテゴリ別ルールでクロップ・リサイズ・WebP変換し、Dropbox の
規定フォルダへ保存する。寝具系カテゴリの 1200×1200 サムネイル
にはサイズバッジを自動付与する。

使い方:
    python process.py
    python process.py --output-base ./out  # Dropbox 以外へ出力（テスト用）
    python process.py --size-list samples/size_list_sample.csv
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from tqdm import tqdm

import utils as U


# =============================================================================
# 対話プロンプト
# =============================================================================

def prompt_category() -> str:
    """カテゴリ選択。番号を受け取り、フォルダ名を返す。"""
    print("\nカテゴリを選んでください:")
    for i, name in enumerate(U.CATEGORIES, start=1):
        badge_mark = " 🏷️バッジあり" if name in U.BADGE_CATEGORIES else ""
        print(f"  {i:>2}. {name}{badge_mark}")

    while True:
        raw = input("> ").strip()
        if not raw.isdigit():
            print("数字で入力してください。")
            continue
        n = int(raw)
        if 1 <= n <= len(U.CATEGORIES):
            return U.CATEGORIES[n - 1]
        print(f"1〜{len(U.CATEGORIES)} の範囲で入力してください。")


def prompt_series_name() -> str:
    """シリーズ名を自由入力で受け取る。空文字は拒否。"""
    while True:
        print("\nシリーズ名を入力してください（例: 2025春コレクション）:")
        s = input("> ").strip()
        if s:
            # ファイル名に使えない文字を簡易置換
            for ch in '<>:"/\\|?*':
                s = s.replace(ch, "_")
            return s
        print("空のシリーズ名は使えません。")


def prompt_model_name(count: int) -> str:
    """input/ にモデル placeholder 付き画像が count 枚見つかった時のみ呼ばれる。"""
    while True:
        print(f"\nモデル画像が {count} 枚あります。モデル名を入力してください：")
        s = input("> ").strip()
        if s:
            for ch in '<>:"/\\|?*':
                s = s.replace(ch, "_")
            return s
        print("空のモデル名は使えません。")


def confirm_continue(prompt: str) -> bool:
    """y/n 確認。デフォルトは n（安全側）。"""
    ans = input(f"{prompt} [y/N]: ").strip().lower()
    return ans in ("y", "yes")


# =============================================================================
# Dropbox パス確認
# =============================================================================

def resolve_output_base(arg_base: Optional[str]) -> Optional[Path]:
    """--output-base が指定されていればそれを、なければ Dropbox 既定パスを返す。

    既定パスが存在しない場合は警告して続行/中止をユーザーに確認。
    中止が選ばれたら None を返す。
    """
    if arg_base:
        base = Path(arg_base).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        print(f"📁 出力ベース: {base}")
        return base

    base = U.DROPBOX_BASE
    if base.exists():
        print(f"📁 出力ベース: {base}")
        return base

    print(f"⚠️  Dropbox の規定パスが見つかりません: {base}")
    print("   このパスを作成して続行することもできます。")
    if confirm_continue("続行しますか？（n を選ぶと中止）"):
        base.mkdir(parents=True, exist_ok=True)
        return base
    return None


# =============================================================================
# 1画像処理
# =============================================================================

def process_one_image(
    src: Path,
    category: str,
    series_root: Path,
    size_list: Dict[str, "U.ImageMapping"],
    font_path: Path,
    model_name: Optional[str],
) -> Dict[str, int]:
    """1枚の画像を全6出力へ書き出す。各出力の成功数を返す。

    出力 stem 決定の優先順:
      1. CSV に正規化済み商品IDがあり、new_name が空でない → new_name
      2. ファイル名に -model_ がある → transform_stem で置換
      3. それ以外 → 入力 stem のまま
    """
    counts = {spec.label: 0 for spec in U.OUTPUT_SPECS}
    counts["バッジ付与"] = 0

    raw_stem = src.stem
    norm_id  = U.normalize_product_id(raw_stem)
    entry    = size_list.get(norm_id)

    # 出力 stem の決定
    if entry and entry.new_name:
        output_stem = entry.new_name
    else:
        output_stem = U.transform_stem(raw_stem, model_name)

    # バッジ可否
    size_code = entry.size_code if entry else None
    badge_eligible = (
        category in U.BADGE_CATEGORIES
        and size_code is not None
    )

    # 修正3: ウェア / ローブ × モデルの全身クロップ判定
    is_full_body_model = (
        category in U.MODEL_FULL_BODY_CATEGORIES
        and U.MODEL_SCENE_MARKER in raw_stem
    )

    with Image.open(src) as im:
        im.load()
        # EXIF Orientation を反映
        try:
            from PIL import ImageOps
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass

        for spec in U.OUTPUT_SPECS:
            out_path = U.output_path_for_spec(series_root, spec, output_stem, src.suffix)

            if spec.format == "ORIGINAL":
                U.copy_original(src, out_path)
            else:
                shift    = 0.0
                vert_top = None
                vert_bot = None

                if is_full_body_model:
                    # 修正3: 横長 (>1.5) は顔〜上半身、それ以外は全身
                    if spec.width / spec.height > 1.5:
                        vert_top, vert_bot = 0.05, 0.45
                    else:
                        vert_top, vert_bot = 0.10, 0.95
                elif spec.can_badge and category in U.BED_CATEGORIES:
                    # 修正1: ベッド系のサムネイルのみ左カット
                    shift = 0.15

                resized = U.crop_and_resize(im, spec.width, spec.height, shift,
                                             vert_top, vert_bot)
                if spec.can_badge and badge_eligible:
                    resized = U.draw_size_badge(resized, size_code, font_path)
                    counts["バッジ付与"] += 1
                U.save_webp(resized, out_path, spec.quality)

            counts[spec.label] += 1

    return counts


# =============================================================================
# サマリー
# =============================================================================

def print_summary(
    total: int,
    success_counts: Dict[str, int],
    badge_count: int,
    error_count: int,
    elapsed_sec: float,
) -> None:
    print("\n" + "=" * 60)
    print("✅ 処理サマリー")
    print("=" * 60)
    print(f"  総処理件数 : {total}")
    print(f"  成功件数   : {total - error_count}")
    print(f"  エラー件数 : {error_count}")
    print(f"  バッジ付与 : {badge_count}")
    print(f"  処理時間   : {elapsed_sec:.1f} 秒")
    print("\n  フォルダ別書き出し件数:")
    for label, n in success_counts.items():
        if label == "バッジ付与":
            continue
        print(f"    - {label:<30s} : {n}")


# =============================================================================
# エラーログ
# =============================================================================

def append_error_log(log_path: Path, product_id: str, exc: BaseException) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {product_id}: {type(exc).__name__}: {exc}\n")
        f.write(traceback.format_exc())
        f.write("-" * 60 + "\n")


# =============================================================================
# main
# =============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HLI 商品画像後処理ツール (Phase 1 / v1)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input-dir", default="input",
                   help="入力画像フォルダ")
    p.add_argument("--size-list", default="size_list.csv",
                   help="サイズリスト CSV のパス")
    p.add_argument("--output-base", default=None,
                   help="Dropbox 以外に出力する場合のベースパス（テスト用）")
    p.add_argument("--error-log", default="error_log.txt",
                   help="エラーログ出力先")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 60)
    print("📷 HLI 商品画像後処理ツール  (Phase 1 / v1)")
    print("=" * 60)

    # 1. 入力画像の列挙（モデル placeholder 検出のため最初に実施）
    images = U.collect_input_images(Path(args.input_dir))
    if not images:
        print(f"❌ 入力画像が見つかりません: {args.input_dir}/")
        print("   JPG/PNG をこのフォルダに配置してから再実行してください。")
        return 1
    print(f"🖼️  入力画像: {len(images)} 枚")

    # 2. 対話プロンプト
    category    = prompt_category()
    series_name = prompt_series_name()

    # 3. モデル placeholder を含む画像があればモデル名を入力させる
    model_count = U.count_model_images(images)
    model_name: Optional[str] = None
    if model_count > 0:
        model_name = prompt_model_name(model_count)
        print(f"👤 モデル名: {model_name}（{model_count} 枚に適用）")

    # 4. 出力ベース確認
    base = resolve_output_base(args.output_base)
    if base is None:
        print("中止しました。")
        return 1

    series_root = base / category / series_name
    U.ensure_output_dirs(base, category, series_name)
    print(f"📂 シリーズ出力先: {series_root}")

    # 5. 商品リスト読込
    size_list = U.load_size_csv(Path(args.size_list))
    if size_list:
        n_rename = sum(1 for e in size_list.values() if e.new_name)
        n_badge  = sum(1 for e in size_list.values() if e.size_code)
        print(f"📄 商品リスト: {len(size_list)} 件読み込み（リネーム {n_rename} / バッジ {n_badge}）")

    # 6. フォント検出
    try:
        font_path = U.find_japanese_serif_font()
        print(f"🔤 バッジフォント: {font_path}")
    except FileNotFoundError as e:
        if category in U.BADGE_CATEGORIES:
            print(f"❌ {e}")
            return 1
        font_path = None  # type: ignore
        print("⚠️  セリフ系フォントが見つかりませんでしたが、このカテゴリではバッジ未使用なので続行します。")

    # 7. 処理ループ
    total_success: Dict[str, int] = {spec.label: 0 for spec in U.OUTPUT_SPECS}
    total_badge   = 0
    error_count   = 0
    error_log_path = Path(args.error_log)

    t0 = time.time()
    for src in tqdm(images, desc="処理中", unit="枚"):
        try:
            counts = process_one_image(src, category, series_root, size_list, font_path, model_name)
            for label, n in counts.items():
                if label == "バッジ付与":
                    total_badge += n
                else:
                    total_success[label] += n
        except Exception as e:
            error_count += 1
            append_error_log(error_log_path, src.stem, e)
            tqdm.write(f"⚠️  {src.name} でエラー: {e}（error_log.txt に記録）")

    elapsed = time.time() - t0
    print_summary(len(images), total_success, total_badge, error_count, elapsed)

    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
