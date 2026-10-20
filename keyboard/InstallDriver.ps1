$ErrorActionPreference = 'Stop'
$driverUrl = 'https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe'
$driverPage = 'https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0'
$driverFile = Join-Path $PSScriptRoot 'drivers\ViGEmBus_1.22.0_x64_x86_arm64.exe'
try {
    if (-not (Test-Path -LiteralPath $driverFile)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $driverFile) -Force | Out-Null
        Write-Host 'Downloading the official ViGEmBus 1.22.0 installer...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $driverUrl -OutFile $driverFile -UseBasicParsing
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $driverFile
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Nefarius') {
        throw "Driver signature verification failed: $($signature.Status). Download a fresh installer from $driverPage"
    }
    Write-Host "Verified publisher: $($signature.SignerCertificate.Subject)"
    Write-Host 'Windows will request administrator permission to install the driver.'
    $driverProcess = Start-Process -FilePath $driverFile -Verb RunAs -Wait -PassThru
    if ($driverProcess.ExitCode -in 0, 3010, 1641) {
        Write-Host 'Installer finished. Restart Windows if requested, then run Launch.cmd.' -ForegroundColor Green
    } else {
        throw "Installer exit code: $($driverProcess.ExitCode)"
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Manual download: $driverPage"
    Write-Host 'The mapping app can be closed while you install the driver.'
}
Read-Host 'Press Enter to close'
