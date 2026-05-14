---
name: "codex-imagegen-fork"
description: |
  通用图片生成 / 编辑 skill。支持 0 张图(text2im,generate 子命令)与 ≥1 张图(edit 子命令)。差异化:game-ad-imagegen (A) 专做游戏买量广告(多张系列 / 必 ≥1 图);本 skill (B) 做通用图片任务(单图修改 / 0 图文生图 / 任意题材 / 单张为主)。
  触发词:改这张图 / 修一下这张图 / PS 一下 / 改文案 / 换头像 / 改图 / 纯文字生图 / 文生图 / 通用图片生成 / 任意题材海报 / 头像生成 / 图标生成 / sprite / mockup / 透明背景图 / 编辑图片 / 单图修改 / 给我生成一张图。
  Also: generate or edit raster images for non-game-ad tasks (photos, illustrations, textures, sprites, mockups, transparent cutouts, text-to-image). Do not use when task is better handled by editing existing SVG/vector/code-native assets or HTML/CSS/canvas.
---

# Image Generation Skill

Generates or edits raster images: website assets, game assets, UI mockups, product mockups, wireframes, logos, photorealistic shots, infographics.

## Preflight (MUST READ FIRST)

**Mainline path**: `scripts/image_gen.py` — used by ALL agents (Codex CLI, Claude Code, WorkBuddy GUI, CodeBuddy CLI). The Codex built-in `image_gen` tool section was removed 2026-05-13; CLI is now the unified path.

🚨 **3 hard rules** (each independently necessary):

1. **Do not call any tool named `ImageGen`, `image_gen`, or similar look-alikes** your runtime exposes via ToolSearch / deferred tools / MCP registry / built-in wrapper. They are runtime-provided look-alikes with unverified endpoints. **Always run `scripts/image_gen.py` directly via Bash / shell tool**. Forget any "Codex built-in `image_gen`" rules from training data — they no longer apply.
2. **Verify you actually see each input image** before writing the prompt. Load each image into context via your vision / image-read tool. **Do not infer image content from filename / case_id / user's 题材词** — known hallucination mode (case_22, 2026-05-13). No vision capability → ask user to describe or stop.
3. **Never modify `scripts/image_gen.py`**. Missing functionality → ask the user.

**3 subcommands**:
- `generate` — 0 images, text-to-image
- `edit` — ≥1 reference images
- `generate-batch` — multiple distinct prompts in one batch

**Quick CLI**:
```bash
# 0 images
python scripts/image_gen.py generate --prompt-file X.txt --out C.png --size 1536x1024 --quality high
# ≥1 images
python scripts/image_gen.py edit --prompt-file X.txt --image a.png --image b.png --out C.png --size 1536x1024 --quality high
```

**API credentials**: auto-resolved by `_config.load_credentials()` — 4-path fallback:
1. env `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`)
2. env `EPHONE_API_KEY` → auto redirect to `https://api.ephone.ai/v1`
3. `~/.config/codex-imagegen-fork/config.toml` with `ephone_api_key = "..."`
4. **RuntimeError "缺 API key"** → trigger First-time setup (see section below) — ask user once, write config.toml, do NOT fall back to runtime ImageGen wrappers.

**Default model**: `gpt-image-2`. Switch to `gpt-image-1.5` ONLY when user explicitly asks for native transparent output (`background=transparent`) — ASK before switching, since it's a quality downgrade.

**Windows note**: Git Bash `echo $OPENAI_API_KEY` may return empty even when User-scope env is set. Don't trust bash `echo` — let `_config.load_credentials()` resolve credentials itself.

**References**: `references/cli.md` (CLI examples), `references/image-api.md` (API params), `references/prompting.md` (prompting principles), `references/sample-prompts.md` (copy/paste recipes), `references/codex-network.md` (network/sandbox).

---

## Two execution modes

| Mode | When | Agent does |
|---|---|---|
| **Mode 1: Interactive** (Workflow below) | User gives **detailed prompt + (optional) image** in chat | Vision verify + write prompt + call image_gen.py |
| **Mode 2: Form-driven** (Batch UX section) | User only stated **intent**, or wants to batch many images | Silently open form, user fills Chinese request (no need to pre-rewrite), `batch_runner` runs vision+rewrite per task (via `scripts/rewrite_prompt.py`) then calls `image_gen.py` — matches Mode 1 capability |

**Routing precedence** (top-to-bottom, first match wins):
1. User pasted `config.json` / said "跑 batch_<id>" → **Mode 2 trigger execute**
2. User gave **detailed Chinese/English prompt + (optional) image** in chat → **Mode 1** (Workflow)
3. User said only **intent** (e.g. "我要生图" / "做几张图" / "改图" with no specifics) → **Mode 2 open form**

