# uvvis_converter

Utilities for converting UV-Vis `.DSW` files, generating per-sample analysis tables, and exporting figures.

## Scripts

- `converter.py`
  - Converts `DSW -> CSV`
  - Groups files by naming pattern: `xx-yyy-t()h-zz`
  - Builds output tables under `data/processed/<group>/`
- `plot_figures.py`
  - Reads processed CSV outputs and generates PNG figures per group

## Input Data

- Raw files: `data/raw/*.DSW`
- Baseline file: `blank.DSW`
- AM1.5G reference: `reference/am15g_spectrum.csv`
  - `wavelength_nm`
  - `irradiance_w_m2_nm`

## Processing Rules

- Wavelength lower bound: `290 nm` (applied globally)
- Peak search range: `290~800 nm`
- Baseline correction:
  - `A_corr(lambda,t) = A_sample(lambda,t) - A_blank(lambda)`

## Output Naming

All processed CSV and figure files include:

- sample/group name (example: `TT-127-5`)
- max exposure time in that group (example: `48h`)

Pattern:

- `..._<group>_<max_h>h.csv`
- `..._<group>_<max_h>h.png`

Example:

- `analysis_TT-127-5_48h.csv`
- `abs_spectra_overlay_TT-127-5_48h.png`

## Processed CSV Outputs

- `raw_<group>_<max_h>h.csv`
  - Raw table aligned to the baseline wavelength axis
  - Columns: `wavelength_nm`, `blank`, `t0h`, `t1h`, ...

- `baseline_corrected_<group>_<max_h>h.csv`
  - Baseline-corrected spectra (`sample - blank`)
  - Columns: `wavelength_nm`, `t0h`, `t1h`, ...

- `lambda_max_<group>_<max_h>h.csv`
  - Peak wavelength and peak absorbance by time
  - Columns: `time_h`, `peak_wavelength_nm`, `peak_absorbance`

- `spectral_overlap_<group>_<max_h>h.csv`
  - AM1.5G-weighted absorbed-energy summary by time
  - Uses:
    - `absorbed_fraction = 1 - 10^(-A_corr)`
    - `absorbed_irradiance = irradiance * absorbed_fraction`
    - trapezoidal integration (`trapz`)
  - Columns:
    - `time_h`
    - `total_irradiance_w_m2`
    - `absorbed_irradiance_w_m2`
    - `spectral_overlap_percent`
    - `spectral_overlap_delta_vs_t0_percent`
    - `retention_vs_t0_percent`
    - `spectral_overlap_abs_change_vs_t0_percent`

- `spectral_decay_<group>_<max_h>h.csv`
  - Timewise decay summary relative to the reference time (`t0`)
  - Columns:
    - `decay_index_mag`
    - `decay_index_signed`
    - `decay_index_positive`
    - `decay_index_negative_abs`
    - `spectral_overlap_abs_change_vs_t0_percent`
    - `t80_h`
  - `t80_h` rule:
    - computed from `decay_index_mag` only
    - linear interpolation where `decay_index_mag = 0.20`

- `spectral_decay_map_<group>_<max_h>h.csv`
  - Per-wavelength decay map
  - Columns: `wavelength_nm`, `t*h_mag...`, `t*h_signed...`

- `analysis_<group>_<max_h>h.csv`
  - Final merged summary for reporting and plotting
  - Includes peak metrics, overlap trend metrics, decay indices, and `t80_h`

## Figures

- `abs_spectra_overlay_<group>_<max_h>h.png`
  - Baseline-corrected absorbance overlay by time (`0h`, `1h`, ...)
- `deltaA_overlay_<group>_<max_h>h.png`
  - Signed difference overlay: `A(t) - A(t0)` by wavelength
- `analysis_summary_<group>_<max_h>h.png`
  - Peak/overlap/decay summary panel
- `spectral_decay_<group>_<max_h>h.png`
  - Decay index trends vs time

## Install

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

1. Full run (DSW conversion + processing)

```powershell
.\venv\Scripts\python.exe converter.py
```

2. Re-process only (reuse existing converted CSV)

```powershell
.\venv\Scripts\python.exe converter.py --skip-convert
```

3. Generate figures for all groups

```powershell
.\venv\Scripts\python.exe plot_figures.py
```

4. Generate figures for one group

```powershell
.\venv\Scripts\python.exe plot_figures.py --group TT-127-5
```
