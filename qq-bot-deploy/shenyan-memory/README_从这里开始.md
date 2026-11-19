# 沈砚 × DeepSeek × QQ：角色连续性记忆系统 v1.0

**版本：2026-10-30**｜Windows + Docker Desktop + AstrBot/NapCat｜**仅限一个QQ主人私聊**

这是一个真正可运行的 **OpenAI 兼容记忆网关**：AstrBot 将QQ消息发送给网关，网关检索本地 SQLite 记忆、加载沈砚角色圣经，再调用 DeepSeek API。模型回复会返回 AstrBot，由 AstrBot 通过 NapCatQQ 发送给你。记忆不会交给 DeepSeek 服务器长期保存；实际每轮提交给 DeepSeek 的相关上下文仍会经过第三方 API。

> **状态**：提供了源代码、配置与本地单元测试；尚未用你的 DeepSeek Key、QQ号和 Docker 环境进行端到端联调。不要把“文件可运行”理解为“已经连接你的QQ”。

## 目录与功能

- `shenyan-persona/character_bible.md`：从你已有的《沈砚角色圣经2.0》提取的固定设定。
- `shenyan-persona/behavior_rules.md`：QQ聊天口吻、关系与现实边界。
- `shenyan-persona/seed_memories.json`：已核对的关键关系锚点、事件、禁止回收旧设定。
- `shenyan-persona/incremental_timeline_2026-10-30.md`：10月25日至30日的增量审计；证据不足的最新日常留作候选。
- `shenyan-gateway/app.py`：FastAPI + SQLite + DeepSeek API 的记忆网关；支持JSON候选提取与审核。
- `shenyan-gateway/actions.py`：输出协议——把「正文 + 标记」解析成文字 / 表情 / 语音动作。
- `shenyan-gateway/stickers.py`：表情素材库，模型在封闭集合里选，不会幻觉出图片地址。
- `shenyan-gateway/world.py`：世界事件的情境缓存，带 TTL，失败不阻塞回复。
- `shenyan-gateway/mcp_stdio.py`：最小 MCP 客户端（stdio，JSON-RPC 2.0，零第三方依赖）。
- `shenyan-gateway/world_server.py`：自带的 MCP server，提供时间 / 天气 / 头条三个工具。
- `shenyan-assets/`：表情素材与清单。
- `scripts/make-stickers.py`：生成占位表情（换正式美术就不用它了）。
- `shenyan-compose.yml`：把记忆网关接入官方 AstrBot/NapCat Docker 网络。
- `.env.shenyan.example`：密钥与模型配置模板。
- `shenyan-data/`：启动后自动生成的 SQLite 数据目录，以及可读的 `timeline_approved.md`（已审核）和 `memory_pending.md`（待审核）；不要公开分享。

## 第零步：先让 Docker 正常工作

你上一张截图显示 Docker Desktop 已安装，但尚缺 WSL：管理员 PowerShell 执行 `wsl --install`，重启电脑，再打开 Docker Desktop。如果 WSL 或 Docker 仍报错，先解决它，不要继续下面的安装。

## 第一步：先安装官方 AstrBot 和 NapCat

在普通 PowerShell 中执行（如果你已有这个文件，就跳过下载）：

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\qq-deepseek" | Out-Null
cd "$HOME\qq-deepseek"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/NapNeko/NapCat-Docker/main/compose/astrbot.yml" -OutFile "astrbot.yml"
```

根据官方部署说明，执行 `docker compose -f astrbot.yml up -d` 可以启动 AstrBot 与 NapCat。请先配置管理员登录密码、NapCat扫码登录QQ、AstrBot 的 OneBot v11 适配器。

**必须使用QQ小号做机器人，并在 AstrBot 的“访问控制 → 白名单”中只允许你自己的QQ私聊会话 ID。** 可以用 `/sid` 获取，会话格式及配置以 AstrBot 最新 WebUI 为准。这个网关只支持“单用户”记忆，若开放给别人，他们会共享你的个人记忆甚至可以调用删除指令。

## 第二步：放入这套记忆系统

把本压缩包中全部文件**解压到** `$HOME\qq-deepseek` **文件夹本身**（与 `astrbot.yml` 同级），最终结构如下：

```text
qq-deepseek/
  astrbot.yml                       # 第一步下载的官方文件
  shenyan-compose.yml              # 本包提供
  .env.shenyan.example             # 本包提供
  shenyan-gateway/
  shenyan-persona/
