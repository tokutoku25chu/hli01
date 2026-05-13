"""HLI 商品画像後処理ツール - ユーティリティ

定数（カテゴリ・出力サイズ・バッジ仕様）と、画像処理／フォント検出／
フォルダ作成などの純関数を提供する。
"""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# =============================================================================
# 定数
# =============================================================================

# カテゴリ番号（CLIで表示する順序） → フォルダ名
CATEGORIES: List[str] = [
    "01_リネン",
    "02_ウェア",
    "03_小物",
    "04_タオル・ローブ",
    "05_パッケージ",
    "06_ギフト",
    "10_ノベルティー",
    "11_シモンズ",
    "12_シルク真綿布団",
    "13_ダウン・フェザー製品",
    "14_ブランケット",
]

# ベッド系：サムネイル（1200×1200 バッジ対象）のみ左カット（中心を右に15%シフト）
# 他の出力サイズはすべて中央クロップ。
BED_CATEGORIES = {
    "01_リネン",
    "11_シモンズ",
    "12_シルク真綿布団",
    "13_ダウン・フェザー製品",
    "14_ブランケット",
}

# サイズバッジ対象カテゴリ
BADGE_CATEGORIES = {
    "01_リネン",
    "11_シモンズ",
    "12_シルク真綿布団",
    "13_ダウン・フェザー製品",
    "14_ブランケット",
}

# 有効なサイズコード（表示用ラベルは将来用に保持）
SIZE_CODES: Dict[str, str] = {
    "S":   "シングル",
    "SD":  "セミダブル",
    "D":   "ダブル",
    "WD":  "ワイドダブル",
    "Q":   "クイーン",
    "K":   "キング",
    "USK": "USキング",
}

# Dropbox 出力ベースパス
DROPBOX_BASE = Path.home() / "Dropbox" / "03_HLIデザイン" / "03_素材写真" / "■商品カテゴリ"

# 出力サブフォルダ名
SUBDIR_HIGH_RES = "高画質（印刷用・バナー作成用）"
SUBDIR_SLIDER   = "スライダー用"
SUBDIR_PC       = "PC"
SUBDIR_SP       = "スマホ"
SUBDIR_THUMB    = "サムネイル"
SUBDIR_PSD      = "psd"
SUBDIR_1200x1800 = "1200×1800"  # 全角 × に注意
SUBDIR_1200x1200 = "1200×1200"

# バッジ仕様
BADGE_DIAMETER  = 140
BADGE_MARGIN    = 50
BADGE_BG_COLOR  = (201, 184, 156)        # #C9B89C
BADGE_BG_ALPHA  = int(255 * 0.7)         # 70%
BADGE_TEXT_RGB  = (255, 255, 255)
BADGE_TEXT_ALPHA = 255
BADGE_FONT_RATIO = 0.50                  # 直径の50%
BADGE_FONT_RATIO_LONG = 0.36             # USK など3文字用
BADGE_FLOURISH_COLOR = (255, 255, 255, 220)

# モデル画像 placeholder（ファイル名内のこの文字列を _model{モデル名}_ に置換）
MODEL_MARKER = "_model_"

# モデル写真全般を判別する広めのマーカー（_model_ プレースホルダも _model 検出に含む）
# 修正3 (ウェア/ローブ×モデル) で「このファイルはモデル着用画像か」を判定するのに使う
MODEL_SCENE_MARKER = "_model"

# 修正3: ファイル名に _model を含む場合に「全身クロップ」を適用するカテゴリ
MODEL_FULL_BODY_CATEGORIES = {
    "02_ウェア",
    "04_タオル・ローブ",
}

# 修正2: ベッド系のサムネイル左カットを抑制するマーカー
# 例: mrblkt-other-sofa_1.jpg ← ベッド以外のシーン（椅子・ソファ等）はサムネイルも中央クロップ
OTHER_SCENE_MARKER = "-other"

# 入力フォルダ
INPUT_DIR = Path("input")

# WebP 品質
WEBP_QUALITY_THUMB  = 90
WEBP_QUALITY_NORMAL = 85


# =============================================================================
# 出力仕様（各サイズの定義）
# =============================================================================

