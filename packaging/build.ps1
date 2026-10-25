<#
Build Bike Log on Windows in one go: get the newest code, install packages, run the tests, build the
screens, BikeLog.exe and the installer. Stops at the first error and says which step failed.

Run from anywhere (PowerShell):
    powershell -ExecutionPolicy Bypass -File D:\Ablage\Coding\bike_log\packaging\build.ps1

Options:
    -NoPull      build what is in the folder now (no git pull)
    -SkipTests   do not run the backend tests (saves about a minute)
    -Install     run the new installer at the end

Your data (%LOCALAPPDATA%\BikeLog) is never touched by this script.
#>
param(
    [switch]$NoPull,
    [switch]$SkipTests,
    [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Branch = 'claude/project-thread-6y3mmh'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step([string]$Name) { Write-Host ""; Write-Host "==> $Name" -ForegroundColor Cyan }
function Fail([string]$Message) { Write-Host ""; Write-Host "STOPPED: $Message" -ForegroundColor Red; exit 1 }
# Run a program and stop if it fails (PowerShell does not stop on a failing .exe by itself).
function Run([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { Fail "$What failed (exit code $LASTEXITCODE). Scroll up for the reason." }
}

Step "Check that Bike Log is closed"
$running = Get-Process -Name BikeLog -ErrorAction SilentlyContinue
if ($running) {
    Fail "Bike Log is still running. Close its window (or end BikeLog.exe in Task Manager) and run this again."
}

if (-not $NoPull) {
    Step "Get the newest code ($Branch)"
    $changes = git status --porcelain --untracked-files=no
    if ($changes) {
        Fail "These code files were changed in this folder: $changes. Run 'git restore .' to throw the changes away (your Bike Log data is not affected), then run this again."
    }
    Run "git fetch" { git fetch origin $Branch }
    Run "git checkout" { git checkout $Branch }
    Run "git pull" { git pull --ff-only origin $Branch }
}
$Commit = (git rev-parse --short=7 HEAD).Trim()
Write-Host "Building commit $Commit"

Step "Python packages"
if (-not (Test-Path .venv\Scripts\python.exe)) {
    Run "creating .venv" { py -3.13 -m venv .venv }
}
Run "pip install" { .venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements-dev.txt }

if (-not $SkipTests) {
    Step "Backend tests"
    Run "the tests" { .venv\Scripts\python -m pytest -q backend/tests }
}

Step "Screens (frontend)"
Push-Location frontend
try {
    Run "npm ci" { npm ci --no-audit --no-fund }
    Run "npm run build" { npm run build }
} finally {
    Pop-Location
}

Step "BikeLog.exe (PyInstaller)"
Run "PyInstaller" { .venv\Scripts\pyinstaller --noconfirm --clean packaging\bikelog.spec }
$version = (& dist\BikeLog\BikeLog.exe --version).Trim()
Write-Host $version
if ($version -notmatch $Commit) { Fail "The new BikeLog.exe reports '$version', expected commit $Commit." }

Step "Installer (Inno Setup)"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Fail "Inno Setup was not found. Install it once with: winget install JRSoftware.InnoSetup"
}
Run "ISCC" { & $iscc /Q "/DBuildCommit=$Commit" packaging\bikelog.iss }
$setup = Get-ChildItem dist\installer\BikeLog-*-$Commit-setup.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { Fail "The installer for commit $Commit was not created." }

Write-Host ""
Write-Host "DONE: $version" -ForegroundColor Green
Write-Host "Installer: $($setup.FullName)  ($($setup.LastWriteTime))" -ForegroundColor Green
if ($Install) {
    Step "Install"
    Start-Process -FilePath $setup.FullName -Wait
} else {
    Write-Host "Next: run that installer (or start dist\BikeLog\BikeLog.exe directly to try it)."
}
Write-Host "In Bike Log, Settings shows 'app commit $Commit · screens commit $Commit'."
