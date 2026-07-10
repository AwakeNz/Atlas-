# Release checklist

A.T.L.A.S. ships as a single `ATLAS.exe`. The in-app updater downloads that
asset from the **latest GitHub Release** and verifies it against the
`ATLAS.exe.sha256` checksum published in the **same** release. Both assets are
mandatory — the updater refuses to install without a matching checksum.

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
   - builds `dist/ATLAS.exe` via `atlas.spec` (onefile, windowed),
   - computes `dist/ATLAS.exe.sha256` (`<hash>  ATLAS.exe`),
   - creates a **draft** Release with both files attached.

6. **Review the draft Release**, confirm both assets are present, then
   **Publish**. Publishing flips it to "latest", which is what the updater
   queries (`GET /repos/<owner>/atlas/releases/latest`).

## Manual build (local, if you're not using CI)

```bat
build.bat
pwsh -c "(Get-FileHash dist\ATLAS.exe -Algorithm SHA256).Hash.ToLower() + '  ATLAS.exe' | Out-File -Encoding ascii dist\ATLAS.exe.sha256"
```
Upload `ATLAS.exe` **and** `ATLAS.exe.sha256` to the release.

## What updates never touch

`plugins/`, `skills/`, `settings.json`, `apps.json`, `memory.db`, `models/`,
and `jarvis`/`atlas.log` live next to the exe and survive every upgrade — the
swap replaces only `ATLAS.exe`.

## Verifying the updater end-to-end

- Install an older build, publish a newer release, launch: the HUD should show
  `UPDATE AVAILABLE — vX.Y.Z` and the tray should offer **Check for updates**.
- Click **INSTALL**: download → checksum verify → `update.bat` swaps the exe
  and relaunches. A deliberately corrupted asset must be **rejected** at the
  checksum step (test this).