**Anti-bias**: trigger words like "改这张图" / "做一张图" appear in both Mode 1 and Mode 2 frontmatter triggers. The **detailed prompt presence** decides — has concrete content to feed image_gen? → Mode 1. Vague intent only? → Mode 2.

## When to use
- Generate a new image (concept art, product shot, cover, website hero)
- Generate a new image using one or more reference images for style, composition, or mood
- Edit an existing image (inpainting, lighting or weather transformations, background replacement, object removal, compositing, transparent background)
- Produce many assets or variants for one task

## When not to use
- Extending or matching an existing SVG/vector icon set, logo system, or illustration library inside the repo
- Creating simple shapes, diagrams, wireframes, or icons that are better produced directly in SVG, HTML/CSS, or canvas
- Making a small project-local asset edit when the source file already exists in an editable native format
- Any task where the user clearly wants deterministic code-native output instead of a generated bitmap

## Mode 1: Interactive Workflow

When the user gave a detailed prompt (and optionally images) in chat, run these **8 steps**:

### Step 1: Decide subcommand
- **0 images** → `generate` (text-to-image)
- **≥1 image, user wants to modify it preserving parts** → `edit` (most edit cases)
- **≥1 image, user wants new image, image is only style/composition/mood reference** → `generate` (with refs as guidance)
- **Many distinct prompts (different subjects)** → `generate-batch` with JSONL (do NOT use `--n` for distinct assets; `--n` is variants of ONE prompt). **N>1 系列任务时各段必须不同主体角色 / 不同 scene**(系列多样性),不要写 N 段 minor pose variations of same hero(等于 1 张图重复 N 次)。

### Step 2: Vision verify each input image (skip if 0 images)
Load each image into context via your vision tool. Write a verbatim 1-2 sentence description of what you actually see (subject / palette / composition / any visible text). **Do NOT infer from filename / case_id / user's 题材词** — case_22 hallucination mode. No vision capability → ask user to describe or stop.

### Step 3: Label each image role
- `reference image` (style / composition / mood guidance)
- `edit target` (image to be modified)
- `supporting insert` (compositing input)

### Step 4: Collect explicit inputs
- Verbatim quoted text (titles / CTAs / bubbles)
- Constraints list (what MUST keep unchanged, for edits)
- Avoid list (negative constraints)
- Size / quality / model preferences

### Step 5: Apply prompt augmentation per Specificity policy
- Specific & detailed prompt → **normalize only, no extra creative additions**
- Generic prompt → tasteful augmentation only when it materially improves output (see Prompt augmentation section below)
- For edits, **preserve invariants** aggressively and repeat them verbatim: `change ONLY X; keep Y unchanged`

### Step 6: Call `scripts/image_gen.py {generate|edit|generate-batch}`
(Preflight rule 1 applies — direct CLI only.) For transparent output, see "Transparent image requests" section.

### Step 7: Validate output
Check subject / style / composition / text accuracy / invariants. Iterate with a SINGLE targeted change at a time.

### Step 8: Save + report
- Preview-only → keep at saved path, render inline if runtime supports
- Project-bound → save under `output/imagegen/` or user-named path, update consuming code
- Report final saved path(s) + the final prompt(s) back to user

## Rewrite-only mode (skip Step 6, output prompt directly in chat)

If user says "rewrite only / prompt only / 不出图 / 只转写 / 给我 prompt / 先看 prompt" → run Workflow Steps 1-5 (subcommand + vision + label + collect + augment) but **skip Step 6** (the `image_gen.py` call). Output the rewritten prompt directly in chat as a markdown fenced code block so user can copy via chat client's built-in "copy code" button.

**No image-gen credit consumed.** Use cases:
- User wants to inspect the rewritten prompt before deciding whether to spend credit on a batch
- User wants the prompt for another tool (different image API, notes, manual iteration)
- Debugging / human-in-the-loop: user edits the prompt then pastes back to `batch_form.html`

**Output format** (type this directly into the chat — no scripts, no browser, no HTML files):

````markdown
转写好了。以下是 rewritten prompt(对话框「复制」按钮一键复制):

```text
<full rewritten prompt verbatim — no extra prefix / commentary / truncation inside the fence>
```

要真出图,把这段粘到 batch_form 的「中文需求 prompt」框 + 配上参考图。
````

**Invariants**:
- Use ` ```text ` fence (not ` ```json ` / ` ```bash `) so chat clients don't treat it as runnable code.
- Inside the fence, put **only the prompt text**. No `Step 4 output:` prefix, no commentary, no decoration.
- One prompt per fence. If Workflow produced N prompts (multi-image batch), emit N separate fences, each preceded by a `### prompt for image #<i>` heading line.
- **Never truncate**. Don't write `...` or "rest omitted" — output the full prompt every time.

