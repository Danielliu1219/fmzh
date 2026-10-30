param(
    [switch]$Check,
    [switch]$PrepareOnly,
    [switch]$Setup,
    [ValidateRange(1,65535)][int]$Port = 8000
)
$ErrorActionPreference='Stop'
$repoRoot=$PSScriptRoot
$pythonPath=Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
$frontendPath=Join-Path $repoRoot 'frontend'
if($Check){
    if(-not(Test-Path -LiteralPath $pythonPath)){throw '先运行 .\start.ps1 -PrepareOnly 安装依赖和构建'}
    & $pythonPath (Join-Path $repoRoot 'backend/run.py') --check
    exit $LASTEXITCODE
}
if(-not(Test-Path -LiteralPath $pythonPath)){
    $pythonCommand=Get-Command python -ErrorAction Stop
    & $pythonCommand.Source -m venv (Join-Path $repoRoot 'backend/.venv')
    if($LASTEXITCODE -ne 0){throw '创建Python虚拟环境失败'}
}
& $pythonPath -m pip install -r (Join-Path $repoRoot 'backend/requirements.lock.txt')
if($LASTEXITCODE -ne 0){throw '后端依赖安装失败，请修复后重试'}
& $pythonPath -m pip check
if($LASTEXITCODE -ne 0){throw '后端依赖冲突，请运行 .\start.ps1 -Setup'}
$npmCommand=Get-Command npm.cmd -ErrorAction Stop
Push-Location -LiteralPath $frontendPath
try{
    if($Setup -or -not(Test-Path -LiteralPath 'node_modules/vite/bin/vite.js')){
        & $npmCommand.Source ci --no-audit --no-fund
        if($LASTEXITCODE -ne 0){throw '前端依赖安装失败，请修复后重试'}
    }
    & $npmCommand.Source run build:app
    if($LASTEXITCODE -ne 0){throw '完整应用前端构建失败'}
}finally{Pop-Location}
& $pythonPath (Join-Path $repoRoot 'backend/run.py') --check
if($LASTEXITCODE -ne 0){throw '运行检查失败；未启动服务，原数据和.env不变'}
if($PrepareOnly){exit 0}
Write-Host "打开 http://127.0.0.1:$Port 使用完整应用；Ctrl+C停止，数据保留。"
& $pythonPath (Join-Path $repoRoot 'backend/run.py') --port $Port
exit $LASTEXITCODE
