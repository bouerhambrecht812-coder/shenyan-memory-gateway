"""Offline tests: no external DeepSeek requests or real QQ credentials needed."""
import importlib.util
import json
import os
import tempfile
import sys
import types
try:
    from openai import AsyncOpenAI  # noqa: F401
except ImportError:
    # The installed Docker image includes the real SDK. Offline unit tests use a stub.
    sys.modules['openai'] = types.SimpleNamespace(AsyncOpenAI=object)
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TMP = tempfile.TemporaryDirectory(prefix='shenyan-test-')
os.environ['DATA_DIR'] = TMP.name
os.environ['PERSONA_DIR'] = str(ROOT/'shenyan-persona')
os.environ['GATEWAY_KEY'] = 'test_local_gateway_key_long_enough_123'
os.environ['DEEPSEEK_API_KEY'] = 'sk-local-mock'
spec = importlib.util.spec_from_file_location('memory_gateway',ROOT/'shenyan-gateway'/'app.py')
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)


def test_schema_and_seed():
    gw.initialize()
    with gw.connect() as c:
        rows=c.execute('SELECT * FROM memories WHERE status="approved"').fetchall()
    assert len(rows)>=12
    assert any('旧手表' in r['content'] for r in rows)


def test_auth_and_mock_chat():
    async def fake_reply(text):
        return '辛苦了。今天先别给自己布置新的任务。'
    gw.generate_reply = fake_reply
    gw.EXTRACT_EVERY = 1000  # avoid real network extraction during mock test
    gw.initialize()
    client=TestClient(gw.app)
    body={'model':'shenyan','messages':[{'role':'user','content':'沈砚，今天忙吗？'}]}
    assert client.post('/v1/chat/completions', json=body).status_code==401
    auth={'Authorization':'Bearer test_local_gateway_key_long_enough_123'}
    r=client.post('/v1/chat/completions',json=body,headers=auth)
    assert r.status_code==200
    assert '辛苦了' in r.json()['choices'][0]['message']['content']
    assert gw.total_turns()==1
    s=client.post('/v1/chat/completions',json={**body,'stream':True}, headers=auth)
    assert s.status_code==200 and 'data: [DONE]' in s.text
    assert 'chat.completion.chunk' in s.text
    m=client.get('/v1/models', headers=auth)
    assert m.status_code==200 and m.json()['data'][0]['id']=='shenyan'


def test_commands_and_seed_preservation():
    gw.initialize()
    with gw.connect() as c:
        c.execute("INSERT INTO memories(kind,content,status,source,created_at) VALUES(?,?,?,?,?)",('fiction_event','用户确认沈砚新写了一页读书笔记','pending','unit-test',gw.now()))
        mid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
    assert '待审核' in gw.render_command('沈砚记忆待审')
    assert '确认' in gw.render_command(f'沈砚确认记忆 {mid}')
    assert '用户确认' in gw.render_command('沈砚记忆列表')
    assert '删除' in gw.render_command(f'沈砚忘记记忆 {mid}')
    gw.render_command('沈砚清空所有记录 我确认')
    gw.initialize()
    assert len(gw.get_memories('旧手表'))==0  # shouldn't re-seed on restart after deletion
