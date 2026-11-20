#!/usr/bin/env python3
"""用 Twemoji 卡通图替换文字卡片表情。

    python scripts/fetch-twemoji-stickers.py

Twemoji 采用 CC-BY 4.0，可公开使用，需保留署名（见 shenyan-assets/README.md）。
"""
from __future__ import annotations

import json
import pathlib
import urllib.request

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "shenyan-assets" / "stickers"
CACHE = ROOT / "shenyan-assets" / ".cache-emoji"
BASE = "https://raw.githubusercontent.com/jdecked/twemoji/main/assets/72x72/{}.png"

SIZE = 192

# id, 文案, 适用情绪, emoji 码点
SPEC = [
    ("st_01", "无语",   ["无语", "无奈", "白眼"],     "1f611"),
    ("st_02", "笑死",   ["好笑", "大笑", "调侃"],     "1f602"),
    ("st_03", "行吧",   ["让步", "答应", "勉强"],     "1f643"),
    ("st_04", "离谱",   ["吐槽", "不满", "惊讶"],     "1f928"),
    ("st_05", "睡了",   ["结束", "晚安", "困"],       "1f634"),
    ("st_06", "别急",   ["安抚", "关心", "耐心"],     "1f60c"),
    ("st_07", "？",     ["疑惑", "不解", "追问"],     "1f914"),
    ("st_08", "……",     ["沉默", "无语", "冷场"],     "1f636"),
    ("st_09", "知道了", ["应答", "收到"],             "1f44c"),
    ("st_10", "算了",   ["放弃", "不想争", "疲惫"],   "1fae0"),
    ("st_11", "挺累",   ["疲惫", "下班", "倾诉"],     "1f62e"),
    ("st_12", "在忙",   ["推迟", "没空", "工作"],     "1f4bc"),
    ("st_13", "想得美", ["拒绝", "玩笑", "打趣"],     "1f60f"),
    ("st_14", "随便",   ["无所谓", "交给你", "懒"],   "1f937"),
    ("st_15", "好",     ["答应", "干脆"],             "1f44d"),
    ("st_16", "不至于", ["劝阻", "夸张", "冷静"],     "1f610"),
    ("st_17", "慢点说", ["倾听", "跟不上"],           "1f642"),
    ("st_18", "没空",   ["拒绝", "忙", "干脆"],       "23f0"),
    ("st_19", "真的？", ["怀疑", "确认", "惊讶"],     "1f633"),
    ("st_20", "服了",   ["佩服", "无语", "被逗到"],   "1f64f"),
]


def fetch(code: str) -> pathlib.Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / f"{code}.png"
    if local.exists() and local.stat().st_size > 0:
        return local
    url = BASE.format(code)
    with urllib.request.urlopen(url, timeout=20) as r:
        local.write_bytes(r.read())
    return local


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for sid, caption, tags, code in SPEC:
        try:
            src = fetch(code)
            img = Image.open(src).convert("RGBA")
            img = img.resize((SIZE, SIZE), Image.LANCZOS)
            img.save(OUT / f"{sid}.png", optimize=True)
        except Exception as ex:
            print(f"{sid} 下载失败 {code}: {type(ex).__name__}，保留原图")
        manifest.append({"id": sid, "file": f"{sid}.png", "caption": caption, "tags": tags})
        print("写入", sid, caption)

    (ROOT / "shenyan-assets" / "stickers.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("清单已更新")


if __name__ == "__main__":
    main()
