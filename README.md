# 沈砚记忆网关 · Shenyan Memory Gateway

给 AI 角色、虚拟人和数字员工加一层**记得住、查得到、改得动**的长期记忆。

记忆存在自己的库里，写不写进正史由人点头；换一个 Base URL 就能接进现有对话产品。

> 这个仓库只包含可以公开的部分：代码、演示角色设定、案例页。
> 没有真实对话记录、没有密钥、没有服务器信息。

---

## 目录

```
qq-bot-deploy/shenyan-memory/   记忆网关（主体）
  shenyan-gateway/              FastAPI：检索、审核、动作协议、MCP 客户端
  shenyan-persona/              演示角色设定与种子记忆
  shenyan-assets/               8 张表情素材与清单
  scripts/                      本机启动、冒烟测试
  tests/                        离线测试（不需要外网）
  start-demo.py                 双击启动入口
web-demo/                       网页演示层：会话隔离代理 + 单页前端
docs/                           产品案例页（静态，可直接开 GitHub Pages）
```

## 它做什么

**记忆分三级**：正史 / 候选 / 拒绝。模型每 5 轮提取最多 3 条候选，必须带原文证据，
且要人工确认才进正史——不会自己越跑越偏。

**两级时间线**：天气、头条这类实时信息只进「情境层」，十分钟过期；
只有被确认的事件才进「正史层」。不是所有发生过的事都该被记住。

**动作协议**：回复不止文字。模型在封闭素材库里选表情，也可以要求这条用语音发，
网关解析成动作列表，各通道自己渲染。

**世界事件走 MCP**：自带一个 stdio MCP server（时间 / 天气 / 头条），
网关当客户端连它，结果按 TTL 缓存后注入系统提示。

## 跑起来

不用 Docker，不用 API Key：

```bash
cd qq-bot-deploy/shenyan-memory
python start-demo.py
```

演示模式下不调用模型，回复是固定话术，但动作解析、情境注入、记忆落库、配额限流都是真的。
接真模型：

```bash
# Windows
set DEEPSEEK_API_KEY=sk-...
python start-demo.py --live

# macOS / Linux
DEEPSEEK_API_KEY=sk-... python start-demo.py --live
```

打开 <http://127.0.0.1:8080>。

## 验证

```bash
python scripts/smoke-test.py              # 8 项端到端检查
python tests/test_multimodal.py           # 动作解析 + MCP 往返 + 端到端
python web-demo/tests/test_isolation.py   # 访客之间互不可见
```

## 技术栈

FastAPI · SQLite · DeepSeek API（OpenAI 兼容）· Docker Compose · MCP（stdio, JSON-RPC 2.0）

单实例跑在 2 GB 云主机上，网关常驻 69.3 MiB，数据一共 212 KB。

## 边界

- 只支持文本输入；表情和语音是**输出**侧的能力，用户发来的图会被丢弃
- 语音只有协议没有 TTS（网页端用浏览器语音合成顶上）
- 检索是字符二元组，不是向量库；两三百条记忆后会撞墙
- 没有多租户，一个实例服务一个角色

案例页在 `docs/`。
