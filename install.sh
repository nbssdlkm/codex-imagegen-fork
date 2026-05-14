#!/usr/bin/env bash
set -e
SKILL_NAME="codex-imagegen-fork"
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing $SKILL_NAME"
echo "    Skill source = $SKILL_DIR"

CLAUDE_SKILLS="$HOME/.claude/skills"
mkdir -p "$CLAUDE_SKILLS"
CLAUDE_TARGET="$CLAUDE_SKILLS/$SKILL_NAME"
if [ -L "$CLAUDE_TARGET" ]; then
  echo "    [skip] $CLAUDE_TARGET already a symlink"
elif [ -e "$CLAUDE_TARGET" ]; then
  echo "    ! $CLAUDE_TARGET exists but not symlink. Rename then re-run."
  exit 1
else
  ln -s "$SKILL_DIR" "$CLAUDE_TARGET"
  echo "    Created symlink $CLAUDE_TARGET → $SKILL_DIR"
fi

WB_SKILLS="$HOME/.workbuddy/skills"
if [ -d "$WB_SKILLS" ]; then
  WB_TARGET="$WB_SKILLS/$SKILL_NAME"
  if [ -L "$WB_TARGET" ]; then
    echo "    [skip] $WB_TARGET already a symlink"
  elif [ ! -e "$WB_TARGET" ]; then
    ln -s "$SKILL_DIR" "$WB_TARGET"
    echo "    Created symlink $WB_TARGET → $SKILL_DIR"
  fi
else
  echo "    [skip] No WorkBuddy install detected"
fi

echo ""
echo "==> Verifying dependencies"
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "    ! Python not found"; exit 1
fi
echo "    Python: $($PY --version 2>&1)"
if ! $PY -c "import openai" >/dev/null 2>&1; then
  echo "    openai SDK missing — installing now ($PY -m pip install --user openai)..."
  if ! $PY -m pip install --user --quiet openai; then
    echo "    ! pip install failed. Run manually: $PY -m pip install --user openai"
    exit 1
  fi
  echo "    openai SDK installed: $($PY -c 'import openai; print(openai.__version__)')"
else
  echo "    openai SDK: $($PY -c 'import openai; print(openai.__version__)')"
fi

CFG_PATH="$HOME/.config/$SKILL_NAME/config.toml"
echo ""
echo "==> Config status"
[ -f "$CFG_PATH" ] && echo "    config.toml exists" || echo "    config.toml NOT set — agent will ask"

echo ""
echo "==> Done! Restart WorkBuddy, then say in chat: '我要改这张图' / '纯文字生图'"
