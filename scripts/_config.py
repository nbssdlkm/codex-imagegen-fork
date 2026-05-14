"""
codex-imagegen-fork skill - 配置层(2026-05-13 加,setup wizard 实施)
============================================================

API 凭据加载。本地不存 secret(skill 在 git 共享仓里)。

优先级:
  0. 环境变量 OPENAI_API_KEY + OPENAI_BASE_URL(标准 OpenAI SDK 兼容路径)
  1. 环境变量 EPHONE_API_KEY + EPHONE_BASE_URL(自动 redirect 到 ephone)
  2. ~/.config/codex-imagegen-fork/config.toml(agent setup wizard 写的)
  3. 报错(agent 应按 SKILL.md First-time setup 段处理)
"""
import os
import sys
from pathlib import Path

DEFAULT_BASE_URL = "https://api.ephone.ai/v1"   # ephone OpenAI 兼容代理,gpt-image-2 / gpt-5.x 池


def _normalize_base_url(url: str) -> str:
    """规范化 base URL — 确保以 /v1 结尾(EPHONE_BASE_URL 可能不带)。"""
    url = (url or "").rstrip('/')
    if not url:
        return DEFAULT_BASE_URL
    if not url.endswith('/v1'):
        url = url + '/v1'
    return url


def load_credentials():
    """返回 (base_url, api_key)。失败抛 RuntimeError。base_url 已规范化。

    优先级见模块 docstring。
    """
    # 路 0:OPENAI_API_KEY env(标准 OpenAI SDK 兼容路径)
    if os.environ.get("OPENAI_API_KEY"):
        base_url = (
            os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("EPHONE_BASE_URL")
            or DEFAULT_BASE_URL
        )
        return _normalize_base_url(base_url), os.environ["OPENAI_API_KEY"]

    # 路 1:EPHONE_API_KEY env(自动 redirect 到 ephone)
    if os.environ.get("EPHONE_API_KEY"):
        base_url = (
            os.environ.get("EPHONE_BASE_URL")
            or DEFAULT_BASE_URL
        )
        return _normalize_base_url(base_url), os.environ["EPHONE_API_KEY"]

    # 路 2:本地 config.toml(agent setup wizard 写的)
    toml_path = Path.home() / ".config" / "codex-imagegen-fork" / "config.toml"
    if toml_path.exists():
        try:
            import tomllib
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            api_key = data.get("ephone_api_key") or data.get("openai_api_key")
            base_url = data.get("base_url") or data.get("openai_base_url") or DEFAULT_BASE_URL
            if api_key:
                return _normalize_base_url(base_url), api_key
        except Exception as e:
            print(f"  [warn] 读取 {toml_path} 失败: {e}", file=sys.stderr)

    # 路 3:都没有 → 报错(agent 应触发 SKILL.md First-time setup)
    raise RuntimeError(
        "缺 API key。任选一种方式配置:\n"
        "  (A) 设系统环境变量 OPENAI_API_KEY(若走 ephone 同时设 OPENAI_BASE_URL=https://api.ephone.ai/v1)\n"
        "  (B) 设系统环境变量 EPHONE_API_KEY\n"
        "  (C) 写入 ~/.config/codex-imagegen-fork/config.toml:\n"
        '      ephone_api_key = "sk-..."\n'
        "Agent 行为(SKILL.md First-time setup 段):若 (A)(B)(C) 都未配,主动问 user 一次要 key,然后写到 (C) 那个文件。"
    )
