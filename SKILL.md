---
name: "codex-imagegen-fork"
description: |
  通用图片生成 / 编辑 / 修改 skill。适合**非游戏买量广告特化**的通用图片任务:单图修改 / 纯文字生图 / 任意题材海报 / 头像 / 图标 / sprite / mockup / 透明背景图 / 插画 / 照片合成。
  支持 0 张图(纯文字生图,走 `generate` 子命令)和 ≥1 张图(参考图编辑,走 `edit` 子命令),runner 自动选。
  **跟 `game-ad-imagegen` (A skill) 的差异化**:A 专做游戏买量广告(爆款复刻 / 多张系列 / 6 步 vision 工作流 / 必须 ≥1 张图),B 做通用图片任务(单图修改 / 0 图文生图 / 任意题材 / 单张为主)。设计师如果是"复刻爆款 + 出 N 张系列广告图"走 A;如果是"修这张图 / PS 一下 / 改文案换头像 / 纯文字生一张"走 B。
  触发词:改这张图 / 修一下这张图 / PS 一下 / 改文案 / 换头像 / 改图 / 纯文字生图 / 文生图 / 通用图片生成 / 任意题材海报 / 头像生成 / 图标生成 / sprite / mockup / 透明背景图 / 编辑图片 / 单图修改 / 给我生成一张图。
  Also: generate or edit raster images for non-game-ad visual tasks (photos, illustrations, textures, sprites, mockups, transparent-background cutouts, single-image edits, text-to-image). Do not use when the task is better handled by editing existing SVG/vector/code-native assets, extending an established icon or logo system, or building the visual directly in HTML/CSS/canvas.
---

# Image Generation Skill

Generates or edits images for the current project (for example website assets, game assets, UI mockups, product mockups, wireframes, logo design, photorealistic images, or infographics).

## Preflight rules (MUST READ FIRST)

This skill is the mainline raster image generation/editing path for both Codex CLI and non-Codex agent runtimes (Claude Code Agent / WorkBuddy GUI / CodeBuddy CLI / etc). The Codex CLI built-in `image_gen` tool section was removed from this SKILL.md on 2026-05-13 — `scripts/image_gen.py` is the unified path now.

🚨 **Do not call any tool named `ImageGen`, `image_gen`, or look-alikes** that your runtime exposes via ToolSearch, deferred tool list, MCP registry, or any built-in wrapper. Those are runtime-provided look-alikes with unverified endpoint and quality, **not** under this skill's control. Always run `scripts/image_gen.py` directly via your Bash / shell tool.

🚨 **Forget any "Codex built-in `image_gen` tool" rules** you may have seen in training data, other Codex skill docs, or earlier versions of this file. They no longer apply — there is only the CLI mainline.

🚨 **Verify you actually see each input image** before writing the prompt — load each image into context via whatever vision / image-read tool your runtime provides (e.g. multimodal vision, `view_image` in Codex, similar). **Do not infer image content from file path / filename / case_id / user's題材词** — that is a known hallucination failure mode (2026-05-13 case_22). If you have no vision capability, ask the user to describe the images or stop the skill.

📌 **Quick path** for the common scenarios:

- **Edit** (≥1 reference image): `python scripts/image_gen.py edit --prompt-file X.txt --image a.png --image b.png --out C.png --size 1536x1024 --quality high`
- **Generate** (0 input images, text-to-image): `python scripts/image_gen.py generate --prompt-file X.txt --out C.png --size 1536x1024 --quality high`

API credentials auto-resolved by `_config.load_credentials()` — env `OPENAI_API_KEY` → env `EPHONE_API_KEY` → `~/.config/codex-imagegen-fork/config.toml` → triggers First-time setup if all empty (see "First-time setup" section near end of file).

The rest of this SKILL.md is detailed reference — decision tree / prompt schema / use-case taxonomy / `gpt-image-2` parameters / T9-style game-ad template / Batch UX. Skip to whatever section you need.

---

## Mode

This skill runs `scripts/image_gen.py` as the mainline path for all agents (Codex CLI and non-Codex alike). The Codex CLI built-in `image_gen` tool section was removed 2026-05-13 — that path was unreachable for the non-Codex runtimes which are the推广 target (Claude Code Agent / WorkBuddy GUI / CodeBuddy CLI / etc). For Codex built-in historical docs, see `git log --before 2026-05-13` or the upstream OpenAI Codex skill samples.

Three subcommands:

- `generate` — text-to-image, 0 input images
- `edit` — image editing with 1+ reference image(s)
- `generate-batch` — multiple distinct prompts in one batch job

