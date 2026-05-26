# Argus — Reasonix onboarding

## Stack
- **Backend**: Rust (edition 2021, toolchain 1.88.0), Axum 0.8, Tokio, SQLx (PostgreSQL)
- **Frontend**: TypeScript 6 + React 19, Vite 8, Tailwind CSS 4, Shadcn/Radix UI
- **Package manager**: pnpm 11 (frontend), Cargo (backend)
- **Key deps**: reqwest, serde, anyhow/thiserror (backend); react-router v7, @tanstack/react-table, zod, axios/ky (frontend)
- **Lint/format**: Biome (frontend), cargo (backend), markdownlint (docs)

## Layout
| Path | Content |
|------|---------|
| `backend/` | Rust Axum server — REST APIs, scan orchestration, LLM integration |
| `frontend/` | React SPA — dashboard, project mgmt, scan config, findings UI |
| `scripts/` | Bootstrap, release, and validation scripts |
| `.github/workflows/` | CI/CD — docker-publish.yml, release.yml |
| `docs/` | Project docs, archive (cubesandbox), guidance schema |
| `assets/` | OpenGrep rules + CodeQL queries |
| `.codex/` | Repo-local Codex/OMX config (gitignored) |
| `.omc/` / `.omx/` | Agent orchestration state, plans, research logs |

## Commands
| What | How |
|------|-----|
| Dev server (frontend) | `cd frontend && pnpm dev` (proxies API → :18000) |
| Build (frontend) | `cd frontend && pnpm build` |
| Type-check (frontend) | `cd frontend && pnpm type-check` |
| Lint (frontend) | `cd frontend && pnpm lint` |
| Format (frontend) | `cd frontend && pnpm format` |
| Test (frontend) | `cd frontend && pnpm test:node` |
| Test (backend) | `cd backend && cargo test` (needs PG + Docker) |
| Bootstrap | `./argus-bootstrap.sh --wait-exit -- default` |

## Conventions
- Frontend path alias: `@/` → `src/`
- Backend config entirely via env vars (see `src/config.rs`)
- PostgreSQL schema created at bootstrap, not via migration files
- DB schema defined in `src/bootstrap/` (Rust), not SQL migrations
- Archive support for zip, tar, xz, bzip2, zstd
- Error handling: `anyhow`/`thiserror` (backend), `zod` (frontend)
- markdownlint: line-length (MD013) disabled, MD024 sibling-only, MD032/MD036 off
- Rust toolchain pinned to 1.88.0 in `rust-toolchain.toml`

## Watch out for
- **CubeSandbox is archived** (2026-05-07) to `docs/archive/cubesandbox/` — scans now use a3s sandbox only
- `.codex/` is gitignored — repo-local Codex setup is opt-in per README
- **AGENTS.md** contains an autonomy directive — agents are instructed to proceed without asking permission
- Dev backend expects PostgreSQL and Docker daemon running; many integration tests require them
- Frontend chunks are obfuscated in production build (`vite-plugin-javascript-obfuscator`)
