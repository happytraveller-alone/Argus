# CubeSandbox Python Quickstart

This repo keeps CubeSandbox setup separate from Argus services. CubeSandbox
is configured in the WSL2 environment directly, not in a Docker helper
container. It needs KVM, QEMU, Docker, and a disposable development VM; Argus
already uses host port `13000`, so the helper forwards CubeSandbox's
E2B-compatible API to `127.0.0.1:23000` by default.

All GitHub URLs go through the required mirror:
`https://v6.gh-proxy.org/https://github.com/...`.

## 1. Prepare WSL2

Install the host-side VM tools in WSL2:

```bash
sudo apt-get update
sudo apt-get install -y qemu-system-x86 qemu-utils
```

If `apt-get update` only fails on unrelated Launchpad PPAs such as
`deadsnakes` or `git-core`, first check whether QEMU is still available from
the Ubuntu jammy main/update/security indexes:

```bash
apt-cache policy qemu-system-x86 qemu-utils
```

If both packages show a `Candidate`, continue with the install command above.
To make `apt-get update` fully clean before installing, temporarily disable
the unreachable PPA list files and refresh again:

```bash
sudo mv /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-jammy.list \
  /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-jammy.list.disabled
sudo mv /etc/apt/sources.list.d/git-core-ubuntu-ppa-jammy.list \
  /etc/apt/sources.list.d/git-core-ubuntu-ppa-jammy.list.disabled
sudo apt-get update
sudo apt-get install -y qemu-system-x86 qemu-utils
```

If `/dev/kvm` exists but is not writable, add the user to the `kvm` group and
start a new WSL login session:

```bash
sudo usermod -aG kvm "$USER"
```

If an earlier Docker-based attempt left root-owned VM files under
`.cubesandbox/vm`, either remove that disposable VM state or fix ownership
before preparing the VM natively:

```bash
sudo rm -rf .cubesandbox/vm
# or:
sudo chown -R "$USER:$USER" .cubesandbox/vm
```

Then verify the WSL2-native prerequisites:

```bash
scripts/cubesandbox-quickstart.sh doctor
```

The check must report:

- WSL2 kernel detected
- `qemu-system-x86_64` and `qemu-img` installed
- Docker daemon reachable
- `/dev/kvm` exists and is readable/writable by the current user
- nested KVM enabled
- ports `10022`, `21080`, `21443`, `22088`, and `23000` free

## 2. Prepare and Boot the VM

```bash
scripts/cubesandbox-quickstart.sh fetch
scripts/cubesandbox-quickstart.sh prepare-vm
scripts/cubesandbox-quickstart.sh run-vm
```

Keep the `run-vm` terminal open. In another terminal, log into the VM:

```bash
scripts/cubesandbox-quickstart.sh login
```

## 3. Install CubeSandbox

From the host, after the VM is booted and SSH is reachable:

```bash
scripts/cubesandbox-quickstart.sh install
```

For China mirror mode inside the CubeSandbox installer:

```bash
CUBE_MIRROR=cn scripts/cubesandbox-quickstart.sh install
```

The default install path also exports:

- `ALPINE_MIRROR_URL=http://mirrors.aliyun.com/alpine`
- `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple`

Check the API health through the Argus-safe forwarded port:

```bash
scripts/cubesandbox-quickstart.sh status
```

## 4. Configure Docker Mirrors in the VM

Configure the VM Docker daemon to prefer DaoCloud for Docker Hub traffic:

```bash
scripts/cubesandbox-quickstart.sh configure-docker-mirror
```

The helper writes `/etc/docker/daemon.json` with:

```json
{
  "registry-mirrors": [
    "https://m.daocloud.io/docker.io"
  ]
}
```

For image references that must bypass Docker's transparent registry mirror
behavior, use the explicit Docker Hub replacement form:

```text
m.daocloud.io/docker.io/<namespace>/<image>:<tag>
```

The helper uses that explicit form for the local registry image:
`m.daocloud.io/docker.io/library/registry:2`.

## 5. Create the Python Code Template

```bash
scripts/cubesandbox-quickstart.sh create-template
```

The command prints a `job_id`. Watch it until the template reaches `READY`:

```bash
scripts/cubesandbox-quickstart.sh watch-template <job_id>
```

Record the printed `template_id`.

## 6. Run Python in CubeSandbox

```bash
CUBE_TEMPLATE_ID=<template_id> scripts/cubesandbox-quickstart.sh python-smoke
```

The smoke command installs `e2b-code-interpreter` inside the VM if needed, sets
`E2B_API_URL=http://127.0.0.1:3000` for the in-VM CubeSandbox API, creates a
sandbox from the template, and runs:

```python
print('Hello from Cube Sandbox, safely isolated!')
```

To run a different one-liner:

```bash
CUBE_TEMPLATE_ID=<template_id> \
CUBE_PYTHON_CODE="print(sum(range(10)))" \
scripts/cubesandbox-quickstart.sh python-smoke
```

## 7. Run Python Through Argus

Argus also exposes a Rust-owned CubeSandbox task API. The helper remains the
bounded lifecycle adapter, but backend execution does not call
`python-smoke`: it checks/starts CubeSandbox through the allowlisted helper
commands, creates a sandbox through CubeAPI, runs Python through the envd data
plane, records normalized output, and deletes the sandbox.

