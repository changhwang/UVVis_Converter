# Release Checklist

This checklist is for preparing a GitHub release of `uvvis_converter`.

## 1. Final Repository Review

- remove one-off or obsolete scripts
- confirm README reflects the current GUI and CLI
- confirm documentation links work
- confirm `.gitignore` excludes local-only data and build artifacts

## 2. Local Test Pass

Inside the project venv:

```powershell
python -m pip install -r requirements.txt
python converter.py --help
python plot_figures.py --help
python uvvis_gui.py
```

Recommended manual GUI checks:

- scan a real dataset
- confirm automatic blank detection
- change one file role to `exclude`
- change one row's `Group Key` or `Time (h)`
- run `Process Only`
- run `Run`
- run `Figures Only`
- confirm `_manifest.json` and `_run.log` are written

## 3. Packaging Prep

Before creating a public release, package the GUI as a Windows executable.

Use the checked-in spec and build script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -EnsureDeps
```

Expected output:

```text
dist\UVVisConverter\
```

Packaging notes:

- `UVVisConverter.spec` bundles `reference\am15g_spectrum.csv`
- `scripts\build_windows.ps1` defaults to `build_venv312` and requires Python 3.12+
- the build is currently a one-folder Windows app
- if an icon is added later, update the spec rather than ad hoc CLI flags

## 4. Clean-Machine Test

Test the packaged app on a Windows machine that does not already have:

- the repository checkout
- your development venv
- your local Python setup

Verify:

- the app launches
- the default AM1.5 reference is found or clearly reported
- a sample dataset can be scanned
- a run completes successfully
- `dist\UVVisConverter\_internal\reference\am15g_spectrum.csv` exists after build

## 5. GitHub Push

Before pushing:

- review changed files
- make sure large local datasets are not included
- make sure temporary outputs are not committed

Then push the branch to GitHub.

## 6. Release Creation

Suggested release contents:

- packaged Windows app archive
- short release notes
- known limitations
- sample screenshots

Suggested release notes topics:

- first desktop GUI version
- supports `.DSW` and `.csv`
- manual file role mapping
- blank override support
- run manifests and logs

## 7. Nice-to-Have Before Public Release

- add an application icon
- add screenshots to the README
- keep packaging flow tied to Python 3.12 build venv
- add a version number in the GUI
- add a sample dataset guide or demo video
