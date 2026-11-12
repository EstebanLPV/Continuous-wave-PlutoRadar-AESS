$ErrorActionPreference = 'Stop'

function Assert-ExitCode($process, [string]$stage) {
    if (-not $process.WaitForExit(60000)) {
        Stop-Process -Id $process.Id -Force
        throw "La prueba excedió 60 segundos en ${stage}."
    }
    if ($process.ExitCode -ne 0) {
        throw "Falló ${stage} con el código $($process.ExitCode)."
    }
}

$installed = Join-Path $env:LOCALAPPDATA 'Programs\PlutoRadar-AESS'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PlutoRadar-AESS'
$startMenu = [Environment]::GetFolderPath('Programs')
$shortcut = Join-Path $startMenu 'PlutoRadar AESS\PlutoRadar AESS.lnk'
$marker = Join-Path $env:RUNNER_TEMP 'plutoradar-inicio.txt'
if (Test-Path $marker) { Remove-Item $marker }

$setup = Start-Process -FilePath 'dist/PlutoRadar-Setup-x64.exe' -ArgumentList '/S' -PassThru -Wait
Assert-ExitCode $setup 'la instalación'
if (-not (Test-Path -LiteralPath (Join-Path $installed 'radar (1).grc'))) {
    throw 'El diagrama no se instaló.'
}
if (-not (Test-Path $uninstallKey) -or -not (Test-Path $shortcut)) {
    throw 'Falta la entrada de desinstalación o el acceso directo.'
}

$app = Start-Process -FilePath (Join-Path $installed 'PlutoRadar.exe') `
    -ArgumentList "--comprobar-inicio `"$marker`"" -WorkingDirectory $env:TEMP -PassThru
Assert-ExitCode $app 'el inicio de PlutoRadar'
if (-not (Test-Path $marker) -or (Get-Content $marker -Raw) -ne 'OK') {
    throw 'La aplicación no confirmó que abrió la interfaz.'
}

$uninstaller = Join-Path $installed 'Desinstalar.exe'
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList '/S' -PassThru -Wait
Assert-ExitCode $uninstall 'la desinstalación'
if ((Test-Path $uninstallKey) -or (Test-Path $shortcut) -or
    (Test-Path (Join-Path $installed 'PlutoRadar.exe'))) {
    throw 'La desinstalación dejó la aplicación registrada o instalada.'
}
