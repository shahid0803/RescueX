# Dataset and download procedure

No large dataset is downloaded in Phase 0.

## Permitted training candidates

- **Kuro Siwo:** recommended by the challenge. Record the official source,
  version, license, access date, and citation in the experiment manifest
  before downloading.
- **Sen1Floods11:** optional challenge-permitted alternative. Record the
  official source, version, license, access date, and citation before use.

Do not add a dataset to the registry merely because it is useful. It must be
explicitly allowed by the challenge and have a documented source/license.
Do not use EMSR927, UNOSAT, or another published damage map as training data.

## Required download record

Every artifact needs: dataset/source ID, URL or provider reference, version,
license/citation, retrieval timestamp, archive checksum, extraction path,
geographic/scene split assignment, and preprocessing version.

## Safe workflow

1. Review the registry and challenge permission.
2. Create a small, documented sample or metadata-only manifest.
3. Verify checksum and license.
4. Store raw data outside git (for example `RESCUEX_DATA_DIR`).
5. Generate derived artifacts with a versioned configuration.
6. Keep train/validation/test geography disjoint where possible.
