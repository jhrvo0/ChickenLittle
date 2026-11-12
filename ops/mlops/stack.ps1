param([switch]$Encerrar, [switch]$ConsoleAirflow, [string]$DataDir = 'data/experiments/phase-c/stack')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
# O docker desta maquina e um wrapper WSL: caminhos de bind/build devem ser Linux.
$linuxRootResult = & wsl -d Ubuntu -- wslpath -a -u $projectRoot.Replace('\', '/')
if ($LASTEXITCODE -ne 0 -or -not $linuxRootResult) { throw 'Nao foi possivel resolver o projeto no WSL.' }
$linuxRoot = $linuxRootResult.Trim()
$compose = "$linuxRoot/ops/mlops/compose.yaml"
$dataRoot = Join-Path $projectRoot $DataDir
if (-not $Encerrar) { New-Item -ItemType Directory -Force $dataRoot | Out-Null }
$linuxDataResult = & wsl -d Ubuntu -- wslpath -a -u $dataRoot.Replace('\', '/')
if ($LASTEXITCODE -ne 0 -or -not $linuxDataResult) { throw 'Nao foi possivel resolver os dados no WSL.' }
$linuxDataRoot = $linuxDataResult.Trim()
if ($Encerrar) {
    & wsl -d Ubuntu -- env "MOTIONLAB_DATA_DIR=$linuxDataRoot" docker compose -f $compose down --timeout 20
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao encerrar a stack.' }
    $keeperFile = Join-Path $projectRoot 'data/experiments/phase-c/wsl-keeper.pid'
    $keeperFlag = Join-Path $projectRoot 'data/experiments/phase-c/wsl-keeper.flag'
    Remove-Item -LiteralPath $keeperFlag -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $keeperFile) {
        $keeperId = [int](Get-Content -LiteralPath $keeperFile)
        $keeper = Get-CimInstance Win32_Process -Filter "ProcessId = $keeperId" -ErrorAction SilentlyContinue
        if ($keeper -and $keeper.Name -eq 'wsl.exe' -and $keeper.CommandLine -match 'wsl-keepalive.sh') {
            Start-Sleep -Seconds 4
            $remainingKeeper = Get-CimInstance Win32_Process -Filter "ProcessId = $keeperId" -ErrorAction SilentlyContinue
            if ($remainingKeeper -and $remainingKeeper.CreationDate -eq $keeper.CreationDate -and $remainingKeeper.CommandLine -match 'wsl-keepalive.sh') {
                Stop-Process -Id $keeperId -ErrorAction SilentlyContinue
            }
        }
        Remove-Item -LiteralPath $keeperFile
    }
    return
}
$freeMB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
Write-Host "Memoria livre no Windows: $freeMB MB. Builds sequenciais; Airflow termina apos o DAG."
if ($freeMB -lt 1000) { throw 'Menos de 1 GB livre. Libere memoria antes de iniciar a stack.' }
$keeperDir = Join-Path $projectRoot 'data/experiments/phase-c'
New-Item -ItemType Directory -Force $keeperDir | Out-Null
$keeperFile = Join-Path $keeperDir 'wsl-keeper.pid'
$keeperFlag = Join-Path $keeperDir 'wsl-keeper.flag'
$keeperActive = $false
if (Test-Path -LiteralPath $keeperFile) {
    $keeper = Get-CimInstance Win32_Process -Filter "ProcessId = $([int](Get-Content -LiteralPath $keeperFile))" -ErrorAction SilentlyContinue
    $keeperActive = $keeper -and $keeper.Name -eq 'wsl.exe' -and $keeper.CommandLine -match 'wsl-keepalive.sh'
}
if (-not $keeperActive) {
    Set-Content -LiteralPath $keeperFlag -Value 'MotionLab phase C'
    $keeperArguments = '-d Ubuntu -- sh "' + $linuxRoot + '/ops/mlops/wsl-keepalive.sh" "' + $linuxRoot + '/data/experiments/phase-c/wsl-keeper.flag"'
    $keeper = Start-Process -FilePath wsl.exe -ArgumentList $keeperArguments -WindowStyle Hidden -PassThru
    $keeper.Id | Set-Content -LiteralPath $keeperFile
}
& wsl -d Ubuntu -- env "MOTIONLAB_DATA_DIR=$linuxDataRoot" docker compose -f $compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Configuracao Compose invalida.' }
foreach ($service in @('api', 'airflow')) {
    & wsl -d Ubuntu -- env "MOTIONLAB_DATA_DIR=$linuxDataRoot" DOCKER_BUILDKIT=0 COMPOSE_PARALLEL_LIMIT=1 docker compose -f $compose build $service
    if ($LASTEXITCODE -ne 0) { throw "Build falhou: $service" }
}
& wsl -d Ubuntu -- env "MOTIONLAB_DATA_DIR=$linuxDataRoot" docker compose -f $compose up -d --no-build
if ($LASTEXITCODE -ne 0) { throw 'Subida incompleta. Consulte docker compose logs; stack.ps1 -Encerrar preserva dados.' }
Write-Host 'Aguardando o DAG Airflow terminar (limite 5 min)...'
$deadline = (Get-Date).AddMinutes(5)
$completed = $false
while ((Get-Date) -lt $deadline) {
    $jobId = & wsl -d Ubuntu -- env "MOTIONLAB_DATA_DIR=$linuxDataRoot" docker compose -f $compose ps -a -q airflow
    if ($jobId) {
        $jobState = & wsl -d Ubuntu -- docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' $jobId.Trim()
        if ($jobState -eq 'exited:0') { $completed = $true; break }
        if ($jobState -like 'exited:*') { throw "Airflow falhou ($jobState). Consulte os logs antes de tentar novamente." }
    }
    Start-Sleep -Seconds 3
}
if (-not $completed) { throw 'DAG nao terminou em 5 min; stack preservada para diagnostico.' }
if ($ConsoleAirflow) {
    & wsl -d Ubuntu -- env "MOTIONLAB_DATA_DIR=$linuxDataRoot" docker compose -f $compose --profile console up -d --no-deps airflow-ui
    if ($LASTEXITCODE -ne 0) { throw 'Console opcional do Airflow nao iniciou.' }
}
Write-Host 'Dashboard http://127.0.0.1:8767/ | API :8768 | MLflow :5000'
Write-Host 'Airflow terminou com exit code 0. Rode verify_stack.py para conferir HTTP/MQTT/MLflow.'
Write-Host 'Encerrar sem apagar dados: ./ops/mlops/stack.ps1 -Encerrar'
