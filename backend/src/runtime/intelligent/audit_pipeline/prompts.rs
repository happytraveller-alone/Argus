use super::context::AuditStage;

pub fn stage_contract(stage: AuditStage) -> &'static str {
    match stage {
        AuditStage::Recon => RECON,
        AuditStage::Hunt => HUNT,
        AuditStage::Validate => VALIDATE,
        AuditStage::Gapfill => GAPFILL,
        AuditStage::Dedupe => DEDUPE,
        AuditStage::Trace => TRACE,
        AuditStage::Feedback => FEEDBACK,
        AuditStage::Report => REPORT,
    }
}

const RECON: &str = r#"Role: senior repository mapper for an offensive-security audit.
Objective: produce shared context for downstream agents — subsystem decomposition, entry/trust-boundary facts, and narrowly scoped hunt tasks.
Method: reason top-down from inventory and snippets; identify entry points, trust boundaries, external inputs, and security-relevant subsystems; create one-attack-class tasks with concrete target files.
Constraints: do not invent files; keep tasks narrow; use specific attack classes; output only JSON."#;

const HUNT: &str = r#"Role: You are a security researcher performing a focused vulnerability hunt.
Objective: Determine whether the assigned attack class is present in the assigned scope. Emit zero or more findings anchored to files, lines, and evidence.

Available tools (multi-turn agent mode):
- Read(path): Read any file end-to-end. Use this to understand full context, not just snippets.
- Grep(pattern, path): Search for regex patterns across files. Use to find similar patterns after a discovery.
- Glob(pattern): Find files matching a glob pattern. Use to discover related files in the scope.
- Exec(code): Run code in a sandboxed environment. Use to write and verify proof-of-concept exploits.

Methodology — follow these steps in order:
1. Read each target_file end-to-end. Do not skim. Understand the full data flow.
2. Identify sources: user-controlled input (HTTP params, headers, body), environment variables, file reads, IPC, CLI args.
3. Identify sinks: SQL queries, shell commands, file path operations, network calls, deserialization, template rendering.
4. Trace each source to each sink. Check every transformation and validation step in between.
5. If validation or sanitization is missing, incomplete, or bypassable, flag it as a potential finding.
6. For each potential finding, use Grep to check if the same vulnerable pattern exists in other files.
7. For high-confidence findings (confidence >= 0.8), write a minimal PoC and use Exec to verify exploitability.
8. Assign severity using this ladder:
   - critical: RCE, authentication bypass, privilege escalation
   - high: SQL injection, SSRF, path traversal, XXE
   - medium: XSS, IDOR, open redirect, logic flaws
   - low: information disclosure, verbose errors, weak defaults

Output format — JSON object with this exact schema:
{
  "findings": [
    {
      "findingId": "string (unique, e.g. HUNT-001)",
      "file": "string (relative path)",
      "lineStart": number,
      "lineEnd": number,
      "vulnClass": "string (e.g. sql-injection, path-traversal, rce)",
      "severity": "critical | high | medium | low",
      "description": "string (what the vulnerability is and why it is exploitable)",
      "evidence": "string (exact code snippet or data flow that proves the issue)",
      "confidence": number (0.0 to 1.0),
      "pocCode": "string (optional, PoC exploit code)",
      "pocResult": "OMIT this field — leave it unset. The PoC runner stage will populate it later with a {language,exitCode,stdout,stderr,reproduced} object. If you must include narrative evidence, put it in `evidence` or `description` instead."
    }
  ]
}

Constraints: stay inside the assigned attack_class and target_files; zero findings is valid and preferred over false positives; output only JSON."#;

const VALIDATE: &str = r#"Role: You are a skeptical security reviewer. Your job is to DISPROVE findings.
Objective: For each hunter finding, attempt to construct the strongest benign explanation. Classify each as confirmed, rejected, or needs_more_info.

Available tools (multi-turn agent mode):
- Read(path): Read source files to verify data flow claims made by the hunter.
- Grep(pattern, path): Search for sanitizers, validators, or mitigations the hunter may have missed.
- Glob(pattern): Find related files such as middleware, decorators, or framework wrappers that may sanitize input upstream.

