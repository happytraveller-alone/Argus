# CubeSandbox Submodule Patches

This file tracks local patches applied to the cubesandbox sources that must be
preserved across submodule rebases AND across `cubesandbox-quickstart.sh install`
runs. **Two trees** in this repo carry the cubesandbox source and BOTH must be
patched in lockstep:

1. `third_party/cubesandbox/...` — the git submodule (`m third_party/cubesandbox`
   in `git status`). This is what your editor / grep / submodule update controls.
2. `.cubesandbox/CubeSandbox/...` — a one-way install copy created by
   `bash scripts/cubesandbox-quickstart.sh install`. There is **no script that
   regenerates this tree from the submodule**; it is the deployed instance that
   the guest VM build/run paths actually consume.

**Pre-rebase / pre-install checklist**: after any submodule bump or install
run, re-apply every patch below to BOTH trees (`diff -u` between the two
trees should be empty afterwards), and rebuild any affected guest-VM binary
(cubemaster, cubelet, etc.).

See also `.omc/skills/cubesandbox-submodule-mirror-expertise.md` and
`.omc/skills/cubesandbox-storage-axes-expertise.md` for the underlying
architectural insights.

---

## P1 — `template_image.go:1508` ext4 formula overhead (256 MB → 1 GiB)

**Files** (must be byte-identical after patching):
- `third_party/cubesandbox/CubeMaster/pkg/templatecenter/template_image.go` (line 1508)
- `.cubesandbox/CubeSandbox/CubeMaster/pkg/templatecenter/template_image.go` (line 1508)

**Diff**:

```diff
 func createExt4Image(ctx context.Context, rootfsDir, ext4Path string) error {
 	sizeBytes, err := directorySize(rootfsDir)
 	if err != nil {
 		return err
 	}

-	raw := sizeBytes + 256*1024*1024
+	raw := sizeBytes + 1024*1024*1024 // FINAL plan Phase 2: 256MB→1GiB overhead so mkfs.ext4 metadata always fits (see oci/cubesandbox/PATCHES.md P1)
 	const gib int64 = 1024 * 1024 * 1024
 	if raw < gib {
 		raw = gib
 	}

 	gibs := (raw + gib - 1) / gib
 	pow := int64(1)
 	for pow < gibs {
 		pow <<= 1
 	}
 	imageSize := pow * gib
```

**Rationale**:

The ext4 image is sized by `next_pow_of_2(sizeBytes + overhead) GiB`. ext4
filesystem metadata at 4–8 GiB images consumes ≈ 230–460 MB. With the
original 256 MB overhead, headroom can drop to ≤ 50 MB when `rootfs` straddles
a power-of-two boundary, causing `mkfs.ext4 -F -d <rootfs>` to fail with
`No space left on device` while populating the last files.

Bumping the overhead to 1 GiB guarantees ext4 metadata fits at every bucket
without forcing a `pow_of_2` jump in steady state:

| Rootfs | Old (256 MB) → ext4 | New (1 GiB) → ext4 |
|---|---|---|
| 0.5 GiB | 1 GiB | 2 GiB |
| 1.5 GiB | 2 GiB | 4 GiB |
| 3.4 GiB | 4 GiB | 4 GiB (no change) |
| 5.0 GiB | 8 GiB | 8 GiB (no change) |
| 7.5 GiB | 8 GiB | 16 GiB |

**Global blast radius (accepted)**: every template kind (sandbox-code,
codeql-cpp, opengrep) gets the same overhead. For tiny templates (e.g.
sandbox-code at ~150 MB rootfs) this means 1 GiB → 2 GiB ext4 (a one-bucket
bump). The user explicitly accepted this trade-off in
`.omc/specs/deep-dive-sandbox-storage-insufficient.md` round 2 (option [D]).

**References**:
- Spec: `.omc/specs/deep-dive-sandbox-storage-insufficient.md`
- Plan: `.omc/plans/ralplan-sandbox-storage-insufficient-FINAL.md` (Phase 2)
- Trace: `.omc/specs/deep-dive-trace-sandbox-storage-insufficient.md`

---

## Operator Runbook

### Concurrent codeql-cpp sandbox ceiling (R2 mitigation)

P1 + the writable-layer bump in `scripts/cubesandbox-quickstart.sh:33`
(`4Gi → 16Gi`) means each codeql-cpp sandbox can claim up to 16 GiB of the
guest VM's `/var/lib/containerd` ext4 disk. The writable layer is enforced
as a **quota**, not allocated as a separate physical disk — so N concurrent
sandboxes share the same backing.

**Before accepting a new codeql-cpp task, verify**:

```bash
ssh opencloudos@127.0.0.1 -p 10022 "df -h /var/lib/containerd"
```

The `Avail` column MUST be **≥ 32 GiB** (2× writable-layer-size).

**Hard ceiling**: at most **2 concurrent in-flight codeql-cpp sandboxes** per
guest VM. A code-level guardrail in `backend/src/scan/codeql_cubesandbox.rs`
to gate task admission by querying guest VM `df` is tracked as a post-FINAL
follow-up.

### Verifying patches survived an install / rebase

```bash
# Both trees must be byte-identical
diff -u third_party/cubesandbox/CubeMaster/pkg/templatecenter/template_image.go \
        .cubesandbox/CubeSandbox/CubeMaster/pkg/templatecenter/template_image.go
# Expected: empty output (no diff)

# Both trees must contain the patched constant
grep -nH 'sizeBytes + 1024\*1024\*1024' \
  third_party/cubesandbox/CubeMaster/pkg/templatecenter/template_image.go \
  .cubesandbox/CubeSandbox/CubeMaster/pkg/templatecenter/template_image.go
# Expected: both files report a hit at line 1508

# No file should still carry the old 256 MB constant
! grep -n 'sizeBytes + 256\*1024\*1024' \
  third_party/cubesandbox/CubeMaster/pkg/templatecenter/template_image.go \
  .cubesandbox/CubeSandbox/CubeMaster/pkg/templatecenter/template_image.go
# Expected: exit 1 (grep finds nothing → assertion `!` returns 0 → OK)
```

If either check fails: re-apply P1 to whichever tree is missing it, then
rebuild any cubemaster binary on the guest VM that consumes `template_image.go`.

### Re-provisioning after a patch

After applying P1 + the writable-layer-size bump, you MUST delete and
re-provision the codeql-cpp template so the new sizing takes effect:

```bash
# 1. Delete the old READY template (irreversible)
ssh opencloudos@127.0.0.1 -p 10022 \
    "cubemastercli template delete --template-id <old_tpl_id>"

# 2. Re-provision (rebuilds image with current Dockerfile + patched cubemaster)
bash scripts/cubesandbox-quickstart.sh provision-codeql-cpp-template

# 3. Capture the new id and update .env
ssh opencloudos@127.0.0.1 -p 10022 "cubemastercli tpl list" | grep READY
# Edit .env: CUBESANDBOX_TEMPLATE_ID=<new_tpl_id>

# 4. Restart argus backend so it reads the new TEMPLATE_ID
docker compose --project-directory /home/xyf/argus \
    --file /home/xyf/argus/docker-compose.yml --project-name argus \
    up -d --force-recreate --no-deps backend
```

See `.omc/plans/ralplan-sandbox-storage-insufficient-FINAL.md` Phase 4 for
the full sequence.