Runtime defaults are seeded from `env.example`, then saved
`system_config.otherConfig.cubeSandbox` becomes the source of truth:

```text
CUBESANDBOX_ENABLED=false
CUBESANDBOX_API_BASE_URL=http://host.docker.internal:23000
CUBESANDBOX_DATA_PLANE_BASE_URL=https://host.docker.internal:21443
CUBESANDBOX_TEMPLATE_ID=
CUBESANDBOX_HELPER_PATH=/app/scripts/cubesandbox-quickstart.sh
CUBESANDBOX_WORK_DIR=.cubesandbox
CUBESANDBOX_AUTO_START=false
CUBESANDBOX_AUTO_INSTALL=false
```

The Docker Compose backend service maps `host.docker.internal` to the Docker
host gateway so a containerized backend can call a host-managed CubeSandbox VM.
Keep `CUBESANDBOX_AUTO_START=false` for that deployment shape; local lifecycle
helper commands are only used when both CubeSandbox control and data-plane URLs
target localhost.

In the System Config page, enable CubeSandbox and save the `templateId`
created above. Then submit a Python task:

```bash
curl -sS -X POST http://localhost:18000/api/v1/cubesandbox-tasks \
  -H 'content-type: application/json' \
  -d '{"code":"print(sum(range(10)))"}'
```

Poll the returned task:

```bash
curl -sS http://localhost:18000/api/v1/cubesandbox-tasks/<task_id>
```

A successful smoke ends with `status="completed"`, `stdout` containing `45`,
and `cleanupStatus="completed"`. `DELETE /api/v1/cubesandbox-tasks/<task_id>`
is accepted only after the task is terminal; use
`POST /api/v1/cubesandbox-tasks/<task_id>/interrupt` for a non-terminal task.

## 8. Verify C/C++ Compilation in CubeSandbox

The upstream `sandbox-code` image currently includes `gcc` and `g++`. Verify
that the template can compile and run both C and C++ programs:

```bash
CUBE_TEMPLATE_ID=<template_id> scripts/cubesandbox-quickstart.sh cc-smoke
```

Expected sandbox stdout includes:

```text
C_OK:42
CPP_OK:10
```

## 9. Build a CMake/Make/CodeQL C++ Template

The base Python template does not include `cmake` or `codeql`. Build a local
CodeQL C++ image inside the CubeSandbox VM, push it to the VM-local registry,
and create a CubeSandbox template from it:

```bash
scripts/cubesandbox-quickstart.sh configure-docker-mirror
scripts/cubesandbox-quickstart.sh start-local-registry
scripts/cubesandbox-quickstart.sh build-codeql-cpp-image
scripts/cubesandbox-quickstart.sh create-codeql-cpp-template
```

The image build definition is stored in
`oci/cubesandbox/codeql-cpp.Dockerfile`. The helper copies that OCI image
configuration into the CubeSandbox VM and injects the local registry image and
CodeQL bundle URL as build arguments.

To build and enter the same CodeQL C++ image directly from WSL without using
the CubeSandbox VM-local registry:

```bash
scripts/cubesandbox-quickstart.sh build-codeql-cpp-image-wsl
scripts/cubesandbox-quickstart.sh shell-codeql-cpp-image-wsl
```

The WSL-local image defaults to `argus/cubesandbox-codeql-cpp:latest`; override
it with `CUBE_CODEQL_CPP_WSL_IMAGE=...` when needed.

`build-codeql-cpp-image` keeps Docker Hub references in explicit DaoCloud
replacement form and rewrites Debian 13 apt sources to Aliyun mirrors inside
the image build. It installs:

- `gcc` / `g++`
- `make`
- `cmake`
- `git`, `curl`, `zstd`, and related build utilities
- CodeQL CLI from the mirrored GitHub bundle URL

Defaults:

- Local registry image: `m.daocloud.io/docker.io/library/registry:2`
- Built image: `127.0.0.1:5000/cubesandbox-codeql-cpp:latest`
- CodeQL bundle: `https://v6.gh-proxy.org/https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.20.5/codeql-bundle-linux64.tar.zst`
- Writable layer size: `4G`

Watch the printed `job_id` until the template reaches `READY`:

```bash
scripts/cubesandbox-quickstart.sh watch-template <job_id>
```

Verified local result on 2026-05-02:

```text
job_id: 6404e1a4-1749-4f31-94fd-85f7fe19295f
template_id: tpl-a4d03d6bf9ac406e9fb6a457
artifact_id: rfs-29298e35a03e8e46b702482c
template_status: READY
```

Run the full C/C++/Make/CMake/CodeQL smoke:

```bash
CUBE_TEMPLATE_ID=tpl-a4d03d6bf9ac406e9fb6a457 \
  scripts/cubesandbox-quickstart.sh codeql-cpp-smoke
```

The smoke verifies:

- `gcc --version`
- `g++ --version`
- `make --version`
- `cmake --version`
- `codeql version`
- C compile and run
- C++ Makefile build and run
- CMake configure/build and run
- `codeql database create --language=cpp --command "cmake --build build"`
- `codeql database analyze` against a bundled C/C++ query pack query
- SARIF `2.1.0` output with at least one run

Expected success markers include:

```text
C_OK:42
CPP_OK:10
CODEQL_DB_OK True
CODEQL_ANALYZE_OK True
CODEQL_SARIF_OK True
```
