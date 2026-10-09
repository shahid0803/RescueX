# Phase 8A implementation report

## Historical boundary

`PHASE7_IMPLEMENTATION_REPORT.md` and `PHASE8_IMPLEMENTATION_REPORT.md` were
not present in this checkout when Phase 8A began. The existing
`PHASE7_EXECUTION_STATUS.md`, `PHASE8_EXECUTION_STATUS.md`, audit script, and
manifests were read as historical records and were not rewritten.

## Change

The previous Phase 8 readiness script computed one global `NO_GO` from CDSE
credentials, Kuro Siwo files, a checkpoint, and a Trishuli AOI. That coupled
independent dependencies. The replacement writes separate records for:

- `cdse`
- `kuro_siwo`
- `ohsome`
- `ml_training`
- `sentinel_inference`
- `trishuli`
- `emsr927_validation`

Each record has `status`, `checked_at`, `dependencies`, `evidence`, `blockers`,
and `notes`. Supported statuses are `READY`, `BLOCKED`, `NOT_CHECKED`,
`PARTIAL`, and `FAILED`.

CDSE credentials now gate Sentinel acquisition/inference only. Kuro Siwo
readiness and ML training readiness are evaluated independently; OHSOME
reachability is evaluated independently; EMSR927 remains validation-only.
`overall_status` reports `PARTIAL_READINESS` when at least one independent
domain is ready or partial while another is blocked.

## Current execution

At implementation time, no Kuro Siwo files, real checkpoint, or real mask were
present. CDSE credentials were absent. The current report therefore remains
blocked/partial where evidence supports it; no domain is marked ready merely
because code exists. The OHSOME endpoint probe is only reachability evidence,
not a historical AOI extraction.

Run:

```powershell
python scripts/phase8_readiness.py
python scripts/phase8_readiness.py --domain kuro-siwo
python scripts/phase8_readiness.py --domain cdse
python scripts/phase8_readiness.py --domain ohsome
python scripts/phase8_readiness.py --domain trishuli
```
