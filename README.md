# CBS Server Billing

This repository contains code meant to process CBS Server registration spreadsheets and automatically generate quarterly billing reports.

The conceptual model here is that you've got a set of `cbsserverbilling.records.BillableProjectRecord`s derived from some data source (only spreadsheets are currently implemented (in `cbsserverbilling.spreadsheet`. `cbsserverbilling.policy.BillingPolicy` knows how to take a record and produce a bill for that project, and `cbsserverbilling.billing` has some functions to produce a bill for multiple projects.

There's a command line entry point at `cbsserverbilling.main.main`, but this will mostly be called by a Snakemake workflow that wraps it.

## Usage

```
cbsserverbilling <pi_form> <pi_update_form> <user_form> <user_update_form> <quarter_start> <out_dir>
```

| Argument | Description |
|---|---|
| `pi_form` | Path to the PI account request spreadsheet (`.xlsx`) |
| `pi_update_form` | Path to the PI/storage update spreadsheet (`.xlsx`) |
| `user_form` | Path to the user account request spreadsheet (`.xlsx`) |
| `user_update_form` | Path to the user update spreadsheet (`.xlsx`) |
| `quarter_start` | ISO-format date for the first day of the billing quarter (e.g. `2024-01-01`) |
| `out_dir` | Directory to write all output artefacts |

### Optional flags

| Flag | Description |
|---|---|
| `--no-quarantine` | Raise an error on any invalid input row instead of quarantining it and continuing |

## Output artefacts

All outputs are written to `<out_dir>/`:

| File | Description |
|---|---|
| `summary_<quarter_start>.xlsx` | Summary spreadsheet with storage and compute charges for each billable PI |
| `pi-<name>_started-<date>_quarter-<date>_bill.tex` | Per-PI LaTeX bill (one file per billable PI) |
| `quarantine_<sheet_name>.csv` | Invalid rows from each input sheet (only written when invalid rows are found) |
| `users_snapshot_<quarter_end>.csv` | Current state of all active users as of the quarter-end date |
| `projects_snapshot_<quarter_end>.csv` | Current state of all active projects as of the quarter-end date |

## Validation and quarantine

Each input sheet is validated after loading.  Row-level checks include:

- **Emails** — must be a non-empty string matching `<local>@<domain>.<tld>`.
- **Timestamps** — must be parseable as a date/datetime.
- **Storage values** — must be numeric and non-negative.
- **Boolean fields** (`power_user`, `pi_is_power_user`) — must be a boolean or boolean-equivalent value.
- **Speed codes** — must be a non-empty string.
- **Required string fields** (`last_name`, `pi_last_name`, etc.) — must be non-empty.

Any row that fails one or more checks is **quarantined**: it is removed from the pipeline and written to `quarantine_<sheet_name>.csv` alongside the other outputs.  Each quarantined row includes a `_quarantine_errors` column that lists every check that failed, with the Excel row number for easy cross-referencing.

**Missing required columns** (e.g. if a spreadsheet export is missing an expected header) are a hard failure: the run is aborted immediately with a `ColumnError` message that lists the missing column names.

## Quarter-end snapshots

After generating bills, the pipeline writes two CSV snapshots that capture the **current state** of every active user and project as of the quarter-end date:

- `users_snapshot_<quarter_end>.csv` — columns: `email`, `name`, `start_date`, `end_date`, `pi_name`, `is_power_user`
- `projects_snapshot_<quarter_end>.csv` — columns: `email`, `pi_last_name`, `open_date`, `close_date`, `storage_tb`, `speed_code`

These snapshots are intended to make it easy to audit "what state was the billing database in at quarter end?" without having to replay the entire event log.

## Module overview

| Module | Description |
|---|---|
| `cbsserverbilling.validation` | Row-level validation and quarantine logic for all input sheets |
| `cbsserverbilling.snapshot` | Quarter-end snapshot and quarantine file writing |
| `cbsserverbilling.spreadsheet.io` | Load functions (`load_*_df`) and ingest wrappers (`ingest_*_df`) that combine loading + validation |
| `cbsserverbilling.spreadsheet.record` | Assembles `BillableProjectRecord` objects from DataFrames |
| `cbsserverbilling.policy` | All billing policy calculations |
| `cbsserverbilling.billing` | High-level bill generation and summary functions |
| `cbsserverbilling.main` | CLI entry point |