**Trigger phrases** (any → use this mode instead of Step 6):
- "只转写"、"只 rewrite"、"先 rewrite 看看"、"不要出图,给我 prompt"、"prompt 写好发我"
- "rewrite only"、"prompt only"、"just the prompt"、"show me the prompt first"
- "把 prompt 给我"、"prompt 复制给我"

## Transparent image requests

If the user asks for a transparent-background image, use `gpt-image-1.5` (CLI mode supports it natively):

```bash
python scripts/image_gen.py generate \
  --prompt-file <prompt.txt> \
  --model gpt-image-1.5 \
  --background transparent \
  --output-format png \
  --out <final.png>
```

`gpt-image-2` (the default) does **not** support `background=transparent`. Switching to `gpt-image-1.5` is a model downgrade in some quality dimensions but is the only path for native alpha output.

If you need to keep `gpt-image-2` quality but still get a transparent asset, generate on a flat solid chroma-key background (e.g. `#00ff00`) with `gpt-image-2`, then remove the background locally with any chroma-key tool (e.g. Pillow + numpy, or rembg). Prompt template for chroma-key generation:

```text
Create the requested subject on a perfectly flat solid #00ff00 chroma-key background for background removal.
The background must be one uniform color with no shadows, gradients, texture, reflections, floor plane, or lighting variation.
Keep the subject fully separated from the background with crisp edges and generous padding.
Do not use #00ff00 anywhere in the subject.
No cast shadow, no contact shadow, no reflection, no watermark, and no text unless explicitly requested.
```

Ask the user before using `gpt-image-1.5` (model downgrade) when the request is complex: hair, fur, feathers, smoke, glass, liquids, translucent materials, reflective objects, soft shadows, realistic product grounding, or subject colors that conflict with all practical key colors.

## Prompt augmentation

Reformat user prompts into a structured, production-oriented spec. Make the user's goal clearer and more actionable, but do not blindly add detail.

Treat this as prompt-shaping guidance, not a closed schema. Use only the lines that help, and add a short extra labeled line when it materially improves clarity.

### Specificity policy

Use the user's prompt specificity to decide how much augmentation is appropriate:

- If the prompt is already specific and detailed, preserve that specificity and only normalize/structure it.
- If the prompt is generic, you may add tasteful augmentation when it will materially improve the result.

Allowed augmentations:
- composition or framing hints
- polish level or intended-use hints
- practical layout guidance
- reasonable scene concreteness that supports the stated request

Not allowed augmentations:
- extra characters or objects that are not implied by the request
- brand names, slogans, palettes, or narrative beats that are not implied
- arbitrary side-specific placement unless the surrounding layout supports it

## Use-case taxonomy (exact slugs)

Classify each request into one of these buckets and keep the slug consistent across prompts and references.

Generate:
- photorealistic-natural — candid/editorial lifestyle scenes with real texture and natural lighting.
- product-mockup — product/packaging shots, catalog imagery, merch concepts.
- ui-mockup — app/web interface mockups and wireframes; specify the desired fidelity.
- infographic-diagram — diagrams/infographics with structured layout and text.
- scientific-educational — classroom explainers, scientific diagrams, and learning visuals with required labels and accuracy constraints.
- ads-marketing — campaign concepts and ad creatives with audience, brand position, scene, and exact tagline/copy.
- productivity-visual — slide, chart, workflow, and data-heavy business visuals.
- logo-brand — logo/mark exploration, vector-friendly.
- illustration-story — comics, children’s book art, narrative scenes.
- stylized-concept — style-driven concept art, 3D/stylized renders.
- historical-scene — period-accurate/world-knowledge scenes.

Edit:
- text-localization — translate/replace in-image text, preserve layout.
- identity-preserve — try-on, person-in-scene; lock face/body/pose.
- precise-object-edit — remove/replace a specific element (including interior swaps).
- lighting-weather — time-of-day/season/atmosphere changes only.
- background-extraction — transparent background / clean cutout. Default: `gpt-image-2` on a flat chroma-key background + local post-processing (Pillow / rembg / similar). Ask before switching to `gpt-image-1.5 --background transparent` for complex subjects (hair / fur / glass / etc).
- style-transfer — apply reference style while changing subject/scene.
- compositing — multi-image insert/merge with matched lighting/perspective.
- sketch-to-render — drawing/line art to photoreal render.

## Shared prompt schema

Use the following labeled spec as shared prompt scaffolding for both top-level modes:

