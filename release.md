# Release checklist

A.T.L.A.S. ships as `ATLAS-Setup-v<version>.exe` (an Inno Setup installer). The
in-app updater downloads that asset from the **latest GitHub Release** and
verifies it against the `ATLAS-Setup-v<version>.exe.sha256` checksum published in
the **same** release. Both assets are mandatory — the updater refuses to install
without a matching checksum, then runs the installer silently to upgrade in place.

## Cut a release

1. **Bump the version** in `src/core/config.py`:
   ```python
   __version__ = "0.3.0"
   ```
   Semantic versioning. The updater rejects same-or-older tags (no downgrades).

2. **Update `docs/`** if behavior changed, and note highlights for the release.

3. **Commit** the version bump on `main`.

4. **Tag and push**:
   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```

5. The **`Build & Release` GitHub Action** (`.github/workflows/release.yml`)
   fires on the tag and:
   - checks the tag matches `__version__` (fails otherwise),
   - converts the icon, builds the exe, and packages `ATLAS-Setup-v<version>.exe`,
   - compiles the Inno Setup installer and computes its `.sha256`,
   - creates a **draft** Release with both files attached.

6. **Review the draft Release**, confirm both assets are present, then
   **Publish**. Publishing flips it to "latest", which is what the updater
   queries (`GET /repos/<owner>/atlas/releases/latest`).

## Manual build (local, if you're not using CI)

```bat
python build.py            REM icon -> PyInstaller -> Inno Setup -> checksums
```
Everything lands in `dist\release\`: upload `ATLAS-Setup-v<version>.exe`
**and** its `.sha256` to the release. (Requires Inno Setup 6 on PATH for the
installer step; without it build.py still produces the exe and warns.)

## What updates never touch

`plugins/`, `skills/`, `settings.json`, `apps.json`, `memory.db`, `models/`,
and `atlas.log` live in `%APPDATA%\ATLAS` and survive every upgrade — the
installer only ever writes to `Program Files\ATLAS`.

## Verifying the updater end-to-end

- Install an older build, publish a newer release, launch: the HUD should show
  `UPDATE AVAILABLE — vX.Y.Z` and the tray should offer **Check for updates**.
- Click **INSTALL**: download → checksum verify → the installer runs
  `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`, upgrades in place, relaunches.
  A corrupted asset must be **rejected** at the checksum step. Confirm
  `%APPDATA%\ATLAS` is untouched across the upgrade.