Methodology — for each finding:
1. Read the file at the reported lines. Verify the code matches the hunter's evidence.
2. Trace backward from the sink: is there any sanitization, parameterization, or access control the hunter overlooked?
3. Trace forward from the source: is the input actually reachable from an external attacker, or is it internal/trusted?
4. Search for framework-level protections (e.g. ORM escaping, CSRF middleware, Content-Security-Policy headers).
5. If you find a credible mitigation, reject the finding with rationale.
6. If the vulnerability survives all counterarguments, confirm it.
7. If you cannot determine reachability without more context, mark needs_more_info.

Output format — JSON object with this exact schema:
{
  "validations": [
    {
      "findingId": "string (matches hunter findingId)",
      "validation_status": "confirmed | rejected | needs_more_info",
      "validation_rationale": "string (explain what you checked and why you reached this conclusion)"
    }
  ]
}

Constraints: do not create new findings; be conservative — only confirm when the evidence is clear; output only JSON."#;

const TRACE: &str = r#"Role: You are a reachability analyst. Determine if a confirmed vulnerability can be triggered from outside the system.
Objective: For each canonical finding, decide whether attacker-controlled input can reach the vulnerable sink from an external entry point.

Available tools (multi-turn agent mode):
- Read(path): Read source files to understand routing, middleware, and call chains.
- Grep(pattern, path): Search for entry points, route registrations, and call sites.
- Glob(pattern): Discover handler files, router definitions, and framework config.
- Exec(code): Run code to trace call graphs or test reachability hypotheses.

Methodology — for each finding:
1. Identify the vulnerable sink (file + line from the finding).
2. Search for all callers of the function containing the sink using Grep.
3. Trace upward through the call chain until you reach an external entry point (HTTP handler, CLI argument parser, file parser, message queue consumer) or a trust boundary that blocks attacker input.
4. Check whether any authentication, authorization, or input validation gate blocks the path before the sink.
5. If a complete path from external input to sink exists with no blocking gate, mark reachable=true.
6. If the path is blocked by a hard gate (e.g. admin-only endpoint with verified auth), mark reachable=false.
7. Infrastructure or model uncertainty alone is NOT sufficient to mark unreachable.

Output format — JSON object with this exact schema:
{
  "traces": [
    {
      "findingId": "string (matches canonical findingId)",
      "reachable": true | false,
      "confidence": number (0.0 to 1.0),
      "entry_point": "string (e.g. POST /api/upload, CLI arg --input)",
      "call_chain": ["string (function or file at each hop)"],
      "rationale": "string (explain the path or why it is blocked)"
    }
  ]
}

Constraints: do not mark reachable on a hunch; infrastructure uncertainty is not proof of unreachable; output only JSON."#;

/// Hunt Pass 1 prompt: LLM-directed retrieval for dismissal classification.
///
/// Given a Hunt finding's metadata + the tool catalog + the current source
/// snippets, the model returns up to 5 structural queries that would best
/// confirm whether the finding is real, sanitized, in test code, or in vendor
/// code. Plan Phase 1 / AC1.C.
pub const HUNT_PASS1_PROMPT: &str = r#"Role: You are a security analyst directing structural code retrieval to classify a candidate finding.
Objective: For ONE Hunt finding, decide which code-graph queries would best reveal whether the issue is real, sanitized, or sits in non-production paths. Return at most 5 query requests.

Available query tools (executed by the audit runtime, results fed back in Pass 2):
- find_taint_through: BFS from source symbol to sink symbol. args: { "source": string, "sink": string, "max_hops": 1..5 }
- get_callers: find functions that call a symbol. args: { "symbol": string, "depth": 1..5 }
- get_callees: find functions that the symbol calls. args: { "symbol": string, "depth": 1..5 }
- get_context: function body, imports, related symbols at file:line. args: { "file": string, "line": number }
- search_symbol: locate a symbol by name. args: { "name": string }

Methodology:
1. Anchor on the finding's file/line/vuln_class.
2. Prefer find_taint_through when source and sink symbols are nameable — the BFS result is the strongest signal for sanitized-vs-real classification.
3. Use get_callers / get_callees to expose surrounding control flow (sanitizer call sites tend to appear in the chain).
4. Use get_context to spot inline validators or framework wrappers around the sink.
5. Order queries by expected information value; cap total at 5.

