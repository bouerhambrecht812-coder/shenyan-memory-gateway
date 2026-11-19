<#
  本机跑一份完整 demo：记忆网关 + 网页代理，不用 Docker。

    .\scripts\run-local.ps1              演示模式（不调用模型，不花钱）
    .\scripts\run-local.ps1 -Live        真模型（要先设 DEEPSEEK_API_KEY）
    .\scripts\run-local.ps1 -NoInstall   依赖装过了，跳过安装

  小白直接双击上一级的「启动演示.bat」就行。
#>
param(
  [switch]$Live,
  [switch]$NoInstall,
  [int]$GatewayPort = 8000,
  [int]$WebPort = 8080,
  [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
$root    = Split-Path -Parent $PSScriptRoot
$repo    = Split-Path -Parent (Split-Path -Parent $root)
$gw      = Join-Path $root 'shenyan-gateway'
$web     = Join-Path $repo 'web-demo'
$runtime = Join-Path $root '.runtime'
$data    = Join-Path $root '.local-data'

function Find-Python {
  param([string]$Explicit)

  $candidates = @()
  if ($Explicit) { $candidates += $Explicit }
  if ($env:SHENYAN_PYTHON) { $candidates += $env:SHENYAN_PYTHON }

  # 优先用 DSH 自带的 3.12：依赖都是给它装的，最稳
  $runtimePy = Get-ChildItem "$env:USERPROFILE\.dsh\dsh-runtimes\*\dependencies\python\python.exe" `
      -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($runtimePy) { $candidates += $runtimePy.FullName }

  foreach ($name in @('python', 'py')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
  }
  $candidates += @('C:\Python313\python.exe', 'C:\Python312\python.exe', 'C:\Python311\python.exe')

  foreach ($c in $candidates) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    try {
      $v = & $c -c "import sys; print(sys.version_info[:2] >= (3,10))" 2>$null
      if ("$v".Trim() -eq 'True') { return $c }
    } catch {}
  }
  return $null
}

$python = Find-Python -Explicit $PythonPath
if (-not $python) {
  Write-Host ''
  Write-Host '找不到可用的 Python（需要 3.10 或更新）。' -ForegroundColor Red
  Write-Host '去 python.org 下载安装，安装时勾上 "Add python.exe to PATH"，然后再双击一次。'
  Write-Host ''
  exit 1
}
Write-Host "使用 Python: $python" -ForegroundColor DarkGray

New-Item -ItemType Directory -Force -Path $runtime, $data | Out-Null

# 上一次没关干净：收掉占着端口的旧进程，否则会报「端口被占用」让人一头雾水
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app:app|proxy\.server:app' } |
  ForEach-Object {
    Write-Host "关掉上一次残留的进程 $($_.ProcessId)" -ForegroundColor DarkYellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

if (-not $NoInstall) {
  $marker = Join-Path $runtime '.installed'
  if (-not (Test-Path $marker)) {
    Write-Host ''
    Write-Host '第一次运行，正在装依赖。要几分钟，别关这个窗口。' -ForegroundColor Cyan
    Write-Host ''
    & $python -m pip install --disable-pip-version-check --target $runtime `
        openai tzdata -r (Join-Path $web 'proxy\requirements.txt')
    if ($LASTEXITCODE -ne 0) {
      Write-Host ''
      Write-Host '依赖装失败了。多半是网络问题，关掉窗口再双击一次；还不行把上面的报错发我。' -ForegroundColor Red
      exit 1
    }
    Set-Content $marker 'ok'
    Write-Host ''
    Write-Host '依赖装好了。' -ForegroundColor Green
  }
}

$env:PYTHONPATH            = $runtime + ';' + $env:PYTHONPATH
$env:DATA_DIR              = $data
$env:PERSONA_DIR           = Join-Path $root 'shenyan-persona'
$env:ASSETS_DIR            = Join-Path $root 'shenyan-assets'
$env:GATEWAY_KEY           = 'dev-local-key'
$env:DEMO_MODE             = '1'
$env:DEMO_PASSCODE         = ''
$env:DEMO_EXTRACT_EVERY    = '2'
$env:WORLD_CONTEXT_TOOLS   = 'clock.now,weather.now'
$env:TZ                    = 'Asia/Singapore'
$env:GATEWAY_URL           = "http://127.0.0.1:$GatewayPort"

if ($Live) {
  if (-not $env:DEEPSEEK_API_KEY) {
    Write-Host '开了 -Live 但没有 DEEPSEEK_API_KEY，这次先用演示模式。' -ForegroundColor Yellow
    $env:SHENYAN_MOCK = '1'
  } else {
    Remove-Item Env:\SHENYAN_MOCK -ErrorAction SilentlyContinue
  }
} else {
  $env:SHENYAN_MOCK = '1'
}

$glog = Join-Path $data 'gateway.log'
$wlog = Join-Path $data 'web.log'
$procs = @()

try {
  $mode = if ($env:SHENYAN_MOCK -eq '1') { '演示模式，不调用模型' } else { '真模型' }
  Write-Host "启动网关（$mode）..." -ForegroundColor Cyan
  $procs += Start-Process -FilePath $python `
      -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port',"$GatewayPort",'--workers','1') `
      -WorkingDirectory $gw -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput "$glog.out" -RedirectStandardError "$glog.err"

  $ok = $false
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try {
      $r = Invoke-RestMethod -Uri "http://127.0.0.1:$GatewayPort/healthz" -TimeoutSec 2
      if ($r.ok) { $ok = $true; break }
    } catch {}
  }
  if (-not $ok) {
    Write-Host ''
    Write-Host '网关没起来。下面是错误日志：' -ForegroundColor Red
    if (Test-Path "$glog.err") { Get-Content "$glog.err" -Tail 25 }
    Write-Host ''
    exit 1
  }
  Write-Host '网关 OK' -ForegroundColor Green

  Write-Host '启动网页...' -ForegroundColor Cyan
  $procs += Start-Process -FilePath $python `
      -ArgumentList @('-m','uvicorn','proxy.server:app','--host','127.0.0.1','--port',"$WebPort",'--workers','1') `
      -WorkingDirectory $web -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput "$wlog.out" -RedirectStandardError "$wlog.err"

  $ok = $false
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try {
      $r = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/healthz" -TimeoutSec 2
      if ($r.ok) { $ok = $true; break }
    } catch {}
  }
  if (-not $ok) {
    Write-Host ''
    Write-Host '网页没起来。下面是错误日志：' -ForegroundColor Red
    if (Test-Path "$wlog.err") { Get-Content "$wlog.err" -Tail 25 }
    Write-Host ''
    exit 1
  }

  $url = "http://127.0.0.1:$WebPort"
  Write-Host ''
  Write-Host "  打开：$url" -ForegroundColor Green
  Write-Host ''
  Write-Host '  这个窗口别关，关了网页就打不开了。' -ForegroundColor Yellow
  Write-Host '  看完按 Ctrl+C，或者直接关掉这个窗口。' -ForegroundColor DarkGray
  Write-Host ''
  Start-Process $url

  Wait-Process -Id $procs[0].Id
}
finally {
  foreach ($p in $procs) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'world_server' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
