"""HLI 商品画像後処理ツール - Streamlit Web UI

既存の process.py / utils.py の関数を再利用したブラウザ版ラッパー。
Dropbox には書き込まず、一時フォルダで処理して ZIP でダウンロードさせる。

起動:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

import io
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

import streamlit as st

import utils as U
from process import process_one_image, append_error_log


# =============================================================================
# ページ設定
# =============================================================================

st.set_page_config(
    page_title="HLI 商品画像後処理ツール",
    page_icon="📷",
    layout="centered",
)

st.title("📷 HLI 商品画像後処理ツール")
st.caption(
    "撮影画像をカテゴリ別ルールでクロップ・リサイズ・WebP変換し、ZIP でダウンロードします。"
    "（Dropbox には書き込みません）"
)


# =============================================================================
# 入力フォーム
# =============================================================================

uploaded_images = st.file_uploader(
    "画像アップロード（複数可・JPG / PNG）",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)
if uploaded_images:
    st.caption(f"📁 {len(uploaded_images)} 個のファイルを選択中")

uploaded_csv = st.file_uploader(
    "商品リスト CSV（任意 / 列: 商品ID, 新ファイル名, サイズコード）",
    type=["csv"],
    accept_multiple_files=False,
)

# カテゴリ選択（バッジ対象には印を付ける）
category_options = [
    f"{name} 🏷️バッジあり" if name in U.BADGE_CATEGORIES else name
    for name in U.CATEGORIES
]
category_label = st.selectbox("カテゴリ", category_options, index=0)
selected_category = U.CATEGORIES[category_options.index(category_label)]

series_name = st.text_input(
    "シリーズ名",
    placeholder="例: 2025春コレクション / mrblkt_test",
)

model_name_input = st.text_input(
    "モデル名（任意）",
    placeholder="例: 花子",
    help="画像名に -model_ が含まれる場合に置換される名前",
)

# --- スライダー用バナー設定 ---
with st.expander("🎨 スライダー用バナー設定（任意）", expanded=False):
    st.caption("スライダー PC / スマホ画像にキャッチコピーを重ねます。両方空ならバナーなし。")
    jp_copy_input = st.text_input(
        "日本語キャッチコピー",
        placeholder="例: 毎日の眠りを、やさしく満たす",
    )
    en_copy_input = st.text_input(
        "英語キャッチコピー (Allura フォント)",
        placeholder="例: Dress the Bed",
    )
    banner_layout_input = st.selectbox(
        "レイアウト",
        U.BANNER_LAYOUTS,
        index=U.BANNER_LAYOUTS.index(U.BANNER_LAYOUT_CENTER),
        format_func=lambda v: f"{v} ({U.BANNER_LAYOUT_LABELS_JP[v]})",
    )

st.divider()

go = st.button(
    "✨ 処理開始",
    type="primary",
    disabled=not (uploaded_images and series_name.strip()),
    use_container_width=True,
)


# =============================================================================
# 処理本体
# =============================================================================

def _sanitize_for_path(s: str) -> str:
    s = s.strip()
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s


if go:
    # 前回結果はクリア
    st.session_state.pop("results", None)

    safe_series = _sanitize_for_path(series_name)
    model_name = model_name_input.strip() or None

    progress_bar = st.progress(0.0)
    status_box = st.empty()

    try:
        with tempfile.TemporaryDirectory(prefix="hli_") as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            output_base = tmp_path / "outputs"
            input_dir.mkdir()
            output_base.mkdir()

            # 1. アップロード画像を一時フォルダに保存
            saved_paths = []
            for uf in uploaded_images:
                dst = input_dir / uf.name
                dst.write_bytes(uf.getbuffer())
                saved_paths.append(dst)

            # 2. CSV があれば読み込み
            size_list = {}
            if uploaded_csv is not None:
                csv_path = tmp_path / "size_list.csv"
                csv_path.write_bytes(uploaded_csv.getbuffer())
                size_list = U.load_size_csv(csv_path)

            # 3. 出力フォルダ準備
            series_root = output_base / selected_category / safe_series
            U.ensure_output_dirs(output_base, selected_category, safe_series)

            # 4. フォント検出（バッジが実際に必要な場合のみ必須）
            font_path = None
            badge_needed = (
                selected_category in U.BADGE_CATEGORIES
                and any(m.size_code for m in size_list.values())
            )
            try:
                font_path = U.find_japanese_serif_font()
            except FileNotFoundError as exc:
                if badge_needed:
                    st.error(f"バッジ用フォントが見つかりません。\n\n{exc}")
                    st.stop()

            # 5. 画像ごとに既存の process_one_image を呼ぶ
            total_success = {spec.label: 0 for spec in U.OUTPUT_SPECS}
            total_badge = 0
            errors: list[tuple[str, str]] = []
            error_log = tmp_path / "error_log.txt"

            t0 = time.time()
            N = len(saved_paths)
            for i, src in enumerate(saved_paths):
                status_box.info(f"処理中: **{src.name}** ({i + 1}/{N})")
                try:
                    counts = process_one_image(
                        src,
                        selected_category,
                        series_root,
                        size_list,
                        font_path,
                        model_name,
                        jp_copy=jp_copy_input,
                        en_copy=en_copy_input,
                        banner_layout=banner_layout_input,
                    )
                    for label, n in counts.items():
                        if label == "バッジ付与":
                            total_badge += n
                        else:
                            total_success[label] += n
                except Exception as exc:
                    errors.append((src.name, f"{type(exc).__name__}: {exc}"))
                    append_error_log(error_log, src.stem, exc)
                progress_bar.progress((i + 1) / N)

            elapsed = time.time() - t0
            status_box.empty()

            # 6. 結果を ZIP 化（temp dir 破棄前にメモリへ）
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for fp in sorted(output_base.rglob("*")):
                    if fp.is_file():
                        zf.write(fp, fp.relative_to(output_base))
            zip_name = f"{selected_category}_{safe_series}.zip"

            # 7. サムネイルプレビューもメモリへ
            preview_items = []
            thumb_dir = series_root / U.SUBDIR_THUMB
            for tp in sorted(thumb_dir.glob("*.webp"))[:6]:
                preview_items.append({
                    "name": tp.stem,
                    "bytes": tp.read_bytes(),
                })

            # 8. セッションに結果を保存（再 run でも表示し続けるため）
            st.session_state["results"] = {
                "zip_bytes":     zip_buffer.getvalue(),
                "zip_name":      zip_name,
                "total":         N,
                "success_count": N - len(errors),
                "badge_count":   total_badge,
                "error_count":   len(errors),
                "errors":        errors,
                "folder_counts": dict(total_success),
                "elapsed":       elapsed,
                "preview_items": preview_items,
                "category":      selected_category,
                "series":        safe_series,
            }
        # ← temp dir はここで自動削除（中身はすべて session_state にコピー済み）

    except Exception:
        st.error("処理中に予期しないエラーが発生しました。")
        st.code(traceback.format_exc())
        st.stop()


# =============================================================================
# 結果表示（再 run 後も表示するため session_state から取り出す）
# =============================================================================

r = st.session_state.get("results")
if r:
    st.divider()

    if r["error_count"] == 0:
        st.success(f"✅ 完了！  ({r['elapsed']:.1f}秒 / {r['total']} 枚)")
    else:
        st.warning(f"⚠️ 完了（{r['error_count']} 件エラー / {r['elapsed']:.1f}秒）")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総処理", r["total"])
    c2.metric("成功",   r["success_count"])
    c3.metric("バッジ", r["badge_count"])
    c4.metric("エラー", r["error_count"])

    st.download_button(
        "📦 結果をダウンロード (ZIP)",
        data=r["zip_bytes"],
        file_name=r["zip_name"],
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

    if r["errors"]:
        with st.expander(f"⚠️ エラー詳細（{r['error_count']} 件）", expanded=True):
            for name, msg in r["errors"]:
                st.error(f"**{name}**: {msg}")

    with st.expander("📂 フォルダ別 書き出し件数"):
        for label, n in r["folder_counts"].items():
            st.write(f"- **{label}**: {n}")

    if r["preview_items"]:
        st.subheader("🖼️ サムネイルプレビュー")
        cols = st.columns(min(len(r["preview_items"]), 3))
        for i, item in enumerate(r["preview_items"]):
            with cols[i % len(cols)]:
                st.image(item["bytes"], caption=item["name"], use_container_width=True)
