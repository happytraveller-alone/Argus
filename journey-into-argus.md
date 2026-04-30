# Journey Into Argus

_Generated on 2026-04-30 from the local `claude-mem` worker/database plus repo-local Codex memory summaries._

## Source Note

The `claude-mem` worker was reachable on port `37700`, and the project resolved from the current working directory as `argus` rather than a git worktree parent. The documented full-context endpoint returned only:

> `# [argus] recent context, 2026-04-30 1:00pm GMT+8`  
> `No previous sessions found.`

Because that endpoint did not expose a full historical transcript, this report uses the authoritative local `~/.claude-mem/claude-mem.db` observations for project `argus` and augments the narrative with the repo-local Codex memory registry and rollout summaries under `.codex/memories/`. Quantitative token-economics figures are therefore database-derived and sparse; historical narrative is memory-summary-derived and should be treated as a compressed project history rather than a complete raw event log.

## 1. Project Genesis

The visible Argus history in the available memory begins not with a greenfield scaffold, but with a mature brownfield system already carrying a clear product identity: a Rust/Axum backend, a React/Vite frontend, Opengrep-only static auditing, and AgentFlow-powered intelligent auditing. By the time the remembered sessions start, Argus is already organized around two audit modes: a deterministic static-analysis path and an agentic intelligent-audit path. The early preserved decisions are therefore less about “what should this app be?” and more about “how do we make this app reliable, operable, and understandable enough that future agents can safely work on it?”

The first strong origin marker in the preserved record is a documentation and agent-contract cleanup on April 29, 2026. That work established the active stack vocabulary and made `AGENTS.md` the durable policy surface for repo-local agent behavior. It also installed and documented the `neat-freak` cleanup workflow as a required post-change knowledge reconciliation habit. In practical terms, Argus’s recent development history begins with a meta-decision: the project would not just accumulate patches; it would preserve operational knowledge in docs, specs, plans, and memory.

This genesis matters because later work repeatedly follows the same pattern. The user does not ask for broad rewrites first. They ask for exact artifacts, exact specs, exact workflow modes, and exact verification evidence. The project’s effective development model becomes artifact-driven brownfield evolution: clarify the contract, preserve the existing UI shape unless explicitly widened, implement narrowly, verify with concrete commands, and sync knowledge afterward.

## 2. Architectural Evolution

The preserved architecture evolves along four major axes: runtime stack clarification, LLM configuration authority, UI boundary stabilization, and build-system hardening.

The first axis is documentation truth. The docs were synchronized around the current stack: Rust/Axum backend, React/Vite frontend, Opengrep static auditing, and AgentFlow intelligent auditing. Older Python/FastAPI-era names and retired backend paths were explicitly treated as historical rather than active. That is a quiet but important architectural pivot: it prevents future agents from designing against stale concepts.

The second axis is LLM configuration authority. A deep-interview session on April 28 clarified that startup imports should flow one way from `.argus-intelligent-audit.env` into backend `system-config`; UI writes should update current-session `system-config` only; and successful real LLM tests should persist fingerprint metadata. This resolved an authority split that could otherwise create inconsistent behavior between reset/start scripts, system settings, and create-project intelligent-audit flows. The important architectural lesson is that Argus treats LLM configuration as a coordinated backend system, not as scattered frontend form state or generated `.env` copies.

The third axis is create-project intelligent-audit gating. A separate but related debugging strand found that scan-engine LLM connectivity could pass while the create-project dialog failed with HTTP 422. The preserved conclusion was that this was not a generic backend outage; it was call-path drift. The settings page used `/system-config/test-llm`, while create-project gating needed to delegate to `/system-config/agent-preflight`. That distinction became a narrow contract: keep `/system-config/test-llm` for settings, make the create dialog preflight-only, avoid dialog redesign, avoid new config sources, run preflight on dialog open/manual retry/create, and retain uploaded project records on agent-side failure.

The fourth axis is Docker/AgentFlow runner build hardening. The old monolithic runner wheel step was identified as the real build bottleneck. The optimized path split wheel building into backend build requirements, local AgentFlow wheel, and runtime dependencies; introduced a local wheelhouse; kept runtime installation offline; and preserved generated wheels inside Docker context while keeping them out of git. This was an architectural build-system change, but it followed the same project principle: one clear path with evidence, not a speculative abstraction layer.

