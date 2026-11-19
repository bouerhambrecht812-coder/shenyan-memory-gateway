"""演示层最要紧的一条：访客碰不到主人的记忆库。

不用装 fastapi / openai / sqlite 驱动，直接把网关模块在假模块下跑一遍。
    python web-demo/tests/test_isolation.py
    # 或 pytest web-demo/tests/test_isolation.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATEWAY = ROOT / 'qq-bot-deploy' / 'shenyan-memory' / 'shenyan-gateway' / 'app.py'
PERSONA = ROOT / 'qq-bot-deploy' / 'shenyan-memory' / 'shenyan-persona'


def load_gateway(data_dir, persona_dir=None):
    os.environ.update(
        DATA_DIR=str(data_dir),
        PERSONA_DIR=str(persona_dir or PERSONA),
        ASSETS_DIR=str(PERSONA.parent / 'shenyan-assets'),
        DEMO_MODE='1',
        GATEWAY_KEY='test-key',
        DEEPSEEK_API_KEY='sk-test',
        WORLD_CONTEXT_TOOLS='',
    )
    sys.path.insert(0, str(GATEWAY.parent))

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
    openai_mod.AsyncOpenAI = type('AsyncOpenAI', (), {'__init__': lambda self, **k: None})

    sys.modules['fastapi'] = fastapi
    sys.modules['fastapi.responses'] = responses
    sys.modules['fastapi.staticfiles'] = static
    sys.modules['openai'] = openai_mod

    spec = importlib.util.spec_from_file_location('shenyan_gateway_app', GATEWAY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    base = os.environ.get('SHENYAN_TEST_DIR')
    root = pathlib.Path(base) if base else pathlib.Path(tempfile.mkdtemp(prefix='shenyan-demo-'))
    data = root / 'data'
    persona = root / 'persona'
    data.mkdir(parents=True, exist_ok=True)
    persona.mkdir(parents=True, exist_ok=True)

    # 自带一份最小的设定，不依赖仓库外的私人文件
    (persona / 'character_bible.md').write_text('OWNER-PERSONA 仅用于测试', encoding='utf-8')
    (persona / 'behavior_rules.md').write_text('', encoding='utf-8')
    (persona / 'seed_memories.json').write_text(
        '[{"kind":"core","content":"OWNER-SEED 只有主人库该有这条"}]', encoding='utf-8')
    (persona / 'demo_seed_memories.json').write_text(
        '[{"kind":"core","content":"DEMO-SEED 只有访客会话该有这条"}]', encoding='utf-8')

    app = load_gateway(data, persona)

    # 主人库
    app.initialize()
    with app.connect() as c:
        owner = [r['content'] for r in c.execute('SELECT content FROM memories')]

    # 演示会话库
    sid = 'abcdefghijklmnop1234'
    session = app.SESSION_ROOT / f'{sid}.sqlite3'
    token = app.SESSION_DB.set(session)
    app.initialize()
    with app.connect() as c:
        demo = [r['content'] for r in c.execute('SELECT content FROM memories')]
    app.SESSION_DB.reset(token)

    assert session.exists(), '会话库没建出来'
    assert any('DEMO-SEED' in x for x in demo), '演示库没读到演示种子'
    assert not any('OWNER-SEED' in x for x in demo), '主人的种子漏进了演示库'
    assert any('OWNER-SEED' in x for x in owner), '主人库没读到自己的种子'
    assert not any('DEMO-SEED' in x for x in owner), '演示种子漏进了主人库'

    # 会话里清空，不能连带主人库
    token = app.SESSION_DB.set(session)
    reply = app.render_command('沈砚清空所有记录 我确认')
    app.SESSION_DB.reset(token)
    with app.connect() as c:
        owner_after = c.execute('SELECT COUNT(*) FROM memories').fetchone()[0]

    assert reply and '已删除' in reply, '清空指令没有执行'
    assert owner_after == len(owner), '主人的库被清掉了'

    # 空库里待审指令仍然正常
    token = app.SESSION_DB.set(session)
    pending = app.render_command('沈砚记忆待审')
    app.SESSION_DB.reset(token)
    assert pending and '待审核记忆' in pending, '待审指令坏了'

    # 时间线导出只属于主人
    timeline = data / 'timeline_approved.md'
    text = timeline.read_text(encoding='utf-8') if timeline.exists() else ''
    assert 'DEMO-SEED' not in text, '演示种子被写进了主人的时间线'
    assert 'OWNER-SEED' in text, '主人的时间线没生成'

    print('ok · 7 组断言全过')


if __name__ == '__main__':
    run()
