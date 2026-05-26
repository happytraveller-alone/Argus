# third_party_lib (vendored)

Stub vendored library used by the `monorepo_bazel_cargo` fixture to exercise
vendor-path exclusion. All files under `vendor/` are expected to be filtered
out of the audit's source-path inclusion when the codegraph handoff supplies
`vendor_paths: ["vendor/"]`.