Mainline rules:

- Always use `scripts/image_gen.py`. API credentials are resolved automatically by `_config.load_credentials()` — 4-path fallback (env `OPENAI_API_KEY` → env `EPHONE_API_KEY` → `~/.config/codex-imagegen-fork/config.toml` → RuntimeError triggering First-time setup; see "Non-Codex agent override" section for the full sequence).
- **Never modify** `scripts/image_gen.py`. If something is missing, ask the user before doing anything else.
- **Do not** call any runtime-discovered `ImageGen` / `image_gen` tool wrapper exposed via ToolSearch / deferred tools / MCP registry. Those are not under this skill's quality control — they may route to unverified endpoints. Always use `scripts/image_gen.py`.
- Use `gpt-image-2` (the default in `scripts/image_gen.py`) unless the user explicitly requests `gpt-image-1.5` for native transparent output. `gpt-image-2` does not support `background=transparent`; if a request needs true transparency, ask before switching.

References (apply to all agents):

- `references/cli.md` — CLI usage examples
- `references/image-api.md` — API parameter reference (sizes, quality, input_fidelity, masks, output format)
- `references/codex-network.md` — network / sandbox notes
- `references/prompting.md` — shared prompting principles
- `references/sample-prompts.md` — copy/paste prompt recipes

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

## Decision tree

Think about two separate questions:

1. **Intent:** is this a new image or an edit of an existing image?
2. **Execution strategy:** is this one asset or many assets/variants?

Intent:
- If the user wants to modify an existing image while preserving parts of it, treat the request as **edit** (`scripts/image_gen.py edit`).
- If the user provides images only as references for style, composition, mood, or subject guidance, treat the request as **generate** (`scripts/image_gen.py generate`).
- If the user provides no images, treat the request as **generate**.

Edit-mode notes:
- Pass the image file paths directly to `--image` flags (multiple `--image` allowed for compositing / multi-reference scenes).
- For edits, preserve invariants aggressively and save non-destructively (use `--out` to control output path, or `--force` to overwrite).
- Use `--mask` when only a specific region should change (see `references/cli.md` for mask format).

Execution strategy:
- Single asset / few variants: one `scripts/image_gen.py generate` or `edit` call per requested image. Use `--n` for variants of one prompt.
- Many distinct prompts (different subjects/scenes): use `scripts/image_gen.py generate-batch` with a JSONL of distinct prompts.
- For many distinct assets, do not use `--n` as a substitute for separate prompts — `--n` is for variants of one prompt; distinct assets need distinct prompts.

Assume the user wants a new image unless they clearly ask to change an existing one.

## Workflow
1. Apply the "Environment detection" gate at the top of this document. All agents (Codex CLI or non-Codex) use `scripts/image_gen.py` as the mainline path.
2. Decide the intent: `generate` or `edit`.
3. Decide whether the output is preview-only or meant to be consumed by the current project.
4. Decide the execution strategy: single CLI call vs `generate-batch` for many distinct prompts.
5. Collect inputs up front: prompt(s), exact text (verbatim), constraints/avoid list, and any input images.
6. For every input image, label its role explicitly:
   - reference image (style / composition / mood guidance)
   - edit target (image to be modified)
   - supporting insert / compositing input
7. 🚨 **Verify you actually see each input image** — before writing the prompt, load each image into your conversation context via whatever vision / image-read tool your runtime provides (e.g. multimodal vision, `view_image` in Codex, similar tools elsewhere). **Do not assume image content from file path / filename / case_id / user's題材词** — that is the known case_22 hallucination failure mode (2026-05-13). If you have no vision capability, ask the user to describe the images or stop the skill.
8. If the user asked for a photo, illustration, sprite, product image, banner, or other explicitly raster-style asset, use this skill. If the request is for an icon, logo, or UI graphic that should match existing repo-native SVG/vector/code assets, prefer editing those directly instead.
9. Augment the prompt based on specificity:
   - If the user's prompt is already specific and detailed, normalize it into a clear spec without adding creative requirements.
   - If the user's prompt is generic, add tasteful augmentation only when it materially improves output quality.
