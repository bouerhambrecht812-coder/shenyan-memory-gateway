"""动作协议 + MCP + 情境注入的离线测试。

不联外网、不装 fastapi：把网关模块在假模块下跑一遍，模型调用换成假的。
    python tests/test_multimodal.py
"""
import asyncio
import importlib
import importlib.util
import os
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
GW = ROOT / 'shenyan-gateway'
PERSONA = ROOT / 'shenyan-persona'
ASSETS = ROOT / 'shenyan-assets'

sys.path.insert(0, str(GW))


# ── 假模块 ────────────────────────────────────────────────
def install_stubs():
    fastapi = types.ModuleType('fastapi')

    class _App:
        def __init__(self, *a, **k):
            self.state = types.SimpleNamespace()

        def get(self, *a, **k):
            return lambda fn: fn

        def post(self, *a, **k):
            return lambda fn: fn

        def on_event(self, *a, **k):
            return lambda fn: fn

        def mount(self, *a, **k):
            return None

    class _HTTPException(Exception):
        def __init__(self, status, detail):
            self.status_code, self.detail = status, detail

    fastapi.FastAPI = _App
    fastapi.HTTPException = _HTTPException
    fastapi.Request = type('Request', (), {})

    responses = types.ModuleType('fastapi.responses')
    responses.JSONResponse = type('JSONResponse', (), {'__init__': lambda self, c=None, *a, **k: setattr(self, 'content', c)})
    responses.StreamingResponse = type('StreamingResponse', (), {'__init__': lambda self, *a, **k: None})
    fastapi.responses = responses

    static = types.ModuleType('fastapi.staticfiles')
    static.StaticFiles = type('StaticFiles', (), {'__init__': lambda self, *a, **k: None})

    openai_mod = types.ModuleType('openai')
    openai_mod.AsyncOpenAI = type('AsyncOpenAI', (), {
        '__init__': lambda self, **k: None,
        'chat': None,
    })

    sys.modules['fastapi'] = fastapi
    sys.modules['fastapi.responses'] = responses
    sys.modules['fastapi.staticfiles'] = static
    sys.modules['openai'] = openai_mod


def check(name, cond, extra=''):
    if cond:
        print('  ok  ', name)
        return True
    print('  FAIL', name, extra)
    return False


# ── 1. 动作解析 ──────────────────────────────────────────
def test_parse():
    import actions
    import stickers

    book = stickers.StickerBook(ASSETS)
    passed = []

    clean, ids, voice = actions.parse_reply('行吧\n[[st:st_03]]', book)
    passed.append(check('解析出表情', ids == ['st_03'], str(ids)))
    passed.append(check('文本已清理', clean == '行吧', repr(clean)))
    passed.append(check('没有误判语音', voice is False))

    # 模型经常漏冒号或改大小写，这几种都得认
    for raw in ('[[st:st_03]]', '[[st_03]]', '[[st：st_03]]', '[[st3]]',
                '[[sticker:st_03]]', '[[ST_03]]', '[[st-03]]'):
        text, ids, _ = actions.parse_reply('行吧\n' + raw, book)
        passed.append(check(f'兼容写法 {raw}', ids == ['st_03'] and '[[' not in text, f'{ids} / {text!r}'))

    clean, ids, voice = actions.parse_reply('早点睡\n[[voice]]', book)
    passed.append(check('识别语音标记', voice is True))
    passed.append(check('语音标记不留在正文', '[[voice]]' not in clean, repr(clean)))

    clean, ids, _ = actions.parse_reply('嗯 [[st:not_exist]]', book)
    passed.append(check('不存在的素材被丢弃', ids == [], str(ids)))

    clean, ids, _ = actions.parse_reply('[[st:st_01]][[st:st_02]][[st:st_03]]', book)
    passed.append(check('一次最多一个表情', len(ids) == 1, str(ids)))

    acts = actions.build('行吧', ['st_03'], False, book)
    passed.append(check('动作结构正确', acts[0]['type'] == 'text' and acts[1]['type'] == 'sticker', str(acts)))
    passed.append(check('表情带 URL', acts[1]['url'].startswith('/stickers/'), acts[1].get('url', '')))

    acts = actions.build('早点睡', [], True, book)
    passed.append(check('语音动作替换文本', acts[0]['type'] == 'voice', str(acts)))

    passed.append(check('素材库已加载', book.status()['count'] >= 8, str(book.status())))
    return all(passed)


