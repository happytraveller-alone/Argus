# analysis agent

Security analysis agent. Analyzes one bounded risk point or analysis task, produces findings with evidence metadata and structured severity/confidence.

## Mounts

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `./data` | `/opt/data` | Runtime home (Hermes state) |
| `<project>` | `/scan` | Target project under analysis |

## Lifecycle

1. Dispatcher sends a task via the handoff schema (see `../shared/schemas/handoff.schema.json`).
2. Container starts, Hermes reads `hermes-home/config.yaml` and `hermes-home/SOUL.md`.
3. Agent analyzes the assigned risk point, writes findings to `artifacts/`.
4. Result is returned via the result schema (see `../shared/schemas/result.schema.json`).
5. Container exits; `data/` persists state for the next run.

## Configuration

- `agent.toml` — dispatch timeout, image, input/output contract
- `container.env.example` — copy to `container.env` and fill in secrets
- `hermes-home/config.yaml` — Hermes runtime config
- `hermes-home/SOUL.md` — role system prompt
