[CmdletBinding()]
param(
    [string]$Vm = "40.76.136.89",
    [string]$AdminUser = "FOSS4Gadmin",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\geonode_azure",
    [string]$ArchivePath = "",
    [string]$PublicOrigin = "http://40.76.136.89",
    [string]$WslRepo = "~/projects/AERIS-Project",
    [switch]$BuildLocal
)

$ErrorActionPreference = "Stop"

if ($BuildLocal) {
    Write-Host "Preparing an explicit AERIS data snapshot in WSL..."
    & wsl.exe bash -lc "cd $WslRepo && bash deploy/geonode/scripts/prepare_data_snapshot.sh"
    if ($LASTEXITCODE -ne 0) { throw "Data snapshot build failed." }
}

if ([string]::IsNullOrWhiteSpace($ArchivePath)) {
    $latest = Get-ChildItem -LiteralPath "$env:USERPROFILE\Downloads" -Filter "aeris-data-*.tar.gz" -File `
        | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $latest) { throw "No AERIS data snapshot archive was found in Downloads." }
    $ArchivePath = $latest.FullName
}

$checksumPath = "$ArchivePath.sha256"
if (-not (Test-Path -LiteralPath $checksumPath)) { throw "Missing checksum file: $checksumPath" }
$expected = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw "Data snapshot checksum mismatch." }

$target = "${AdminUser}@${Vm}"
$remoteArchive = "/tmp/aeris-data-snapshot.tar.gz"
& scp.exe -i $KeyPath $ArchivePath "${target}:${remoteArchive}"
if ($LASTEXITCODE -ne 0) { throw "Data snapshot upload failed." }

$remote = @"
set -euo pipefail
sudo bash /opt/aeris/current/deploy/geonode/scripts/install_data_snapshot.sh --archive '$remoteArchive' --promote
set -a
. /opt/aeris/shared/aeris.env
. /opt/aeris/shared/active-data-snapshot.env
set +a
sudo docker compose -p aeris --env-file /opt/aeris/shared/aeris.env -f /opt/aeris/current/deploy/geonode/docker-compose.yml restart api
sudo bash /opt/aeris/current/deploy/geonode/scripts/verify_remote.sh '$PublicOrigin'
"@
& ssh.exe -t -i $KeyPath $target $remote
if ($LASTEXITCODE -ne 0) { throw "Data snapshot promotion failed." }

Write-Host "Data snapshot promoted and AERIS verified."