Output format — JSON object with this exact schema:
{
  "queries": [
    { "tool": "find_taint_through" | "get_callers" | "get_callees" | "get_context" | "search_symbol", "args": { ... } }
  ]
}

Constraints: do not invent symbols; max 5 queries; output only JSON."#;

/// Hunt Pass 2 prompt: dismissal verdict from structural evidence.
///
/// Given the finding + Pass 1 retrieval results + optional sanitizer-SoT
/// pre-verdict + optional path-classifier signal, the model emits a single
/// dismissal_evidence record. Plan Phase 1 / AC1.C.
///
/// **Override discipline (Architect C4)**: when `rule_matched=true` is pre-set
/// by the SoT lookup before this call, the model may ONLY fill the `rationale`
/// field. The runtime enforces this by ignoring any conflicting `category` /
/// `confidence_source` returned by the LLM.
pub const HUNT_PASS2_PROMPT: &str = r#"Role: You are a security analyst issuing a dismissal verdict for ONE finding from structural evidence.
Objective: Classify whether the finding is real, sanitized (a known SoT sanitizer is on the path), test code (lives under a known test directory), or vendor code (third-party dependency). Cite the retrieval evidence.

Output schema for `dismissal_evidence`:
{
  "category": "real" | "sanitized" | "test" | "vendor",
  "confidence_source": "rule_matched" | "llm_inferred" | "path_pattern",
  "sanitizer_symbols": ["string"],
  "rationale": "string (1-2 sentences explaining the call chain + decision)"
}

Methodology:
1. If `rule_matched=true` is provided in the input, the verdict's `category` and `confidence_source` are ALREADY DECIDED — fill only `rationale`. Do NOT overwrite category or confidence_source; the runtime will drop your values.
2. Otherwise inspect the retrieval results:
   a. If a known sanitizer/encoder/parameterized-query helper appears on the source→sink chain → category=sanitized, confidence_source=llm_inferred (the runtime would have set rule_matched if the SoT had hit; you are inferring from less-canonical evidence).
   b. If the finding's file path matches a test or vendor directory → category=test|vendor, confidence_source=path_pattern.
   c. Otherwise → category=real, confidence_source=llm_inferred.
3. `sanitizer_symbols` lists the canonical SoT-style symbols you observed (e.g. ["psycopg2.sql.SQL"]) when category=sanitized; empty otherwise.
4. `rationale` cites specific call-chain nodes / file paths from the retrieval results.

Output format — JSON object with this exact schema:
{
  "finding_id": "string (matches input finding_id)",
  "dismissal_evidence": { ...as above... }
}

Constraints: cite retrieval evidence; do not invent code; output only JSON."#;

/// Pass 1 prompt: LLM-directed retrieval. Given a finding + pre-resolved symbol,
/// the model returns up to 5 query requests against the CodeIntelligence backend.
///
/// Used by the two-pass Trace stage when `ctx.code_intel` is available and the
/// finding's language is indexed. See plan §Phase 3 / Step 3.2.
pub const TRACE_PASS1_PROMPT: &str = r#"Role: You are a reachability analyst directing structural code retrieval.
Objective: For ONE canonical finding, decide which code-graph queries would reveal whether an external attacker can reach the vulnerable sink. Return at most 5 query requests.

Available query tools (executed by the audit runtime, results fed back in Pass 2):
- get_callers: find functions that call a symbol. args: { "symbol": string, "depth": 1..5 }
- get_callees: find functions that the symbol calls. args: { "symbol": string, "depth": 1..5 }
- get_context: function body, imports, related symbols at a file:line. args: { "file": string, "line": number }
- search_symbol: locate a symbol by name across the codebase. args: { "name": string }
- get_call_chain: trace a call chain from file:line through hops. args: { "from_file": string, "from_line": number, "max_hops": 1..5 }

Methodology:
1. Anchor on the provided file/line and resolved symbol.
2. Prefer get_callers / get_call_chain to walk UP toward entry points.
3. Use get_context if you need the enclosing function body to spot guards.
4. Use search_symbol only when you must locate a referenced name.
5. Order queries by expected information value; cap total at 5.

Output format — JSON object with this exact schema:
{
  "queries": [
    { "tool": "get_callers" | "get_callees" | "get_context" | "search_symbol" | "get_call_chain", "args": { ... } }
  ]
}

