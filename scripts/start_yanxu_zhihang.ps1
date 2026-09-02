param(
    [int]$Port = 8501
)

$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project ".venv-cloud311\Scripts\python.exe"
$logDir = Join-Path $project "results\local_release"
$stdout = Join-Path $logDir "yanxu_zhihang.stdout.log"
$stderr = Join-Path $logDir "yanxu_zhihang.stderr.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到本地 Python 3.11 环境：$python"
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Output "研序智航已经在 http://localhost:$Port 运行。"
    exit 0
}

$arguments = @(
    "-m", "streamlit", "run", "app.py",
    "--server.address", "127.0.0.1",
    "--server.port", "$Port",
    "--server.headless", "true",
    "--browser.gatherUsageStats", "false"
)

$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $project `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

Write-Output "研序智航正在启动：http://localhost:$Port（进程 $($process.Id)）"
Write-Output "运行日志：$logDir"