@dataclass(frozen=True)
class OutputSpec:
    """1つの出力先の仕様"""
    label: str              # 進捗/ログ表示用
    subdir: Tuple[str, ...] # ベースからの相対パス（タプル）
    width: int
    height: int
    format: str             # "WEBP" | "ORIGINAL"
    quality: int            # WebPのみ有効
    can_badge: bool         # この出力にバッジを描画する候補か（サムネイルのみTrue）


@dataclass(frozen=True)
class ImageMapping:
    """size_list.csv 1 行分。商品IDに対する「新ファイル名」と「サイズコード」。

    どちらも任意。new_name が None なら出力ファイル名は変えず、
    size_code が None ならバッジを描画しない。
    """
    new_name: Optional[str]
    size_code: Optional[str]


OUTPUT_SPECS: List[OutputSpec] = [
    # 高画質：元画像をそのままコピー
    OutputSpec(
        label="高画質（無加工コピー）",
        subdir=(SUBDIR_HIGH_RES,),
        width=0, height=0,         # 無加工
        format="ORIGINAL",
        quality=0,
        can_badge=False,
    ),
    # サムネイル：1200×1200 WebP q=90、バッジ候補
    OutputSpec(
        label="サムネイル 1200×1200",
        subdir=(SUBDIR_THUMB,),
        width=1200, height=1200,
        format="WEBP",
        quality=WEBP_QUALITY_THUMB,
        can_badge=True,
    ),
    # 1200×1800
    OutputSpec(
        label="1200×1800",
        subdir=(SUBDIR_1200x1800,),
        width=1200, height=1800,
        format="WEBP",
        quality=WEBP_QUALITY_NORMAL,
        can_badge=False,
    ),
    # 1200×1200（バッジなし）
    OutputSpec(
        label="1200×1200",
        subdir=(SUBDIR_1200x1200,),
        width=1200, height=1200,
        format="WEBP",
        quality=WEBP_QUALITY_NORMAL,
        can_badge=False,
    ),
    # スライダー PC
    OutputSpec(
        label="スライダー PC 1922×824",
        subdir=(SUBDIR_SLIDER, SUBDIR_PC),
        width=1922, height=824,
        format="WEBP",
        quality=WEBP_QUALITY_NORMAL,
        can_badge=False,
    ),
    # スライダー スマホ
    OutputSpec(
        label="スライダー スマホ 641×854",
        subdir=(SUBDIR_SLIDER, SUBDIR_SP),
        width=641, height=854,
        format="WEBP",
        quality=WEBP_QUALITY_NORMAL,
        can_badge=False,
    ),
]


# =============================================================================
# CSV 読み込み / 商品ID 正規化
# =============================================================================

# Windows がコピー時に付ける「のコピー」「のコピー2」「のコピー (2)」末尾を除去する正規表現
_COPY_SUFFIX_RE = re.compile(r"\s*のコピー(?:\s*\(?\s*\d+\s*\)?)?\s*$")

# 末尾の「(1)」「(2)」等を除去する正規表現（Windows の重複ファイル名対策）
_PAREN_SUFFIX_RE = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def normalize_product_id(stem: str) -> str:
    """商品ID 照合 & 出力ファイル名に使う stem の正規化。

    繰り返し以下を末尾から除去し、変化が無くなるまで適用：
    - 前後の空白
    - 「のコピー」「のコピー2」「のコピー (2)」等（Windows のコピー作成時のサフィックス）
    - 「(1)」「(2)」等（Windows の重複ファイル名）

    例：「foo のコピー (2)」→「foo」、「marinarobe (3)」→「marinarobe」
    """
    s = stem.strip()
    while True:
        before = s
        s = _COPY_SUFFIX_RE.sub("", s)
        s = _PAREN_SUFFIX_RE.sub("", s)
        s = s.strip()
        if s == before:
            break
    return s


