"""最小 MCP 客户端（stdio 传输，JSON-RPC 2.0，零第三方依赖）

只实现网关用得到的那几个方法：initialize / tools/list / tools/call。
不引官方 SDK 有两个理由：网关跑在 AstrBot 基础镜像里，那个镜像锁了 pydantic；
以及协议本身很小，自己实现反而更好测、更好排查。

MCP 的 stdio 传输规定：一条消息一行 JSON，stdout 只走协议，日志走 stderr。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import deque
from pathlib import Path

PROTOCOL_VERSION = '2025-06-18'


class MCPUnavailable(RuntimeError):
    pass


class StdioMCPSession:
    """一个 MCP server 子进程 = 一条长连接。挂了就重启，重启失败就降级。"""

    def __init__(self, name: str, command: list[str], cwd: str | None = None,
                 env: dict | None = None, timeout: float = 20.0):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.env = env
        self.timeout = timeout

        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._ready = False
        self._last_error = ''
        self._stderr_tail: deque[str] = deque(maxlen=20)

    # ── 生命周期 ────────────────────────────────────────────
    async def start(self) -> None:
        if self._proc and self._proc.returncode is None:
            return
        await self.close()
        env = dict(os.environ)
        if self.env:
            env.update(self.env)
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=env,
            limit=1024 * 1024,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._drain_stderr())

        info = await self._request('initialize', {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {},
            'clientInfo': {'name': 'shenyan-memory', 'version': '1.0.0'},
        })
        self._ready = bool(info)

        # 按协议补一条 initialized 通知（无 id，不期待回复）
        await self._notify('notifications/initialized', {})

    async def close(self) -> None:
        self._ready = False
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        proc, self._proc = self._proc, None
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MCPUnavailable(f'{self.name} 连接已关闭'))
        self._pending.clear()

    # ── 收发 ────────────────────────────────────────────────
    async def _read_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode('utf-8', 'replace').strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                msg_id = msg.get('id')
                if msg_id is None:
                    continue  # server 主动发的通知，当前用不到
                fut = self._pending.pop(msg_id, None)
                if fut and not fut.done():
                    fut.set_result(msg)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            self._last_error = type(ex).__name__
        finally:
            self._ready = False
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(MCPUnavailable(f'{self.name} 连接中断'))

    async def _drain_stderr(self) -> None:
        proc = self._proc
        if not proc or not proc.stderr:
            return
        try:
            while True:
                raw = await proc.stderr.readline()
                if not raw:
                    break
                self._stderr_tail.append(raw.decode('utf-8', 'replace').rstrip())
        except Exception:
            pass

    async def _send(self, payload: dict) -> None:
        proc = self._proc
        if not proc or not proc.stdin or proc.returncode is not None:
            raise MCPUnavailable(f'{self.name} 未启动')
        async with self._write_lock:
            proc.stdin.write((json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8'))
            await proc.stdin.drain()

    async def _notify(self, method: str, params: dict) -> None:
        try:
            await self._send({'jsonrpc': '2.0', 'method': method, 'params': params})
        except Exception:
            pass

    async def _request(self, method: str, params: dict, timeout: float | None = None) -> dict:
        self._next_id += 1
        msg_id = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await self._send({'jsonrpc': '2.0', 'id': msg_id, 'method': method, 'params': params})
            msg = await asyncio.wait_for(fut, timeout=timeout or self.timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise MCPUnavailable(f'{self.name} 超时（{method}）')
        finally:
            self._pending.pop(msg_id, None)

        if 'error' in msg:
            raise MCPUnavailable(f"{self.name}: {msg['error'].get('message')}")
        return msg.get('result') or {}

    # ── 对外 ────────────────────────────────────────────────
    async def list_tools(self) -> list[dict]:
        result = await self._request('tools/list', {})
        tools = result.get('tools') or []
        return [t for t in tools if isinstance(t, dict) and t.get('name')]

    async def call_tool(self, name: str, arguments: dict | None = None) -> str:
        """返回工具结果里的文本，多段用换行拼接。"""
        result = await self._request('tools/call', {'name': name, 'arguments': arguments or {}}, timeout=25.0)
        parts = []
        for block in result.get('content') or []:
            if isinstance(block, dict) and block.get('type') == 'text':
                parts.append(str(block.get('text') or ''))
        text = '\n'.join(p for p in parts if p).strip()
        if result.get('isError'):
            raise MCPUnavailable(f'{self.name}/{name}: {text or "工具返回错误"}')
        return text

    @property
    def ready(self) -> bool:
        return self._ready and self._proc is not None and self._proc.returncode is None

    def status(self) -> dict:
        return {
            'name': self.name,
            'ready': self.ready,
            'pid': self._proc.pid if self._proc else None,
            'stderr': list(self._stderr_tail)[-3:],
            'last_error': self._last_error,
        }


def default_command() -> list[str]:
    """默认连本仓库自带的世界事件服务端。"""
    server = Path(__file__).resolve().parent / 'world_server.py'
    return [sys.executable, str(server)]


def load_server_config() -> list[dict]:
    """MCP_SERVERS 可以用 JSON 覆盖/追加： [{"name":"world","command":["python","..."],"env":{}}]"""
    raw = os.getenv('MCP_SERVERS', '').strip()
    if raw:
        try:
            servers = json.loads(raw)
            if isinstance(servers, list) and servers:
                return [s for s in servers if isinstance(s, dict) and s.get('command')]
        except Exception as ex:
            print(f'MCP_SERVERS 解析失败：{type(ex).__name__}', file=sys.stderr)
    return [{'name': 'shenyan-world', 'command': default_command()}]


class MCPSessionPool:
    """所有 MCP server 的集合。任何一台挂了都不能影响主链路。"""

    def __init__(self, servers: list[dict] | None = None):
        self.sessions: list[StdioMCPSession] = []
        for cfg in (servers if servers is not None else load_server_config()):
            command = cfg.get('command')
            if isinstance(command, str):
                command = [command]
            if not isinstance(command, list) or not command:
                continue
            self.sessions.append(StdioMCPSession(
                name=str(cfg.get('name') or f'mcp{len(self.sessions) + 1}'),
                command=[str(c) for c in command],
                cwd=cfg.get('cwd'),
                env=cfg.get('env'),
            ))

    async def start(self) -> None:
        for session in self.sessions:
            try:
                await session.start()
            except Exception as ex:
                print(f'MCP {session.name} 启动失败：{type(ex).__name__}', file=sys.stderr)

    async def close(self) -> None:
        for session in self.sessions:
            try:
                await session.close()
            except Exception:
                pass

    def find(self, name: str) -> StdioMCPSession | None:
        for session in self.sessions:
            if session.name == name:
                return session
        return None

    async def call(self, qualified: str, arguments: dict | None = None) -> str:
        """qualified 形式：server.tool 或 tool（在所有 server 里找同名的唯一一个）。

        工具名本身可能带点（clock.now），所以不能从右边切，只能按 server 名前缀匹配。
        """
        for session in sorted(self.sessions, key=lambda s: len(s.name), reverse=True):
            prefix = session.name + '.'
            if qualified.startswith(prefix):
                tool_name = qualified[len(prefix):]
                if not session.ready:
                    await session.start()
                return await session.call_tool(tool_name, arguments)

        for session in self.sessions:
            if not session.ready:
                continue
            tools = {t.get('name') for t in await session.list_tools()}
            if qualified in tools:
                return await session.call_tool(qualified, arguments)
        raise MCPUnavailable(f'没有找到工具 {qualified}')

    def status(self) -> list[dict]:
        return [s.status() for s in self.sessions]