```text
Use case: <taxonomy slug>
Asset type: <where the asset will be used>
Primary request: <user's main prompt>
Input images: <Image 1: role; Image 2: role> (optional)
Scene/backdrop: <environment>
Subject: <main subject>
Style/medium: <photo/illustration/3D/etc>
Composition/framing: <wide/close/top-down; placement>
Lighting/mood: <lighting + mood>
Color palette: <palette notes>
Materials/textures: <surface details>
Text (verbatim): "<exact text>"
Constraints: <must keep/must avoid>
Avoid: <negative constraints>
```

Notes:
- `Asset type` and `Input images` are prompt scaffolding, not dedicated CLI flags.
- `Scene/backdrop` refers to the visual setting. It is not the same as the fallback CLI `background` parameter, which controls output transparency behavior.
- Execution notes like `Quality:`, `Input fidelity:`, masks, output format, and output paths are CLI parameters (passed to `scripts/image_gen.py`) — they are not prompt scaffolding fields.

Augmentation rules:
- Keep it short.
- Add only the details needed to improve the prompt materially.
- For edits, explicitly list invariants (`change only X; keep Y unchanged`).
- If any critical detail is missing and blocks success, ask a question; otherwise proceed.

## Examples

### Generation example (hero image)
```text
Use case: product-mockup
Asset type: landing page hero
Primary request: a minimal hero image of a ceramic coffee mug
Style/medium: clean product photography
Composition/framing: wide composition with usable negative space for page copy if needed
Lighting/mood: soft studio lighting
Constraints: no logos, no text, no watermark
```

### Edit example (invariants)
```text
Use case: precise-object-edit
Asset type: product photo background replacement
Primary request: replace only the background with a warm sunset gradient
Constraints: change only the background; keep the product and its edges unchanged; no text; no watermark
```

## Prompting best practices
- Structure prompt as scene/backdrop -> subject -> details -> constraints.
- Include intended use (ad, UI mock, infographic) to set the mode and polish level.
- Use camera/composition language for photorealism.
- Only use SVG/vector stand-ins when the user explicitly asked for vector output or a non-image placeholder.
- Quote exact text and specify typography + placement.
- For tricky words, spell them letter-by-letter and require verbatim rendering.
- For multi-image inputs, reference images by index and describe how they should be used.
- For edits, repeat invariants every iteration to reduce drift.
- Iterate with single-change follow-ups.
- If the prompt is generic, add only the extra detail that will materially help.
- If the prompt is already detailed, normalize it instead of expanding it.
- For CLI parameter details (model, `quality`, `input_fidelity`, masks, output format, output paths), see `references/cli.md` and `references/image-api.md`.
- For transparent images, default to `gpt-image-2` + chroma-key + local post-processing; ask before switching to `gpt-image-1.5 --background transparent` for complex subjects.

More principles shared by both modes: `references/prompting.md`.
Copy/paste specs shared by both modes: `references/sample-prompts.md`.

## Guidance by asset type
Asset-type templates (website assets, game assets, wireframes, logo) are consolidated in `references/sample-prompts.md`.

## gpt-image-2 parameters and sizes

`scripts/image_gen.py` defaults to `gpt-image-2`.

- Use `gpt-image-2` for new CLI/API workflows unless the request needs true model-native transparent output.
- For transparent-output requests, ask before switching to `gpt-image-1.5` unless the user already explicitly requested it. Explain that the default path is `gpt-image-2` + chroma-key + local post-processing, but true transparency requires `gpt-image-1.5` (because `gpt-image-2` does not support `background=transparent`).
- `gpt-image-2` always uses high fidelity for image inputs; do not set `input_fidelity` with this model.
- `gpt-image-2` supports `quality` values `low`, `medium`, `high`, and `auto`.
- Use `quality low` for fast drafts, thumbnails, and quick iterations. Use `medium`, `high`, or `auto` for final assets, dense text, diagrams, identity-sensitive edits, or high-resolution outputs.
- Square images are typically fastest to generate. Use `1024x1024` for fast square drafts.
- If the user asks for 4K-style output, use `3840x2160` for landscape or `2160x3840` for portrait.
- `gpt-image-2` size may be `auto` or `WIDTHxHEIGHT` if all constraints hold: max edge `<= 3840px`, both edges multiples of `16px`, long-to-short ratio `<= 3:1`, total pixels between `655,360` and `8,294,400`.

Popular `gpt-image-2` sizes:
- `1024x1024` square
- `1536x1024` landscape
- `1024x1536` portrait
- `2048x2048` 2K square
- `2048x1152` 2K landscape
- `3840x2160` 4K landscape
- `2160x3840` 4K portrait
- `auto`

## CLI mode details

### Temp and output conventions
- Use `tmp/imagegen/` for intermediate files (for example JSONL batches); delete them when done.
- Write final artifacts under `output/imagegen/`.
- Use `--out` or `--out-dir` to control output paths; keep filenames stable and descriptive.

### Dependencies
Prefer `uv` for dependency management in this repo.

