# python_sqli_vendor_negative

This fixture demonstrates a non-actionable finding in **vendored** code. The
vulnerable shape (Flask handler → parser → f-string SQL interpolation) is
**identical** to `python_sqli/` but the entire fixture lives under
`vendor/python_sqli_vendor_negative/` — the conventional third-party-pin
location for Python projects (akin to Go's `vendor/`, Node's `node_modules/`).

The audit pipeline's path classifier (`path_classifier.rs`) MUST recognize the
`vendor/` component and emit `category=vendor`, `confidence_source=path_pattern`,
and `path_pattern="vendor/"`. No structural analysis is required to dismiss
this finding — the path alone is sufficient: vendored code is outside the
first-party patch scope, so the internal reviewer cannot fix the sink here.

This is a static-analysis test fixture demonstrating non-first-party code
classification. It is NOT a real application and MUST NOT be deployed.
