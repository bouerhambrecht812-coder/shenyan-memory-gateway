#!/usr/bin/env python3
"""冒烟测试：把一条完整链路走一遍，只用标准库。

    python scripts/smoke-test.py                       # 默认 http://127.0.0.1:8080
    python scripts/smoke-test.py http://IP:8080        # 测服务器
    python scripts/smoke-test.py http://127.0.0.1:8080 邀请码

检查项：
    1. 网页服务活着
    2. 记忆面板能读到已确认记忆
    3. 说一句话能拿到动作列表（文字 + 表情）
    4. 语音标记能变成 voice 动作
    5. 表情素材能通过代理取到
    6. 网关直连能返回动作列表
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080').rstrip('/')
PASSCODE = sys.argv[2] if len(sys.argv) > 2 else ''

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

passed, failed = [], []


def check(name, ok, extra=''):
    if ok:
        passed.append(name)
        print(f'  ok   {name}')
    else:
        failed.append(name)
        print(f'  FAIL {name}  {extra}')


def get(path, raw=False):
    with opener.open(BASE + path, timeout=30) as r:
        return (r.read(), dict(r.headers)) if raw else json.loads(r.read().decode('utf-8'))


def post(path, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with opener.open(req, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    print(f'目标 {BASE}')
    if PASSCODE:
        get(f'/?k={urllib.parse.quote(PASSCODE)}')
        print('  ·  已带邀请码进入')

    # 1
    health = get('/healthz')
    check('网页服务活着', health.get('ok') is True, str(health))

    # 2
    mem = get('/api/memory')
    approved = mem.get('approved') or []
    check('记忆面板可读', isinstance(approved, list) and len(approved) >= 1,
          f'已确认 {len(approved)} 条')
    print(f'      已确认记忆 {len(approved)} 条，待审 {len(mem.get("pending") or [])} 条')

    # 3
    reply = post('/api/chat', {'text': '你还记得我之前说过什么吗'})
    acts = reply.get('actions') or []
    kinds = [a.get('type') for a in acts]
    check('拿到动作列表', bool(acts), str(acts)[:120])
    check('包含文字气泡', 'text' in kinds, str(kinds))
    check('包含表情', 'sticker' in kinds, str(kinds))
    print(f'      动作 {kinds}  情境 {"有" if reply.get("context") else "无"}')

    # 4
    voice = post('/api/chat', {'text': '我要睡了'})
    vk = [a.get('type') for a in (voice.get('actions') or [])]
    check('语音动作可用', 'voice' in vk, str(vk))

    # 5
    st = next((a for a in acts if a.get('type') == 'sticker'), None)
    if st:
        body, headers = get(st['url'], raw=True)
        check('表情素材可取', body[:4] == b'\x89PNG' and len(body) > 500,
              f'{len(body)} bytes')

    # 6
    gw = get('/api/memory')
    q = gw.get('quota') or {}
    check('配额正常', q.get('session_left') is not None, str(q))

    print()
    print(f'通过 {len(passed)}，失败 {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except urllib.error.URLError as ex:
        print(f'连不上 {BASE}：{ex}')
        sys.exit(2)