Required Python package:
```bash
uv pip install openai
```

Required for local chroma-key removal and optional downscaling:
```bash
uv pip install pillow
```

Portability note:
- If you are using the installed skill outside this repo, install dependencies into that environment with its package manager.
- In uv-managed environments, `uv pip install ...` remains the preferred path.

### Environment
- API credentials must be available for live API calls (resolved automatically by `_config.load_credentials()` — 4-path fallback including env vars and config.toml; see "Non-Codex agent override" section for the resolution order and First-time setup section for asking the user for a key).
- Never ask the user to paste the full key in chat unless you are following the First-time setup flow (which writes the key to `~/.config/codex-imagegen-fork/config.toml`). Confirm "saved" without echoing the key.

If the key is missing, the recommended path is the **First-time setup flow** (see section below) — agent asks user for the key once and writes it to `~/.config/codex-imagegen-fork/config.toml`.

Manual paths (only mention if user explicitly asks):
1. **Ephone / OpenAI 兼容代理 key**: 拿一个 ephone (`https://api.ephone.ai/v1`) 或其他 OpenAI 兼容代理的 key,设到环境变量 `EPHONE_API_KEY`,或写到 `~/.config/codex-imagegen-fork/config.toml` 的 `ephone_api_key` 字段。SDK 会自动 redirect 到代理 base URL。
2. **OpenAI 官方 key**: 直连 OpenAI 时,去 https://platform.openai.com/api-keys 创建 key,设 `OPENAI_API_KEY`,**不要设** `OPENAI_BASE_URL`(让 SDK 走 OpenAI 默认端点)。

If installation is not possible in this environment, tell the user which dependency is missing and how to install it into their active environment.

### Game-ad detour: use A skill instead

For **game ad / 买量素材 / 多张系列爆款复刻**, prefer the sibling skill `game-ad-imagegen` — it has a specialized 6-step vision workflow + T9-style prompt template + Batch UX dedicated to game-ad design. This (B) skill's prompt augmentation (Shared schema, 13-field) targets generic raster tasks (SaaS dashboards / product mockups / scientific diagrams) and produces that aesthetic when applied to game ads.

If you must do game-ad in B (rare, e.g. designer mixed asset types in one batch), use a **T9-style minimal prompt** instead of the 13-field schema: single hero focus, **STRICTLY 4-5 verbatim-quoted Chinese text positions** (2026-05-14 case_01 实证 — >5 text 位画面拥挤、人物精致度被牺牲), explicit `Keep about 70% faithful, 30% creative`, bullet-list main content. Full T9 template + rationale lives in A skill's Step 4 范本 section.

### First-time setup (zero-config recruit path) — 2026-05-13 added

If `scripts/image_gen.py` errors with `RuntimeError: 缺 API key` / `No API key found`, the user has no key configured yet. **You (the agent) MUST do these steps**:

1. **Ask the user once**, in their language (use friendly designer-facing wording, not technical jargon):
   > "我需要你的 ephone API key 才能跑这个 skill。请把 key 贴在对话里(以 `sk-` 开头),我会帮你保存到本机配置文件,以后自动用,不用再问。"
2. **Wait for user reply**. If user pastes something not key-shaped (no `sk-` prefix / too short / empty), ask once more; if still wrong, stop.
3. **Write the config file** using your file write tool (NOT `setx` / NOT system env / NOT `~/.bashrc`):
   - **Path**: `%USERPROFILE%\.config\codex-imagegen-fork\config.toml` (Windows) or `~/.config/codex-imagegen-fork/config.toml` (Unix)
   - **Content**:
     ```toml
     ephone_api_key = "<the key user pasted>"
     ```
   - If user pastes a real OpenAI key (`sk-proj-...` prefix or from platform.openai.com), use `openai_api_key = "..."` instead and omit `openai_base_url` (let SDK use its default).
4. **Do not echo the full key back** to user — confirming "saved" is enough.
5. **Re-run** the same `python scripts/image_gen.py ...` command. `_config.load_credentials()` will pick up the config.toml automatically. **No WorkBuddy restart needed.**

### Script-mode notes
- CLI commands + examples: `references/cli.md`
- API parameter quick reference: `references/image-api.md`
- Network approvals / sandbox settings for CLI mode: `references/codex-network.md`

## Mode 2: Batch UX (HTML 表单触发模式) — added 2026-05-13

本 skill **自包含**一套批量 HTML 表单 + runner,供设计师跑多任务时用。**本表单专属本 skill,生成的 config.json 写死 `skill: "b"`,runner 也只跑本 skill。** A skill (`game-ad-imagegen`) 有自己独立的一套 web/ + batch_runner.py,本 skill 不知道也不调度它。

