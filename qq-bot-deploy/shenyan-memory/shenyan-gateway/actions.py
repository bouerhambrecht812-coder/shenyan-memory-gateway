"""输出协议：一坨文本 → 一串动作。

为什么不让模型直接返回 JSON：聊天场景里每条回复都套 JSON 模式，失败面和延迟都会翻倍。
这里用「正文 + 行内标记」的写法，模型只会写字，标记由网关解析成动作，
解析失败也只是少发一个表情，不会让整条回复丢掉。

标记：
    [[st:st_01]]   发一个表情（只能从素材库里选）
    [[voice]]      这条回复用语音发（网页端先用浏览器 TTS 顶上）
"""
from __future__ import annotations

import re

STICKER_RE = re.compile(r'\[\[\s*(?:st(?:icker)?\s*[:：]\s*)?([A-Za-z0-9_\-]{1,32})\s*\]\]', re.I)
VOICE_RE = re.compile(r'\[\[\s*voice\s*\]\]')
MAX_STICKERS = 1


def normalize_id(raw: str) -> str:
    """模型会写成 st_07 / st07 / st-7 / ST_7，统一成素材库里的 id。"""
    s = (raw or '').strip().lower().replace('-', '_').replace(' ', '')
    m = re.fullmatch(r'st_?(\d{1,3})', s)
    if m:
        return f'st_{int(m.group(1)):02d}'
    return s


def parse_reply(text: str, book) -> tuple[str, list[str], bool]:
    """返回 (干净文本, 表情 id 列表, 是否要发语音)。"""
    text = text or ''
    voice = bool(VOICE_RE.search(text))
    text = VOICE_RE.sub('', text)

    ids: list[str] = []
    for match in STICKER_RE.finditer(text):
        sid = normalize_id(match.group(1))
        if book.exists(sid) and sid not in ids and len(ids) < MAX_STICKERS:
            ids.append(sid)
    text = STICKER_RE.sub('', text)

    # 标记被拿掉之后常留下空行和行尾空格
    lines = [line.strip() for line in text.split('\n')]
    clean = '\n'.join(line for line in lines if line).strip()
    return clean, ids, voice


def build(clean_text: str, stickers: list[str], voice: bool, book) -> list[dict]:
    actions: list[dict] = []
    if clean_text:
        actions.append({'type': 'voice' if voice else 'text', 'text': clean_text})
    for sid in stickers[:MAX_STICKERS]:
        item = book.get(sid) or {}
        actions.append({
            'type': 'sticker',
            'id': sid,
            'url': book.url(sid),
            'caption': item.get('caption', ''),
        })
    return actions


def prompt_rules(book) -> str:
    menu = book.menu() if book else ''
    if not menu:
        return ''
    return (
        '【可选动作】\n'
        '想发一个表情时，在回复最后单独占一行，写 [[st:ID]]，例如 [[st:st_03]]。\n'
        'ID 只能从下面选，一次最多一个；标记那一行前后不要再写别的字，也不要解释这是什么：\n'
        + menu +
        '\n不要每句都发，情绪到了才发。\n'
        '如果这条回复更适合用语音说，在最后单独一行写 [[voice]]。语音比文字更亲近，别滥用。\n'
    )
