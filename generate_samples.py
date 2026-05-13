"""動作確認用のサンプル画像（3:2 横）を input/ に生成する。

使い方:
    python generate_samples.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INPUT_DIR = Path("input")

# 3:2 横、十分大きい解像度
SAMPLE_W, SAMPLE_H = 3000, 2000

SAMPLES = [
    {"id": "ITEM001", "bg": (215, 200, 178), "fg": (90, 70, 50),  "label": "Linen Sample"},
    {"id": "ITEM002", "bg": (180, 195, 215), "fg": (40, 60, 110), "label": "Wear Sample"},
    {"id": "ITEM003", "bg": (200, 220, 195), "fg": (40, 100, 70), "label": "Towel Sample"},
    # モデル placeholder のデモ用（-model_ を含むので process.py が
    # 「モデル名を入力してください」と聞き、出力ファイル名で置換される）
    {"id": "flinenblkt01-model_1", "bg": (230, 220, 200), "fg": (80, 60, 40), "label": "Model Shot"},
]


def _pick_font(size: int) -> ImageFont.ImageFont:
    """システムにあるサンセリフを順に試す。"""
    candidates = [
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_one(sample: dict, out_dir: Path) -> Path:
    img = Image.new("RGB", (SAMPLE_W, SAMPLE_H), sample["bg"])
    draw = ImageDraw.Draw(img)

    # 中央十字（クロップ位置の確認用）
    draw.line([(SAMPLE_W // 2, 0), (SAMPLE_W // 2, SAMPLE_H)], fill=sample["fg"], width=4)
    draw.line([(0, SAMPLE_H // 2), (SAMPLE_W, SAMPLE_H // 2)], fill=sample["fg"], width=4)

    # 左1/3 と 右1/3 の縦線（「右に15%シフト」を視認するため）
    for x_ratio, dash in ((1 / 3, 6), (2 / 3, 6)):
        x = int(SAMPLE_W * x_ratio)
        for y in range(0, SAMPLE_H, dash * 4):
            draw.line([(x, y), (x, y + dash * 2)], fill=sample["fg"], width=2)

    # 左端／右端マーカー（クロップで消える側を確認）
    draw.rectangle([0, 0, 160, SAMPLE_H], outline=sample["fg"], width=8)
    draw.rectangle([SAMPLE_W - 160, 0, SAMPLE_W, SAMPLE_H], outline=sample["fg"], width=8)
    font_small = _pick_font(48)
    draw.text((20, 20),                     "LEFT",  fill=sample["fg"], font=font_small)
    draw.text((SAMPLE_W - 140, 20),         "RIGHT", fill=sample["fg"], font=font_small)

    # 中央にIDとラベル
    font_big   = _pick_font(140)
    font_mid   = _pick_font(72)
    text_id    = sample["id"]
    text_label = sample["label"]

    bbox = draw.textbbox((0, 0), text_id, font=font_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SAMPLE_W - tw) // 2, SAMPLE_H // 2 - th - 20),
              text_id, fill=sample["fg"], font=font_big)

    bbox = draw.textbbox((0, 0), text_label, font=font_mid)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SAMPLE_W - tw) // 2, SAMPLE_H // 2 + 30),
              text_label, fill=sample["fg"], font=font_mid)

    out_path = out_dir / f"{sample['id']}.jpg"
    img.save(out_path, "JPEG", quality=92)
    return out_path


def main() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 {INPUT_DIR}/ にサンプル画像を生成します...")
    for s in SAMPLES:
        p = make_one(s, INPUT_DIR)
        print(f"  ✓ {p}  ({SAMPLE_W}×{SAMPLE_H})")
    print("完了。`python process.py` で動作確認できます。")


if __name__ == "__main__":
    main()
