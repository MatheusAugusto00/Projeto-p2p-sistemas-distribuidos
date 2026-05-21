# PowerShell demo runner for Sprint 3 (Windows)
# Opens multiple PowerShell windows and runs the server and workers

Param(
    [int]$START_DELAY = 1,
    [string]$PYTHON_BIN = $(if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { 'py -3' })
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Write-Host "Projeto: $ProjectDir"

function Start-Terminal {
    param(
        [string]$Title,
        [string]$CommandLine
    )

    $psArgs = "-NoExit", "-ExecutionPolicy Bypass", "-Command", "cd '$ProjectDir'; $CommandLine"
    Start-Process -FilePath powershell -ArgumentList $psArgs -WindowStyle Normal
}

Write-Host "Abrindo 5 janelas PowerShell para demo Sprint 3..."

# Master A
$cmdA = "$env:MASTER_UUID='Master_A'; $env:MASTER_HOST='127.0.0.1'; $env:MASTER_PORT='8000'; $env:INITIAL_TASK_COUNT='50'; $env:CAPACITY='5'; $env:RELEASE_THRESHOLD='2'; $env:PEER_MASTERS='Master_B@127.0.0.1:8001'; & $PYTHON_BIN server.py"
Start-Terminal -Title "Sprint3 Master A" -CommandLine $cmdA
Start-Sleep -Seconds $START_DELAY

# Master B
$cmdB = "$env:MASTER_UUID='Master_B'; $env:MASTER_HOST='127.0.0.1'; $env:MASTER_PORT='8001'; $env:INITIAL_TASK_COUNT='0'; $env:CAPACITY='100'; $env:RELEASE_THRESHOLD='60'; $env:PEER_MASTERS='Master_A@127.0.0.1:8000'; & $PYTHON_BIN server.py"
Start-Terminal -Title "Sprint3 Master B" -CommandLine $cmdB
Start-Sleep -Seconds $START_DELAY

# Worker B1
$cmdWB1 = "$env:WORKER_ID='B1'; $env:MASTER_HOST='127.0.0.1'; $env:MASTER_PORT='8001'; $env:RECONNECT_DELAY='2'; & $PYTHON_BIN client.py"
Start-Terminal -Title "Sprint3 Worker B1" -CommandLine $cmdWB1
Start-Sleep -Seconds $START_DELAY

# Worker B2
$cmdWB2 = "$env:WORKER_ID='B2'; $env:MASTER_HOST='127.0.0.1'; $env:MASTER_PORT='8001'; $env:RECONNECT_DELAY='2'; & $PYTHON_BIN client.py"
Start-Terminal -Title "Sprint3 Worker B2" -CommandLine $cmdWB2
Start-Sleep -Seconds $START_DELAY

# Worker A1
$cmdWA1 = "$env:WORKER_ID='A1'; $env:MASTER_HOST='127.0.0.1'; $env:MASTER_PORT='8000'; $env:RECONNECT_DELAY='2'; & $PYTHON_BIN client.py"
Start-Terminal -Title "Sprint3 Worker A1" -CommandLine $cmdWA1

Write-Host "Janelas abertas. Para encerrar a demo, feche as janelas ou use Ctrl+C nas que executam o servidor/clients."