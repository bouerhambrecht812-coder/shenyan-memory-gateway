#!/usr/bin/env python3
"""生成表情包占位素材（正式用图直接替换同名文件即可）。

    python scripts/make-stickers.py

输出：../shenyan-assets/stickers/*.png
风格：深色圆角卡片 + 大字，256×256，透明底。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "shenyan-assets" / "stickers"

SIZE = 256
BG = (36, 31, 24, 255)
FG = (236, 230, 216, 255)
LINE = (90, 80, 62, 255)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]

STICKERS = [
    ("st_01", "无语", ["无语", "无奈", "白眼"]),
    ("st_02", "笑死", ["好笑", "大笑", "调侃"]),
    ("st_03", "行吧", ["让步", "答应", "勉强"]),
    ("st_04", "离谱", ["吐槽", "不满", "惊讶"]),
    ("st_05", "睡了", ["结束", "晚安", "困"]),
    ("st_06", "别急", ["安抚", "关心", "耐心"]),
    ("st_07", "？", ["疑惑", "不解", "追问"]),
    ("st_08", "……", ["沉默", "无语", "冷场"]),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("找不到中文字体，请改 FONT_CANDIDATES")


def draw(text: str) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, SIZE - 6, SIZE - 6], radius=48, fill=BG, outline=LINE, width=2)

    size = 104 if len(text) <= 2 else 72
    font = load_font(size)
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1]), text, font=font, fill=FG)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for sid, text, tags in STICKERS:
        name = f"{sid}.png"
        draw(text).save(OUT / name, optimize=True)
        manifest.append({
            "id": sid,
            "file": name,
            "caption": text,
            "tags": tags,
        })
        print("写出", name)
    (ROOT / "shenyan-assets" / "stickers.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("清单：shenyan-assets/stickers.json")


if __name__ == "__main__":
    main()