## 3. Key Breakthroughs

The first breakthrough was procedural: the project learned to drive ambiguity to operational zero before implementation. The UI/dashboard/static-table deep-interview session converted vague bundled UI concerns into explicit acceptance targets. Model fetching should select the backend recommended/default model. Dashboard totals should count verified vulnerabilities only. Static search should cover visible main fields only. DataTable header active state should be icon/text color and weight only, without an outer active frame. Dashboard dimensions should be implementation-chosen ratios validated by screenshots. That was not just “requirements gathering”; it turned subjective UI complaints into testable constraints.

The second breakthrough was recognizing the create-project 422 as a parity problem. The tempting path would have been to treat the HTTP 422 as a backend validation bug. The preserved evidence instead compared two UI call paths and found divergent ownership: settings connectivity and create-time agent readiness were not the same contract. This reframed the bug from “fix the request” to “route the dialog through the correct preflight authority.”

The third breakthrough was the LLM fingerprint authority model. The project avoided a common brownfield trap: making every writer update every file. The accepted model was narrower and safer: startup imports `.argus-intelligent-audit.env` into `system-config`, UI writes `system-config`, and successful live tests persist fingerprints. That created a single runtime authority without pretending that all surfaces should be symmetrical writers.

The fourth breakthrough was the AgentFlow runner build split. The memory records show that build optimization succeeded because the work isolated the real bottleneck, split it into separately cacheable stages, and captured logs/timings rather than making broad “faster now” claims. Evidence included network fallback, local wheelhouse, cached final build, runtime smoke, and static hygiene logs.

The fifth breakthrough was operational: stale Ralph/OMX state cleanup had to be real. A later memory entry captures that if hooks report an active Ralph state, agents must clear and verify both `/home/xyf` and `/home/xyf/argus` state before claiming completion. This moved “workflow cleanup” from a vague afterthought into a verifiable runtime invariant.

## 4. Work Patterns

Argus development follows a strong clarify-plan-execute-verify rhythm. Broad or risky requests begin with `$deep-interview` or consensus planning. Implementation starts only after a named artifact is sufficiently explicit. Ralph is used as a persistent execution loop, but only after the approved spec/plan is grounded. The user strongly prefers continuing exact artifact paths over restarting discovery.

A recurring pattern is the separation of authoring and review. Plans are expected to receive Architect/Critic pressure before approval. Code or doc changes are verified with concrete commands, not self-approval. UI work is split into separate acceptance targets rather than being treated as a single vague “fix the page” request.

Debugging cycles tend to start from user-provided reproduction or symptom framing, then compare actual call paths. The LLM 422 work compared `/system-config/test-llm` and `/system-config/agent-preflight`. The OMX cwd issue preserved the exact reproduction command `cd /home/xyf/argus && omx --tmux --madmax --high` and traced the issue to shell initialization rather than prematurely editing launcher code. The build optimization work preserved exit status through `pipefail`/`PIPESTATUS` rather than trusting logs piped through `tee`.

Refactoring and cleanup are conservative. The project guidelines explicitly prefer deletion over addition, existing utilities over new abstractions, and narrow reversible diffs over broad rewrites. Even where unification is desired, the memory repeatedly warns against UI redesign, new config sources, or “just in case” parallel paths.

## 5. Technical Debt

The most visible technical debt is historical terminology drift. Docs and memories previously risked mixing active Rust/Axum/React/Vite/Opengrep/AgentFlow terminology with retired Python/FastAPI-era references. The April 29 docs sync paid down that debt by making active and retired terms explicit.

Another debt cluster is configuration drift. LLM config touched startup scripts, Docker env files, backend system-config storage, frontend settings UI, and create-project gating. The debt was not simply duplicated code; it was unclear authority. The accepted one-way startup import plus system-config runtime authority paid down the conceptual debt without overgeneralizing every surface into a bi-directional sync system.

UI debt appears as shared component boundary drift. DataTable header styling, dashboard chart placement, static-analysis project-name fallback, and AgentAudit header layout all had page-level symptoms. The preserved fix strategy was to identify shared fix points such as `DataTableColumnHeader.tsx` and `resolveStaticAnalysisProjectNameFallback(...)`, then test robust behavior rather than brittle snapshots.