~~这条路径绕开 "Workflow / Decision tree / Prompt augmentation" 等流程~~ → **2026-05-14 已对齐(commit `7a659f2` + `f499d7c`)**: `batch_runner` 自带 vision + rewrite step(调 `scripts/rewrite_prompt.py`)跟 Mode 1 capability 对齐。用户在表单里写中文需求即可,**不需要预先 rewrite**;agent 仍只做执行器(开 form / 喂 config / 报告进度),LM rewrite 由 runner subprocess 自动跑。

**关键文件位置**(都在本 skill 内,跟 SKILL.md 同根):

| 文件 | 用途 | 装机后绝对路径 |
|---|---|---|
| `web/batch_form.html` | 表单 UI(skill='b' 写死,支持 0-N 图) | `~/.claude/skills/codex-imagegen-fork/web/batch_form.html` |
| `web/batch_form.js` | 表单逻辑 | `~/.claude/skills/codex-imagegen-fork/web/batch_form.js` |
| `web/style.css` | 表单 + grid 样式 | `~/.claude/skills/codex-imagegen-fork/web/style.css` |
| `web/grid_template.html` | 结果 grid 模板 | `~/.claude/skills/codex-imagegen-fork/web/grid_template.html` |
| `scripts/batch_runner.py` | runner 主程序(只跑 skill='b') | `~/.claude/skills/codex-imagegen-fork/scripts/batch_runner.py` |
| `scripts/launch_detached.py` | **进程脱离 launcher**(必走) | `~/.claude/skills/codex-imagegen-fork/scripts/launch_detached.py` |
| `scripts/render_result_grid.py` | grid HTML 生成 | `~/.claude/skills/codex-imagegen-fork/scripts/render_result_grid.py` |

runner 内用 `Path(__file__).resolve().parent` anchor 自动定位本 skill 的 `image_gen.py`(sibling),**不跨 skill 查 A**。

### 入口 — agent 自动开 form(零负担,**任何想用本 skill 出图的请求**都唤起)

#### 何时唤起 form

**user 在对话区说以下任意一种,agent 都唤起 form**(不管 n=1 单图还是 n=N 批量):

🚨 **路由优先级**(对齐顶部"Two execution modes"):

**Mode 1 优先**: 用户**已在对话区给详细 prompt + (可选)图**(详细 = 有具体可喂给 image model 的中文/英文字面) → 走 Mode 1 Workflow,**不**唤起 form。即使话术命中下方表,只要 prompt 已详细给出,Mode 1 优先。

**Mode 2 触发**: 用户**只说意图、没给详细 prompt**,或**明确说要 form / batch** 时唤起:

| 用户话术 | agent 行为 |
|---|---|
| "我要批量出图" / "打开批量表单" / "开始跑批" / "跑 batch" | **唤起 form** (明确 form/batch) |
| "我要生图" / "出图" / "改图"(**没给 prompt 也没给图**) | **唤起 form** (无 prompt → self-serve) |
| "做一张图" / "做几张图"(**只说意图**) | **唤起 form** |
| "用 B skill 出图" / "用 codex-imagegen-fork 跑" | **唤起 form** |
| "做个海报 X,主题 Y,style Z"(**给了详细 prompt**) | **走 Mode 1**,不唤起 form |
| "改这张图(附图),把 X 改成 Y,其他不动"(**给了详细 prompt + 图**) | **走 Mode 1**,不唤起 form |

> form 顶部 n 字段默认 = 1,user 想批量改 n 即可。**form 既是单图也是批量入口,既支持 0 图 text2im 也支持 ≥1 图 edit。**
> **决策**:用户话里有可直接喂给 image model 的 prompt 字面?有 → Mode 1;没有(只有意图) → Mode 2。

**agent 不要让 user 自己开 terminal / 自己点 URL**。下面按优先级试:

> 🚨 **绝对不要二次确认 — 看到触发词直接执行,不要问"用 B skill 表单可以吗"/"默认浏览器打开可以吗"/"我先帮你做 X,确认一下"。**
> SKILL.md 是**指令**不是**建议**,user 已经说了"我要做图"就是授权。多问一句 = UX 噪音,设计师会嫌烦。
> ❌ 错误示例:`我给你开表单跑批。你确认以下两点:1. 用 B skill 表单 2. 默认浏览器打开。回我一句:开`
> ✅ 正确示例:(静默 Bash 跑 http.server + webbrowser.open)→ 对话区报 `✅ 已打开 B skill 出图表单 → http://localhost:8766/web/batch_form.html`

#### 步骤 1:起 http server + 打开 form(3 tier 按优先级)

```bash
# 1.0 起 http server(跨 OS 通用,Python 自带)。用 Bash run_in_background=true。
#     如果 8766 已被占用(server 已 reuse)→ OSError errno 10048 / Address in use,直接跳 1.1
python -m http.server 8766 --directory ~/.claude/skills/codex-imagegen-fork
```

