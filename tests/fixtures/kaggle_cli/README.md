# Recorded Kaggle CLI output (CLI 2.2.4, 2026-11-06)

Real output from the M3 spike runs on profile `sunny`, **redacted**: the account name is replaced by `aas-test-user`,
GPU UUIDs are zeroed, and no file contains a token. Used by `tests/unit/test_kaggle_cli.py`.

| File | Command |
|---|---|
| `quota.json.txt` | `kaggle quota --format json` |
| `status_running.txt`, `status_complete.txt` | `kaggle kernels status <owner>/<slug>` |
| `status_cannot_access.*` | the same, seconds after a push, or with the wrong owner (exit code 1) |
| `push_ok.txt` | `kaggle kernels push -p DIR --timeout 900 --accelerator NvidiaTeslaT4` |
| `config_view.txt` | `kaggle config view` with `KAGGLE_API_TOKEN` set |
| `logs_blob_t4x2.txt` | `kaggle kernels logs <owner>/<slug>` after a T4×2 run (trimmed) |
| `logs_blob_running.txt` | the same while the run is still running (the blob is empty) |
| `network_error.*` | a dropped connection during `kernels status` (exit code 1) |
| `quota_old_cli.stderr.txt` | **synthetic**: argparse's error for a CLI without `quota` (< 2.2.1), not recorded |
