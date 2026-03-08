# 2026-03-08: VulHunter Deployment Rename

## Scope

This change renames deployment-chain `DeepAudit` / `deepaudit` references to `VulHunter` / `vulhunter` only.

Included:

- Docker Compose deployment files
- Dockerfiles used by deployment/build packaging
- Release/deploy shell scripts
- GitHub Actions release / docker publish workflows
- Debian packaging rootfs, control scripts, package/service/CLI naming

Excluded:

- Backend business logic
- Database models and application-level branding outside deployment files
- General documentation outside release/deployment paths

## Goals

- Make deployment-facing names consistently use `VulHunter` / `vulhunter`
- Keep release artifacts, Docker image names, package names, service names, and CLI names aligned
- Avoid partial renames where compose pulls one image name but release workflows still publish another

## Non-Goals

- Full-repo rename
- Runtime code refactor unrelated to deployment
- Backward-compatibility shims for every historical `deepaudit` path or command

## Design

### 1. Compose and Docker image naming

- Rename compose comments and deployment-facing labels to `VulHunter`
- Rename local image tags from `deepaudit/...` to `vulhunter/...`
- Rename GHCR image repositories from `*-deepaudit-*` style to `*-vulhunter-*` style while keeping the existing registry/owner structure intact
- Rename deployment helper defaults such as sandbox image references and compose project/network names

### 2. Dockerfile cache and deployment metadata

- Rename BuildKit cache IDs and deployment-facing comments in `backend/Dockerfile`, `frontend/Dockerfile`, and `frontend/Dockerfile.legacy`
- Rename deployment cache directories that are only used during image build packaging where safe within the deployment chain

### 3. Release / deploy artifact naming

- Rename packaged artifact prefixes from `deepaudit-*` to `vulhunter-*`
- Update deployment extraction scripts to resolve artifacts by generic `*-source-*` / `*-docker-*` patterns so they remain robust after the rename
- Keep release workflow artifact names and human-facing changelog text aligned with the new prefix

### 4. Debian package rename

- Rename package name to `vulhunter`
- Rename config root from `/etc/deepaudit` to `/etc/vulhunter`
- Rename runtime state/log roots to `/var/lib/vulhunter` and `/var/log/vulhunter`
- Rename CLI from `deepauditctl` to `vulhunterctl`
- Rename systemd unit from `deepaudit.service` to `vulhunter.service`
- Rename deployment env keys exposed by the package from `DEEPAUDIT_*` to `VULHUNTER_*`

## Risk Notes

- Changing database default names inside compose is deployment-visible and will change fresh-install defaults. This is acceptable for this scoped deployment rename.
- Existing operators using old package paths, env keys, service names, or artifact names may need to update automation.
- The release and docker-publish workflows must be updated together with compose templates to avoid publishing the old image names.

## Verification

- No `deepaudit` / `DeepAudit` remains in the approved deployment-chain files
- Shell scripts pass `bash -n`
- GitHub workflow YAML parses via `python3 -c 'import yaml,sys; yaml.safe_load(...)'` when PyYAML is available, otherwise at least plain syntax checks via inspection
- Debian packaging script still references the renamed rootfs paths consistently

