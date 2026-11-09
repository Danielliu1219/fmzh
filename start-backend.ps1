<#
.SYNOPSIS
从零启动本机后端（仅 API），自动准备 Python 环境、依赖和 OCR 模型。
.EXAMPLE
.\start-backend.ps1
.EXAMPLE
.\start-backend.ps1 -Port 8010 -NoWarm
#>
param(
    [ValidateRange(1,65535)][int]$Port = 8000,
    [switch]$NoWarm
)
$ErrorActionPreference='Stop'
$arguments=@{ ApiOnly=$true; Port=$Port }
if($NoWarm){$arguments.NoWarm=$true}
& (Join-Path $PSScriptRoot 'start.ps1') @arguments
exit $LASTEXITCODE