Build debt appeared in the AgentFlow runner image. A monolithic wheel step created slow/hanging builds and poor observability. The split-wheelhouse design paid down that debt by making cache boundaries and log markers explicit.

Workflow debt appeared as stale OMX/Ralph state and cwd surprises. The `.zshrc` unconditional `cd /home/xyf` bug was especially instructive: the system looked like an OMX launcher problem until direct shell probes showed the reset came from user shell initialization.

## 6. Challenges and Debugging Sagas

The LLM configuration saga is the clearest multi-stage challenge. The user wanted reset/start, scan-engine settings, create-project intelligent audit, synchronization, and fingerprint persistence to align. The first plausible model was not enough; the user corrected the direction toward `.argus-intelligent-audit.env -> system-config`, and the interview kept pressure-testing startup authority, UI write authority, and compose/backend env behavior. The eventual result was a crisp contract rather than a broad refactor.

The create-dialog 422 saga extended that same theme. Scan-engine tests passed; create-dialog tests failed. The correct diagnosis came from comparing frontend and backend ownership boundaries rather than chasing a generic 422. The final plan preserved the settings endpoint while making the dialog’s create gate use agent preflight. It also preserved the existing dialog shape, required create-time preflight, blocked unsaved-config retry confusion, and retained projects after agent-side failure.

The UI/dashboard/static-table saga shows how subjective visual issues became explicit. The work involved model fetch behavior, preflight gating, dashboard totals/layout, static-analysis search/project naming, and shared DataTable header visuals. The key challenge was preventing one bundled UI request from becoming a vague rewrite. The successful pattern was to decompose into separate acceptance targets and explicitly mark non-goals.

The AgentFlow runner build saga was a verification challenge. Optimization work can easily become anecdotal. Here the project recorded exact files, scripts, generated wheelhouse behavior, mirror fallback, `.dockerignore`/`.gitignore` interactions, and log discipline. A later note warns that unrelated `npm install` network behavior can obscure runner-wheelhouse proof, so future verification should isolate the relevant layer.

The OMX cwd saga was a tooling challenge. The user expected `cd /home/xyf/argus && omx --tmux --madmax --high` to start in the repo, but the shell landed in `/home/xyf`. The fix was not in tmux or OMX launcher code; it was an unconditional `cd /home/xyf` in `~/.zshrc`, guarded to run only in interactive shells. That debugging arc reinforced a project-wide habit: preserve the reproduction command and verify the actual path of execution.

## 7. Memory and Continuity

Persistent memory is central to Argus’s current workflow. The repo-local memory summary carries user preferences such as preserving named artifact paths, treating repeated requests as continuation signals, requiring exact verification evidence, and reconciling docs after implementation. These memories prevent repeated negotiation over already-settled process rules.

The most valuable continuity is not raw implementation detail; it is boundary memory. Future agents learn that broad UI bundles must be split into acceptance targets; that create-dialog LLM parity is a call-path issue; that screenshot limitations must be reported explicitly; that generated wheelhouse `.whl` files must be ignored by git but visible to Docker; and that stale Ralph state cleanup must be verified before stopping.

There is also a meta-continuity loop: memory informs AGENTS.md, AGENTS.md requires post-change cleanup, cleanup updates docs/memory, and future agents inherit the sharper contract. Argus is therefore developing not only application features but also an operating system for safe agentic maintenance.

## 8. Token Economics & Memory ROI

### Database-Derived Metrics

| Metric | Value |
| --- | ---: |
| Project | `argus` |
| Worker port | `37700` |
| Observations in `~/.claude-mem/claude-mem.db` | 15 |
| Distinct sessions in DB | 1 |
| Date range in DB | 2026-04-30T03:37:58.196Z to 2026-04-30T03:37:58.210Z |
| Total `discovery_tokens` | 0 |
| Average estimated read tokens per observation | ~147.28 |
| Explicit recall events by SQL heuristic | 0 |
| Full context endpoint result | No previous sessions found |