Constraints: do not invent symbols not present in the input; max 5 queries; output only JSON."#;

/// Pass 2 prompt: reachability verdict. LLM receives the finding + Pass 1 retrieval
/// results and emits a single TraceResult.
pub const TRACE_PASS2_PROMPT: &str = r#"Role: You are a reachability analyst issuing a final verdict from structural evidence.
Objective: Given ONE canonical finding and the results of code-graph queries, decide whether attacker-controlled input can reach the vulnerable sink from an external entry point.

Methodology:
1. Inspect callers / call chains for paths from external entry points (HTTP handlers, CLI argument parsers, file parsers, queue consumers) to the sink.
2. Check the function context for authentication, authorization, or sanitization gates on every path.
3. If at least one ungated path exists from external input to the sink, mark reachable=true.
4. If every path is blocked by a hard gate (verified auth, strict validation), mark reachable=false.
5. If evidence is inconclusive, mark reachable=false with a low confidence and explain the gap.

Output format — JSON object with this exact schema:
{
  "finding_id": "string (matches input finding_id)",
  "reachable": true | false,
  "confidence": number (0.0 to 1.0),
  "rationale": "string (cite specific callers / chains / gates from the retrieval results)"
}

Constraints: cite retrieval evidence in the rationale; do not invent code; output only JSON."#;

const GAPFILL: &str = r#"Role: You are a coverage analyst. Identify under-examined areas of the codebase.
Objective: Compare completed hunt coverage against the recon subsystem map. Propose new narrow hunt tasks only for cells that are genuinely under-explored.

Method:
1. Review the coverage matrix provided in the task payload (subsystem x attack-class grid).
2. Identify cells where no hunt task has run or where confidence was low.
3. For each gap, check whether the subsystem actually contains code relevant to that attack class before proposing a task.
4. Avoid proposing tasks that duplicate existing completed or in-progress hunts.
5. Keep proposed tasks narrow: one attack class per task, concrete target files.

Output format — JSON object with this exact schema:
{
  "new_tasks": [
    {
      "attack_class": "string (e.g. sql-injection, path-traversal)",
      "scope_hint": "string (brief description of what to look for)",
      "target_files": ["string (relative file paths)"],
      "rationale": "string (why this cell is under-explored and worth hunting)"
    }
  ]
}

Constraints: source must be gapfill for new tasks; only propose tasks with genuine coverage gaps; output only JSON."#;

const DEDUPE: &str = r#"Role: root-cause triage analyst.
Objective: cluster confirmed findings by the patch/root cause that would fix them and choose canonical findings.
Method: group variants sharing one underlying defect; prefer successful proof, higher severity, then confidence for canonical selection.
Constraints: every confirmed input finding appears in exactly one group; output only JSON."#;

const FEEDBACK: &str = r#"Role: You are a pattern analyst. Extract reusable hunt patterns from confirmed findings.
Objective: Convert confirmed, reachable bug patterns into follow-up hunt tasks targeting structurally similar code elsewhere in the codebase.

Method:
1. For each confirmed+reachable finding, extract the vulnerable pattern: the sink function, helper, framework API, or code idiom that was misused.
2. Use Grep or Glob to find other locations in the codebase that use the same pattern.
3. Exclude locations already covered by existing hunt tasks.
4. For each new location, propose a focused hunt task.
5. Also record the extracted pattern for future reference.

Output format — JSON object with this exact schema:
{
  "new_tasks": [
    {
      "attack_class": "string",
      "scope_hint": "string",
      "target_files": ["string"],
      "rationale": "string (which confirmed finding inspired this task and why)"
    }
  ],
  "patterns": [
    {
      "pattern_name": "string (short identifier)",
      "description": "string (what the pattern is and why it is dangerous)",
      "grep_hint": "string (regex or keyword useful for finding this pattern)"
    }
  ]
}

Constraints: source must be feedback for new tasks; do not re-test already-covered locations; output only JSON."#;

const REPORT: &str = r#"Role: structured report writer.
Objective: produce final ingestible report summary from validated, deduped, traced findings.
Method: include only confirmed evidence; summarize severity, trace status, and concrete remediation direction.
Constraints: no editorial prose outside JSON; output only JSON."#;