10. Call `scripts/image_gen.py {generate|edit|generate-batch}` per the decisions above. **Do not** call any ToolSearch / deferred-tool / MCP-registry-discovered `ImageGen` / `image_gen` wrapper — those are runtime-provided look-alikes with unverified endpoints.
11. For transparent-output requests, see "Transparent image requests" section below.
12. Inspect outputs and validate: subject, style, composition, text accuracy, and invariants/avoid items.
13. Iterate with a single targeted change, then re-check.
14. For preview-only work, render the image inline if your runtime supports inline rendering; otherwise keep the file at the saved path.
15. For project-bound work, save under `output/imagegen/` or a path the user named, and update any consuming code or references.
16. For batches or multi-asset requests, persist every requested deliverable final in the workspace unless the user explicitly asked to keep outputs preview-only. Discarded variants do not need to be kept unless requested.
17. For CLI-specific controls (model, quality, `input_fidelity`, masks, output format, output paths, network setup) see `references/cli.md` and `references/image-api.md`.
18. Always report the final saved path(s) for any workspace-bound asset(s), plus the final prompt or prompt set.

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

### Game-ad prompt template (T9 style — added 2026-05-12 for Chinese-text-heavy assets)

For game ads / posters / illustrations with **multiple Chinese text positions** (titles, CTAs, speech bubbles, stamps), the default 13-field schema in `references/prompting.md` and `sample-prompts.md` is **not optimal** — those samples target dev-utility scenes (SaaS dashboards, product mockups, scientific diagrams), and produce that aesthetic when applied to game ads.

Use this **T9-style template** for game-ad / illustration-story / commercial-game-asset scenes (cross-validated 2026-05-12 on 3 cases — recipe doc in developer's local workspace, not bundled with skill):

```
Create a polished {orientation} {asset type} in {WxH}, aspect ratio {ratio}.
Use Image A as primary style/UI reference: {describe Image A elements}.
Use Image B/C as character source sheets: {describe character sources}.

Design a brand-new composition echoing Image A's visual language while
adapting to {orientation/ratio}. Keep about 70% faithful to reference, 30% creative.

Main content requirements:
- {Central hero: visual description + pose}
- {Background/scene: atmosphere + props + color palette}
- Large stylized title at top in {style}: "{CHINESE_TITLE}".
- Main promotional banner: "{CHINESE_MAIN_TEXT}".
- {Optional speech bubble near hero}: "{CHINESE_BUBBLE}".
- {Optional small inset/stamp/tag}: "{CHINESE_SIDE}".

Quality and style requirements:
- No raw screenshot artifacts (no phone UI / vConsole / FPS / watermarks).
- Polished commercial-quality finish, {style-specific finish}.
- {Orientation} composition only, {WxH}.
- All Chinese text rendered crisply and readably DIRECTLY in the image.
- Do NOT leave any text container blank.
- Do NOT use placeholder pseudo-Chinese.
- Do NOT use English subtitles (unless explicitly requested).
```

**Key T9-style constraints** (different from default 13-field schema):
1. **Single hero focus** — 1 main subject + ≤2 supporting (inset / sidekick / reaction). Do NOT stack multi-panel multi-scene.
2. **4-7 explicit Chinese text positions** — fewer than 3 looks empty, more than 7 dilutes image-model text precision.
3. **Quote Chinese text verbatim**: write the literal target Chinese characters in double-quotes (e.g. `Large stylized title at top: "群雄之巅"` or whatever the actual title is for this asset) — not an English description like `"the calligraphy title"`. The image model renders the quoted string as-is, character by character, so verbatim Chinese is required.
4. **Explicit "70% faithful 30% creative"** ratio in the prompt body.
5. **Bullet list** for main content (NOT 13-field schema, NOT 草图编号 1)-N) Chinese prose).

**Reference**: the template above is distilled from a 2229-char production English prompt verified 0-typo across 3 cases via `/v1/images/edits` endpoint. No external file lookup needed — the structure here is self-contained.

**Why T9 over 13-field**: cross-case investigation 2026-05-12 found that 13-field schema with inline Chinese verbatim works on `/v1/images/edits` (no L2 rewriter) when the L1 is strong (Claude Opus 4.7 / GPT-5+), but T9 style is more **robust across L1 capability tiers** — fewer text positions, simpler scene complexity, explicit "70/30" ratio all reduce image-model burden, making it the safer template for company推广 to weaker L1 (GLM, Hy3, etc.).

### Non-Codex agent override (added 2026-05-12 for company use)

This section is a backstop reminder for non-Codex agent runtimes (Claude Code Agent, WorkBuddy GUI, CodeBuddy CLI, any third-party agent). The mainline path is `scripts/image_gen.py` for all agents — this section spells out the mandatory rules to prevent fallback to runtime-provided ImageGen wrappers. See also "Preflight rules" at the top of this document.

