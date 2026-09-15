# AERIS v0.8 Phase 1 — Release and Data Stability

AERIS v0.8 Phase 1 separates **application releases** from **GIS data** so new
code can be deployed, tested, and rolled back without re-downloading or
repackaging the Maryland data estate.

## Operating model

```text
/opt/aeris/
  current -> releases/<active release>
  previous -> releases/<previous release>
  releases/
    aeris-v0.8.0-...
  shared/
    aeris.env
    active-release.env
    active-data-snapshot.env
    data/                    # persistent writable operational data
    data-snapshots/
      baseline-.../
        snapshot.json        # immutable checksums
        required-data.tar.gz # immutable recovery copy of required baseline
```

The application container always mounts `/opt/aeris/shared/data`. A normal code
release contains an empty `AERIS/data` directory and cannot overwrite production
GIS data.

## First v0.8 deployment

The installer detects the data directory currently mounted into `aeris-api`.
It validates the required statewide/parcel baseline, builds and smoke-tests the
candidate release against that data, and only then stops the current runtime.
The existing data directory is **moved on the VM** into
`/opt/aeris/shared/data`; it is not downloaded again and is not duplicated
across release folders.

Before cutover, the required baseline artifacts receive an immutable checksum
manifest and compressed recovery snapshot under `shared/data-snapshots`.

## Normal code deployment

From Windows PowerShell, after this kit is installed in the repository:

```powershell
.\deploy-to-geonode.ps1 `
  -Vm "40.76.136.89" `
  -AdminUser "FOSS4Gadmin" `
  -KeyPath "$HOME\.ssh\geonode_azure" `
  -PublicOrigin "http://40.76.136.89" `
  -BuildLocal
```

`-BuildLocal` asks WSL to run the production build, tests, lint, and release
packaging first. The resulting code archive contains **no GIS data**.

## Deployment gates

A release is not marked current until all of the following pass:

1. Docker Compose v2 is available.
2. The required persistent data artifacts exist.
3. The active data manifest verifies against SHA-256 checksums.
4. At least the configured minimum free disk space is available.
5. Versioned API and web images build successfully.
6. Candidate containers pass API/frontend health checks before cutover.
7. Candidate API passes smoke tests for:
   - Site Evaluator decision model;
   - Statewide Screening health, summary, grid, and candidate zones;
   - Parcel Investigation health/scopes and a bundle when a built scope exists.
8. GeoNode Nginx configuration passes `nginx -t`.
9. The same product smoke tests pass through the GeoNode reverse proxy.

If a post-cutover gate fails, the installer restores the previous release.
`/opt/aeris/current` is only changed after the candidate passes.

## Manual rollback

```bash
sudo /opt/aeris/current/deploy/geonode/scripts/rollback_remote.sh
```

Rollback changes code/images only. The persistent data directory is not
replaced.

To roll back to a specific retained release:

```bash
sudo /opt/aeris/current/deploy/geonode/scripts/rollback_remote.sh \
  --release aeris-v0.8.0-YYYYMMDDTHHMMSSZ
```

## Status and verification

```bash
sudo /opt/aeris/current/deploy/geonode/scripts/release_status.sh

sudo /opt/aeris/current/deploy/geonode/scripts/verify_remote.sh \
  http://40.76.136.89
```

The `/aeris-api/health` response now reports the deployment release ID, active
data snapshot ID, and data-manifest SHA-256 in addition to the AERIS application
version.

## Intentional data refresh

Data changes are a separate operation. Prepare a snapshot locally:

```bash
cd ~/projects/AERIS-Project
bash deploy/geonode/scripts/prepare_data_snapshot.sh
```

The default `baseline` snapshot includes only the stable files listed in
`deploy/geonode/data-required.txt`. For a complete data archive excluding
runtime/cache state:

```bash
AERIS_DATA_SNAPSHOT_MODE=full \
  bash deploy/geonode/scripts/prepare_data_snapshot.sh
```

Promote it explicitly from PowerShell:

```powershell
.\deploy-data-snapshot.ps1 -BuildLocal
```

Normal code deployments never invoke this process.

## Required baseline data

The authoritative deployment list is `deploy/geonode/data-required.txt`.
It covers the statewide final grid/preview, candidate-zone artifacts, score/bias
manifests, climate-final manifest, and parcel source audit used by the three
product smoke tests.

Runtime parcel jobs, caches, and temporary files are intentionally excluded from
the immutable baseline checksum set so normal analyst activity does not make a
code release fail checksum validation.