def load_size_csv(path: Path) -> Dict[str, ImageMapping]:
    """size_list.csv を読み込み、{正規化商品ID: ImageMapping} を返す。

    新形式（3列）: 商品ID, 新ファイル名, サイズコード
    旧形式（2列）: 商品ID, サイズコード も後方互換で読める。

    - ファイルが無い場合は空辞書を返す
    - 不正なサイズコードは警告のみ出してその値だけ無効化（リネームは生かす）
    - 商品IDは normalize_product_id() で正規化してから格納
    - BOM 付き UTF-8 にも対応
    """
    mapping: Dict[str, ImageMapping] = {}
    if not path.exists():
        print(f"⚠️  商品リストが見つかりません: {path}（リネーム・バッジは適用されません）", file=sys.stderr)
        return mapping

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return mapping

        id_keys   = ["商品ID", "product_id", "id"]
        name_keys = ["新ファイル名", "new_name", "rename"]
        size_keys = ["サイズコード", "size_code", "size"]

        id_key   = next((k for k in id_keys   if k in reader.fieldnames), None)
        name_key = next((k for k in name_keys if k in reader.fieldnames), None)  # optional
        size_key = next((k for k in size_keys if k in reader.fieldnames), None)  # optional

        if id_key is None:
            print(f"⚠️  CSV に '商品ID' 列がありません: {reader.fieldnames}", file=sys.stderr)
            return mapping

        for row in reader:
            raw_id = (row.get(id_key) or "").strip()
            if not raw_id:
                continue
            norm_id = normalize_product_id(raw_id)

            new_name: Optional[str] = None
            if name_key:
                v = (row.get(name_key) or "").strip()
                if v:
                    # Windows ファイル名に使えない文字を簡易置換
                    for ch in '<>:"/\\|?*':
                        v = v.replace(ch, "_")
                    new_name = v

            size_code: Optional[str] = None
            if size_key:
                v = (row.get(size_key) or "").strip().upper()
                if v:
                    if v in SIZE_CODES:
                        size_code = v
                    else:
                        print(f"⚠️  未知のサイズコードをスキップ: {raw_id} -> {v}", file=sys.stderr)

            mapping[norm_id] = ImageMapping(new_name=new_name, size_code=size_code)

    return mapping


# =============================================================================
# フォント検出
# =============================================================================

_FONT_CANDIDATES_SERIF = [
    # macOS
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/ヒラギノ明朝 ProN W3.otf",
    "/System/Library/Fonts/Supplemental/HiraginoSerif.ttc",
    "/Library/Fonts/Hiragino Mincho ProN.ttc",
    # Windows
    "C:/Windows/Fonts/yumin.ttf",
    "C:/Windows/Fonts/YuMincho.ttf",
    "C:/Windows/Fonts/msmincho.ttc",
    "C:/Windows/Fonts/HGRME.TTC",
    # Linux（Noto Serif JP がよく入る）
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
]

