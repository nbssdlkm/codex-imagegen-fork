# install.ps1 — Windows 一键安装 codex-imagegen-fork skill
$ErrorActionPreference = 'Stop'
$SkillName = 'codex-imagegen-fork'
$SkillDir = (Get-Location).Path

Write-Host "==> Installing $SkillName" -ForegroundColor Cyan
Write-Host "    Skill source = $SkillDir"

$ClaudeSkills = Join-Path $env:USERPROFILE ".claude\skills"
if (-not (Test-Path $ClaudeSkills)) {
  New-Item -ItemType Directory -Path $ClaudeSkills -Force | Out-Null
}
$ClaudeTarget = Join-Path $ClaudeSkills $SkillName
if (Test-Path $ClaudeTarget) {
  $item = Get-Item $ClaudeTarget -Force
  if ($item.LinkType -eq 'Junction') {
    Write-Host "    [skip] $ClaudeTarget already a junction → $($item.Target)" -ForegroundColor Yellow
  } else {
    Write-Host "    ! $ClaudeTarget exists but not a junction. Rename then re-run." -ForegroundColor Red
    exit 1
  }
} else {
  New-Item -ItemType Junction -Path $ClaudeTarget -Target $SkillDir | Out-Null
  Write-Host "    Created junction $ClaudeTarget → $SkillDir" -ForegroundColor Green
}

$WbSkills = Join-Path $env:USERPROFILE ".workbuddy\skills"
if (Test-Path $WbSkills) {
  $WbTarget = Join-Path $WbSkills $SkillName
  if (Test-Path $WbTarget) {
    $item = Get-Item $WbTarget -Force
    if ($item.LinkType -eq 'Junction') {
      Write-Host "    [skip] $WbTarget already a junction → $($item.Target)" -ForegroundColor Yellow
    } else {
      Write-Host "    ! $WbTarget exists but not a junction. Skip." -ForegroundColor Yellow
    }
  } else {
    New-Item -ItemType Junction -Path $WbTarget -Target $SkillDir | Out-Null
    Write-Host "    Created junction $WbTarget → $SkillDir" -ForegroundColor Green
  }
} else {
  Write-Host "    [skip] No WorkBuddy install detected"
}

Write-Host ""
Write-Host "==> Verifying dependencies" -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "    ! Python not found. Install Python 3.10+" -ForegroundColor Red
  exit 1
}
Write-Host "    Python: $(python --version 2>&1)"
$openai = python -c "import openai; print(openai.__version__)" 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "    openai SDK missing — installing now (pip install --user openai)..." -ForegroundColor Yellow
  python -m pip install --user --quiet openai
  if ($LASTEXITCODE -ne 0) {
    Write-Host "    ! pip install failed. Run manually:" -ForegroundColor Red
    Write-Host "      python -m pip install --user openai"
    exit 1
  }
  $openai = python -c "import openai; print(openai.__version__)" 2>&1
  Write-Host "    openai SDK installed: $openai" -ForegroundColor Green
} else {
  Write-Host "    openai SDK: $openai"
}

$CfgPath = Join-Path $env:USERPROFILE ".config\$SkillName\config.toml"
Write-Host ""
Write-Host "==> Config status" -ForegroundColor Cyan
if (Test-Path $CfgPath) {
  Write-Host "    config.toml exists ($CfgPath)" -ForegroundColor Green
} else {
  Write-Host "    config.toml NOT set — agent will ask on first run"
}

Write-Host ""
Write-Host "==> Done!" -ForegroundColor Green
Write-Host "    1. Restart WorkBuddy if it was running"
Write-Host "    2. Say in chat: '我要改这张图' / '纯文字生图' / '做个海报'"