**Mandatory rules for non-Codex runtimes**:

1. **Do not** call any tool named `ImageGen`, `image_gen`, or similar that your runtime exposes via ToolSearch, deferred tool list, MCP registry, or built-in wrapper. Those are runtime-provided look-alikes, not the Codex built-in this SKILL.md is written for. Their output endpoint and quality are not under this skill's control.
2. **Do** run `scripts/image_gen.py {generate|edit|generate-batch}` per the standard fallback docs above. This is the only path with verified quality (see project recipe lock).
3. **API key resolution is automated since 2026-05-13** — `scripts/image_gen.py` calls `_config.load_credentials()` which tries 4 paths in order:
   - `OPENAI_API_KEY` env (+ optional `OPENAI_BASE_URL`)
   - `EPHONE_API_KEY` env → auto redirect to `https://api.ephone.ai/v1`
   - `~/.config/codex-imagegen-fork/config.toml` with `ephone_api_key = "..."`
   - **RuntimeError** → trigger First-time setup section below

   **You no longer need to manually set env vars** before running the script. Just invoke `python scripts/image_gen.py edit ...` directly.

4. **If the script raises "缺 API key" / "No API key found" error**, do not silently fall back to any runtime ImageGen wrapper. Trigger "First-time setup" section below to ask the user for their key and write the config.toml.
5. **Do not pause to ask the user about mode choice** — non-Codex runtime means CLI is mandatory.
6. **Windows note**: in Git Bash subshells, `echo $OPENAI_API_KEY` may return empty even when the variable is set at User-scope (Git Bash does not inherit Windows User-scope env vars). Do **not** trust bash `echo` results; instead, just let `scripts/image_gen.py` resolve credentials itself (Python `os.environ` reads from the parent process env block correctly).

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

## Batch UX (HTML 表单触发模式) — added 2026-05-13

本 skill **自包含**一套批量 HTML 表单 + runner,供设计师跑多任务时用。**本表单专属本 skill,生成的 config.json 写死 `skill: "b"`,runner 也只跑本 skill。** A skill (`game-ad-imagegen`) 有自己独立的一套 web/ + batch_runner.py,本 skill 不知道也不调度它。

**这条路径绕开"Workflow / Decision tree / Prompt augmentation"等流程**(用户已在表单里手填中文 prompt + 直接给图路径),agent 只做执行器。

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

| 用户话术(中文/英文,意图任意一种) | agent 行为 |
|---|---|
| "我要生图" / "做一张图" / "做几张图" / "出图" | 唤起 form |
| "改这张图" / "修一下这张图" / "PS 一下" / "改文案" / "换头像" | 唤起 form |
| "我要纯文字生图" / "文生图" / "给我生成一张图" | 唤起 form |
| "我要批量出图(用 B)" / "打开 B 的批量表单" | 唤起 form |
| "做个海报 / 头像 / 图标 / sprite / mockup" | 唤起 form |
| "用 B skill 出图" / "用 codex-imagegen-fork 跑" | 唤起 form |

> form 顶部 n 字段默认 = 1(单图模式),user 想批量改 n 即可。**form 既是单图也是批量入口,既支持 0 图 text2im 也支持 ≥1 图 edit。**

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

`--no-augment` = batch UX 终稿模式,不让 image_gen 给 prompt 加 13 字段 schema augmentation(用户在表单里写的就是终稿)。

### B skill 在 Batch UX 模式下的特点

- **支持 0 图纯文字生图**(`generate` 子命令)。"生成第一人称视角的古代战场..."这种纯描述请求 work。
- 子命令 `generate` / `edit` 自动二选一,由 `reference_images` 数量决定。
- 1-N 张图都走 `edit`,顺序对应用户 prompt 里"图1/图2/..."。

### Batch UX 模式下要明确**不做**的事

- ❌ **不要** 走 Workflow / Decision tree / Prompt augmentation:用户已在表单里手填中文 prompt,原样跑就行。
- ❌ **不要** 自己写 13 字段 schema 包装:batch_runner 已加 `--no-augment`。
- ❌ **不要** 试 ToolSearch / 任何 runtime-provided ImageGen wrapper:batch UX 永远走 `scripts/image_gen.py`,跟 Preflight 段同样原则。
- ❌ **不要** 改 reference_images 顺序:顺序对应用户 prompt 里"图1/图2/图3"。
- ❌ **不要** 主动给 prompt 加修饰词或英文化:表单 JSON 里的中文 prompt 原样传入。

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
