#!/usr/bin/env python
"""
batch_runner.py — 跑 HTML 表单(web/batch_form.html)生成的 batch config.json

⚠️ 本脚本只跑本 skill (codex-imagegen-fork)。不跨 skill 调度。
   A skill (game-ad-imagegen) 有自己独立的 batch_runner.py + web/。

物理位置:本脚本随 codex-imagegen-fork skill 一起分发,设计师装机后通过
~/.claude/skills/codex-imagegen-fork/scripts/batch_runner.py 调到。

工作流:
  1. 读 config.json(由本 skill 的 web/batch_form.html 生成,config.skill 写死 "b")
  2. 校验 skill 字段必须是 "b"(否则停止 + 提示走 A 的 runner)
  3. 对每个 task: reference_images (0-N) + prompt,跑 n 次,调本 skill 的 scripts/image_gen.py
     - 0 张图 → 子命令 generate (text2im)
     - ≥1 张图 → 子命令 edit
  4. 把每张图的 meta 汇总到 out_dir/_batch_meta.json
  5. 渲染 out_dir/result_grid.html(缩略图网格)

CLI:
  python scripts/batch_runner.py <config.json>
  python scripts/batch_runner.py <config.json> --dry-run

config.json schema:
  {
    "batch_id": "batch_20260513_1430",
    "skill": "b",                 # 必须 "b";其他值 reject
    "out_dir": "...",
    "size": "1536x1024",          # batch 默认
    "quality": "medium",          # batch 默认
    "tasks": [
      {
        "task_id": "t01",
        "reference_images": [".../a.png"],   # 0-N 张(0 = text2im / ≥1 = edit)
        "prompt": "...",            # 中文 prompt(终稿,原样传入,不改)
        "n": 1,
        "size": "1024x1536",      # 可选,覆盖 batch 默认
        "quality": "high"         # 可选,覆盖 batch 默认
      }
    ]
  }

调用形态:
  0 张图: `image_gen.py generate --prompt-file X --out C --size S --quality Q --no-augment --force`
  ≥1 张图: `image_gen.py edit --prompt-file X --image A --image B --out C --size S --quality Q --no-augment --force`
  端点: 自动 generate vs edit
  --no-augment = batch UX 终稿模式,不让 image_gen 给 prompt 加 13-field schema augmentation

通用规则:
- 同一 task 内 n 次共享 size/quality 设置
- prompt 原样传(--no-augment 模式),不假设角色分工
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Windows console 默认 cp936,强制 stdout/stderr 用 UTF-8(Bash 工具按 UTF-8 解码)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except (AttributeError, Exception):
    pass

# ============================================================
# Skill 定位 — 本 skill 自包含,不跨 skill 找 sibling
# ============================================================
SCRIPTS_DIR = Path(__file__).resolve().parent             # .../codex-imagegen-fork/scripts/
THIS_SKILL_ID = "b"                                        # 本 runner 只接 skill=b 的 config
IMAGE_GEN_PY = SCRIPTS_DIR / "image_gen.py"


def build_cmd(prompt_file: Path, refs: list[Path],
              out_path: Path, size: str, quality: str) -> list[str]:
    """构造 B 的 image_gen.py CLI。子命令 generate (0 imgs) 或 edit (≥1 imgs)。"""
    subcmd = "edit" if len(refs) > 0 else "generate"
    cmd = [
        sys.executable, "-u", str(IMAGE_GEN_PY),
        subcmd,
        "--prompt-file", str(prompt_file),
        "--out", str(out_path),
        "--size", size,
        "--quality", quality,
        "--no-augment",      # 让中文 prompt 原样传(batch UX 终稿模式)
        "--force",           # 覆盖 out path 已存在的文件
    ]
    for r in refs:
        cmd.extend(["--image", str(r)])
    return cmd


def run_one(prompt_file: Path, refs: list[Path],
            out_path: Path, size: str, quality: str) -> dict:
    """跑一张图。**防御设计**: 任何异常都返回 error dict 而不 raise,主循环始终能走到结尾写 _batch_meta.json。

    历史失败模式:多张图跑完后某张 child 偶发返回非 0,但 PNG 实际成功,导致整 batch exit=1。
    修法:returncode != 0 时检查 out_path 是否真生成,若已生成视为 soft success。
    """
    cmd = build_cmd(prompt_file, refs, out_path, size, quality)
    t0 = time.time()
    subcmd_display = cmd[3]
    print(f"  $ image_gen.py {subcmd_display} --out {out_path.name} --size {size} --quality {quality}", flush=True)

    import os as _os
    import traceback as _tb
    env = {**_os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    stdout_lines = []

    try:
        # ⚠️ stderr=STDOUT 防 Windows 4KB pipe buffer 死锁(B 的 image_gen.py 大量走 stderr)。
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, bufsize=1,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
        for line in iter(proc.stdout.readline, ''):
            line = line.rstrip("\r\n")
            stdout_lines.append(line)
            print(f"    | {line}", flush=True)
        proc.wait()
        returncode = proc.returncode
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        return {
            "out_path": str(out_path),
            "http_status": None,
            "elapsed_sec": elapsed,
            "error": f"subprocess 异常: {type(e).__name__}: {e}\n{_tb.format_exc()[-1500:]}",
        }

    elapsed = round(time.time() - t0, 1)

    if returncode != 0:
        # child 非 0 退出。但 child 可能已经写出了 PNG(写完文件后 cleanup 时报错)
        # → 检查 out_path 是否真的成功生成,如果是,视为 soft success
        err_tail = "\n".join(stdout_lines[-20:]) if stdout_lines else f"exit code {returncode}"
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"    ⚠️ child returncode={returncode} 但 PNG 实际成功生成({out_path.stat().st_size // 1024} KB),视为 soft success", flush=True)
            return {
                "out_path": str(out_path),
                "http_status": 200,
                "elapsed_sec": elapsed,
                "size_bytes": out_path.stat().st_size,
                "soft_success": True,
                "child_returncode": returncode,
                "child_warn_tail": err_tail[-1000:],
            }
        return {
            "out_path": str(out_path),
            "http_status": None,
            "elapsed_sec": elapsed,
            "error": err_tail[-2000:],
        }

    # B 不写 meta-out,所以 out_path 存在即视为 OK
    if out_path.exists() and out_path.stat().st_size > 0:
        meta = {"out_path": str(out_path), "http_status": 200, "size_bytes": out_path.stat().st_size}
    else:
        meta = {"out_path": str(out_path), "http_status": None, "error": "out file missing or empty"}
    meta["elapsed_sec"] = elapsed
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", help="config.json (由本 skill 的 batch_form.html 生成)")
    ap.add_argument("--dry-run", action="store_true",
                    help="只做校验 + 打印将执行的命令,不真调 image_gen.py(省 credit)")
    ap.add_argument("--no-rewrite", action="store_true",
                    help="跳过 vision + rewrite step，直接把 config 里的 prompt 字面喂给 image_gen.py。"
                         "向后兼容已自己 rewrite 好英文 prompt 的旧 config。"
                         "也可在 config 里加 \"prompt_already_rewritten\": true 全批跳过，"
                         "或在单个 task 里加同名字段单 task 跳过。")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        # 业务校验失败用 print + return 2,不走 argparse usage 风格(避免被误以为是 CLI 语法错)
        print(f"\n! 配置失败:config 不存在: {cfg_path}", file=sys.stderr)
        return 2
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # 校验 skill 字段必须是本 skill (B) — 业务校验,不走 argparse
    skill = (cfg.get("skill") or "").lower()
    if skill != THIS_SKILL_ID:
        print(
            f"\n! 配置失败:config.skill = {skill!r},本 runner 只跑 skill='b' (codex-imagegen-fork)。\n"
            f"  - 如果你想用 A skill,请用 ~/.claude/skills/game-ad-imagegen/scripts/batch_runner.py\n"
            f"  - 如果是误填,请把 config.skill 改成 'b' 或回 batch_form 重新生成",
            file=sys.stderr,
        )
        return 2

    if not IMAGE_GEN_PY.exists():
        print(f"\n! 配置失败:image_gen.py 不在: {IMAGE_GEN_PY}(本 skill 安装不完整)", file=sys.stderr)
        return 2

    batch_id = cfg["batch_id"]
    # expanduser 让 form 里的 ~/Desktop/... 之类 token 展开成跨 OS 绝对路径
    out_dir = Path(cfg["out_dir"]).expanduser()
    batch_size = cfg.get("size", "1536x1024")
    batch_quality = cfg.get("quality", "medium")
    tasks = cfg["tasks"]

    out_dir.mkdir(parents=True, exist_ok=True)

    # ===== 校验阶段(先把所有问题都列出来,不要跑一半才报错) =====
    errors = []
    for t in tasks:
        tid = t.get("task_id", "?")
        refs = t.get("reference_images") or []
        if not isinstance(refs, list):
            errors.append(f"{tid}: reference_images 必须是 list")
            continue
        # B skill: 任意张数(0 = generate / ≥1 = edit),不 reject 0 图
        for p in refs:
            if not Path(p).exists():
                errors.append(f"{tid}: 参考图不存在 — {p}")
        if not (t.get("prompt") or "").strip():
            errors.append(f"{tid}: prompt 不能空")
        n = int(t.get("n", 1))
        if n < 1 or n > 10:
            errors.append(f"{tid}: n 应在 1-10(实际 {n})")
        # anchor_candidates 范围 + n>=2 配套校验 (mirror A 的 anchor workflow)
        M_anchor = int(t.get("anchor_candidates", 0))
        if M_anchor > 0 and M_anchor < 2:
            errors.append(f"{tid}: anchor_candidates={M_anchor} 无效, 必须 ≥2 才启用 anchor mode (或 0/缺省关闭)")
        if M_anchor > 10:
            errors.append(f"{tid}: anchor_candidates={M_anchor} 超过上限 10 (太多候选浪费 token)")
        if M_anchor >= 2 and n < 2:
            errors.append(f"{tid}: anchor_candidates={M_anchor} (≥2) 但 n={n} (<2); anchor mode 需要 n>=2 才能产 N-1 张 series; 改 n>=2 或删 anchor_candidates")
        # B-specific: anchor 模式需要 ≥1 张 ref (Phase 3 把 picked anchor 作 ref,Phase 1 也要 vision)
        if M_anchor >= 2 and len(refs) == 0:
            errors.append(f"{tid}: anchor_candidates={M_anchor} 需要 ≥1 张参考图 (0 图 text2im 不支持 anchor workflow)")

    if errors:
        print(f"\n! 校验失败 ({len(errors)} 个问题):", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        return 2

    # ===== 跑批 =====
    # Anchor workflow (anchor_candidates >= 2 + n >= 2 + refs ≥ 1 时启用):
    #   Phase 1: 跑 M 张候选 → user 挑 → Phase 3: copied anchor + N-1 series with anchor in refs
    # 单 task 总图数 = M (candidates) + n (1 picked-anchor copy + n-1 generated series)
    def _is_anchor_mode(t):
        M = int(t.get("anchor_candidates", 0))
        n = int(t.get("n", 1))
        refs_ok = isinstance(t.get("reference_images"), list) and len(t["reference_images"]) >= 1
        return M >= 2 and n >= 2 and refs_ok

    def _task_image_count(t):
        n = int(t.get("n", 1))
        if _is_anchor_mode(t):
            return int(t["anchor_candidates"]) + n
        return n

    n_images_total = sum(_task_image_count(t) for t in tasks)
    n_anchor_tasks = sum(1 for t in tasks if _is_anchor_mode(t))
    anchor_summary = f", {n_anchor_tasks} task(s) in anchor mode" if n_anchor_tasks > 0 else ""
    print(f"=== batch {batch_id} [skill=b · codex-imagegen-fork]: {len(tasks)} 任务 × ~ = {n_images_total} 张图{anchor_summary} ===", flush=True)
    print(f"  image_gen.py: {IMAGE_GEN_PY}", flush=True)
    print(f"  out_dir: {out_dir}", flush=True)
    print(f"  defaults: size={batch_size}, quality={batch_quality}", flush=True)
    if args.dry_run:
        print("  [dry-run] 仅校验 + 打印计划,不真调 image_gen.py\n", flush=True)
    else:
        print(flush=True)

    all_results = []
    t_batch_start = time.time()
    img_seq = 0

    # 增量进度: 每张图跑完就写一次 _batch_meta.json + 渲染 result_grid.html
    def _write_incremental_progress(results_so_far, n_total, status="running"):
        partial_meta = {
            "batch_id": batch_id,
            "out_dir": str(out_dir),
            "config": cfg,
            "results": results_so_far,
            "ok_count": sum(1 for r in results_so_far if r.get("http_status") == 200),
            "total": n_total,
            "completed": len(results_so_far),
            "status": status,
            "elapsed_sec": round(time.time() - t_batch_start, 1),
        }
        meta_p = out_dir / "_batch_meta.json"
        try:
            meta_p.write_text(json.dumps(partial_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"  ! 增量写 _batch_meta.json 失败(忽略): {e}", file=sys.stderr, flush=True)
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from render_result_grid import render as _render
            _render(out_dir, partial_meta)
        except Exception as e:
            print(f"  ! 增量渲染 result_grid.html 失败(忽略): {e}", file=sys.stderr, flush=True)
        return partial_meta

    if not args.dry_run:
        _write_incremental_progress([], n_images_total, status="running")
        print(f"  📊 进度页已就绪: {out_dir / 'result_grid.html'}\n", flush=True)

    # Anchor mode 累积:Phase 1 跑完后等 user 挑选,Phase 3 再继续 (mirror A)
    anchor_pending_tasks = []

    for t_idx, task in enumerate(tasks, 1):
        task_id = task["task_id"]
        refs = [Path(p) for p in task["reference_images"]]
        prompt = task["prompt"]
        n = int(task.get("n", 1))
        task_size = task.get("size") or batch_size
        task_quality = task.get("quality") or batch_quality
        is_anchor = _is_anchor_mode(task)
        M = int(task.get("anchor_candidates", 0)) if is_anchor else 0

        # anchor mode 时把 refs 复制到 out_dir,让 anchor_pick.html 用相对路径能 load ref 缩略图
        if is_anchor:
            import shutil as _shutil
            for _ref in refs:
                _ref_dst = out_dir / Path(_ref).name
                if not _ref_dst.exists():
                    try:
                        _shutil.copy(_ref, _ref_dst)
                    except Exception as _e:
                        print(f"  ! [task {task_id}] copy ref {_ref.name} → out_dir 失败(继续): {_e}", file=sys.stderr, flush=True)

        # === Vision + Rewrite (Mode 2 → 跟 Mode 1 对齐的核心能力) ===
        skip_rewrite = (
            args.no_rewrite
            or cfg.get("prompt_already_rewritten")
            or task.get("prompt_already_rewritten")
            or len(refs) == 0
        )

        if is_anchor:
            # ===== Anchor mode Phase 1: 同段 prompt × M 次 sampling 出候选 =====
            if skip_rewrite or args.dry_run:
                cand_prompt = prompt
            else:
                print(f"\n[task {task_id}] (anchor Phase 1) vision + rewrite ({len(refs)} refs, M={M} candidates)...", flush=True)
                try:
                    sys.path.insert(0, str(Path(__file__).parent))
                    from rewrite_prompt import rewrite as _do_rewrite
                    _cand_prompts = _do_rewrite(prompt, refs, n=1, anchor_phase="phase1")
                    cand_prompt = _cand_prompts[0]
                    (out_dir / f"{task_id}_prompt_original.txt").write_text(prompt, encoding="utf-8")
                    print(f"[task {task_id}] Phase 1 rewrite done ({len(cand_prompt)} chars)", flush=True)
                except Exception as e:
                    print(f"! [task {task_id}] Phase 1 rewrite failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                    cand_prompt = prompt

            cand_prompt_file = out_dir / f"{task_id}_anchor_cand_prompt.txt"
            cand_prompt_file.write_text(cand_prompt, encoding="utf-8")

            candidate_paths = []
            for ci in range(1, M + 1):
                img_seq += 1
                cand_out = out_dir / f"{task_id}_anchor_cand_{ci:02d}.png"
                candidate_paths.append(cand_out)

                print(f"\n--- {img_seq}/{n_images_total}  ({task_id} anchor cand {ci}/{M}) ---", flush=True)
                print(f"  refs ({len(refs)}): {[r.name for r in refs]}", flush=True)
                print(f"  prompt: {cand_prompt[:100]}{'...' if len(cand_prompt) > 100 else ''}", flush=True)

                if args.dry_run:
                    res = {"out_path": str(cand_out), "http_status": 200, "elapsed_sec": 0.0, "_dry_run": True}
                else:
                    try:
                        res = run_one(cand_prompt_file, refs, cand_out, task_size, task_quality)
                    except Exception as e:
                        import traceback as _tb2
                        print(f"\n    ! run_one(anchor cand) 异常: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                        res = {"out_path": str(cand_out), "http_status": None, "elapsed_sec": 0.0,
                               "error": f"run_one raised: {type(e).__name__}: {e}\n{_tb2.format_exc()[-1500:]}"}
                res.update({
                    "task_id": task_id, "skill": THIS_SKILL_ID, "task_seq_in_batch": t_idx,
                    "image_seq_in_task": -ci, "is_anchor_candidate": True, "anchor_candidate_idx": ci,
                    "reference_images": [str(r) for r in refs], "prompt": prompt,
                    "size": task_size, "quality": task_quality,
                })
                all_results.append(res)
                if not args.dry_run:
                    _write_incremental_progress(all_results, n_images_total, status="running")

            # Stash 给后面 Phase 2+3 用
            anchor_pending_tasks.append({
                "t_idx": t_idx, "task": task, "refs": refs,
                "candidate_paths": candidate_paths,
                "task_size": task_size, "task_quality": task_quality,
            })
            continue  # 跳过下面的 standard mode logic

        # === Standard mode (沿用 N 段独立 prompt 流程) ===
        if skip_rewrite or args.dry_run:
            rewritten_prompts = [prompt] * n
            if skip_rewrite and not args.dry_run:
                reason = "0 refs" if len(refs) == 0 else "prompt_already_rewritten / --no-rewrite"
                print(f"\n[task {task_id}] skip rewrite ({reason}), reusing original × {n}", flush=True)
        else:
            print(f"\n[task {task_id}] vision + rewrite step ({len(refs)} refs, n={n})...", flush=True)
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from rewrite_prompt import rewrite as _do_rewrite
                rewritten_prompts = _do_rewrite(prompt, refs, n=n)
                # 存原始中文 prompt 作 debug trail
                (out_dir / f"{task_id}_prompt_original.txt").write_text(prompt, encoding="utf-8")
                total_chars = sum(len(p) for p in rewritten_prompts)
                print(f"[task {task_id}] rewrite done ({len(rewritten_prompts)} prompts, {total_chars} chars total)", flush=True)
            except Exception as e:
                print(f"! [task {task_id}] rewrite failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                print(f"  falling back to original prompt × {n} — image quality may suffer", file=sys.stderr, flush=True)
                rewritten_prompts = [prompt] * n

        # 兜底:确保 len == n(rewrite 内部应已保证,这里 belt-and-suspenders)
        while len(rewritten_prompts) < n:
            rewritten_prompts.append(rewritten_prompts[-1])

        for i in range(1, n + 1):
            img_seq += 1
            # 每张图独立 prompt_file(对应这次 sampling 的那段 rewrite,N 段不同主体增加系列多样性)
            prompt_file = out_dir / f"{task_id}_{i:02d}_prompt.txt"
            prompt_file.write_text(rewritten_prompts[i - 1], encoding="utf-8")
            out_path = out_dir / f"{task_id}_{i:02d}.png"
            print(f"\n--- {img_seq}/{n_images_total}  ({task_id} {i}/{n}) ---", flush=True)
            print(f"  refs ({len(refs)}): {[r.name for r in refs] if refs else '(text2im,0 图)'}", flush=True)
            print(f"  size={task_size}, quality={task_quality}", flush=True)
            # 打这张图实际喂给 image_gen 的 prompt(N 段不同时各张不一样,方便用户日志里直观看)
            _this_p = rewritten_prompts[i - 1]
            print(f"  prompt: {_this_p[:100]}{'...' if len(_this_p) > 100 else ''}", flush=True)

            if args.dry_run:
                preview_cmd = build_cmd(prompt_file, refs, out_path, task_size, task_quality)
                print(f"  $ [dry-run] {' '.join(str(c) for c in preview_cmd[:6])}{' ...' if len(preview_cmd) > 6 else ''}", flush=True)
                res = {
                    "out_path": str(out_path),
                    "http_status": 200,
                    "elapsed_sec": 0.0,
                    "_dry_run": True,
                }
            else:
                # 防御:即使 run_one 内部还有 raise(理论上不该)也接住
                try:
                    res = run_one(prompt_file, refs, out_path, task_size, task_quality)
                except Exception as e:
                    import traceback as _tb2
                    print(f"\n    ! run_one 内异常(catch + 继续): {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                    res = {
                        "out_path": str(out_path),
                        "http_status": None,
                        "elapsed_sec": 0.0,
                        "error": f"run_one raised: {type(e).__name__}: {e}\n{_tb2.format_exc()[-1500:]}",
                    }
            res.update({
                "task_id": task_id,
                "skill": THIS_SKILL_ID,
                "task_seq_in_batch": t_idx,
                "image_seq_in_task": i,
                "reference_images": [str(r) for r in refs],
                "prompt": prompt,
                "size": task_size,
                "quality": task_quality,
            })
            all_results.append(res)

            if not args.dry_run:
                _write_incremental_progress(all_results, n_images_total, status="running")

    # ==========================================================
    # === Anchor mode Phase 2: render anchor_pick.html + poll picks JSON ===
    # === Anchor mode Phase 3: 跑 N-1 张 series with anchor 锁风格 ===
    # ==========================================================
    if anchor_pending_tasks and not args.dry_run:
        # 渲染 anchor_pick.html (默认 UI;技术团队可自行替换)
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from render_anchor_pick import render as _render_pick
            pick_html = _render_pick(out_dir, batch_id, anchor_pending_tasks)
            print(f"\n📋 anchor_pick.html ready: {pick_html}", flush=True)
        except Exception as e:
            print(f"! 渲染 anchor_pick.html 失败(继续 poll JSON 文件): {e}", file=sys.stderr, flush=True)

        picks_file = out_dir / f"{batch_id}_anchor_picks.json"
        ready_file = out_dir / f"{batch_id}_anchor_pick_ready.txt"
        ready_msg_lines = [
            f"Phase 1 done at {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Anchor candidates ready for {len(anchor_pending_tasks)} task(s).",
            "",
            f"NEXT: open anchor_pick.html in browser to pick anchor for each task,",
            f"   submit → save the JSON output to: {picks_file}",
            "",
            "OR write JSON manually with this schema:",
            "{",
        ]
        for ap in anchor_pending_tasks:
            tid = ap["task"]["task_id"]
            M_ = int(ap["task"]["anchor_candidates"])
            ready_msg_lines.append(f'  "{tid}": <1..{M_}>,')
        ready_msg_lines.extend(["}", ""])
        ready_file.write_text("\n".join(ready_msg_lines), encoding="utf-8")

        # Poll timeout 防 user 忘记挑选 / 浏览器关
        ANCHOR_POLL_TIMEOUT_SEC = 1800  # 30 min
        ANCHOR_POLL_INTERVAL_SEC = 30

        # 首次写一次 "awaiting_picks" 状态到 _batch_meta.json,让前端立刻看到状态变化
        _write_incremental_progress(all_results, n_images_total, status="awaiting_picks")

        print(f"\n⏸️ Phase 1 done — waiting for anchor picks (timeout {ANCHOR_POLL_TIMEOUT_SEC // 60} min)", flush=True)
        print(f"   1. Open: {out_dir / 'anchor_pick.html'}", flush=True)
        print(f"   2. Pick one anchor per task → save JSON to: {picks_file.name}", flush=True)
        print(f"   batch_runner polls every {ANCHOR_POLL_INTERVAL_SEC}s...\n", flush=True)

        _poll_start = time.time()
        picks = None
        while True:
            _elapsed = round(time.time() - _poll_start, 0)
            if picks_file.exists():
                try:
                    picks = json.loads(picks_file.read_text(encoding="utf-8"))
                    print(f"\n✅ picks received at {int(_elapsed)}s: {picks}", flush=True)
                    break
                except Exception as e:
                    print(f"  ! picks JSON 解析失败 at {int(_elapsed)}s (will retry): {e}", file=sys.stderr, flush=True)
            if _elapsed >= ANCHOR_POLL_TIMEOUT_SEC:
                print(f"\n⏰ Anchor pick TIMEOUT after {int(_elapsed)}s — abort batch (Phase 3 skipped for {len(anchor_pending_tasks)} task(s))",
                      file=sys.stderr, flush=True)
                (out_dir / f"{batch_id}_anchor_pick_TIMEOUT.txt").write_text(
                    f"Timed out at {time.strftime('%Y-%m-%d %H:%M:%S')} after {int(_elapsed)}s waiting for {picks_file.name}",
                    encoding="utf-8",
                )
                picks = None
                break
            print(f"  ⏳ polling for {picks_file.name} ({int(_elapsed)}s elapsed / timeout {ANCHOR_POLL_TIMEOUT_SEC}s, next check in {ANCHOR_POLL_INTERVAL_SEC}s)...", flush=True)
            # 持续更新 _batch_meta.json 让前端看到时间在动
            _write_incremental_progress(all_results, n_images_total, status="awaiting_picks")
            time.sleep(ANCHOR_POLL_INTERVAL_SEC)

        if picks is None:
            anchor_pending_tasks = []  # timeout 跳过 Phase 3

        # Phase 3: 对每个 anchor task 跑 N-1 张 series
        for pending in anchor_pending_tasks:
            task = pending["task"]
            t_idx = pending["t_idx"]
            task_id = task["task_id"]
            refs = pending["refs"]
            candidate_paths = pending["candidate_paths"]
            task_size = pending["task_size"]
            task_quality = pending["task_quality"]
            n = int(task.get("n", 1))
            prompt = task["prompt"]

            # picks JSON 容错 int conversion (string "3" → 3 OK)
            picked_idx_raw = picks.get(task_id)
            try:
                picked_idx = int(picked_idx_raw) if picked_idx_raw is not None else None
            except (ValueError, TypeError):
                picked_idx = None
            if picked_idx is None or picked_idx < 1 or picked_idx > len(candidate_paths):
                print(f"! [task {task_id}] invalid pick {picked_idx_raw!r} (need int 1..{len(candidate_paths)}), skipping Phase 3", file=sys.stderr, flush=True)
                continue

            picked_path = candidate_paths[picked_idx - 1]
            if not picked_path.exists():
                print(f"! [task {task_id}] picked candidate {picked_path} not found", file=sys.stderr, flush=True)
                continue

            # 防御性 check: n_series < 1 时跳过 (理论 _is_anchor_mode 要求 n>=2 不会触发)
            n_series = n - 1
            if n_series < 1:
                print(f"[task {task_id}] Phase 3 skipped (n={n} → n-1={n_series} < 1)", flush=True)
                continue

            # 复制 picked candidate → t0X_01.png
            import shutil as _shutil
            first_out = out_dir / f"{task_id}_01.png"
            _shutil.copy(picked_path, first_out)
            img_seq += 1
            print(f"\n[task {task_id}] Phase 3: picked cand {picked_idx} → {first_out.name}", flush=True)
            all_results.append({
                "out_path": str(first_out), "http_status": 200, "elapsed_sec": 0.0,
                "is_anchor_picked": True, "anchor_candidate_source": picked_idx,
                "task_id": task_id, "skill": THIS_SKILL_ID, "task_seq_in_batch": t_idx,
                "image_seq_in_task": 1, "reference_images": [str(r) for r in refs],
                "prompt": prompt, "size": task_size, "quality": task_quality,
            })
            _write_incremental_progress(all_results, n_images_total, status="running")

            # Phase 3 rewrite + dedup
            new_refs = list(refs)
            if picked_path in new_refs:
                anchor_idx = new_refs.index(picked_path) + 1
            else:
                new_refs.append(picked_path)
                anchor_idx = len(new_refs)
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from rewrite_prompt import rewrite as _do_rewrite
                series_prompts = _do_rewrite(prompt, new_refs, n=n_series, anchor_phase="phase3", anchor_idx=anchor_idx)
                total_chars = sum(len(p) for p in series_prompts)
                print(f"[task {task_id}] Phase 3 rewrite done ({len(series_prompts)} prompts, {total_chars} chars, anchor-locked)", flush=True)
            except Exception as e:
                print(f"! [task {task_id}] Phase 3 rewrite failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                series_prompts = [prompt] * n_series

            while len(series_prompts) < n_series:
                series_prompts.append(series_prompts[-1])

            for i in range(2, n + 1):
                img_seq += 1
                prompt_for_this = series_prompts[i - 2]
                prompt_file = out_dir / f"{task_id}_{i:02d}_prompt.txt"
                prompt_file.write_text(prompt_for_this, encoding="utf-8")
                out_path = out_dir / f"{task_id}_{i:02d}.png"
                print(f"\n--- {img_seq}/{n_images_total}  ({task_id} Phase 3 series {i}/{n}) ---", flush=True)
                print(f"  refs ({len(new_refs)}): {[r.name for r in new_refs]}", flush=True)
                print(f"  prompt: {prompt_for_this[:100]}{'...' if len(prompt_for_this) > 100 else ''}", flush=True)

                try:
                    res = run_one(prompt_file, new_refs, out_path, task_size, task_quality)
                except Exception as e:
                    import traceback as _tb2
                    print(f"\n    ! run_one(Phase 3 series) 异常: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                    res = {"out_path": str(out_path), "http_status": None, "elapsed_sec": 0.0,
                           "error": f"run_one raised: {type(e).__name__}: {e}\n{_tb2.format_exc()[-1500:]}"}
                res.update({
                    "task_id": task_id, "skill": THIS_SKILL_ID, "task_seq_in_batch": t_idx,
                    "image_seq_in_task": i, "is_anchor_series": True, "anchor_image_used": str(picked_path),
                    "reference_images": [str(r) for r in new_refs], "prompt": prompt,
                    "size": task_size, "quality": task_quality,
                })
                all_results.append(res)
                _write_incremental_progress(all_results, n_images_total, status="running")

    batch_meta = {
        "batch_id": batch_id,
        "out_dir": str(out_dir),
        "config": cfg,
        "results": all_results,
        "ok_count": sum(1 for r in all_results if r.get("http_status") == 200),
        "total": len(all_results),
        "completed": len(all_results),
        "status": "done",
        "elapsed_sec": round(time.time() - t_batch_start, 1),
    }
    meta_path = out_dir / "_batch_meta.json"
    try:
        meta_path.write_text(json.dumps(batch_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"\n! 写最终 _batch_meta.json 失败: {e}", file=sys.stderr, flush=True)
    print(f"\n=== batch done: {batch_meta['ok_count']}/{batch_meta['total']} OK in {batch_meta['elapsed_sec']}s ===", flush=True)
    print(f"  meta -> {meta_path}", flush=True)

    # 渲染 result_grid.html
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from render_result_grid import render
        grid_path = render(out_dir, batch_meta)
        print(f"  grid -> {grid_path}", flush=True)
    except Exception as e:
        print(f"  ! render_result_grid 失败: {e}", file=sys.stderr, flush=True)

    return 0 if batch_meta["ok_count"] == batch_meta["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