# ── 2. MCP 往返 ──────────────────────────────────────────
def test_mcp():
    from mcp_stdio import MCPSessionPool

    async def run():
        pool = MCPSessionPool([{'name': 'world', 'command': [sys.executable, str(GW / 'world_server.py')],
                                'env': {'WORLD_TZ': 'Asia/Singapore'}}])
        await pool.start()
        try:
            session = pool.sessions[0]
            tools = [t['name'] for t in await session.list_tools()]
            ok1 = check('握手 + tools/list', set(tools) == {'clock.now', 'weather.now', 'news.headlines'}, str(tools))
            clock = await pool.call('world.clock.now')
            ok2 = check('tools/call 返回文本', '时区' in clock and '20' in clock, clock[:40])
            try:
                await pool.call('world.no_such_tool')
                ok3 = check('未知工具应该报错', False)
            except Exception:
                ok3 = check('未知工具应该报错', True)
            return ok1 and ok2 and ok3
        finally:
            await pool.close()

    return asyncio.run(run())


# ── 3. 端到端：假模型 + 真 MCP ────────────────────────────
def test_compose():
    install_stubs()
    data = pathlib.Path(tempfile.mkdtemp(prefix='shenyan-multi-'))

    os.environ.update(
        DATA_DIR=str(data),
        PERSONA_DIR=str(PERSONA),
        ASSETS_DIR=str(ASSETS),
        DEMO_MODE='1',
        GATEWAY_KEY='test-key',
        DEEPSEEK_API_KEY='sk-test',
        WORLD_CONTEXT_TOOLS='clock.now',
    )

    spec = importlib.util.spec_from_file_location('shenyan_app_multi', GW / 'app.py')
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)

    captured = {}

    async def fake_generate(user_text, context=''):
        captured['context'] = context
        return '别急\n我记着呢\n[[st:st_06]]'

    app.generate_reply = fake_generate

    data.joinpath('shenyan.sqlite3').write_text('', encoding='utf-8')
    app.initialize()

    async def run():
        await app.WORLD.start()
        try:
            clean, acts, context = await app.compose('你还记得吗')
            return clean, acts, context
        finally:
            await app.WORLD.close()

    clean, acts, context = asyncio.run(run())

    passed = [
        check('情境注入到了系统提示', '当前情境' in captured.get('context', ''), str(captured.get('context'))[:60]),
        check('正文不含标记', '[[' not in clean, clean),
        check('动作含表情', any(a['type'] == 'sticker' for a in acts), str(acts)),
        check('正文落库', clean.startswith('别急'), clean),
    ]

    with app.connect() as c:
        turns = c.execute('SELECT COUNT(*) FROM turns').fetchone()[0]
        mems = c.execute("SELECT COUNT(*) FROM memories WHERE content LIKE '%天气%' OR content LIKE '%时区%'").fetchone()[0]
    passed.append(check('对话已写入 turns', turns == 1, str(turns)))
    passed.append(check('情境没有被写进记忆库', mems == 0, str(mems)))

    return all(passed)


if __name__ == '__main__':
    print('[1] 动作解析')
    a = test_parse()
    print('[2] MCP 往返')
    b = test_mcp()
    print('[3] 端到端')
    c = test_compose()
    print()
    print('结果：', ' 全过' if all([a, b, c]) else ' 有失败')
    sys.exit(0 if all([a, b, c]) else 1)