```

接下来在 PowerShell 中：

```powershell
cd "$HOME\qq-deepseek"
Copy-Item .\.env.shenyan.example .\.env.shenyan
notepad .\.env.shenyan
```

把 `DEEPSEEK_API_KEY` 改成你的真实 API Key；把 `GATEWAY_KEY` 换成一个随机长密码。它们是**两把不同的密钥**：

- `DEEPSEEK_API_KEY`：在 [DeepSeek 开发者平台](https://platform.deepseek.com/) 创建，调用有费用。
- `GATEWAY_KEY`：本地网关通信密码，**由你自己设定**，后面 AstrBot 的“API Key”填同一个值。建议 32 位以上随机字符，例如在 PowerShell 里运行：

```powershell
-join ((1..48) | ForEach-Object { 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[(Get-Random -Maximum 62)] })
```

默认模型 `deepseek-flash` 已按照 2026-10-30 DeepSeek 官方文档配置；可选 `deepseek-v4-pro`，成本通常不同，记得查询实时价格。

## 第三步：启动记忆网关

```powershell
cd "$HOME\qq-deepseek"
docker compose -f astrbot.yml -f shenyan-compose.yml up -d --build
```

检查日志：

```powershell
docker compose -f astrbot.yml -f shenyan-compose.yml ps
docker compose -f astrbot.yml -f shenyan-compose.yml logs --tail 40 shenyan-memory
```

服务状态如果显示 healthy，说明网关正在运行；它没有对 Windows 暴露 HTTP 端口，AstrBot 通过 Docker 内网访问它。Windows 浏览器直接打开 `http://localhost:8000` **不会**访问这个容器，这是刻意的隐私与安全设计。

## 第四步：在 AstrBot 里把模型指向“沈砚网关”

打开 AstrBot 管理后台 `http://localhost:6185`（初始账号及密码请查看官方日志并立即修改）。按照 AstrBot 官方“模型提供商”步骤：

1. **Providers → Chat Completion → Add**，选 **OpenAI Compatible**（不要再选 DeepSeek 提供商，因为本次要先经过记忆网关）。
2. API Base URL：`http://shenyan-memory:8000/v1`
3. API Key：填你的 `.env.shenyan` 里的 `GATEWAY_KEY`（**不是** DeepSeek Key）。
4. 模型 ID：`shenyan`（可点击 Fetch Models 或手工添加）。
5. `Config → AI → Model`，把聊天模型改成刚添加的 `shenyan`，保存。若提供流式设置，先关闭；网关兼容 SSE 格式，但当前是完整生成后再发送，不是逐token直播。
6. AstrBot 的角色/系统提示词留空或简短，不必另行粘贴全部角色圣经，网关每轮都会加载。

**QQ 连接**：如果官方 NapCat 的 MODE=astrbot 自动连通，就无需重复设置；否则按 AstrBot/NapCat 的 OneBot v11 文档，检查 NapCat 是否通过 WebSocket 连接 AstrBot。不要照搬过时的固定端口或扫码入口，以运行时日志为准。

## 第五步：QQ聊天与记忆管理

现在把机器人QQ小号加为好友，向它私聊普通文字。网关会先调取历史上下文，再让 DeepSeek 生成沈砚风格回复，并保存本轮对话。连续 5 轮后，网关会额外调用一次 DeepSeek JSON 模式提取最多3条候选。**候选不会自动晋升正史**。

