# AERIS v0.8 deployment behind GeoNode Nginx

AERIS runs as two containers on the GeoNode Docker network:

- `aeris-web` — React/Vite production application;
- `aeris-api` — FastAPI/geospatial analysis engine.

GeoNode Nginx exposes:

- `/aeris/` -> `aeris-web`;
- `/aeris-api/` -> `aeris-api`.

## v0.8 safety boundary

**Code releases and GIS data are separate.**

- Releases live under `/opt/aeris/releases`.
- The active and previous releases are symlinked as `/opt/aeris/current` and
  `/opt/aeris/previous`.
- Operational GIS data lives once at `/opt/aeris/shared/data`.
- Required baseline data is checksum-manifested and archived under
  `/opt/aeris/shared/data-snapshots`.
- A normal release archive does not contain GIS data.

On the first v0.8 deployment, the installer adopts the data already mounted by
the running AERIS API and moves it into shared storage on the same VM after the
candidate release has passed pre-cutover tests. No network re-download is
required.

## One-command release from PowerShell

After the deployment files are installed in the repository:

```powershell
.\deploy-to-geonode.ps1 `
  -Vm "40.76.136.89" `
  -AdminUser "FOSS4Gadmin" `
  -KeyPath "$HOME\.ssh\geonode_azure" `
  -PublicOrigin "http://40.76.136.89" `
  -BuildLocal
```

The command builds/tests the frontend in WSL, creates a code-only archive,
verifies its SHA-256, uploads it, builds versioned Docker images, runs candidate
smoke tests, cuts over, tests through GeoNode Nginx, and rolls back automatically
if the post-cutover checks fail.

## Build a code release only

```bash
cd ~/projects/AERIS-Project
bash deploy/geonode/scripts/prepare_release.sh
```

Useful development overrides:

```bash
AERIS_SKIP_NPM_CI=1 bash deploy/geonode/scripts/prepare_release.sh
AERIS_SKIP_FRONTEND_BUILD=1 AERIS_SKIP_LINT=1 \
  bash deploy/geonode/scripts/prepare_release.sh
```

Do not use the skip switches for a formal release unless the same build/tests
were already completed from the exact working tree.

## Rollback

```bash
sudo /opt/aeris/current/deploy/geonode/scripts/rollback_remote.sh
```

The rollback never rolls back or deletes the persistent GIS data.

## Verify/status

```bash
sudo /opt/aeris/current/deploy/geonode/scripts/release_status.sh
sudo /opt/aeris/current/deploy/geonode/scripts/verify_remote.sh \
  http://40.76.136.89
```

## Intentional data refresh

Local:

```bash
bash deploy/geonode/scripts/prepare_data_snapshot.sh
```

PowerShell:

```powershell
.\deploy-data-snapshot.ps1 -BuildLocal
```

This is deliberately separate from code deployment.

See `AERIS/docs/V08_PHASE1_RELEASE_STABILITY.md` for architecture and acceptance
gates.
