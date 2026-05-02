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

The image installs C/C++ build tooling, CMake, Make, Git, curl, zstd, and the
CodeQL CLI from the mirrored bundle URL, then pushes the result to the
CubeSandbox VM-local registry before `cubemastercli tpl create-from-image`
creates the template.
