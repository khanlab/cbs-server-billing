# CBS Server Billing

This repository contains code meant to process CBS Server registration spreadsheets and automatically generate quarterly billing reports.

The conceptual model here is that you've got a set of `cbsserverbilling.records.BillableProjectRecord`s derived from some data source (only spreadsheets are currently implemented (in `cbsserverbilling.spreadsheet`. `cbsserverbilling.policy.BillingPolicy` knows how to take a record and produce a bill for that project, and `cbsserverbilling.billing` has some functions to produce a bill for multiple projects.

There's a command line entry point at `cbsserverbilling.main.main`, but this will mostly be called by a Snakemake workflow that wraps it.