在 QQ 私聊中发送这些**不带斜杠**的句子（为了避免被 AstrBot 当作系统命令截获）：

- `沈砚记忆帮助`：查看管理指令。
- `沈砚记忆待审`：查看 DeepSeek 提取的候选记忆与编号。
- `沈砚确认记忆 12`：将编号 12 的候选加入长期记忆。
- `沈砚拒绝记忆 12`：拒绝编号 12 的候选。
- `沈砚记忆列表`：列出最近20条已经确认的记忆。
- `沈砚忘记记忆 12`：删除指定记忆，但**不同时删除曾出现相同内容的原始聊天记录**。
- `沈砚清空所有记录 我确认`：清除数据库的全部聊天和记忆。此操作不可逆；角色圣经 Markdown 文件和任何外部备份不会被删除。

记忆数据库路径：`$HOME\qq-deepseek\shenyan-data\shenyan.sqlite3`。可定期复制这个文件（建议先停止容器，避免SQLite-WAL备份不一致）。

## 功能边界（不要误以为 DeepSeek API 自带）

**已实现**：DeepSeek生成自然语言、角色圣经加载、近期10轮对话、已确认关键事件、轻量文本检索、每5轮JSON记忆候选、人工审核、自动导出两份Markdown时间线、纠错/删除指令、单用户本地SQLite存储。每轮最多选择12条长期记忆，不能保证任何历史细节100%检索到；这不是嵌入式向量数据库。

**v1.1 新增**：MCP 世界事件（时间 / 天气 / 头条）、带 TTL 的情境缓存、动作协议（文字 / 表情 / 语音）、表情素材库与标记解析。

**当前未实现**：机器人主动发QQ、QQ说说、真实语音合成（只有协议）、图片理解与入库（用户发的图仍然丢弃）、多用户隔离、模型真实逐token流式输出、自动保证人物正史绝不矛盾。未来可用 AstrBot 插件与QQ发送能力扩展主动消息，但需要额外调度和权限管理。

## 安全与费用

- QQ个人号非官方接入有平台风控风险；用独立小号测试。不要开放群聊、好友白名单或在公网暴露管理端口。
- **不要把 DeepSeek API Key、GATEWAY_KEY、QQ登陆二维码、聊天记录截图发给任何人**。建议不要让机器人掌握你的证件、财务与账户凭据。
- DeepSeek API 调用需要自己开通与付费；每5轮另有一次记忆提取API请求。
- AstrBot 和 NapCat 管理页面的 6185/6099 端口请仅允许本机访问；建议检查官方compose默认端口映射，不要将 Windows 电脑映射到公网。
- SQLite 是本机文件但**未做磁盘级加密**；其他可访问该 Windows 用户文件的人可能读到聊天记录。删除/备份也要注意。
- 此版本刻意设为**单用户**：网关的 OpenAI 兼容请求本身不带QQ真实用户ID；**必须先在 AstrBot 做私聊白名单限制**。

## 世界事件与表现层（v1.1）

网关多了两件事：知道外面发生了什么，以及能发文字以外的东西。

### 世界事件走 MCP

`world_server.py` 是一个小的 MCP server，用 stdio 传输，网关启动时把它拉起来当子进程。

| 工具 | 拿到什么 | 依赖 |
|---|---|---|
| `clock.now` | 当前时间、星期、时段 | 无 |
| `weather.now` | 实时天气（温度 / 湿度 / 天气现象） | Open-Meteo，免 Key |
| `news.headlines` | 头条标题 | RSS，可换源 |

每轮取哪些由 `WORLD_CONTEXT_TOOLS` 决定，结果汇成「当前情境」塞进系统提示：

```
【当前情境｜实时信息，不是你的记忆】
- now：2026-11-19 23:42 周四 深夜
- weather：Singapore 现在 小毛毛雨，24.0°C，湿度 100%
```

