#!/usr/bin/env python3
"""用 Microsoft Fluent Emoji（MIT）替换表情素材。

    python scripts/fetch-fluent-stickers.py

仓库：https://github.com/microsoft/fluentui-emoji
许可：MIT

路径规律：assets/<CLDR 名称>/3D/<name>_3d.png
CLDR 名称的空格要转义，文件名里连字符和空格的处理不一定，所以每个都试几个候选。
拉不到的会保留原图，并打印出来。
"""
from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "shenyan-assets" / "stickers"
CACHE = ROOT / "shenyan-assets" / ".cache-fluent"
BASE = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets"

SIZE = 256

# id, 文案, 情绪标签, CLDR 名称
SPEC = [
    ("st_01", "无语",   ["无语", "无奈", "白眼"],   "Expressionless face"),
    ("st_02", "笑死",   ["好笑", "大笑", "调侃"],   "Face with tears of joy"),
    ("st_03", "行吧",   ["让步", "答应", "勉强"],   "Upside-down face"),
    ("st_04", "离谱",   ["吐槽", "不满", "惊讶"],   "Face with raised eyebrow"),
    ("st_05", "睡了",   ["结束", "晚安", "困"],     "Sleeping face"),
    ("st_06", "别急",   ["安抚", "关心", "耐心"],   "Relieved face"),
    ("st_07", "？",     ["疑惑", "不解", "追问"],   "Thinking face"),
    ("st_08", "……",     ["沉默", "无语", "冷场"],   "Face without mouth"),
    ("st_09", "知道了", ["应答", "收到"],           "Ok hand"),
    ("st_10", "算了",   ["放弃", "不想争", "疲惫"], "Melting face"),
    ("st_11", "挺累",   ["疲惫", "下班", "倾诉"],   "Face with open mouth"),
    ("st_12", "在忙",   ["推迟", "没空", "工作"],   "Briefcase"),
    ("st_13", "想得美", ["拒绝", "玩笑", "打趣"],   "Smirking face"),
    ("st_14", "随便",   ["无所谓", "交给你", "懒"], "Person shrugging"),
    ("st_15", "好",     ["答应", "干脆"],           "Thumbs up"),
    ("st_16", "不至于", ["劝阻", "夸张", "冷静"],   "Neutral face"),
    ("st_17", "慢点说", ["倾听", "跟不上"],         "Slightly smiling face"),
    ("st_18", "没空",   ["拒绝", "忙", "干脆"],     "Alarm clock"),
    ("st_19", "真的？", ["怀疑", "确认", "惊讶"],   "Flushed face"),
    ("st_20", "服了",   ["佩服", "无语", "被逗到"], "Folded hands"),
]


def candidates(name: str) -> list[str]:
    folder = name[0].upper() + name[1:]
    stem = name.lower()
    variants = {
        stem.replace(" ", "_"),
        stem.replace(" ", "_").replace("-", "_"),
        stem.replace(" ", "_").replace("-", ""),
        stem.replace(" ", "-"),
        stem.replace(" ", ""),
    }
    urls = []
    for v in sorted(variants):
        q = urllib.parse.quote(v)
        folder_q = urllib.parse.quote(folder)
        # 有肤色的手势（👍🤷🙏👌）单独放在 Default/<风格>/ 下，文件名带 _default
        urls.append(f"{BASE}/{folder_q}/Default/3D/{q}_3d_default.png")
        urls.append(f"{BASE}/{folder_q}/3D/{q}_3d.png")
    return urls


def fetch(name: str, sid: str) -> pathlib.Path | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for url in candidates(name):
        local = CACHE / url.rsplit("/", 1)[-1].replace("%20", "_")
        if local.exists() and local.stat().st_size > 0:
            return local
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "shenyan/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) > 2000 and data[:4] == b"\x89PNG":
                local.write_bytes(data)
                return local
        except Exception:
            continue
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, failed = [], []
    for sid, caption, tags, name in SPEC:
        path = fetch(name, sid)
        if path:
            img = Image.open(path).convert("RGBA")
            img = img.resize((SIZE, SIZE), Image.LANCZOS)
            img.save(OUT / f"{sid}.png", optimize=True)
            print("ok  ", sid, caption)
        else:
            failed.append((sid, caption, name))
            print("miss", sid, caption, name)
        manifest.append({"id": sid, "file": f"{sid}.png", "caption": caption, "tags": tags})

    (ROOT / "shenyan-assets" / "stickers.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failed:
        print("\n下载失败（保留了原图）：")
        for sid, caption, name in failed:
            print(f"  {sid} {caption}  ← {name}")
    else:
        print("\n全部下载成功")


if __name__ == "__main__":
    main()
