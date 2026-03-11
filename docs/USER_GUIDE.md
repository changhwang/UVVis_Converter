# User Guide

## Purpose

`uvvis_converter` is a UV-Vis dataset processing tool for lab workflows.

It takes raw spectra, lets the user choose the blank and sample mapping, and generates:

- cleaned CSV outputs
- summary tables
- trend metrics
- figures for reporting

The goal is to replace path editing and one-off scripts with a repeatable workflow that other lab members can use.

## Inputs

The app accepts raw files in either format:

- `.DSW`
- `.csv`

It also needs:

- one blank spectrum
- one AM1.5 reference spectrum

The default reference file is:

```text
reference\am15g_spectrum.csv
```

## Dataset Selection

When you select a folder:

- if it contains `raw\`, the app scans that folder
- otherwise, the selected folder itself is treated as the raw input folder

That allows both strict and loose dataset layouts.

Preferred layout:

```text
<dataset>\
  raw\
  converted\
  processed\
```

## Files Tab

Each file gets a role:

- `sample`
  - included in processing
- `blank`
  - used as the baseline spectrum
- `exclude`
  - ignored for the current run

Important notes:

- the blank is not processed as a sample
- invalid files are not excluded automatically
- if you want to skip a file, change its role to `exclude`

Columns:

- `Role`
- `Filename`
- `Detected`
- `Group Key`
- `Time (h)`
- `Sample`
- `Confidence`
- `Status`
- `Note`
- `Source`

`Source` shows where the file comes from:

- a dataset-relative path such as `raw\blank.DSW`
- or an external absolute path if it was chosen manually

## Blank Selection

The app tries to detect blank candidates automatically from names like:

- `blank`
- `baseline`
- `base`
- `reference`

You can still override the detected blank by:

- choosing another internal file
- browsing to an external file

## Filename Parsing

The parser supports both `-` and `_`.

Examples:

- `TT-127-t48h-5`
- `TT_127_t48h_5`
- `TT-127-48h-5`

The parser tries to infer:

- time in hours
- sample number
- canonical group key

If the parser is not confident, the row stays editable and should be reviewed manually.

## Validation

The app blocks processing when required information is missing.

Examples of validation errors:

- no blank selected
- missing `Group Key`
- missing `Time (h)`
- duplicate `group + time` mappings
- `Process Only` requested but converted CSV files are missing

Warnings do not block execution, but should still be reviewed.

## Run Modes

### Run

The normal workflow.

Behavior:

- converts `.DSW` to `.csv` when needed
- uses raw `.csv` files directly
- processes grouped outputs
- generates figures if the checkbox is enabled

### Convert Only

Only generates or refreshes converted CSV files.

Use this when:

- you want to inspect raw-to-CSV conversion first
- you want to prepare converted files before using `Process Only`

### Process Only

Processes data without converting `.DSW` files first.

Use this when:

- converted CSV files already exist
- you want to rerun analysis with different roles or settings

Important:

- for `.DSW` inputs, converted CSV files must already exist
- for raw `.csv` inputs, processing can continue directly

### Figures Only

Creates or refreshes figures from an existing processed output folder.

Use this when:

- processed CSV outputs already exist
- you only want updated PNG figures

## Outputs

Each run writes into:

```text
processed\<run_label>\
```

Each sample group gets its own folder:

```text
processed\<run_label>\<group_key>\
```

Important files:

- `raw_...csv`
- `baseline_corrected_...csv`
- `lambda_max_...csv`
- `spectral_overlap_...csv`
- `spectral_decay_...csv`
- `spectral_decay_map_...csv`
- `analysis_...csv`
- `figures\*.png`

Run metadata:

- `_manifest.json`
  - exact mapping and settings used
- `_run.log`
  - run log for traceability

## FAQ

### Do files have to be inside `raw\`?

No.

If the selected folder does not contain `raw\`, the app treats the selected folder itself as raw input.

### Can I use CSV instead of DSW?

Yes.

Raw `.csv` inputs are supported.

### Why is a file not included automatically?

Possible reasons:

- it was detected as a blank candidate
- parsing failed and it needs manual mapping
- you or a previous manifest set it to `exclude`

### Does `Group Key` affect output folders?

Yes.

The `Group Key` becomes the per-group output folder name.
