#!/usr/bin/env python
"""
codex-imagegen-fork / rewrite_prompt.py — vision + rewrite 模块（多段 prompt 版）
=================================================================================

把"用户中文/英文需求 + 参考图"→ N 段独立英文 image-gen prompt（每段对应 1 张图）。
由 batch_runner.py 内部调用让 Mode 2 (form / 跑批) 也享受 skill 的核心 rewrite 能力。

调用方式:
  CLI:
    python rewrite_prompt.py --user-prompt-file in.txt --refs r1.png,r2.jpg --out rewritten.txt --n 5

  模块:
    from rewrite_prompt import rewrite
    prompts = rewrite(user_prompt="...", reference_images=[Path("r1.png"), ...], n=5)

内部: ephone /v1/chat/completions(OpenAI SDK + base_url redirect)，多模态(image_url base64)。
"""
import argparse
import base64
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from _config import load_credentials

DEFAULT_LM_MODEL = "gpt-5.5"
DEFAULT_TIMEOUT_SEC = 600

# n>1 时各段之间的分隔符。LLM 必须在独立行上输出此标记。
PROMPT_SEP = "---PROMPT-SEP---"


REWRITE_SYSTEM = f"""You are the prompt-rewriting agent inside the `codex-imagegen-fork` skill (generic image generation / edit skill).

USER GIVES YOU:
- Zero or more reference images, numbered Image 1, Image 2, ... in the order provided.
  (0 = pure text-to-image; ≥1 = edit / composite / variation.)
- A natural-language request (often Chinese)
- A target count N (how many independent image-gen prompts to produce)

YOUR JOB: produce **N detailed English image-generation prompts**, one per output image.
Each prompt is sent verbatim to gpt-image-2 as a separate API call — they do NOT share state,
so each prompt must be self-contained.

== STEP A: Vision verify each image (silently) ==
For each input image, internally note:
- key_visuals (subject, pose, composition, UI elements, visible text verbatim)
- style_summary (rendering style, palette, mood)
- role in the request (composition anchor / character source / UI template / text-edit target / etc.)

== STEP B: Detect task type ==
- Single-image edit (modify text / swap element / re-color)
- Multi-image composite (Image 1 style anchor + Image 2/3 content source)
- Pure generation (no refs)
- Style transfer / variation
Adapt the skeleton accordingly — do NOT impose a fixed game-ad template.

== STEP C: Build a CandidatePool (if request needs characters) ==
Scan input images for available characters / subjects. When N>1, lean toward **N different primary characters / subjects** for series variety unless the user clearly asks for variations of a single subject.

== STEP D: Write N independent prompts using this flexible skeleton ==

```
Create a [polished | clean | stylized] {{orientation}} {{asset type}} in {{WxH}}, aspect ratio {{ratio}}.
Image 1 (<role>): <concise visual description of what Image 1 shows>.
Image 2 (<role>): <...>.
{{... one line per reference image ...}}

<Composition statement: "Design a brand-new composition echoing Image 1's visual language" / "Modify the target image by ..." / etc.>
Keep about 70% faithful to <reference>, 30% creative.

Main content requirements:
- <Central subject: visual description + pose / state>
- <Background: atmosphere + key props>
- <Text positions, each verbatim in double-quotes, or explicit "leave empty">

Quality and style requirements:
- All Chinese text rendered crisply and readably DIRECTLY in the image.
- Do NOT leave any text container blank / use placeholder pseudo-Chinese / use English subtitles (unless user wants English).
- No raw screenshot artifacts / phone UI / FPS / watermarks / app-store badges / debug text / blank text containers.
- <Polished commercial finish, style notes>.
- {{Orientation}} composition only, {{WxH}}.
```

== CRITICAL RULES ==
1. **Single primary subject per prompt**: 1 main subject + ≤2 supporting elements. NEVER write multi-panel / split-screen / N-grid / collage in a single prompt.
2. **STRICTLY 4-5 Chinese text positions per prompt, NEVER MORE THAN 5**. Fewer = empty-looking; more = dilutes gpt-image-2 text rendering budget. Be aggressive about cutting.
3. **Strip batch-control language from user's Chinese**: words like "分别"/"5张"/"做N张"/"each" tell you how many prompts to make, NOT what to render. Do NOT echo into prompts.
4. **Verbatim Chinese**: every text position must specify (a) exact Chinese in double-quotes, OR (b) "leave this position empty". Never unspecified.
5. **Series variety when N>1**: each prompt features a different primary subject (from CandidatePool) OR clearly different pose / scene. Avoid producing N minor variations of the same subject.
6. **Style words from your vision** (e.g. `polished 2D illustration`, `semi-realistic CG`, `flat vector`, `photographic`) — never genre stereotypes.

== OUTPUT FORMAT ==
- If N == 1: output ONLY the single English prompt as plain text. No preamble, no fences.
- If N >= 2: output N prompts separated by a line containing exactly `{PROMPT_SEP}` (no other chars on that line):

  ```
  Create a polished landscape ... (full prompt 1) ...
  {PROMPT_SEP}
  Create a polished landscape ... (full prompt 2) ...
  ```

NO preamble like "Here are the prompts:", NO ```fences``` around individual prompts, NO numbering ("Prompt 1:"). The separator line is the only structure marker.
"""


