# CubeSandbox OCI Images

This directory stores CubeSandbox image configuration used by Argus helper
workflows. It mirrors the upstream CubeSandbox convention of keeping image
definitions as Dockerfiles, but keeps Argus-specific images outside the
default `docker/` Compose service tree.

## `codeql-cpp.Dockerfile`

Builds the CubeSandbox CodeQL C/C++ template image described in
`docs/cubesandbox-python-quickstart.md`.

Source conventions:

- CubeSandbox dev VM and template workflow:
  `.cubesandbox/CubeSandbox/dev-env/README.md`
- CubeSandbox upstream image-definition style:
  `.cubesandbox/CubeSandbox/docker/README.md`
- Argus CodeQL template requirements:
  `docs/cubesandbox-python-quickstart.md`

Runtime defaults are injected by `scripts/cubesandbox-quickstart.sh`:

- `CUBE_LOCAL_REGISTRY_IMAGE`
- `CUBE_CODEQL_BUNDLE_URL`
- `CUBE_CODEQL_CPP_IMAGE`
- `CUBE_CODEQL_CPP_WSL_IMAGE`

The image installs C/C++ build tooling, CMake, Make, Git, curl, zstd, and the
CodeQL CLI from the mirrored bundle URL, then pushes the result to the
CubeSandbox VM-local registry before `cubemastercli tpl create-from-image`
creates the template.

For WSL-local inspection without the CubeSandbox VM registry, use:

```bash
scripts/cubesandbox-quickstart.sh build-codeql-cpp-image-wsl
scripts/cubesandbox-quickstart.sh shell-codeql-cpp-image-wsl
```

### Storage axes and slim stages (2026-05-04 rework)

`codeql-cpp.Dockerfile` slims the upstream `sandbox-code:latest` base in two
sequential stages:

- **Stage 0** removes e2b/code-interpreter runtime trees (Jupyter packages,
  NumPy/Pandas/SciPy/torch/etc., Node ecosystem, JVM, e2b user trees). This
  is the slim that originally landed in commit `25b8b9ad`.
- **Stage 0.5** (new on 2026-05-04) drops alternate language runtimes and
  decoration NOT needed for the codeql-cpp scan or the sandbox-code envd
  agent: `/opt/deno`, `/usr/lib/go-1.24` + `/usr/share/go-1.24`, `/usr/lib/R`
  + `/usr/share/R`, `/usr/share/perl5` + `/usr/bin/perl*` + system Perl libs,
  `/usr/lib/python3.13` (only — `python3.11`/`python3.12` are explicitly
  preserved for envd), `/usr/share/{fonts,icons,gir-1.0,applications,hwdata,X11}`.
  A Python-preserve sanity check fails the build if neither `python3.11` nor
  `python3.12` imports after the slim.

The slimmed rootfs lands at ~2.8 GiB → `next_pow_of_2(2.8 + 1) = 4 GiB` ext4
image with ~970 MB of mkfs.ext4 metadata headroom. The runtime writable layer
is sized separately via `--writable-layer-size 16Gi` so the CodeQL database
and trap caches have room. The full storage architecture (template ext4 vs
runtime writable layer) is documented in `.omc/skills/cubesandbox-storage-axes-expertise.md`.

### Probe port: 49983 (envd) — NOT 49999 (uvicorn)

`cubemastercli tpl create-from-image --probe 49983` for codeql-cpp; the
slimmed image's uvicorn at 49999 never binds because Stage 0 removes the
`jupyter_core` Python package and uvicorn waits forever on `localhost:8888`
for jupyter. Argus's codeql runner uses envd directly (the
`run_command`/`run_python` paths in `backend/src/runtime/cubesandbox/client.rs`
all hit the envd `/process` endpoint), so probing envd both avoids the
uvicorn deadlock and tests the path argus actually depends on.

