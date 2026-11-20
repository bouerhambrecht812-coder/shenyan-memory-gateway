"""把 MCP 工具结果汇成「当前情境」，注入系统提示。

这里有一条硬边界：**情境不写进记忆库**。
天气、时间、头条都是时效性信息，写进正史之后角色会记着三个月前那场雨，
记忆库很快就会被噪声淹掉。情境只活在当轮的系统提示里，过了就没了。

这就是「两级时间线」的第一级。
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

from mcp_stdio import MCPUnavailable, MCPSessionPool

DEFAULT_TOOLS = ['clock.now', 'weather.now']
MAX_LINES = 6
MAX_CHARS_PER_LINE = 160

# 工具名最后一段常常是 now / headlines，用它会得到「now：…」这种看不懂的标签
LABELS = {'clock': '时间', 'time': '时间', 'weather': '天气', 'news': '头条', 'holiday': '节假日'}


def _label(qualified: str) -> str:
    parts = [p for p in qualified.split('.') if p]
    for part in reversed(parts[:-1] or parts):
        if part.lower() in LABELS:
            return LABELS[part.lower()]
    return parts[-1] if parts else qualified


def _split(value: str) -> list[str]:
    return [x.strip() for x in value.split(',') if x.strip()]


class WorldContext:
    """带 TTL 的情境缓存。任何一次采集失败都只是少一行，绝不阻塞回复。"""

    def __init__(self, pool: MCPSessionPool | None = None):
        self.pool = pool or MCPSessionPool()
        self.tools = _split(os.getenv('WORLD_CONTEXT_TOOLS', ','.join(DEFAULT_TOOLS)))
        self.ttl = max(30.0, float(os.getenv('WORLD_CACHE_TTL', '600')))
        self.lines: list[str] = []
        self.updated_at = 0.0
        self.last_error = ''
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self.pool.start()

    async def close(self) -> None:
        await self.pool.close()

    async def refresh(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.updated_at < self.ttl:
            return
        async with self._lock:
            if not force and time.monotonic() - self.updated_at < self.ttl:
                return
            lines: list[str] = []
            for qualified in self.tools[:MAX_LINES]:
                try:
                    text = await self.pool.call(qualified)
                except MCPUnavailable as ex:
                    self.last_error = str(ex)
                    continue
                except Exception as ex:
                    self.last_error = type(ex).__name__
                    continue
                flat = ' '.join(str(text).split())
                if flat:
                    lines.append(f'{_label(qualified)}：{flat[:MAX_CHARS_PER_LINE]}')
            if lines:
                self.lines = lines
                self.updated_at = time.monotonic()
                self.last_error = ''

    async def snapshot(self) -> str:
        try:
            await self.refresh()
        except Exception as ex:
            self.last_error = type(ex).__name__
        if not self.lines:
            return ''
        body = '\n'.join(f'- {line}' for line in self.lines)
        return (
            '【当前情境｜实时信息，不是你的记忆】\n'
            + body
            + '\n这些信息可以用来判断时间、天气和外面的世界，但不要当成你的亲身经历，'
              '也不要每句话都提。不知道就说不知道。'
        )

    def status(self) -> dict:
        return {
            'tools': self.tools,
            'ttl': self.ttl,
            'age_seconds': round(time.monotonic() - self.updated_at, 1) if self.updated_at else None,
            'lines': list(self.lines),
            'last_error': self.last_error,
            'servers': self.pool.status(),
        }

    async def ensure_alive(self) -> None:
        """定时体检：子进程死了就拉起来，活着就什么都不做。"""
        for session in self.pool.sessions:
            try:
                if not session.ready:
                    await session.start()
            except Exception as ex:
                print(f'MCP {session.name} 重启失败：{type(ex).__name__}')


async def self_check() -> None:
    """命令行自检：python world.py"""
    ctx = WorldContext()
    await ctx.start()
    await ctx.refresh(force=True)
    print(await ctx.snapshot() or '（没有拿到情境）')
    print(ctx.status(), file=sys.stderr)
    await ctx.close()


if __name__ == '__main__':
    asyncio.run(self_check())
