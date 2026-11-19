"""沈砚记忆网关 · 网页演示代理（shenyan-web）

只做一件事：把记忆网关藏到服务端后面，让没有 QQ 的访客也能聊天，
同时保证访客之间互不可见、互不可毁。

- GATEWAY_KEY 只存在服务端，前端永远拿不到
- 每个访客一个 HttpOnly cookie，对应网关里 /data/sessions/<sid>.sqlite3
- 三层限流：单会话 / 单 IP / 全球每日
- 只放行 待审、列表、确认、拒绝 四个指令；清空和忘记留在主人手里
- 这个服务不挂 /data 卷，不读写任何 SQLite，所有数据操作都在网关里
"""
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

GATEWAY_URL = os.getenv('GATEWAY_URL', 'http://shenyan-memory:8000').rstrip('/')
GATEWAY_KEY = os.getenv('GATEWAY_KEY', '').strip()
STATIC_DIR = Path(os.getenv('STATIC_DIR', str(Path(__file__).resolve().parent.parent / 'static')))
PASSCODE = os.getenv('DEMO_PASSCODE', '').strip()

COOKIE = 'sy_sid'
PASS_COOKIE = 'sy_pass'
SID_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
STICKER_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}\.png$')

SESSION_LIMIT = int(os.getenv('SESSION_LIMIT', '30'))   # 单会话 / 10 分钟
IP_LIMIT = int(os.getenv('IP_LIMIT', '60'))             # 单 IP / 10 分钟
DAILY_LIMIT = int(os.getenv('DAILY_LIMIT', '600'))      # 全站 / 天
LIMIT_WINDOW = 600

# 按钮会用到这四条；打字写别的指令一律不给过。
ALLOWED_COMMANDS = re.compile(r'^沈砚(记忆待审|记忆列表|确认记忆\s+\d{1,7}|拒绝记忆\s+\d{1,7})$')
BLOCKED_COMMANDS = re.compile(r'^沈砚.*(清空|忘记|帮助|指令)')

client: httpx.AsyncClient | None = None


class SlidingWindow:
    """单进程内存限流。uvicorn 只起 1 个 worker 时是准确的。"""

    def __init__(self, limit):
        self.limit = limit
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > LIMIT_WINDOW:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def used(self, key: str) -> int:
        q = self.hits.get(key)
        if not q:
            return 0
        now = time.monotonic()
        while q and now - q[0] > LIMIT_WINDOW:
            q.popleft()
        return len(q)


class DailyBudget:
    def __init__(self, limit):
        self.limit = limit
        self.day = date.today().isoformat()
        self.count = 0

    def allow(self) -> bool:
        today = date.today().isoformat()
        if today != self.day:
            self.day, self.count = today, 0
        if self.count >= self.limit:
            return False
        self.count += 1
        return True

    @property
    def left(self) -> int:
        return max(0, self.limit - self.count)


session_window = SlidingWindow(SESSION_LIMIT)
ip_window = SlidingWindow(IP_LIMIT)
daily = DailyBudget(DAILY_LIMIT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title='Shenyan Web Demo', docs_url=None, redoc_url=None, lifespan=lifespan)


def authorized(request: Request) -> bool:
    if not PASSCODE:
        return True
    return request.cookies.get(PASS_COOKIE) == PASSCODE


def sid_of(request: Request) -> tuple[str, bool]:
    sid = request.cookies.get(COOKIE, '')
    if SID_RE.match(sid):
        return sid, False
    return secrets.token_urlsafe(16), True


def with_session(response, sid: str, new: bool):
    if new:
        response.set_cookie(COOKIE, sid, max_age=7 * 86400, httponly=True, samesite='lax')
    return response


def quota(sid: str) -> dict:
    return {
        'session_left': max(0, SESSION_LIMIT - session_window.used(sid)),
        'daily_left': daily.left,
    }


def read_page(name: str) -> str:
    path = STATIC_DIR / name
    if not path.exists():
        return '<h1 style="font:16px/1.6 system-ui;padding:2em">缺少静态页：' + name + '</h1>'
    return path.read_text(encoding='utf-8')


