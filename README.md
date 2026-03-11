# uvvis_converter

Desktop app and CLI for turning UV-Vis spectroscopy datasets into analysis tables and figures.

It is built for lab workflows where raw spectra come from `.DSW` or `.csv` files, a blank spectrum is preferred (or can be assumed as zero), and time-series measurements need to be grouped, corrected, summarized, and exported in a repeatable way.

## What It Does

`uvvis_converter` helps a lab member do four things without editing paths in code:

1. Scan a dataset folder and find raw spectra
2. Choose which files are samples, which file is the blank, and which files should be excluded
3. Convert `.DSW` spectra to `.csv` when needed
4. Generate processed analysis outputs and figures per sample group

The app is designed to be usable by non-developers once packaged as a Windows executable.

## Main Features

- Desktop GUI for dataset scanning, file mapping, validation, and execution
- CLI entry points for scripted or developer workflows
- Supports both `.DSW` and `.csv` raw inputs
- Supports both `-` and `_` in filenames
- Automatic blank candidate detection with manual override
- Optional "assume zero blank" mode when no blank spectrum is available
- Manual correction of `Group Key`, `Time (h)`, and `Sample`
- Run manifests and logs saved with each output run
- Processed CSV outputs for peak, overlap, decay, and `T80`
- Optional figure generation for processed groups

## Typical Dataset Layout

The preferred layout is:

```text
<dataset>\
  raw\
  converted\
  processed\
```

If you select a folder that does not contain `raw\`, the app treats the selected folder itself as the raw input folder.

That means both of these work:

- select `<dataset>\`
- select `<dataset>\raw\`

## GUI Workflow

Run the app:

```powershell
.\venv\Scripts\python.exe uvvis_gui.py
```

Recommended workflow:

1. Select a dataset folder
2. Click `Scan`
3. Confirm the selected blank file (or enable `Assume zero blank if none selected`)
4. In the `Files` tab, set each file role:
   - `sample`
   - `blank`
   - `exclude`
5. Fix any missing `Group Key`, `Time (h)`, or `Sample` values
6. Review the `Validation` tab
7. Run one of:
   - `Run`
   - `Convert Only`
   - `Process Only`
   - `Figures Only`

`Process Only` is strict for `.DSW` inputs:

- existing converted CSV files must already be present
- if they are missing, validation shows a clear error
- if you use a real `.DSW` blank, its converted CSV must also already exist

## File Naming Support

The parser accepts both `-` and `_` separators.

Examples:

- `TT-127-t48h-5.DSW`
- `TT_127_t48h_5.DSW`
- `TT-127-48h-5.DSW`

The app tries to infer:

- group prefix
- time in hours
- sample number

If inference is ambiguous, the file remains editable in the mapping table.

## Output Structure

Each run can write into its own labeled folder:

```text
processed\<run_label>\
```

Each processed group is written under its `Group Key`:

```text
processed\<run_label>\TT-127-5\
```

Typical outputs per group:

- `raw_<group>_<max_h>h.csv`
- `baseline_corrected_<group>_<max_h>h.csv`
- `lambda_max_<group>_<max_h>h.csv`
- `spectral_overlap_<group>_<max_h>h.csv`
- `spectral_decay_<group>_<max_h>h.csv`
- `spectral_decay_map_<group>_<max_h>h.csv`
- `analysis_<group>_<max_h>h.csv`
- `figures\*.png`

Each run folder also includes:

- `_manifest.json`
- `_run.log`

## CLI Usage

Full run:

```powershell
.\venv\Scripts\python.exe converter.py --dataset-dir data\Tiara_021126_127
```

Process only with existing converted CSV files:

```powershell
.\venv\Scripts\python.exe converter.py --dataset-dir data\Tiara_021126_127 --skip-convert
```

Run without a blank file (assume absorbance `0` for all wavelengths):

```powershell
.\venv\Scripts\python.exe converter.py --dataset-dir data\Tiara_021126_127 --assume-zero-blank
```

Write to a separate run label:

```powershell
.\venv\Scripts\python.exe converter.py --dataset-dir data\Tiara_021126_127 --run-label 2026-03-10_1542
```

Generate figures from an existing processed run:

```powershell
.\venv\Scripts\python.exe plot_figures.py --processed-dir data\Tiara_021126_127\processed\2026-03-10_1542
```

## Installation

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Repository Structure

```text
uvvis_app/
  core/   # parsing, validation, processing, plotting, manifests
  gui/    # PySide6 desktop app
converter.py
plot_figures.py
uvvis_gui.py
reference/
```

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)

## Windows Packaging

This repository includes a PyInstaller spec file for the desktop app:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -EnsureDeps
```

The packaged app is written to:

```text
dist\UVVisConverter\
```

The build bundles the default AM1.5 reference file so the packaged GUI can use it without relying on the repository layout.

Packaging notes:

- the build script uses `.\build_venv312\Scripts\python.exe` by default
- Python 3.12+ is required for packaging
- pass `-EnsureDeps` to install/refresh build dependencies before packaging

## Current Status

This repository is ready for:

- internal lab testing
- GitHub publication
- Windows executable packaging

Before publishing a GitHub release, the remaining practical step is testing the packaged app on a clean Windows machine.
