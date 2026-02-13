# Seed Assets

These archives are used by the VulHunter backend during database initialization.

This directory stores offline seed archives used by database initialization.

## libplist default project

- Archive file: `libplist-2.7.0.zip`
- Upstream source: `https://github.com/libimobiledevice/libplist/archive/refs/tags/2.7.0.zip`
- Used by: `app/db/init_db.py` during `ensure_default_libplist_project(...)`

## Update procedure

1. Download a new upstream release archive.
2. Replace `libplist-2.7.0.zip` with the target version archive.
3. Update the constants in `app/db/init_db.py`:
   - `DEFAULT_LIBPLIST_ARCHIVE_NAME`
   - `DEFAULT_LIBPLIST_LOCAL_ZIP_PATH`
   - Optional description text if needed.
4. Run backend tests related to init seed and project description.