async def gateway_ok() -> bool:
    meta = await gateway_meta()
    return bool(meta)


_meta_cache = {'at': 0.0, 'data': {}}


async def gateway_meta(ttl: float = 30.0) -> dict:
    """网关的 /healthz，缓存一下，用来判断是不是演示模式。"""
    now = time.monotonic()
    if _meta_cache['data'] and now - _meta_cache['at'] < ttl:
        return _meta_cache['data']
    try:
        r = await client.get(f'{GATEWAY_URL}/healthz', timeout=4.0)
        data = r.json() if r.status_code == 200 else {}
    except Exception:
        data = {}
    _meta_cache['at'], _meta_cache['data'] = now, data
    return data


@app.get('/healthz')
async def health():
    return {'ok': await gateway_ok(), 'gateway': GATEWAY_URL}


@app.get('/')
async def index(request: Request):
    if not authorized(request):
        target = request.query_params.get('k', '')
        if target and target == PASSCODE:
            resp = RedirectResponse('/', status_code=302)
            resp.set_cookie(PASS_COOKIE, PASSCODE, max_age=30 * 86400, httponly=True, samesite='lax')
            return resp
        return HTMLResponse(read_page('gate.html'), status_code=401)
    return HTMLResponse(read_page('index.html'), headers={'Cache-Control': 'no-store'})


@app.get('/new')
async def new_session():
    """丢掉当前 sid。旧库留在网关上，到 TTL 自己回收。"""
    resp = RedirectResponse('/', status_code=302)
    resp.delete_cookie(COOKIE)
    return resp


async def forward(sid: str, text: str) -> str:
    """把一句话交给网关。sid 决定用哪个库，所以访客之间天然隔离。"""
    if not GATEWAY_KEY:
        raise HTTPException(503, '演示服务尚未配置 GATEWAY_KEY。')
    try:
        r = await client.post(
            f'{GATEWAY_URL}/v1/chat/completions',
            headers={'Authorization': f'Bearer {GATEWAY_KEY}', 'X-Demo-Session': sid},
            json={'model': 'shenyan', 'messages': [{'role': 'user', 'content': text}], 'stream': False},
        )
    except httpx.RequestError:
        raise HTTPException(502, '连不上记忆网关。')
    if r.status_code != 200:
        raise HTTPException(502, '记忆网关暂时不可用。')
    try:
        return (r.json()['choices'][0]['message']['content'] or '').strip()
    except Exception:
        raise HTTPException(502, '记忆网关返回了无法解析的内容。')


async def forward_actions(sid: str, text: str) -> dict:
    """走 /v1/reply，直接拿动作列表（文字 / 表情 / 语音）。"""
    if not GATEWAY_KEY:
        raise HTTPException(503, '演示服务尚未配置 GATEWAY_KEY。')
    try:
        r = await client.post(
            f'{GATEWAY_URL}/v1/reply',
            headers={'Authorization': f'Bearer {GATEWAY_KEY}', 'X-Demo-Session': sid},
            json={'messages': [{'role': 'user', 'content': text}]},
        )
    except httpx.RequestError:
        raise HTTPException(502, '连不上记忆网关。')
    if r.status_code != 200:
        raise HTTPException(502, '记忆网关暂时不可用。')
    try:
        return r.json()
    except Exception:
        raise HTTPException(502, '记忆网关返回了无法解析的内容。')


@app.get('/stickers/{name}')
async def sticker(name: str):
    """表情素材由网关持有，这里只做转发和缓存。"""
    if not STICKER_RE.match(name):
        raise HTTPException(404, 'not found')
    try:
        r = await client.get(f'{GATEWAY_URL}/stickers/{name}', timeout=10.0)
    except httpx.RequestError:
        raise HTTPException(502, '素材服务不可用。')
    if r.status_code != 200:
        raise HTTPException(404, 'not found')
    return Response(content=r.content, media_type='image/png',
                    headers={'Cache-Control': 'public, max-age=86400'})