_FONT_CANDIDATES_FALLBACK = [
    # 最終フォールバック（英字のみのバッジ文字には十分）
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/georgia.ttf",
    "/System/Library/Fonts/Times.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]


def find_japanese_serif_font() -> Path:
    """日本語セリフ系フォントを探す。

    バッジに使う文字は英大文字のみだが、SPEC ではセリフ系・日本語フォント
    優先のため、まず日本語明朝系を試し、なければ英字セリフへフォールバック。
    全滅した場合は分かりやすいメッセージで例外を投げる。
    """
    for p in _FONT_CANDIDATES_SERIF + _FONT_CANDIDATES_FALLBACK:
        path = Path(p)
        if path.exists():
            return path

    raise FileNotFoundError(
        "セリフ系フォントが見つかりませんでした。\n"
        "下記のいずれかをインストールするか、フォントパスをコードに追記してください：\n"
        "  Windows : Yu Mincho（標準搭載）／MS 明朝\n"
        "  macOS   : ヒラギノ明朝 ProN（標準搭載）\n"
        "  Linux   : Noto Serif CJK JP （apt: fonts-noto-cjk）"
    )


# =============================================================================
# クロップ / リサイズ
# =============================================================================

def compute_crop_box(
    src_w: int, src_h: int,
    tgt_w: int, tgt_h: int,
    shift_x_ratio: float = 0.0,
    vert_top_ratio: Optional[float] = None,
    vert_bottom_ratio: Optional[float] = None,
) -> Tuple[int, int, int, int]:
    """ソース画像から、ターゲット縦横比に切り出すための (left, top, right, bottom) を返す。

    通常モード（vert_*_ratio が None）:
      - target がソースより横長 → 上下カット（垂直中央）
      - target がソースより縦長／正方形 → 左右カット（水平中央 + shift_x_ratio）
      - shift_x_ratio はソース幅に対する比率。+0.15 なら中心が右に15%動く。

    縦範囲指定モード（vert_top_ratio, vert_bottom_ratio が指定された場合）:
      - 縦は固定範囲 [src_h * top, src_h * bottom] に切り出す
      - 横はターゲット縦横比に合わせて水平中央クロップ
      - shift_x_ratio はこのモードでは無視
      - 修正3 (ウェア/ローブ × モデルの全身クロップ) で使用

    範囲はソース境界内にクランプ。
    """
    # ---- 縦範囲指定モード（修正3 用） ----
    if vert_top_ratio is not None and vert_bottom_ratio is not None:
        top    = int(round(src_h * vert_top_ratio))
        bottom = int(round(src_h * vert_bottom_ratio))
        # ソース境界内にクランプ
        top    = max(0, min(top, src_h - 1))
        bottom = max(top + 1, min(bottom, src_h))
        crop_h = bottom - top

        tgt_ar = tgt_w / tgt_h
        crop_w = int(round(crop_h * tgt_ar))
        # 横幅がソースを超える場合はソース幅にクランプ
        crop_w = min(crop_w, src_w)
        left   = max(0, (src_w - crop_w) // 2)
        if left + crop_w > src_w:
            left = src_w - crop_w
        return (left, top, left + crop_w, top + crop_h)

    # ---- 通常モード（既存挙動） ----
    src_ar = src_w / src_h
    tgt_ar = tgt_w / tgt_h

    if tgt_ar > src_ar:
        # 上下カット
        crop_w = src_w
        crop_h = int(round(src_w / tgt_ar))
        left = 0
        top  = (src_h - crop_h) // 2
    else:
        # 左右カット
        crop_h = src_h
        crop_w = int(round(src_h * tgt_ar))
        cx = src_w / 2 + src_w * shift_x_ratio
        left = int(round(cx - crop_w / 2))
        # クランプ
        left = max(0, min(left, src_w - crop_w))
        top  = 0

    right  = left + crop_w
    bottom = top + crop_h
    return (left, top, right, bottom)


def crop_and_resize(
    img: Image.Image,
    tgt_w: int, tgt_h: int,
    shift_x_ratio: float,
    vert_top_ratio: Optional[float] = None,
    vert_bottom_ratio: Optional[float] = None,
) -> Image.Image:
    """compute_crop_box でクロップ → Lanczos でリサイズ。

    vert_top_ratio / vert_bottom_ratio を渡すと縦範囲指定モード（修正3 用）。
    """
    box = compute_crop_box(img.width, img.height, tgt_w, tgt_h,
                            shift_x_ratio, vert_top_ratio, vert_bottom_ratio)
    cropped = img.crop(box)
    return cropped.resize((tgt_w, tgt_h), Image.Resampling.LANCZOS)


# =============================================================================
# バッジ描画
# =============================================================================

def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    """文字の幅・高さを返す（Pillow バージョン差異を吸収）"""
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    # 古い Pillow 用フォールバック
    return font.getsize(text)


def draw_size_badge(img: Image.Image, size_code: str, font_path: Path) -> Image.Image:
    """画像右下に丸いサイズバッジを描画して返す（元画像は破壊しない）。"""
    if img.mode != "RGBA":
        base = img.convert("RGBA")
    else:
        base = img.copy()

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 配置：右下から margin 引いた位置
    cx = base.width  - BADGE_MARGIN - BADGE_DIAMETER // 2
    cy = base.height - BADGE_MARGIN - BADGE_DIAMETER // 2
    r  = BADGE_DIAMETER // 2

    # 円（半透明）
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(*BADGE_BG_COLOR, BADGE_BG_ALPHA),
    )

    # フォント
    ratio = BADGE_FONT_RATIO_LONG if len(size_code) >= 3 else BADGE_FONT_RATIO
    font_size = int(BADGE_DIAMETER * ratio)
    font = ImageFont.truetype(str(font_path), font_size)

    # 文字サイズが横幅をはみ出さないよう自動縮小
    tw, th = _measure_text(draw, size_code, font)
    max_w = int(BADGE_DIAMETER * 0.78)
    while tw > max_w and font_size > 10:
        font_size -= 2
        font = ImageFont.truetype(str(font_path), font_size)
        tw, th = _measure_text(draw, size_code, font)

    # フローリッシュ（文字の上に短い水平線 + 中央に菱形）
    flourish_y = cy - th // 2 - 14
    line_half = int(BADGE_DIAMETER * 0.18)
    draw.line(
        [(cx - line_half, flourish_y), (cx + line_half, flourish_y)],
        fill=BADGE_FLOURISH_COLOR, width=2,
    )
    diamond = 4
    draw.polygon(
        [
            (cx, flourish_y - diamond),
            (cx + diamond, flourish_y),
            (cx, flourish_y + diamond),
            (cx - diamond, flourish_y),
        ],
        fill=BADGE_FLOURISH_COLOR,
    )

    # テキスト中央配置（baseline 補正のため少し上に）
    draw.text(
        (cx - tw / 2, cy - th / 2 - 2),
        size_code,
        font=font,
        fill=(*BADGE_TEXT_RGB, BADGE_TEXT_ALPHA),
    )

    composed = Image.alpha_composite(base, overlay)
    return composed


# =============================================================================
# 保存・コピー・ディレクトリ作成
# =============================================================================

def save_webp(img: Image.Image, path: Path, quality: int) -> None:
    """RGBA を保ったまま WebP 保存（透過ピクセルがある場合に備える）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if img.mode == "RGBA":
        img.save(path, "WEBP", quality=quality, method=6)
    else:
        img.convert("RGB").save(path, "WEBP", quality=quality, method=6)


def copy_original(src: Path, dst_path: Path) -> Path:
    """元画像を指定パスにそのままコピー（バイト単位）。

    出力ファイル名は呼び出し側が組み立てる（モデル placeholder 置換に対応するため）。
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    # shutil.copy2 だと OneDrive 上で稀にロックが入るので、バイト単位で書き出す
    dst_path.write_bytes(src.read_bytes())
    return dst_path


def ensure_output_dirs(base: Path, category_dir: str, series_name: str) -> Dict[str, Path]:
    """カテゴリ／シリーズ配下の出力フォルダ群を作成し、ラベル→Path の辞書を返す。"""
    series_root = base / category_dir / series_name
    dirs = {
        "high_res":  series_root / SUBDIR_HIGH_RES,
        "slider_pc": series_root / SUBDIR_SLIDER / SUBDIR_PC,
        "slider_sp": series_root / SUBDIR_SLIDER / SUBDIR_SP,
        "thumb":     series_root / SUBDIR_THUMB,
        "psd":       series_root / SUBDIR_PSD,
        "size_1200x1800": series_root / SUBDIR_1200x1800,
        "size_1200x1200": series_root / SUBDIR_1200x1200,
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def output_path_for_spec(series_root: Path, spec: OutputSpec, output_stem: str, src_ext: str) -> Path:
    """OutputSpec とベース＋出力ファイル名（拡張子なし）から最終的な出力先パスを組み立てる。

    - ORIGINAL 出力（高画質フォルダ）は元拡張子を保つ
    - それ以外は .webp に変換
    output_stem は呼び出し側で transform_stem() 済みのものを渡すこと。
    """
    folder = series_root.joinpath(*spec.subdir)
    if spec.format == "ORIGINAL":
        return folder / f"{output_stem}{src_ext}"
    return folder / f"{output_stem}.webp"


# =============================================================================
# 入力画像列挙
# =============================================================================

def collect_input_images(input_dir: Path) -> List[Path]:
    """input/ 配下の JPG/PNG を取得（隠しファイル除外、名前順）。"""
    if not input_dir.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
    files = [p for p in input_dir.iterdir()
             if p.is_file() and p.suffix in exts and not p.name.startswith(".")]
    return sorted(files, key=lambda p: p.name.lower())


# =============================================================================
# モデル画像 placeholder 置換
# =============================================================================

def has_model_marker(name: str) -> bool:
    """ファイル名（または stem）に -model_ が含まれるか。"""
    return MODEL_MARKER in name


def count_model_images(images: List[Path]) -> int:
    """モデル placeholder を含む画像の枚数を返す。"""
    return sum(1 for p in images if has_model_marker(p.name))


def transform_stem(stem: str, model_name: Optional[str]) -> str:
    """ファイル名 stem を出力用に変換する。

    -model_ を -model{モデル名}_ に置換する。
    model_name が None / 空、または stem に MODEL_MARKER が無い場合はそのまま返す。
    """
    if not model_name:
        return stem
    if MODEL_MARKER not in stem:
        return stem
    return stem.replace(MODEL_MARKER, f"_model{model_name}_")
