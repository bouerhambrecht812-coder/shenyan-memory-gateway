#!/usr/bin/env python3
"""生成分享卡片和 favicon。

    python web-demo/scripts/make-brand.py

输出：
    web-demo/static/og.png       1200×630，微信/飞书/推特抓取用
    web-demo/static/favicon.png  256×256，浏览器标签页
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static"

BG = (20, 19, 15, 255)
CARD = (36, 31, 24, 255)
FG = (236, 230, 216, 255)
GOLD = (200, 164, 74, 255)
MUTED = (148, 140, 122, 255)

FONT_BOLD = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
FONT_REG = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def font(candidates, size):
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("找不到中文字体")


def make_og() -> Image.Image:
    W, H = 1200, 630
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 左侧一条金色竖线，有点版式感
    d.rectangle([70, 150, 74, 380], fill=GOLD)

    d.text((110, 148), "沈砚记忆网关", font=font(FONT_BOLD, 92), fill=FG)
    d.text((114, 268), "SHENYAN MEMORY GATEWAY", font=font(FONT_REG, 26), fill=MUTED)

    d.text((114, 340), "给 AI 角色用的长期记忆层", font=font(FONT_BOLD, 44), fill=FG)
    d.text((114, 412), "记忆自持 · 写入要人点头 · 换一个 Base URL 就能接入",
           font=font(FONT_REG, 28), fill=MUTED)

    # 右下角小数据
    d.text((114, 520), "跨会话记忆  /  人工审核闸门  /  MCP 世界事件  /  表情与语音",
           font=font(FONT_REG, 24), fill=(120, 113, 98, 255))

    # 右上角圆点，呼应页面的状态灯
    d.ellipse([1080, 96, 1100, 116], fill=(122, 160, 111, 255))
    d.text((1050, 128), "live", font=font(FONT_REG, 22), fill=MUTED)
    return img


def make_favicon() -> Image.Image:
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, S - 8, S - 8], radius=56, fill=CARD, outline=(90, 80, 62, 255), width=3)
    f = font(FONT_BOLD, 150)
    box = d.textbbox((0, 0), "砚", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((S - w) / 2 - box[0], (S - h) / 2 - box[1]), "砚", font=f, fill=GOLD)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_og().convert("RGB").save(OUT / "og.png", optimize=True)
    make_favicon().save(OUT / "favicon.png", optimize=True)
    print("写出", OUT / "og.png")
    print("写出", OUT / "favicon.png")


if __name__ == "__main__":
    main()
