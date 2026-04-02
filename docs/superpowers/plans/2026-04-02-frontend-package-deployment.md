# Frontend Package Deployment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frontend ship as a static deployment package that uses same-origin `/api/v1`, with production deployment consuming the package directly instead of rebuilding the frontend on the target host.

**Architecture:** Frontend API calls converge on a single `/api/v1` contract, the production Docker image becomes a plain static Nginx image, and release artifacts include a frontend package plus a deploy-specific compose overlay that mounts the packaged assets and Nginx config.

**Tech Stack:** Vite, React, Node test runner, Docker, Docker Compose, Nginx, Bash

---

### Task 1: Lock the frontend API and runtime contract with tests

**Files:**
- Create: `frontend/tests/frontendDeploymentContract.test.ts`
- Modify: `frontend/tests/runtimeLaunchers.test.ts`

- [ ] **Step 1: Write failing tests for the new deployment contract**

```ts
test("agent task event URLs use the shared API base contract", () => {
  assert.equal(buildAgentTaskEventsUrl("task-1", 2), "/api/v1/agent-tasks/task-1/events?after_sequence=2");
});

test("frontend production Dockerfile no longer requires Node runtime injection", () => {
  assert.doesNotMatch(dockerfile, /frontend-runtime\.mjs/);
  assert.doesNotMatch(dockerfile, /apk add --no-cache nodejs/);
});
```

- [ ] **Step 2: Run targeted tests and verify they fail for the right reason**

Run: `cd frontend && node --import tsx --test tests/runtimeLaunchers.test.ts tests/frontendDeploymentContract.test.ts`
Expected: FAIL because the current Dockerfile still installs Node / copies `prod-runtime.mjs`, and the shared agent task event URL helper does not exist yet.

### Task 2: Converge frontend runtime behavior on the same-origin API contract

**Files:**
- Create: `frontend/src/shared/api/apiBase.ts`
- Modify: `frontend/src/shared/api/serverClient.ts`
- Modify: `frontend/src/shared/api/agentTasks.ts`
- Modify: `frontend/src/shared/config/env.ts`

- [ ] **Step 1: Add a single API base helper with `/api/v1` as the default**
- [ ] **Step 2: Switch axios and agent task streaming helpers to use the shared helper**
- [ ] **Step 3: Keep compile-time override support only as an explicit fallback, not as a production runtime contract**
- [ ] **Step 4: Re-run the targeted tests**

Run: `cd frontend && node --import tsx --test tests/runtimeLaunchers.test.ts tests/frontendDeploymentContract.test.ts tests/agentTasksApi.test.ts`
Expected: PASS

### Task 3: Remove frontend production runtime injection and make the image static-only

**Files:**
- Modify: `docker/frontend.Dockerfile`
- Delete: `frontend/scripts/prod-runtime.mjs` (if no references remain)

- [ ] **Step 1: Replace the production stage with a plain Nginx image that copies only static assets and Nginx config**
- [ ] **Step 2: Remove the runtime placeholder injection path from the Dockerfile**
- [ ] **Step 3: Delete the now-unused runtime injection script if the codebase no longer references it**
- [ ] **Step 4: Re-run the Dockerfile contract tests**

Run: `cd frontend && node --import tsx --test tests/runtimeLaunchers.test.ts`
Expected: PASS

### Task 4: Package and deploy the frontend as a release artifact

**Files:**
- Modify: `deploy/package-release-artifacts.sh`
- Modify: `deploy/deploy-release-artifacts.sh`
- Create: `deploy/compose/docker-compose.prod.yml`
- Create: `deploy/compose/docker-compose.prod.cn.yml`
- Modify: `README.md`
- Modify: `scripts/README-COMPOSE.md`

- [ ] **Step 1: Make the frontend release package contain deployable static assets plus Nginx config**
- [ ] **Step 2: Add deploy-specific compose overlays that mount the unpacked frontend package instead of rebuilding frontend**
- [ ] **Step 3: Update the release deploy script to extract the frontend package and use the new compose overlays**
- [ ] **Step 4: Document the split between dev compose and production package deployment**

### Task 5: Run final verification

**Files:**
- Modify: `docs/superpowers/plans/2026-04-02-frontend-package-deployment.md`

- [ ] **Step 1: Run frontend targeted tests**

Run: `cd frontend && node --import tsx --test tests/runtimeLaunchers.test.ts tests/frontendDeploymentContract.test.ts tests/agentTasksApi.test.ts`
Expected: PASS

- [ ] **Step 2: Validate deploy compose files**

Run: `docker compose -f docker-compose.yml -f deploy/compose/docker-compose.prod.yml config`
Expected: exit code 0

- [ ] **Step 3: Record any verification gaps if Docker validation cannot run in the current environment**
