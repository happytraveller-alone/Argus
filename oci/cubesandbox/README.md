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

## `sandbox-code:latest` Source Trace

`codeql-cpp.Dockerfile` extends
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