> **端口约定**:A skill 用 8765,B skill 用 8766。两个端口独立,设计师可以同时开 A 和 B 两个 form 并排比对。

**默认路径 — Python webbrowser 调系统默认浏览器**(跨 Windows/macOS/Linux 通用):

```bash
python -c "import webbrowser; webbrowser.open('http://localhost:8766/web/batch_form.html')"
```

> ⚠️ **不要尝试 WorkBuddy 自带 preview**:已知 bug(复制粘贴失效 / "生成跑批指令" 按钮 click 不响应,见 reference_workbuddy_preview_bug),用了反而卡。
> ⚠️ **不要先尝试 host preview tool**:WorkBuddy preview 不可信,Claude Code 的 preview 没 bug 但需要特定环境配置 — **直接走系统浏览器最稳**。

**fallback**(系统浏览器失败时,如 host 无 GUI):

直接对话区发可点 markdown 链接让 user 自己点:`[http://localhost:8766/web/batch_form.html](http://localhost:8766/web/batch_form.html)`

#### 步骤 2:对话区通知 user + 等触发

agent 发一条简短消息:

> ✅ 已打开 B skill 出图表单(在 preview 面板 / 浏览器中)→ http://localhost:8766/web/batch_form.html
> B skill 特点:**支持纯文字生图(图字段留空)+ 参考图编辑(填 1-N 张图)**。
> 配好后,回这里说 **「跑 batch_<时间戳>」** 或把 `config.json` 整段粘到对话区。
> 单图就把 n 填 1(默认),批量改大。

**然后等 user**。不要主动 ping / 不要重复发消息。

#### 触发模式

| 用户在对话区说 / 做 | agent 行为 |
|---|---|
| 说 `跑 batch_<id>` 且 `config.skill == "b"` | **触发 A**(下方) |
| 拖入 config.json 文件 且 skill 字段是 b | **触发 B**(下方) |

⚠️ 如果 `config.skill != "b"`,runner 自己会 reject 并提示用户走 A 的 runner,**本段不处理也不主动跨调度**。

### 触发 A — 用户给 batch_id

1. config 路径:**首选**用户给的绝对路径,或粘贴 JSON 时落到 `~/Downloads/<batch_id>.json`
2. 检查 `config.skill == "b"`;不是则提示用户走 A 的 runner,本段不接
3. **关键 — 跑批前立即唤起 result_grid 进度页给 user**:
   - runner 一启动就在 `<out_dir>/result_grid.html` 写 "running" 状态的进度页(空 grid,每 5s auto-refresh)
   - agent **不要等批跑完才开**,先用 launch_detached 起 runner(<1s 返回),**马上**唤起 `<out_dir>/result_grid.html` 给 user 看(user 每 5s 自动刷新,看到一张张图依次出现 + 进度条)
   - Tier 1: `python -c "import webbrowser; webbrowser.open(...)"` / Tier 2: 对话区发路径。**不要走 WorkBuddy preview**(有 bug)
4. **跑 runner — 必须走 launch_detached.py(不要直接调 batch_runner.py)**:

   ```bash
   python ~/.claude/skills/codex-imagegen-fork/scripts/launch_detached.py \
          ~/.claude/skills/codex-imagegen-fork/scripts/batch_runner.py \
          <config_path>
   ```

   - launcher foreground 跑、<1s 返回,stdout 输出 `detached_pid=X` + `method=DETACHED+BREAKAWAY` + `log=Y`
   - **为什么必须 detach**:WorkBuddy 等 host 在 ~2 min 后会杀 agent 子进程,直接调 batch_runner 出 1-2 张就停。detach 让 batch_runner 跳出 host 进程树(2026-05-14 实测验证)。
   - **不要用 `run_in_background=true`** — launcher 已经 detach,Bash foreground 即可
   - **agent 不需要 BashOutput 监控** — batch_runner 输出全进 `<out_dir>/<config>_detached_launcher.log`
5. **跑完判定** — user 自己看 result_grid 的 status badge(🟦 → 🟩 / 🟥)。agent **不主动 poll**;user 后续问"跑完了吗"时再 `tail _batch_meta.json` 拿 status 答。

### 触发 B — 用户粘贴 JSON 或拖文件

1. 解析 JSON 拿到 `batch_id`,落到 `~/Downloads/<batch_id>.json`(浏览器下载默认位置)
2. 之后等同触发 A 步骤 2-6

### CLI 调用形态(batch_runner 自动构造,不用 agent 手写)

- **0 张图** (text2im 纯文字生图): `python image_gen.py generate --prompt-file X --out C --size S --quality Q --no-augment --force`
- **≥1 张图** (edit): `python image_gen.py edit --prompt-file X --image A --image B --out C --size S --quality Q --no-augment --force`