def _encode_image(p: Path) -> dict:
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = p.suffix.lower()
    mime = (
        "image/jpeg" if ext in (".jpg", ".jpeg") else
        "image/webp" if ext == ".webp" else
        "image/gif" if ext == ".gif" else
        "image/png"
    )
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def rewrite(user_prompt: str, reference_images, n: int = 1, model: str = None, verbose: bool = False, anchor_phase: str = None, anchor_idx: int = None) -> list:
    """vision + rewrite。返回 list[str] of length n。

    anchor_phase: None (默认) / "phase1" (anchor 候选模式) / "phase3" (anchor 锁风格)
    anchor_idx: phase3 时 caller 指定 refs 列表中哪张是 picked anchor (1-based);
                None 时默认最后一张
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    base_url, api_key = load_credentials()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT_SEC)

    model = model or DEFAULT_LM_MODEL
    ref_paths = [Path(p) for p in reference_images]

    image_contents = [_encode_image(p) for p in ref_paths]

    user_text = user_prompt
    if n > 1:
        user_text += (
            f"\n\n[runner instruction] Produce {n} independent prompts (one per output image), "
            f"separated by `{PROMPT_SEP}` on its own line. Each prompt should feature a DIFFERENT "
            f"primary subject so the {n}-image series gives visual variety. Strip any '分别' / "
            f"'{n} 张' counting words — those tell you how many prompts to make, not what to render."
        )
    else:
        user_text += f"\n\n[runner instruction] Produce 1 prompt (single output image)."

    # Anchor workflow Phase 3: caller 指定 anchor_idx (或默认最后一张) — caller 必须保证该 idx 处是 picked anchor
    if anchor_phase == "phase3" and len(ref_paths) >= 1:
        if anchor_idx is None:
            anchor_idx = len(ref_paths)
        if anchor_idx < 1 or anchor_idx > len(ref_paths):
            raise ValueError(f"anchor_idx={anchor_idx} 超出 refs 范围 1..{len(ref_paths)}")
        user_text += (
            f"\n\n[ANCHOR LOCK MODE — Phase 3] Image {anchor_idx} (out of {len(ref_paths)} ref images) is the "
            f"user-picked **anchor image** from a Phase 1 candidate round. It represents the LOCKED "
            f"visual style for this entire series — rendering technique, color palette, lighting, UI "
            f"layout, typography, composition language. Your {n} prompts MUST visually echo Image "
            f"{anchor_idx}'s style very tightly (**~85% faithful to anchor instead of the usual 70%**) "
            f"— only the primary subject identity / pose / sidekick may vary across prompts. "
            f"All other reference images (not Image {anchor_idx}) provide subject source material as before. "
            f"In each prompt, **explicitly write** at the end: "
            f"`Strictly match Image {anchor_idx}'s rendering style, palette, UI plate styling, and typography.` "
            f"The final output series (picked anchor + {n} new images) should look like one coherent "
            f"set, not {n+1} unrelated images."
        )
    elif anchor_phase == "phase1":
        user_text += (
            f"\n\n[ANCHOR CANDIDATE MODE — Phase 1] This prompt will be used to generate M candidate "
            f"variants (same prompt × M sampling), letting the user pick the best one as anchor for "
            f"a subsequent Phase 3 series. Write a single well-crafted prompt with concrete subject "
            f"choice (don't artificially leave it vague — sampling will provide pose/detail variety)."
        )

    user_content = image_contents + [{"type": "text", "text": user_text}]

    if verbose:
        print(f"  [rewrite] model={model}  refs={len(ref_paths)}  n={n}  user_prompt_chars={len(user_prompt)}", flush=True)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )
    text = _strip_fence(response.choices[0].message.content or "")

    if n == 1:
        return [text]

    raw_parts = [p.strip() for p in text.split(PROMPT_SEP)]
    parts = [_strip_fence(p) for p in raw_parts if p.strip()]

    if len(parts) == 0:
        print(f"  [rewrite] WARN: LLM returned empty output", file=sys.stderr, flush=True)
        return [text] * n

    if len(parts) < n:
        print(f"  [rewrite] WARN: expected {n} prompts, got {len(parts)}; padding with last", file=sys.stderr, flush=True)
        while len(parts) < n:
            parts.append(parts[-1])
    elif len(parts) > n:
        print(f"  [rewrite] WARN: expected {n} prompts, got {len(parts)}; truncating", file=sys.stderr, flush=True)
        parts = parts[:n]

    return parts


def main():
    ap = argparse.ArgumentParser(description="rewrite 中文/英文需求 + 0+ 张参考图 → N 段英文 image-gen prompt")
    ap.add_argument("--user-prompt-file", required=True, help="用户需求 prompt 文件")
    ap.add_argument("--refs", default="", help="comma-separated reference image paths (0+ 张; 空 = 纯文字生图)")
    ap.add_argument("--out", required=True, help="输出文件(N 段用 `---PROMPT-SEP---` 分隔)")
    ap.add_argument("--n", type=int, default=1, help="期望输出几段独立 prompt(默认 1)")
    ap.add_argument("--model", default=None, help=f"override LM model (default: {DEFAULT_LM_MODEL})")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    user_prompt = Path(args.user_prompt_file).read_text(encoding="utf-8")
    refs = [Path(p) for p in args.refs.split(",") if p.strip()] if args.refs else []
    for p in refs:
        if not p.exists():
            print(f"! ref image not found: {p}", file=sys.stderr)
            return 2

    try:
        prompts = rewrite(user_prompt, refs, n=args.n, model=args.model, verbose=args.verbose)
    except Exception as e:
        print(f"! rewrite failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    out_text = (f"\n{PROMPT_SEP}\n").join(prompts) if args.n > 1 else prompts[0]
    Path(args.out).write_text(out_text, encoding="utf-8")
    print(f"OK: wrote {args.out} ({len(out_text)} chars, {len(prompts)} prompts)")
    if args.verbose:
        for i, p in enumerate(prompts, 1):
            print(f"--- prompt {i}/{len(prompts)} (first 200 chars) ---")
            print(p[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
