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

## 4. Create the Python Code Template

```bash
scripts/cubesandbox-quickstart.sh create-template
```

The command prints a `job_id`. Watch it until the template reaches `READY`:

```bash
scripts/cubesandbox-quickstart.sh watch-template <job_id>
```

Record the printed `template_id`.

## 5. Run Python in CubeSandbox

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

## 6. Verify C/C++ Compilation in CubeSandbox

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
