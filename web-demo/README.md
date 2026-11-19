# 沈砚 · 网页演示层

给没有 QQ 的人看这个项目用的：一个聊天页，旁边是记忆闸门。
访客不用注册、不用装任何东西，打开链接就能聊；聊出来的记忆只在他自己那一份库里。

它**不替代** QQ 链路。网关那边新增的东西全部在 `DEMO_MODE` 开关后面，
开关关掉时，`AstrBot → 网关` 的行为和改动前一模一样。

---

## 为什么是这么拆的

QQ 只是最外面那层壳。真正的系统是 `shenyan-gateway`，它本来就是个 OpenAI 兼容的 HTTP 服务。
所以这里没有重写任何业务逻辑，只加了一个「入口」：

```
浏览器 ──► shenyan-web（代理，持密钥）──► shenyan-memory（网关）──► DeepSeek
                    │                            │
                    └─ 每人一个 cookie            └─ /data/sessions/<sid>.sqlite3
```

三件事是刻意这么做的：

| 决策 | 原因 |
|---|---|
| `GATEWAY_KEY` 只在服务端 | 前端拿不到密钥，F12 里翻不出任何东西 |
| 一个访客一个库 | 网关原本假设「单用户」，公网挂出去会互相污染；`清空所有记录` 更是一句能毁掉全部 |
| 代理不挂 `/data` | 数据只有网关一个进程在主写，代理是纯 HTTP，删不掉也改不了 |

---

## 目录

```
web-demo/
├─ static/
│  ├─ index.html      聊天页 + 记忆面板（单文件，无外链资源）
│  └─ gate.html       邀请码页
├─ proxy/
│  ├─ server.py       代理：会话、限流、指令收口
│  ├─ requirements.txt
│  └─ Dockerfile
├─ compose.demo.yml
└─ nginx.conf.example
```

网关侧一共动了三处，都在 `qq-bot-deploy/shenyan-memory/`：

- `shenyan-gateway/app.py`：`DEMO_MODE`、按 `X-Demo-Session` 分库、`GET /v1/demo/memory`、会话库回收
- `shenyan-persona/demo_seed_memories.json`：演示用的中立种子（不含主人的私人关系史）
- `.env.shenyan.example`：新的演示变量

---

## 部署

假设服务器上是这样（和原来的部署同一层）：

```
/opt/qq-bot/
├─ astrbot.yml
├─ shenyan-compose.yml
├─ .env.shenyan
├─ shenyan-gateway/
├─ shenyan-persona/
└─ web-demo/          ← 把这个目录放进来
```

**第一步：改 `.env.shenyan`**

```bash
DEMO_MODE=1
DEMO_EXTRACT_EVERY=2
DEMO_PASSCODE=换成你自己的口令
```

`DEMO_PASSCODE` 别留空——留空等于把 DeepSeek 的钱包挂在公网上。

**第二步：起服务**

```bash
cd /opt/qq-bot
docker compose -f astrbot.yml -f shenyan-compose.yml -f web-demo/compose.demo.yml up -d --build
docker compose -f astrbot.yml -f shenyan-compose.yml -f web-demo/compose.demo.yml ps
```

三个文件必须一起给，`astrbot_network` 是在 `astrbot.yml` 里定义的。
如果你已经把 AstrBot 那段删了，就把它 `networks:` 那几行抄进 `compose.demo.yml`。

**第三步：开**

```
http://<你的IP>:8080/?k=你的口令
```

阿里云安全组要放行 8080。拿到链接之后给自己手机发一遍，确认微信里能打开。

---

## 上线前逐条过

- [ ] 不带 `?k=` 打开首页，看到的是邀请码页，不是聊天页
- [ ] 两个浏览器各聊几句，记忆面板里的内容互不可见
- [ ] 在输入框打「沈砚清空所有记录 我确认」，回的是「演示环境里关掉了」
- [ ] `docker compose logs --tail 30 shenyan-memory`，没有报错，也没出现你的 `shenyan.sqlite3`
- [ ] 连发 30 条，第 31 条开始提示额度到上限
- [ ] 关掉浏览器再开，右上角出现「聊过 N 轮，我还记着」
- [ ] `ls shenyan-data/` 里多了一个 `sessions/`，主库文件时间戳没变

---

## 加域名和 HTTPS（可选）

有域名再套，没域名前 `IP:8080` 也能用，微信弹一次「非官方网页」提示，点继续就行。

```bash
sudo cp web-demo/nginx.conf.example /etc/nginx/sites-available/shenyan-demo
# 改掉 server_name
sudo ln -s /etc/nginx/sites-available/shenyan-demo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d demo.example.com
```

然后 `docker-compose` 里把 `8080:8080` 改成 `127.0.0.1:8080:8080`，只留 nginx 对外。

---

## 成本

一次对话 = 一条 DeepSeek 请求；每 `DEMO_EXTRACT_EVERY` 轮再多一条抽提请求。
按 `DAILY_LIMIT=600` 算，一天最多 900 次左右的调用，`deepseek-flash` 这个量级基本可以忽略。

真担心跑飞，把 `DAILY_LIMIT` 往下调到 100，面试周再开。

## 安全

- 密钥只在服务端，前端没有
- 三层限流都在同一进程内存里，所以 `--workers` 必须是 1（Dockerfile 里已经写死了）
- 会话库三小时没动静就回收，回收逻辑在网关里，代理碰不到 `/data`
- 演示库用的是 `demo_seed_memories.json`，只含可公开的演示设定，和主人的库完全隔离

## 多模态（v1.1）

网关现在返回动作列表，代理原样透传，前端按类型渲染：

| 动作 | 网页端 | 说明 |
|---|---|---|
| `text` | 逐条气泡 | 和以前一样 |
| `sticker` | 120px 表情图 | 走 `/stickers/<文件>`，代理从网关转发并缓存一天 |
| `voice` | 可点击的语音气泡 | 服务器没接 TTS，用的是浏览器自带的 speechSynthesis |

`/api/chat` 的返回也从 `{reply}` 换成了 `{actions, context}`，前端一次渲染一串动作。

顶栏那个「实时情境」小标表示这条回复带上了 MCP 拉来的时间和天气，鼠标悬停能看到具体内容。
这个标记只是提示，情境本身不会写进记忆库。

代理新增了一个 `/stickers/{name}` 路由，把网关里的素材转发出去；文件名做了白名单校验，
不会变成任意路径读取。

## 已知限制

- **UI 不显示历史消息**。刷新后聊天框是空的，但网关那边上下文还在——所以会看到「聊过 14 轮，我还记着」这种提示。想完整保留得加一个 `/v1/demo/turns`，这次没做。
- **限流是单进程内存**。重启就清零，多实例也不准。演示够用。
- **公网 AI 对话服务在国内涉及《生成式人工智能服务管理暂行办法》**。带邀请码、不公开传播的小范围演示一般没人管，但别把它当公开产品挂出去——尤其你投的是政策研究方向，这点最好自己心里有数，面试时被问到反而是加分项。
- 记忆检索还是轻量字符匹配，不是向量库。`README_从这里开始.md` 里已经写明了，别在演示里吹成 RAG。
