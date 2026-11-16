# AFK Notes — установка через терминал:
#   irm https://raw.githubusercontent.com/look-afk/afk-notes/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$dir = Join-Path $env:USERPROFILE ".afk-notes"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$base = "https://raw.githubusercontent.com/look-afk/afk-notes/main"
$dst = Join-Path $dir "afk.py"

Write-Host "Качаю afk.py -> $dst" -ForegroundColor Cyan
Invoke-WebRequest -Uri "$base/afk.py" -OutFile $dst

$py = $null
foreach ($c in @("py", "python")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) {
    Write-Host "Python не найден — установи Python 3 и повтори." -ForegroundColor Red
    exit 1
}

Write-Host "Запускаю настройку..." -ForegroundColor Cyan
& $py $dst --setup
