# VulHunter Deployment Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename deployment-chain `DeepAudit` / `deepaudit` references to `VulHunter` / `vulhunter` across compose files, Dockerfiles, release/deploy scripts, workflows, and Debian packaging.

**Architecture:** Keep the change focused on deployment-facing assets only. Update all release/publish/package layers together so Docker image names, artifact names, package names, service names, and CLI entrypoints stay internally consistent after the rename.

**Tech Stack:** Docker Compose, Dockerfiles, Bash, GitHub Actions YAML, Debian packaging scripts

---

### Task 1: Update compose and Dockerfiles

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.prod.cn.yml`
- Modify: `docker-compose.build.yml`
- Modify: `docker-compose.override.yml`
- Modify: `docker-compose.frontend-dev.yml`
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`
- Modify: `frontend/Dockerfile.legacy`

**Step 1: Write the failing check**

Run:

```bash
rg -n -i 'deepaudit' docker-compose.yml docker-compose.prod.yml docker-compose.prod.cn.yml docker-compose.build.yml docker-compose.override.yml docker-compose.frontend-dev.yml backend/Dockerfile frontend/Dockerfile frontend/Dockerfile.legacy
```

Expected: matches are present.

**Step 2: Implement the rename**

- Replace deployment-facing `DeepAudit` / `deepaudit` names with `VulHunter` / `vulhunter`
- Keep the change limited to the approved deployment-chain files

**Step 3: Verify the check turns green**

Run:

```bash
rg -n -i 'deepaudit' docker-compose.yml docker-compose.prod.yml docker-compose.prod.cn.yml docker-compose.build.yml docker-compose.override.yml docker-compose.frontend-dev.yml backend/Dockerfile frontend/Dockerfile frontend/Dockerfile.legacy
```

Expected: no output.

### Task 2: Update release and deploy scripts

**Files:**
- Modify: `scripts/package-release-artifacts.sh`
- Modify: `scripts/deploy-release-artifacts.sh`
- Modify: `scripts/compose-up-with-fallback.sh`

**Step 1: Write the failing check**

Run:

```bash
rg -n -i 'deepaudit' scripts/package-release-artifacts.sh scripts/deploy-release-artifacts.sh scripts/compose-up-with-fallback.sh
```

Expected: matches are present.

**Step 2: Implement the rename and script cleanup**

- Rename artifact prefixes and image names to `vulhunter`
- Make deploy artifact resolution generic enough for renamed artifact prefixes
- Rename deployment env variables to `VULHUNTER_*`

**Step 3: Verify script syntax**

Run:

```bash
bash -n scripts/package-release-artifacts.sh scripts/deploy-release-artifacts.sh scripts/compose-up-with-fallback.sh
```

Expected: exit code 0.

### Task 3: Update GitHub release/publish workflows

**Files:**
- Modify: `.github/workflows/docker-publish.yml`
- Modify: `.github/workflows/release.yml`

**Step 1: Write the failing check**

Run:

```bash
rg -n -i 'deepaudit' .github/workflows/docker-publish.yml .github/workflows/release.yml
```

Expected: matches are present.

**Step 2: Implement the rename**

- Rename published GHCR image names and release artifact names to `vulhunter`
- Update release summary / changelog text to match

**Step 3: Verify the check turns green**

Run:

```bash
rg -n -i 'deepaudit' .github/workflows/docker-publish.yml .github/workflows/release.yml
```

Expected: no output.

### Task 4: Rename Debian packaging assets

**Files:**
- Modify: `packaging/deb/build_deb.sh`
- Modify: `packaging/deb/debian/control`
- Modify: `packaging/deb/debian/conffiles`
- Modify: `packaging/deb/debian/postinst`
- Modify: `packaging/deb/debian/prerm`
- Modify: `packaging/deb/debian/postrm`
- Rename: `packaging/deb/rootfs/etc/deepaudit` → `packaging/deb/rootfs/etc/vulhunter`
- Rename: `packaging/deb/rootfs/usr/bin/deepauditctl` → `packaging/deb/rootfs/usr/bin/vulhunterctl`
- Rename: `packaging/deb/rootfs/etc/systemd/system/deepaudit.service` → `packaging/deb/rootfs/etc/systemd/system/vulhunter.service`

**Step 1: Write the failing check**

Run:

```bash
rg -n -i 'deepaudit' packaging/deb/build_deb.sh packaging/deb/debian packaging/deb/rootfs
```

Expected: matches are present.

**Step 2: Implement the rename**

- Rename package/service/CLI/path/env-key references to `vulhunter`
- Update the packaging build script to stage the renamed paths and binary names

**Step 3: Verify the check turns green**

Run:

```bash
rg -n -i 'deepaudit' packaging/deb/build_deb.sh packaging/deb/debian packaging/deb/rootfs
```

Expected: no output.

### Task 5: Final verification

**Files:**
- Verify only

**Step 1: Run focused rename scan**

```bash
rg -n -i 'deepaudit' docker-compose.yml docker-compose.prod.yml docker-compose.prod.cn.yml docker-compose.build.yml docker-compose.override.yml docker-compose.frontend-dev.yml backend/Dockerfile frontend/Dockerfile frontend/Dockerfile.legacy scripts/package-release-artifacts.sh scripts/deploy-release-artifacts.sh scripts/compose-up-with-fallback.sh .github/workflows/docker-publish.yml .github/workflows/release.yml packaging/deb/build_deb.sh packaging/deb/debian packaging/deb/rootfs
```

Expected: no output.

**Step 2: Run syntax checks**

```bash
bash -n scripts/package-release-artifacts.sh scripts/deploy-release-artifacts.sh scripts/compose-up-with-fallback.sh packaging/deb/build_deb.sh packaging/deb/debian/postinst packaging/deb/debian/prerm packaging/deb/debian/postrm packaging/deb/rootfs/usr/bin/vulhunterctl
```

Expected: exit code 0.

**Step 3: Inspect final diff**

```bash
git diff -- docker-compose.yml docker-compose.prod.yml docker-compose.prod.cn.yml docker-compose.build.yml docker-compose.override.yml docker-compose.frontend-dev.yml backend/Dockerfile frontend/Dockerfile frontend/Dockerfile.legacy scripts/package-release-artifacts.sh scripts/deploy-release-artifacts.sh scripts/compose-up-with-fallback.sh .github/workflows/docker-publish.yml .github/workflows/release.yml packaging/deb/build_deb.sh packaging/deb/debian packaging/deb/rootfs docs/plans/2026-03-08-vulhunter-deployment-rename-design.md docs/plans/2026-03-08-vulhunter-deployment-rename.md
```

Expected: only scoped deployment-chain changes appear.
