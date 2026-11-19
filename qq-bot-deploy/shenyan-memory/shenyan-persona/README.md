# 角色设定

这个目录只放**演示用**的设定，可以公开。

| 文件 | 作用 |
|---|---|
| `demo_character_bible.md` | 演示角色的人物设定（身份、作息、性格、说话方式） |
| `demo_behavior_rules.md` | 演示角色的沟通规则（长度、语气、什么时候发表情） |
| `demo_seed_memories.json` | 演示会话的种子记忆，新建会话时写入 |

网关在 `DEMO_MODE=1` 且是访客会话时读 `demo_*` 这几个文件；
自己的角色设定放在 `character_bible.md` / `behavior_rules.md` / `seed_memories.json`，
**那几个文件不在仓库里**，需要自己写。

想换角色：改这三个 `demo_*` 文件就行，代码不用动。
