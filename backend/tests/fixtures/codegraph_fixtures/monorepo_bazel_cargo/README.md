# Fixture: monorepo_bazel_cargo (v0.3.b)

Real mixed-build-system monorepo fixture used by `codegraph_ac3_acceptance` to
replace the in-test mocked file list from v0.2. Exercises:

- **Language detection**: Python (`services/api/main.py`), Rust
  (`crates/auth/src/lib.rs`), Java (`services/legacy-java/...`).
- **Vendor exclusion ratio**: when the codegraph handoff supplies
  `vendor_paths: ["vendor/"]`, all files under `vendor/third_party_lib/`
  must be excluded. The dual-run protocol asserts ≥80% reduction.

## Build systems present
- `BUILD.bazel` + `services/api/BUILD` — Bazel
- `Cargo.toml` (workspace) + `crates/auth/Cargo.toml` — Cargo
- `pom.xml` (aggregator) + `services/legacy-java/pom.xml` — Maven

## Vendor subtree (excluded)
- `vendor/third_party_lib/LICENSE`
- `vendor/third_party_lib/helper.py`
- `vendor/third_party_lib/parser.py`
- `vendor/third_party_lib/README.md`

## Asserted by the test
1. Vendor files in run #1 (with `vendor_paths: ["vendor/"]` exclusion) = 0.
2. Vendor files in run #2 (no handoff) = 4 (all files under `vendor/`).
3. Reduction = 100% ≥ 80% threshold (AC2.D / v0.2).
