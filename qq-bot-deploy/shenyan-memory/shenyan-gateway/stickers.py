"""表情包素材库。

模型不会画图，它只会在一个封闭集合里**选**——这样不会幻觉出图片地址。
素材多了以后可以换成向量检索，`menu()` 留了 limit 参数。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def assets_dir() -> Path:
    return Path(os.getenv('ASSETS_DIR', '/app/assets'))


class StickerBook:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or assets_dir()
        self.items: list[dict] = []
        self.load()

    def load(self) -> None:
        manifest = self.dir / 'stickers.json'
        if not manifest.exists():
            self.items = []
            return
        try:
            raw = json.loads(manifest.read_text(encoding='utf-8'))
        except Exception:
            self.items = []
            return
        self.items = [
            m for m in raw
            if isinstance(m, dict) and m.get('id') and m.get('file')
        ]

    def get(self, sid: str) -> dict | None:
        for item in self.items:
            if item['id'] == sid:
                return item
        return None

    def exists(self, sid: str) -> bool:
        return self.get(sid) is not None

    def url(self, sid: str) -> str:
        item = self.get(sid)
        return f"/stickers/{item['file']}" if item else ''

    def menu(self, limit: int = 24) -> str:
        """给模型看的候选清单：只有 id + 意思 + 适用场景。"""
        if not self.items:
            return ''
        lines = []
        for item in self.items[:limit]:
            tags = '/'.join(item.get('tags') or [])
            lines.append(f"- {item['id']} {item.get('caption', '')}（{tags}）")
        return '\n'.join(lines)

    def status(self) -> dict:
        return {'dir': str(self.dir), 'count': len(self.items)}


def pick_candidates(book: StickerBook, hint: str = '', limit: int = 12) -> list[dict]:
    """按关键词粗筛候选，没有命中就全给（素材少的时候够用）。"""
    hint = (hint or '').strip()
    if not hint or len(book.items) <= limit:
        return book.items[:limit]
    scored = []
    for item in book.items:
        hay = (item.get('caption', '') + ' ' + ' '.join(item.get('tags') or []))
        score = sum(1 for ch in set(hint) if ch in hay)
        scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    top = [item for score, item in scored if score > 0][:limit]
    return top or book.items[:limit]
