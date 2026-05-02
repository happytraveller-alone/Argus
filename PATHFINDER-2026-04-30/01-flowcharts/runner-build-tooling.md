# Runner Images and Build/Release Tooling Flowchart

## Sources consulted

- `README.md:7-30` — Docker Compose startup and `.argus-intelligent-audit.env` notes.
- `docs/architecture.md:32-55` — Opengrep and AgentFlow runner entry points.
- `docker/opengrep-scan.sh:182-316` — Opengrep runner execution/recovery/summary.
- `docker/argus-pip-wheel-group.sh:1` — wheel group helper entry.
- `scripts/prepare-agentflow-wheelhouse.sh:1` — local wheelhouse prep script entry.
- `docker/agentflow-runner.Dockerfile:1` — AgentFlow runner image definition entry.
- `scripts/test-argus-bootstrap.sh:1` — bootstrap script contract test entry.

## Concrete findings

- Compose is the documented startup path.
- Opengrep runner is a shell script with JSON recovery and batch helpers.
- AgentFlow runner build has separate wheelhouse preparation and Docker image build surfaces.
- Build/release tooling is operational support, not application domain logic.

```mermaid
flowchart TD
  User["docker compose up --build<br/>README.md:10"] --> Compose["docker-compose services<br/>README.md:13"]
  Compose --> BackendImage["backend image<br/>docker/backend.Dockerfile:1"]
  Compose --> FrontendImage["frontend image<br/>docker/frontend.Dockerfile:1"]
  Compose --> OpengrepImage["opengrep runner image<br/>docker/opengrep-runner.Dockerfile:1"]
  Compose --> AgentImage["agentflow runner image<br/>docker/agentflow-runner.Dockerfile:1"]
  OpengrepImage --> OpengrepShell["run_opengrep_once<br/>docker/opengrep-scan.sh:182"]
  AgentImage --> WheelPrep["prepare wheelhouse<br/>scripts/prepare-agentflow-wheelhouse.sh:1"]
  WheelPrep --> WheelGroup["argus-pip-wheel-group<br/>docker/argus-pip-wheel-group.sh:1"]
  ResetTest["bootstrap script tests<br/>scripts/test-argus-bootstrap.sh:1"] --> Compose
```

## Side effects

- Docker builds/images/containers.
- Wheelhouse file generation.
- Runner workspace/result file I/O.
- Potential Docker prune only in aggressive reset mode (per remembered contract; not re-traced here).

## External dependencies

- Docker daemon and Compose.
- Python/pip mirrors for AgentFlow wheelhouse when cache misses.
- Backend task execution invokes runner images.

## Confidence / gaps

- **Confidence**: Medium.
- **Gaps**: Did not print Dockerfile line ranges because this phase focused on source feature flows; verify before implementing build changes.