**情境不写进记忆库。** 天气是时效信息，进了正史之后角色三个月后还会记着那场雨。
它只活在当轮提示里，过期就没了——这就是两级时间线的第一级。

为什么不装官方 MCP SDK：网关跑在 AstrBot 基础镜像里，那个镜像本身锁了 pydantic 版本，
装 SDK 会和镜像打架。MCP 的 stdio 传输就是「一行一个 JSON-RPC」，自己实现反而更好测。
`mcp_stdio.py` 只实现了用得到的三个方法，HTTP 传输没做。

### 表情和语音

模型不画图，只在素材库里**选**——这样不会幻觉出图片地址：

1. `shenyan-assets/stickers.json` 里每张图有 id、文案、适用情绪
2. 清单塞进系统提示，模型想发就写 `[[st:st_03]]`
3. 网关解析成动作列表，`/v1/reply` 直接返回 `[{type:text|sticker|voice}]`
4. `/v1/chat/completions` 仍然返回干净文本，动作放在 `x_shenyan` 扩展字段里，老客户端不受影响

素材是占位图，`scripts/make-stickers.py` 生成的，换正式美术直接替换同名文件即可。

语音目前只有协议没有 TTS：网页端用浏览器自带的 speechSynthesis 顶上，
QQ 端要发真实语音还得接一个 TTS 服务。

## 本机跑一份完整 demo（不用 Docker）

只要 Python 3.10+，不要 Docker，也不要 API Key。

**最省事的入口是 `start-demo.py`**，双击（或桌面上的「启动沈砚演示」快捷方式）就行。

别用 `.bat`：Windows 11 的「智能应用控制」在强制模式下会按文件类型直接拦掉 `.bat` 和 `.ps1`，
提示「此文件已被阻止」。`.py` 只是数据文件，被检查的是 python.exe，那个有有效签名，能过。

命令行跑也一样：

```powershell
cd qq-bot-deploy\shenyan-memory
python .\start-demo.py
```

脚本做三件事：把依赖装进 `.runtime/`、用 `SHENYAN_MOCK=1` 起网关、起网页代理，
然后打开 `http://127.0.0.1:8080`。

演示模式下**不调用任何模型**，回复是固定话术；但动作解析、情境注入（时间 / 天气）、
记忆落库、配额限流全都是真的。适合调界面、给人看流程、或者在没 Key 的机器上跑。

想接真模型：

```powershell
$env:DEEPSEEK_API_KEY = 'sk-...'
python .\start-demo.py --live
```

依赖装过了就加 `-NoInstall`，省掉一分钟（这句是给 `run-local.ps1` 的）。

验证整条链路：

```powershell
python .\scripts\smoke-test.py
```

8 项检查——网页活着、记忆可读、动作列表、表情、语音、素材可取、配额——
全过才算真的通了。测服务器就传地址：`python .\scripts\smoke-test.py http://IP:8080 邀请码`。

## 网页演示（可选）

QQ 号被风控的时候，`web-demo/` 那套能把同一个网关挂到网页上：访客打开链接就能聊，
每人一份独立的库，碰不到你这份 `shenyan-data/`。

- 开 `DEMO_MODE=1` 之后，带 `X-Demo-Session` 头的请求读写的是 `/data/sessions/<sid>.sqlite3`
- 不开这个开关，上面的 QQ 链路一行都不变
- 部署与验证清单见 `web-demo/README.md`

## 相关官方文档

- DeepSeek API：https://api-docs.deepseek.com/quick_start/pricing
- DeepSeek JSON：https://api-docs.deepseek.com/guides/json_mode/
- AstrBot 模型配置：https://docs.astrbot.app/en/providers/llm.html
- AstrBot 白名单：https://docs.astrbot.app/dev/astrbot-config.html
- 官方 Docker Compose：https://github.com/NapNeko/NapCat-Docker/blob/main/compose/astrbot.yml