async def fetch_memory(sid: str) -> dict:
    empty = {'approved': [], 'pending': [], 'turns': 0}
    if not GATEWAY_KEY:
        return empty
    try:
        r = await client.get(
            f'{GATEWAY_URL}/v1/demo/memory',
            headers={'Authorization': f'Bearer {GATEWAY_KEY}', 'X-Demo-Session': sid},
        )
        return r.json() if r.status_code == 200 else empty
    except Exception:
        return empty


@app.get('/api/memory')
async def memory(request: Request):
    if not authorized(request):
        raise HTTPException(403, '需要邀请码。')
    sid, new = sid_of(request)
    data = await fetch_memory(sid)
    data['quota'] = quota(sid)
    data['new_session'] = new
    meta = await gateway_meta()
    data['mock'] = bool(meta.get('mock'))
    return with_session(JSONResponse(data), sid, new)


@app.post('/api/chat')
async def chat(request: Request):
    if not authorized(request):
        raise HTTPException(403, '需要邀请码。')
    sid, new = sid_of(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, '请求格式错误。')

    text = str(body.get('text', '')).strip()
    if not text:
        raise HTTPException(400, '空消息。')
    if len(text) > 500:
        return with_session(JSONResponse({'reply': '太长了，演示版限定 500 字以内。'}), sid, new)
    if BLOCKED_COMMANDS.match(text):
        return with_session(JSONResponse({
            'reply': '这条指令在演示环境里关掉了。\n记忆的确认和拒绝请点旁边的按钮。'}), sid, new)
    if text.startswith('沈砚') and not ALLOWED_COMMANDS.match(text):
        return with_session(JSONResponse({
            'reply': '演示环境只留了几条记忆指令。\n待审、列表、确认、拒绝直接点按钮就行。'}), sid, new)

    ip = (request.headers.get('x-forwarded-for', '') or
          (request.client.host if request.client else '')).split(',')[0].strip()

    if not ip_window.allow(ip or 'unknown'):
        return with_session(JSONResponse({
            'reply': '这个网络刚才聊得有点快。\n等十分钟再来。'}), sid, new)
    if not session_window.allow(sid):
        return with_session(JSONResponse({
            'reply': '这个会话的额度到上限了。\n想继续看，刷新一下会开一个新的。'}), sid, new)
    if not daily.allow():
        return with_session(JSONResponse({
            'reply': '今天的演示额度用完了。\n想继续看，跟我说一声，我给你重开。'}), sid, new)

    try:
        data = await forward_actions(sid, text)
    except HTTPException as ex:
        return with_session(JSONResponse({
            'actions': [{'type': 'text', 'text': f'（{ex.detail}）'}],
            'quota': quota(sid),
        }), sid, new)

    acts = data.get('actions') or [{'type': 'text', 'text': '……'}]
    return with_session(JSONResponse({
        'actions': acts,
        'context': data.get('context', ''),
        'quota': quota(sid),
    }), sid, new)


@app.post('/api/memory/{mid}')
async def act(request: Request, mid: int):
    """确认 / 拒绝一条候选记忆。走的还是网关里那两条指令，不是新接口。"""
    if not authorized(request):
        raise HTTPException(403, '需要邀请码。')
    sid, new = sid_of(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = body.get('action')
    if action not in ('confirm', 'reject'):
        raise HTTPException(400, '未知操作。')
    if not 0 < mid < 10_000_000:
        raise HTTPException(400, '编号不对。')

    command = '沈砚' + ('确认记忆' if action == 'confirm' else '拒绝记忆') + f' {mid}'
    try:
        reply = await forward(sid, command)
    except HTTPException as ex:
        return with_session(JSONResponse({'message': str(ex.detail)}), sid, new)

    data = await fetch_memory(sid)
    data['message'] = reply
    data['quota'] = quota(sid)
    return with_session(JSONResponse(data), sid, new)