Because all 15 `argus` observations in the SQLite database have `discovery_tokens = 0`, the strict numeric ROI formulas from the skill cannot produce a meaningful positive ratio. The database appears to contain a compact imported snapshot of high-value memories rather than original token-cost telemetry.

### Monthly Breakdown

| Month | Observations | Sessions | Discovery tokens |
| --- | ---: | ---: | ---: |
| 2026-04 | 15 | 1 | 0 |

### Observation-Type Breakdown

| Type | Count |
| --- | ---: |
| decision | 11 |
| discovery | 4 |

### Top Five Highest-Value Observations by `discovery_tokens`

All entries tie at `0` discovery tokens, so these are “top” only by ordering, not measured original cost:

| ID | Title | Discovery tokens |
| ---: | --- | ---: |
| 42 | Argus named-spec continuation contract | 0 |
| 43 | Zero-ambiguity clarification before broad UI implementation | 0 |
| 44 | Ralph implementation starts from approved artifacts | 0 |
| 45 | Create-project LLM preflight parity split | 0 |
| 46 | Create-project agent preflight narrow UI contract | 0 |

### Practical ROI Interpretation

The measurable DB ROI is indeterminate, but the practical value of memory is clear. The memory corpus prevents expensive repeated discovery on issues that previously required multi-step interviews, planning, implementation, and verification. The highest-value remembered areas are:

1. Named-spec continuation and zero-ambiguity workflow rules.
2. LLM config authority and fingerprint persistence.
3. Create-project agent-preflight parity.
4. Shared frontend UI boundary points.
5. AgentFlow runner wheelhouse build optimization.
6. OMX cwd and stale state cleanup.

A conservative practical estimate is that each of these areas saves at least one full investigation loop when rediscovered, even though the local `discovery_tokens` column does not quantify that cost.

## 9. Timeline Statistics

The strict `claude-mem` database timeline for `argus` is a compact snapshot: 15 observations, 1 session, all inserted within milliseconds on April 30, 2026. It is not a complete chronological raw project history.

The broader repo-local memory summaries cover at least April 28 through April 29, 2026, with major remembered episodes:

- April 28: AgentFlow runner wheelhouse build optimization.
- April 28: LLM config authority and create-project 422/preflight parity clarification.
- April 28: OMX cwd reset diagnosis and `.zshrc` interactive guard.
- April 29: UI/dashboard/static-table zero-ambiguity clarification and implementation.
- April 29: Systemic UI adjustment planning and Ralph startup context.
- April 29: Repo docs/AGENTS/neat-freak synchronization.
- April 30: Compact `claude-mem` observations imported for project `argus`.

There is no reliable longest-debugging-session metric in the SQLite rows because original prompt/session durations are not present in the fetched observations. The most complex sagas by narrative density are LLM config/preflight parity, UI dashboard/static-table work, AgentFlow runner build optimization, and OMX cwd/state cleanup.

## 10. Lessons and Meta-Observations

Argus is a project where process discipline is part of the architecture. The most repeated lesson is that brownfield work must preserve existing contracts unless the user explicitly authorizes broader change. That shows up in UI work, config work, build optimization, and workflow cleanup.

A new developer should learn five principles from the available timeline:

First, names and paths matter. If the user names a spec or plan, continue that exact artifact. Do not rename, broaden, or restart unless the user asks.

Second, authority matters more than surface symmetry. The LLM config work succeeded by deciding who writes what and when, not by making every place update every other place.

Third, parity bugs require path comparison. When one UI path passes and another fails, inspect endpoint ownership and payload differences before assuming a backend outage.

Fourth, UI fixes should be split into acceptance targets. Shared components such as DataTable headers and static-analysis view models are preferred fix points; page-specific duplicate controls are usually a smell.

Fifth, verification is a first-class deliverable. Argus expects exact commands, exit codes, logs, test counts, timings, and explicit limitations. If screenshot runtime is unavailable, say so and substitute targeted render/source tests plus build evidence; do not pretend visual proof exists.

The broader story is that Argus is becoming a maintainable agent-assisted codebase by making tacit decisions explicit. Specs, plans, memory, docs, and runtime state are all part of the system. The strongest future path is to keep turning ambiguous requests into concrete contracts, implement narrowly, verify honestly, and reconcile knowledge before moving on.
