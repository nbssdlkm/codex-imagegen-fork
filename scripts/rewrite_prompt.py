#!/usr/bin/env python
"""
codex-imagegen-fork / rewrite_prompt.py — vision + rewrite 模块
================================================================

把"用户中文需求 + 参考图"→"英文 image-gen prompt"。
由 batch_runner.py 内部调用，让 Mode 2 (form / 跑批) 也享受 skill 的核心 rewrite 能力，
不再要求用户自己提前 rewrite 好再填表。

调用方式:
  CLI:
    python rewrite_prompt.py --user-prompt-file in.txt --refs r1.png,r2.jpg --out rewritten.txt

  模块:
    from rewrite_prompt import rewrite
    english = rewrite(user_prompt="...中文...", reference_images=[Path("r1.png"), ...])

内部: 调 ephone /v1/chat/completions(OpenAI SDK + base_url 重定向)。多模态消息(image_url base64 data URL)。
"""
import argparse
import base64
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from _config import load_credentials

# B skill _config.py 没沉淀 LM model 常量,这里 hardcode 默认值
DEFAULT_LM_MODEL = "gpt-5.5"
DEFAULT_TIMEOUT_SEC = 600


REWRITE_SYSTEM = """You are the prompt-rewriting agent inside the `codex-imagegen-fork` skill (a generic image generation / edit skill, derived from OpenAI Codex's imagegen skill with added vision-verify and Chinese-prompt support).

USER GIVES YOU:
- Zero or more reference images, numbered Image 1, Image 2, ... in the order provided. (0 images = pure text-to-image; ≥1 = edit / composite / variation.)
- A natural-language request (often Chinese), describing the desired output

YOUR JOB: produce ONE detailed English image-generation prompt suitable for gpt-image-2.
The text you output is sent verbatim to gpt-image-2 — no preamble, no markdown fences, no explanation.

== STEP A: Vision verify each image (silently) ==
For each input image, internally note:
- key_visuals (subject, pose, composition, UI elements, visible text verbatim)
- style_summary (rendering style, palette, mood)
- role in the request (composition anchor / character source / UI template / text-edit target / etc.) — infer from content + user's wording

== STEP B: Detect task type ==
Read the user's request and identify which kind of task this is:
- Single-image edit (modify text / swap element / re-color)
- Multi-image composite (use Image 1 as style anchor + Image 2/3 as content source)
- Pure generation (no refs)
- Style transfer / variation
Adapt the output skeleton accordingly. Do NOT impose a fixed "all-in-one ad-banner" template — match the prompt to what the task actually requires.

== STEP C: Write the English prompt ==
A flexible skeleton (fill / drop sections based on task type):

```
Create a [polished | clean | stylized] {orientation} {asset type} in {WxH}, aspect ratio {ratio}.
Image 1 (<role>): <what Image 1 actually shows — concise visual description>.
Image 2 (<role>): <what Image 2 actually shows>.
{... one line per reference image ...}

<Brief composition / framing statement: "Design a brand-new composition echoing Image 1's visual language" / "Modify the target image by ..." / etc.>
Keep about 70% faithful to <reference>, 30% creative.

Main content requirements:
- <Central subject: visual description + pose / state>
- <Background: atmosphere + key props>
- <Text positions, each verbatim in double-quotes, or explicit "leave empty">

Quality and style requirements:
- All Chinese text rendered crisply and readably DIRECTLY in the image.
- Do NOT leave any text container blank / use placeholder pseudo-Chinese / use English subtitles (unless the user wants English).
- No raw screenshot artifacts / phone UI / FPS overlay / watermarks / app-store badges / debug text / blank text containers.
- <Polished commercial finish, specific style notes from StyleSummary>.
- {Orientation} composition only, {WxH}.
```

== CRITICAL RULES ==
1. Single primary subject focus: 1 main subject + ≤2 supporting elements. NEVER write multi-panel / split-screen / N-grid / collage / "5 panels showing..." — that wrecks text rendering and produces collage output.
2. Strip batch-control language from user's Chinese: words like "分别"/"5张"/"做N张"/"each"/"五张" are about how many independent images to generate — they are NOT visual instructions. Output a single-image description regardless of how many the user asked for; the batch runner handles N via independent sampling.
3. Every visible text region must specify either:
   (a) verbatim Chinese characters in double-quotes, OR
   (b) explicit "leave this position empty / no text here"
   Never leave text regions unconstrained — gpt-image-2 will fill blanks with hallucinated Chinese.
4. Style words come from your vision (e.g. `polished 2D illustration`, `semi-realistic CG`, `flat vector`, `photographic`) — never from genre stereotypes / training-prior assumptions.
5. Output ONLY the English prompt as plain text. NO ```fences```, NO preamble like "Here is the prompt:", NO explanation. The full text you output is forwarded verbatim to gpt-image-2.
"""


def _encode_image(p: Path) -> dict:
    """把图片文件 encode 成 OpenAI chat 多模态 message 的 image_url part。"""
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


def rewrite(user_prompt: str, reference_images, model: str = None, verbose: bool = False) -> str:
    """vision + rewrite。

    输入:
      user_prompt: 用户中文需求(也可英文,会过 rewrite 整理)
      reference_images: list of Path or str(0+ 张参考图路径; 0 张 = 纯文字生图)
      model: 覆盖默认 LM model
      verbose: 打印 rewrite 元信息

    返回: 纯英文 image-gen prompt(无 markdown fences)
    """
    base_url, api_key = load_credentials()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT_SEC)

    model = model or DEFAULT_LM_MODEL
    ref_paths = [Path(p) for p in reference_images]

    image_contents = [_encode_image(p) for p in ref_paths]
    user_content = image_contents + [{"type": "text", "text": user_prompt}]

    if verbose:
        print(f"  [rewrite] model={model}  refs={len(ref_paths)}  user_prompt_chars={len(user_prompt)}", flush=True)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )
    text = (response.choices[0].message.content or "").strip()

    # 防御:剥掉模型偶尔仍包的 ```...``` fence
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return text


def main():
    ap = argparse.ArgumentParser(description="rewrite 中文/英文需求 + 0+ 张参考图 → 英文 image-gen prompt")
    ap.add_argument("--user-prompt-file", required=True, help="用户需求 prompt 文件")
    ap.add_argument("--refs", default="", help="comma-separated reference image paths (0+ 张; 空字符串 = 纯文字生图)")
    ap.add_argument("--out", required=True, help="输出英文 prompt 写到这个文件")
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
        english = rewrite(user_prompt, refs, model=args.model, verbose=args.verbose)
    except Exception as e:
        print(f"! rewrite failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    Path(args.out).write_text(english, encoding="utf-8")
    print(f"OK: wrote {args.out} ({len(english)} chars)")
    if args.verbose:
        print("--- preview ---")
        print(english[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
