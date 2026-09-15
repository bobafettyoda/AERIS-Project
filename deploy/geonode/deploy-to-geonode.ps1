[CmdletBinding()]
param(
    [string]$Vm = "40.76.136.89",
    [string]$AdminUser = "FOSS4Gadmin",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\geonode_azure",
    [string]$ArchivePath = "",
    [string]$PublicOrigin = "http://40.76.136.89",
    [string]$GeoNodeNginxContainer = "nginx4geonode_project",
    [string]$GeoNodeNginxConfig = "/var/lib/docker/volumes/geonode_project-nginxconfd/_data/sites-enabled/geonode.conf",
    [string]$WslRepo = "~/projects/AERIS-Project",
    [switch]$BuildLocal
)

$ErrorActionPreference = "Stop"

function ConvertTo-BashQuoted([string]$Value) {
    $replacement = "'" + '"' + "'" + '"' + "'"
    return "'" + $Value.Replace("'", $replacement) + "'"
}

if (-not (Test-Path -LiteralPath $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

if ($BuildLocal) {
    Write-Host "Building a fresh code-only AERIS release in WSL..."
    $command = "cd $WslRepo && bash deploy/geonode/scripts/prepare_release.sh"
    & wsl.exe bash -lc $command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL release build failed with exit code $LASTEXITCODE"
    }
}

if ([string]::IsNullOrWhiteSpace($ArchivePath)) {
    $latest = Get-ChildItem -LiteralPath "$env:USERPROFILE\Downloads" `
        -Filter "aeris-v*.tar.gz" -File `
        | Where-Object { $_.Name -notlike "aeris-data-*" } `
        | Sort-Object LastWriteTime -Descending `
        | Select-Object -First 1

    if ($null -eq $latest) {
        throw "No AERIS code release archive was found in Downloads. Use -BuildLocal or run prepare_release.sh first."
    }
    $ArchivePath = $latest.FullName
}

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    throw "Release archive not found: $ArchivePath"
}

$checksumPath = "$ArchivePath.sha256"
if (Test-Path -LiteralPath $checksumPath) {
    $expected = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        throw "Release archive checksum mismatch. Expected $expected but calculated $actual"
    }
    Write-Host "Release checksum verified:" $actual
}
else {
    throw "Release checksum file not found: $checksumPath"
}

$target = "${AdminUser}@${Vm}"
$remoteArchive = "/tmp/aeris-code-release.tar.gz"

Write-Host "Uploading code-only release:" $ArchivePath
Write-Host "Target:" $target

$scpArguments = @(
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=20",
    "-i", $KeyPath,
    $ArchivePath,
    "${target}:${remoteArchive}"
)
& scp.exe @scpArguments
if ($LASTEXITCODE -ne 0) {
    throw "SCP upload failed with exit code $LASTEXITCODE"
}

$arguments = @(
    "--source-dir", "/tmp/aeris-release",
    "--nginx-container", $GeoNodeNginxContainer,
    "--nginx-config", $GeoNodeNginxConfig
)
if (-not [string]::IsNullOrWhiteSpace($PublicOrigin)) {
    $arguments += @("--public-origin", $PublicOrigin.TrimEnd('/'))
}

$quotedArguments = ($arguments | ForEach-Object { ConvertTo-BashQuoted $_ }) -join " "
$quotedArchive = ConvertTo-BashQuoted $remoteArchive

$remoteCommand = @"
set -euo pipefail
sudo rm -rf /tmp/aeris-release
sudo mkdir -p /tmp/aeris-release
sudo tar -xzf $quotedArchive -C /tmp/aeris-release
sudo bash /tmp/aeris-release/deploy/geonode/scripts/install_remote.sh $quotedArguments
"@

Write-Host "Installing AERIS with candidate preflight, smoke tests, and automatic rollback..."
$sshArguments = @(
    "-t",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=20",
    "-i", $KeyPath,
    $target,
    $remoteCommand
)
& ssh.exe @sshArguments
if ($LASTEXITCODE -ne 0) {
    throw "Remote installation failed with exit code $LASTEXITCODE. The installer attempts automatic rollback before returning failure."
}

Write-Host ""
Write-Host "Server-side deployment and product smoke tests passed."
Write-Host "Rollback command: sudo /opt/aeris/current/deploy/geonode/scripts/rollback_remote.sh"

if (-not [string]::IsNullOrWhiteSpace($PublicOrigin)) {
    $origin = $PublicOrigin.TrimEnd('/')
    try {
        $health = Invoke-RestMethod -Uri "$origin/aeris-api/health" -TimeoutSec 20
        Write-Host "Client verification:" $health.release_label "release" $health.deployment_release_id "data" $health.data_snapshot_id
        Write-Host "AERIS:" "$origin/aeris/"
    }
    catch {
        Write-Warning "The server-side checks passed, but this Windows client could not reach the public URL: $($_.Exception.Message)"
    }
}
