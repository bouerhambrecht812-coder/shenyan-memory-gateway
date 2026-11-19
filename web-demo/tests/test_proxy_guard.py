"""代理层的两条底线：指令白名单、限流计数。

不装 fastapi / httpx，用假模块导入 server.py 直接验。
    python web-demo/tests/test_proxy_guard.py
"""
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / 'web-demo' / 'proxy' / 'server.py'


def load():
    httpx = types.ModuleType('httpx')
    httpx.AsyncClient = type('AsyncClient', (), {})
    httpx.Timeout = type('Timeout', (), {'__init__': lambda self, *a, **k: None})
    httpx.RequestError = type('RequestError', (Exception,), {})

    fastapi = types.ModuleType('fastapi')

    class _App:
        def __init__(self, *a, **k):
            pass

        def get(self, *a, **k):
            return lambda fn: fn

        def post(self, *a, **k):
            return lambda fn: fn

    fastapi.FastAPI = _App
    fastapi.HTTPException = type('HTTPException', (Exception,), {
        '__init__': lambda self, s, d: (setattr(self, 'status_code', s), setattr(self, 'detail', d))})
    fastapi.Request = type('Request', (), {})
    fastapi.Response = type('Response', (), {'__init__': lambda self, *a, **k: None})

    responses = types.ModuleType('fastapi.responses')
    for name in ('HTMLResponse', 'JSONResponse', 'RedirectResponse'):
        setattr(responses, name, type(name, (), {'__init__': lambda self, *a, **k: None}))
    fastapi.responses = responses

    sys.modules['httpx'] = httpx
    sys.modules['fastapi'] = fastapi
    sys.modules['fastapi.responses'] = responses

    spec = importlib.util.spec_from_file_location('shenyan_web_proxy', SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    m = load()

    # 按钮走的那四条放行
    for cmd in ('沈砚确认记忆 27', '沈砚拒绝记忆 3', '沈砚记忆待审', '沈砚记忆列表'):
        assert m.ALLOWED_COMMANDS.match(cmd), f'该放行的被拦了：{cmd}'
        assert not m.BLOCKED_COMMANDS.match(cmd), f'被误判为危险：{cmd}'

    # 能毁库的、以及任意野生指令一律拦
    for cmd in ('沈砚清空所有记录 我确认', '沈砚忘记记忆 12', '沈砚记忆帮助',
                '沈砚随便写点什么', '沈砚确认记忆 abc'):
        assert not m.ALLOWED_COMMANDS.match(cmd), f'该拦的放行了：{cmd}'
    for cmd in ('沈砚清空所有记录 我确认', '沈砚忘记记忆 12'):
        assert m.BLOCKED_COMMANDS.match(cmd), f'危险指令没被识别：{cmd}'

    # 滑动窗口
    w = m.SlidingWindow(3)
    assert all(w.allow('k') for _ in range(3))
    assert not w.allow('k'), '超过上限还放行'
    assert w.allow('other'), '不同 key 被串在一起'
    assert w.used('k') == 3

    # 日额度
    d = m.DailyBudget(2)
    assert d.allow() and d.allow()
    assert not d.allow()
    assert d.left == 0

    # 邀请码正则不该吃掉合法 sid
    assert m.SID_RE.match('A' * 22)
    assert not m.SID_RE.match('../etc/passwd')

    print('ok · 16 组断言全过')


if __name__ == '__main__':
    run()
