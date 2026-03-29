# Seed Archives

Default demo projects are no longer stored as repo-tracked ZIP files.

## Runtime behavior

- On backend startup, `app/db/init_db.py` ensures the default GitHub-backed seed projects exist for the demo user.
- If a project ZIP is not stored yet, backend builds the pinned GitHub archive URL, probes configured mirror candidates plus the official GitHub source, then downloads the fastest reachable archive.
- With Docker Compose defaults:
  - Postgres data is persisted in `postgres_data`.
  - ZIP files are persisted in `backend_uploads` (`/app/uploads/zip_files`).
- Result: after the first successful install, the projects are reused across restarts/rebuilds without re-downloading.

## Managed seed projects

- `libplist` → `libimobiledevice/libplist@tag:2.7.0`
- `DVWA` → `digininja/DVWA@commit:eba982f486aef10fd4278948cd1bb078504b74e7`
- `DSVW` → `stamparm/DSVW@commit:7d40f4b7939c901610ed9b85724552d60e7d63fa`
- `WebGoat` → `WebGoat/WebGoat@commit:7d3343d08c360d4751e5298e1fe910463b7731a1`
- `JavaSecLab` → `whgojp/JavaSecLab@tag:V1.4`
- `govwa` → `0c34/govwa@commit:4058f79f31eeb4a36d8f1e64bba1f0c899646e6f`
- `fastjson` → `alibaba/fastjson@commit:c942c83443117b73af5ad278cc780270998ba3e1`

## Update procedure

1. Update the pinned seed manifest in `backend/app/db/init_db.py`.
2. Adjust probe/download settings in `docker/env/backend/env.example` if mirror behavior needs tuning.
3. Run backend seed tests:
   - `cd backend && ./.venv/bin/pytest tests/test_seed_archive.py tests/test_init_db_libplist_seed.py -q`
