# 表情素材

`stickers/` 里的 20 张图来自 **Microsoft Fluent Emoji**，采用 **MIT** 许可。

- 项目：https://github.com/microsoft/fluentui-emoji
- 许可：MIT（保留版权声明即可，无强制署名要求）
- 用途：取 3D 风格，缩放到 256×256，改名为 `st_01` … `st_20`

MIT 是最宽松的一档，公开商用也可以，只要留下这段版权说明。

## 重新生成

```bash
python scripts/fetch-fluent-stickers.py      # Microsoft Fluent Emoji（MIT，当前使用的）
python scripts/fetch-twemoji-stickers.py     # Twemoji（CC-BY 4.0，72px，较小）
python scripts/make-stickers.py              # 纯文字卡片（不依赖任何第三方素材）
```

换素材只要覆盖同名 png 并更新 `stickers.json`，代码不用动。

## 清单格式

`stickers.json` 每条包含：

| 字段 | 说明 |
|---|---|
| `id` | 模型输出里用的 id，如 `st_05` |
| `file` | 文件名 |
| `caption` | 给模型看的一句话说明 |
| `tags` | 情绪标签，素材多了以后用来筛候选 |

## 手上没有的素材怎么办

手势类 emoji（👍🙏🤷👌）在 Fluent 仓库里放在 `<名称>/Default/3D/` 下面，
文件名以 `_3d_default.png` 结尾，不是 `_3d.png`。脚本已经处理了这条规则。
