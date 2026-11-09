param(
    [switch]$Check,
    [switch]$PrepareOnly,
    [switch]$Setup,
    [switch]$ApiOnly,
    [switch]$NoWarm,
    [ValidateRange(1,65535)][int]$Port = 8000
)
$ErrorActionPreference='Stop'
$repoRoot=$PSScriptRoot
$pythonPath=Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
$frontendPath=Join-Path $repoRoot 'frontend'
function Assert-PythonVersion($Executable){
    & $Executable -c 'import sys; sys.exit(0 if (3,12) <= sys.version_info < (3,14) else 1)'
    if($LASTEXITCODE -ne 0){throw '公式OCR依赖需要Python 3.12或3.13，请使用兼容版本建立backend/.venv'}
}
if($Check){
    if(-not(Test-Path -LiteralPath $pythonPath)){throw '先运行 .\start.ps1 -PrepareOnly 安装依赖和构建'}
    & $pythonPath (Join-Path $repoRoot 'backend/tools/prepare_ocr.py') --check --warm
    if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
    if($ApiOnly){
        & $pythonPath (Join-Path $repoRoot 'backend/run.py') --check --api-only
    }else{
        & $pythonPath (Join-Path $repoRoot 'backend/run.py') --check
    }
    exit $LASTEXITCODE
}
if(-not(Test-Path -LiteralPath $pythonPath)){
    $pythonCommand=Get-Command python -ErrorAction Stop
    Assert-PythonVersion $pythonCommand.Source
    & $pythonCommand.Source -m venv (Join-Path $repoRoot 'backend/.venv')
    if($LASTEXITCODE -ne 0){throw '创建Python虚拟环境失败'}
}
Assert-PythonVersion $pythonPath
& $pythonPath -m pip install -r (Join-Path $repoRoot 'backend/requirements.lock.txt')
if($LASTEXITCODE -ne 0){throw '后端依赖安装失败，请修复后重试'}
& $pythonPath -m pip check
if($LASTEXITCODE -ne 0){throw '后端依赖冲突，请运行 .\start.ps1 -Setup'}
# 只校验/补齐模型文件；后端启动时在自身进程内预热，避免重复加载。
& $pythonPath (Join-Path $repoRoot 'backend/tools/prepare_ocr.py')
if($LASTEXITCODE -ne 0){throw '本机公式OCR模型尚未准备完成，请按上方提示检查下载连接后重试'}
if(-not $ApiOnly){
    $npmCommand=Get-Command npm.cmd -ErrorAction Stop
    $nodeVersion=(& node --version).TrimStart('v')
    if([version]$nodeVersion -lt [version]'22.12.0'){throw '前端需要Node.js 22.12或更高版本'}
    Push-Location -LiteralPath $frontendPath
    try{
        $lockHash=(Get-FileHash -LiteralPath 'package-lock.json' -Algorithm SHA256).Hash
        $installedHash=if(Test-Path -LiteralPath 'node_modules/.fmzh-lock-sha256'){(Get-Content -LiteralPath 'node_modules/.fmzh-lock-sha256' -Raw).Trim()}else{''}
        if($Setup -or $installedHash -ne $lockHash -or -not(Test-Path -LiteralPath 'node_modules/vite/bin/vite.js')){
            & $npmCommand.Source ci --no-audit --no-fund
            if($LASTEXITCODE -ne 0){throw '前端依赖安装失败，请修复后重试'}
            Set-Content -LiteralPath 'node_modules/.fmzh-lock-sha256' -Value $lockHash
        }
        & $npmCommand.Source run build:app
        if($LASTEXITCODE -ne 0){throw '完整应用前端构建失败'}
    }finally{Pop-Location}
}
if($ApiOnly){
    & $pythonPath (Join-Path $repoRoot 'backend/run.py') --check --api-only
}else{
    & $pythonPath (Join-Path $repoRoot 'backend/run.py') --check
}
if($LASTEXITCODE -ne 0){throw '运行检查失败；未启动服务，原数据和.env不变'}
if($PrepareOnly){exit 0}
$runArguments=@('--port',"$Port")
if($ApiOnly){$runArguments=@('--api-only','--port',"$Port")}
if($NoWarm){$runArguments+='--no-warm'}
if($ApiOnly){
    Write-Host "后端已启动：http://127.0.0.1:$Port/docs；Ctrl+C停止，数据保留。"
}else{
    Write-Host "打开 http://127.0.0.1:$Port 使用完整应用；Ctrl+C停止，数据保留。"
}
& $pythonPath (Join-Path $repoRoot 'backend/run.py') @runArguments
exit $LASTEXITCODE