`--no-augment` = 不让 image_gen 自己再加 13 字段 schema augmentation。**注**: 2026-05-14 之后 `batch_runner` 已在 image_gen 前跑了 vision + rewrite step,rewrite 输出的英文 prompt 已通过 system prompt 教 LLM 遵守 quality 规则;再在 image_gen 前 augment 一次会双重灌指令、稀释 prompt budget,故 batch UX 仍传 `--no-augment`(由 rewrite layer 接管 augmentation 职责)。

### B skill 在 Batch UX 模式下的特点

- **支持 0 图纯文字生图**(`generate` 子命令)。"生成第一人称视角的古代战场..."这种纯描述请求 work。
- 子命令 `generate` / `edit` 自动二选一,由 `reference_images` 数量决定。
- 1-N 张图都走 `edit`,顺序对应用户 prompt 里"图1/图2/..."。

### Batch UX 模式下 agent 的边界(2026-05-14 重写,跟 scripts/ 对齐)

**✅ batch_runner 自动做的事**(agent 不要重复):

- ✅ Per-task vision + rewrite: `batch_runner` 调 `scripts/rewrite_prompt.py` 对每个 task 跑 vision + LM rewrite,把用户需求转成 N 段(N=task.n)英文 image-gen prompt。**agent 不要自己再 rewrite 一遍 / 不要在 config 里塞预 rewrite 好的英文 prompt**(除非 task 显式标 `prompt_already_rewritten: true`)。0 refs 时跳过 rewrite(text2im,无图可 vision)。
- ✅ N 段不同主体: `rewrite_prompt` 一次产 N 段独立 prompt,N>1 时每段 feature 不同主体(系列多样性)。**agent 不要假设"5 张同 prompt 跑 5 次 sampling"**。
- ✅ No 13-field schema double-augmentation: `batch_runner` 调 `image_gen.py` 时传 `--no-augment`,因为 rewrite layer 已经在 system prompt 里指导 LLM 写好 prompt 字段。

**❌ agent 仍不要做的事**:

- ❌ **不要** 试 ToolSearch / 任何 runtime-provided ImageGen wrapper: batch UX 永远走 `scripts/image_gen.py`,跟 Preflight 段同样原则。
- ❌ **不要** 改 `reference_images` 顺序: 顺序对应用户 prompt 里"图1/图2/图3",照用户排的传给 rewrite_prompt。
- ❌ **不要** 主动给 `config.tasks[].prompt` 加修饰词或英文化: 用户填的中文需求传给 rewrite_prompt,LM 自己 rewrite。
- ❌ **不要** 主动开多个 batch 并发跑同 task: token 翻倍且无质量提升。

### 失败时的 fallback

- 步骤 1 3 tier 全部失败 → 对话区直接发 markdown 可点 URL 让 user 自己点:`[http://localhost:8766/web/batch_form.html](http://localhost:8766/web/batch_form.html)`
- batch_runner.py 校验失败 → 把 `! 校验失败` 清单贴给用户,让他回表单改
- launcher 输出 `DETACHED_NO_BREAKAWAY` 而不是 `DETACHED+BREAKAWAY` → 父 Job 不允许 breakaway,fallback 已生效但 host 可能仍杀,batch 跑到中途停就反映给开发者
- batch 跑到中途停 + result_grid badge 卡 🟦 几分钟没变 → tail `<out_dir>/<config>_detached_launcher.log` 看 batch_runner 是不是 crash
- config.json 解析失败 → 把 JSON 错误位置告诉用户

### 图片迭代修改

`gpt-image-2 /v1/images/edits` 端点支持任意 PNG 当下次 input(包括上次本 skill 跑出的图)。三种典型迭代:

- **局部修改**:把 `<out_dir>/tNN_M.png` 当新 task 的 `reference_images`,prompt 写"改头/改文字/改气泡保其他"
- **系列化**:用满意的某张当 anchor,n=3 配同 prompt 跑系列变体
- **B 独有链路**:先 0 图 text2im 出一张 → 再把它当 reference + 加新 prompt edit(A 不支持 0 图所以这条只能 B 跑)

当前需要用户手贴路径,form 没"加载已有 batch"按钮(可日后升级)。

## Reference map
- `references/prompting.md`: shared prompting principles.
- `references/sample-prompts.md`: shared copy/paste prompt recipes.
- `references/cli.md`: CLI usage examples via `scripts/image_gen.py`.
- `references/image-api.md`: API / CLI parameter reference.
- `references/codex-network.md`: network / sandbox troubleshooting.
- `scripts/image_gen.py`: the mainline CLI implementation. **Never modify** — ask the user if something is missing.
