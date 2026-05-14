# codex-imagegen-fork

Claude Code / WorkBuddy / 任意 agent 框架的图片生成 skill。**通用图片任务**:单图修改 / 纯文字生图 / 任意题材海报 / 头像 / 图标 / sprite / mockup / 透明背景 / 插画。

游戏买量广告特化任务(爆款复刻 + 多张系列)请用兄弟 skill [`game-ad-imagegen`](https://github.com/nbssdlkm/game-ad-imagegen)(A 路径)。两个 skill 完全独立,可分别安装。

> **本 skill 起源**:fork 自 [OpenAI Codex CLI 自带的 imagegen skill](https://github.com/openai/codex)(`codex-rs/skills/src/assets/samples/imagegen/`,commit `fca81ee`,Apache License 2.0,见 [LICENSE.txt](LICENSE.txt))。已经 generic 化改造:删除 Codex built-in tool 相关段、加 First-time setup(零负担 key 配置)、加 Batch UX(HTML 表单 + 增量进度页)、加 vision verify 强制(防 hallucination)。

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

| | A: game-ad-imagegen | B: codex-imagegen-fork (本 skill) |
|---|---|---|
| 定位 | 游戏买量广告特化 | 通用图片任务 |
| 0 图 text2im | ❌ reject | ✅ `generate` 子命令 |
| 工作流 | 6 步 vision/拆解/选角 | 18 步通用 workflow |
| 端点 | `/v1/images/edits` 写死 | `generate` / `edit` 自动选 |
| 装哪个 | 主要做游戏广告 | 通用 / 单图修改 / 文生图 |

通常**都装上**,agent 根据用户话术自动路由。

## 依赖

- Python 3.10+
- `openai` SDK(`pip install openai`)
- 一个 OpenAI 兼容 API key(ephone / OpenAI 官方 / 其他代理皆可)
- `Pillow`(可选,用 `remove_chroma_key.py` 时需要)
