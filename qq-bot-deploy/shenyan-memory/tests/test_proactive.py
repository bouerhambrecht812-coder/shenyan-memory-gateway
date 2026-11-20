"""验证主动消息调度：闲置会话能生成一条，且频率闸门有效。"""
import asyncio
import importlib.util
import os
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[3]
GW = ROOT / 'qq-bot-deploy' / 'shenyan-memory' / 'shenyan-gateway' / 'app.py'
PERSONA = ROOT / 'qq-bot-deploy' / 'shenyan-memory' / 'shenyan-persona'
ASSETS = ROOT / 'qq-bot-deploy' / 'shenyan-memory' / 'shenyan-assets'


def load(data, persona):
    os.environ.update(
        DATA_DIR=str(data), PERSONA_DIR=str(persona), ASSETS_DIR=str(ASSETS),
        DEMO_MODE='1', GATEWAY_KEY='k', DEEPSEEK_API_KEY='sk-test',
        WORLD_CONTEXT_TOOLS='', PROACTIVE_ENABLED='1', PROACTIVE_IDLE_MIN='1',
        PROACTIVE_HOUR_START='0', PROACTIVE_HOUR_END='24',
        PROACTIVE_MAX_PER_DAY='2', PROACTIVE_COOLDOWN_MIN='180',
        PROACTIVE_PER_SWEEP='3',
    )
    sys.path.insert(0, str(GW.parent))

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

        def middleware(self, *a, **k):
            return lambda fn: fn

        def mount(self, *a, **k):
            return None

    class _HTTP(Exception):
        def __init__(self, s, d):
            self.status_code, self.detail = s, d

    fastapi.FastAPI = _App
    fastapi.HTTPException = _HTTP
    fastapi.Request = type('Request', (), {})

    resp = types.ModuleType('fastapi.responses')
    resp.JSONResponse = type('JSONResponse', (), {'__init__': lambda self, c=None, *a, **k: None})
    resp.StreamingResponse = type('StreamingResponse', (), {'__init__': lambda self, *a, **k: None})
    fastapi.responses = resp

    st = types.ModuleType('fastapi.staticfiles')
    st.StaticFiles = type('StaticFiles', (), {'__init__': lambda self, *a, **k: None})

    oa = types.ModuleType('openai')
    oa.AsyncOpenAI = type('AsyncOpenAI', (), {'__init__': lambda self, **k: None})

    sys.modules.update({'fastapi': fastapi, 'fastapi.responses': resp,
                        'fastapi.staticfiles': st, 'openai': oa})

    spec = importlib.util.spec_from_file_location('gw_proactive', GW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    root = pathlib.Path(tempfile.mkdtemp(prefix='sy-pro-'))
    data = root / 'data'
    persona = root / 'persona'
    data.mkdir(parents=True, exist_ok=True)
    persona.mkdir(parents=True, exist_ok=True)
    (persona / 'seed_memories.json').write_text('[]', encoding='utf-8')
    (persona / 'demo_seed_memories.json').write_text('[]', encoding='utf-8')

    app = load(data, persona)

    sid = 'testsession00000001'
    path = app.SESSION_ROOT / f'{sid}.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('', encoding='utf-8')

    token = app.SESSION_DB.set(path)
    app.initialize()
    # 造一条两小时前的对话，满足“闲置足够久”
    with app.connect() as c:
        c.execute("INSERT INTO turns(created_at,user_text,reply_text) VALUES(?,?,?)",
                  ('2026-11-20 00:00:00 +08', '在吗', '嗯'))
    app.SESSION_DB.reset(token)

    calls = {'n': 0}

    async def fake_generate(user_text, context='', extra_system=''):
        calls['n'] += 1
        return '刚洗完澡\n你还没睡啊\n[[st:st_05]]'

    app.generate_reply = fake_generate

    async def go():
        await app.proactive_sweep()
        await app.proactive_sweep()   # 第二次应该被冷却挡住

    asyncio.run(go())

    token = app.SESSION_DB.set(path)
    with app.connect() as c:
        rows = c.execute('SELECT text,actions,delivered_at FROM proactive').fetchall()
    app.SESSION_DB.reset(token)

    ok = True
    def check(name, cond, extra=''):
        nonlocal ok
        print(('  ok   ' if cond else '  FAIL ') + name + ('' if cond else f'  <{extra}>'))
        ok = ok and cond

    check('生成了主动消息', len(rows) == 1, f'{len(rows)} 条')
    check('模型只被调用一次（冷却生效）', calls['n'] == 1, f'{calls["n"]} 次')
    if rows:
        check('正文正确', '刚洗完澡' in rows[0]['text'], rows[0]['text'])
        acts = __import__('json').loads(rows[0]['actions'])
        check('带上了表情动作', any(a['type'] == 'sticker' for a in acts), str(acts))
        check('初始未投递', rows[0]['delivered_at'] is None)
    print()
    print('结果：', '全过' if ok else '有失败')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(run())