`scripts/cubesandbox-quickstart.sh codeql-cpp-smoke` is incompatible with the
slimmed image because it uses the e2b code-interpreter Python SDK, which
talks through the cube-api openresty proxy to uvicorn on 49999 → returns 502
Bad Gateway. Use the argus end-to-end task path
(`POST /api/v1/static-tasks/codeql/tasks`) for actual verification — it goes
through envd and is unaffected.

### Cubesandbox submodule patches

The ext4 sizing formula is patched in the cubesandbox submodule from
`+256 MB` overhead to `+1 GiB` overhead at
`third_party/cubesandbox/CubeMaster/pkg/templatecenter/template_image.go:1508`.
The same patch must be applied to the install copy at
`.cubesandbox/CubeSandbox/CubeMaster/pkg/templatecenter/template_image.go:1508`
because `cubesandbox-quickstart.sh install` is a one-way copy and the
deployed cubemaster binary is built from the install tree. See
`oci/cubesandbox/PATCHES.md` (P1) for the full patch + operator runbook
(concurrent-sandbox ceiling, post-install verification commands, post-rebase
replay checklist).

## `opengrep.Dockerfile`

Builds the CubeSandbox Opengrep template image used when a static audit task
selects `OCI CubeSandbox 沙箱` in the Opengrep advanced configuration.

The image intentionally does **not** reuse the `codeql-cpp.Dockerfile`
`sandbox-code` base. It starts from an independent Debian slim runtime
(`CUBE_OPENGREP_BASE_IMAGE`, defaulting to the DaoCloud mirror of
`debian:trixie-slim`), installs only the Opengrep wrapper runtime
dependencies, copies Argus's `docker/opengrep-scan.sh` wrapper, and embeds the
checked-in `backend/assets/scan_rule_assets/rules_opengrep` rule bundle as
`/opt/opengrep/rules.tar.gz`.

The final image also copies the CubeSandbox `envd` binary from the upstream
`cubesandbox-base` image in a separate build stage. The final base remains the
independent Debian slim image; `envd` only provides the CubeSandbox control
plane on port `49983` so template creation can probe `/health` and the backend
can execute `opengrep-scan` through envd.

Runtime defaults are injected by `scripts/cubesandbox-quickstart.sh`:

- `CUBE_OPENGREP_IMAGE`
- `CUBE_OPENGREP_WSL_IMAGE`
- `CUBE_OPENGREP_BASE_IMAGE`
- `CUBE_ENVD_BASE_IMAGE`
- `CUBE_OPENGREP_WRITABLE_LAYER_SIZE`
- `CUBE_OPENGREP_DOCKERFILE`

`CUBE_ENVD_BASE_IMAGE` defaults to the `ghcr.nju.edu.cn` mirror for reliable
local/VM pulls, but it is still the upstream
`tencentcloud/cubesandbox-base:2026.16` image and is used only as a source for
`/usr/bin/envd`.

The public lifecycle API remains `/api/v1/cubesandbox/templates/opengrep` for
compatibility, but current backend rows are stored as
`kind='opengrep_dedicated'`. Responses keep `kind: "opengrep"` and expose the
stored kind as `recordKind`.

For WSL-local inspection without the CubeSandbox VM registry, use:

```bash
scripts/cubesandbox-quickstart.sh build-opengrep-image-wsl
scripts/cubesandbox-quickstart.sh shell-opengrep-image-wsl
```

## `sandbox-code:latest` Source Trace

Only `codeql-cpp.Dockerfile` extends
`ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest` because the Argus
quickstart uses that same CubeSandbox code-template image. No matching
Dockerfile for `sandbox-code:latest` is present in the checked-out upstream
CubeSandbox source under `.cubesandbox/CubeSandbox`.

Trace summary: No matching Dockerfile for `sandbox-code:latest` is vendored in
this repository.

Registry metadata for the image points at an OCI manifest whose annotations
identify `localhost/e2bdev/code-interpreter:ags` as the base image and Docker
official Python `3.12.13-trixie` as the lower base. Treat the exact
`sandbox-code:latest` build recipe as an upstream/prebuilt image artifact, not
as a reproducible Dockerfile currently vendored in this repository.
