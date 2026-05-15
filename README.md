# codex-imagegen-fork

Claude Code / WorkBuddy / 任意 agent 框架的图片生成 skill。**通用图片任务**:单图修改 / 纯文字生图 / 任意题材海报 / 头像 / 图标 / sprite / mockup / 透明背景 / 插画 / 产品照 / logo / 真实摄影 / infographic。

游戏买量广告(爆款复刻 + 多张系列 + 锁风格 anchor + 纯文字买量素材)请用兄弟 skill [`game-ad-imagegen`](https://github.com/nbssdlkm/game-ad-imagegen)(A 路径)。两个 skill 完全独立,可分别安装。

> **本 skill 起源**:fork 自 [OpenAI Codex CLI 自带的 imagegen skill](https://github.com/openai/codex)(`codex-rs/skills/src/assets/samples/imagegen/`,commit `fca81ee`,Apache License 2.0,见 [LICENSE.txt](LICENSE.txt))。已经 generic 化改造:删除 Codex built-in tool 相关段、加 First-time setup(零负担 key 配置)、加 Batch UX(HTML 表单 + 增量进度页)、加 vision verify 强制(防 hallucination)。

## v0.1.3 主要改动

- 🚨 **Hard Invariant — Prompt Provenance**:进入 image API 的每一个 prompt 必须来自 `scripts/rewrite_prompt.py`(产出时加 SENTINEL marker `# REWRITTEN-V1`)。`scripts/image_gen.py` 入口 `_augment_prompt_fields` 双闸校验:SENTINEL marker + CJK 字符占比兜底(>10% 拒)。三子命令 (`generate` / `edit` / `generate-batch`) 全部走同一闸
- 🔧 删除所有 bypass:`--no-rewrite` CLI flag / `prompt_already_rewritten` config 字段 / 0 图 hardcoded `skip_rewrite` / rewrite 失败 silent fallback。失败现在整批 fail-fast
- 🔧 Rewrite 模型升 `gpt-5.5` → `gpt-5.4` + `reasoning_effort="high"`(模型不支持时自动 fallback 重试)
- 📄 SKILL.md 顶部加 Hard Invariant — Prompt Provenance 段;Mode 1 Step 5 改为 `invoke rewrite_prompt.py` 而非 hand-craft prompt

## 快速安装

### Windows (PowerShell)

```powershell
git clone <repo-url> D:\codex-imagegen-fork
cd D:\codex-imagegen-fork
.\install.ps1
```

### macOS / Linux

```bash
git clone <repo-url> ~/codex-imagegen-fork
cd ~/codex-imagegen-fork
./install.sh
```

`install` 脚本会在 `~/.claude/skills/codex-imagegen-fork/` 和 `~/.workbuddy/skills/codex-imagegen-fork/` 建 junction(Windows)/ symlink(Unix)→ 当前目录。

## 首次使用

装完后,在 WorkBuddy / Claude Code 对话区直接说:

> "我要改这张图" / "PS 一下这张图" / "纯文字生图" / "做个海报/头像/图标" / "我要生图(用 codex-imagegen-fork)"

agent 自动起 HTML 表单 + 引导 user 填图(可留空,0 图 = text2im)/ prompt + 跑批 + 显示进度页。

**首次会要 API key**:agent 问你贴 ephone(或其他 OpenAI 兼容代理)的 API key,自动写到 `~/.config/codex-imagegen-fork/config.toml`,以后不再问。

## 文件结构

```
codex-imagegen-fork/
├── SKILL.md              ← 主体: 18 步通用 workflow + Batch UX 段
├── README.md             ← 本文件
├── LICENSE.txt           ← Apache License 2.0 (from upstream OpenAI Codex)
├── install.ps1           ← Windows 安装
├── install.sh            ← Unix 安装
├── scripts/
│   ├── image_gen.py      ← 出图(generate/edit 子命令)
│   ├── _config.py        ← key 加载 3 路 fallback
│   ├── batch_runner.py   ← 跑批
│   ├── render_result_grid.py
│   └── remove_chroma_key.py  ← 透明背景工具(B 独有)
├── web/                  ← HTML 表单
│   ├── batch_form.html (0-N 图都支持)
│   ├── batch_form.js
│   ├── style.css
│   └── grid_template.html
├── fixtures/             ← 最小反例 JSON
├── references/           ← 详细参考(CLI/API/prompting/samples)
├── agents/               ← (OpenAI 原版保留)
└── assets/               ← (OpenAI 原版保留)
```

## 跟 A skill 的差异化

| | A: game-ad-imagegen | B: codex-imagegen-fork(本 skill) |
|---|---|---|
| 定位 | 游戏买量广告特化(爆款复刻 + 多张系列 + 锁风格 anchor + 纯文字 banner) | 通用图片任务(任意题材 / 单图修改 / 文生图 / 产品照 / logo / infographic) |
| 0 图 text2im | ✅ v0.1.3 起支持(game-ad 特化 system prompt) | ✅ `generate` 子命令(generic taxonomy) |
| Anchor mode 锁风格 | ✅ Phase 1/2/3 form UI(系列广告画风一致) | ❌ 后端代码 mirror 有但前端无入口(主场景单图无需) |
| Rewrite system prompt | game-ad 特化(CandidatePool + T9 横版骨架 + 4-5 中文 text 位硬约束) | generic taxonomy(11+8 use-case slug:photorealistic-natural / product-mockup / ui-mockup / infographic / logo-brand 等) |
| 端点 | 自动选: 0 图 `generations` / ≥1 图 `edits`(v0.1.3 起) | 自动选: `generate` / `edit` / `generate-batch` 子命令 |
| 装哪个 | 主要做**游戏广告**(含 0 图买量素材) | 主要做**非游戏题材通用图**(产品照 / logo / 写实 / infographic) |

通常**都装上**,agent 根据用户话术自动路由。

## 依赖

- **Python 3.10+** —— 唯一要你手装的(`install.ps1` 会自动 `pip install --user openai`,设计师不用懂 pip)
- **OpenAI 兼容 API key**(ephone / OpenAI 官方 / 任意代理) —— 首次跑时 agent 会问你贴一次,写到 `~/.config/codex-imagegen-fork/config.toml`,以后不再问
- `Pillow`(可选,用 `remove_chroma_key.py` 时需要;不用 chroma-key 功能可以不装)
