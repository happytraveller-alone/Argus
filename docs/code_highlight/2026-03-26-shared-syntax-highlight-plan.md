# Shared Syntax-Highlighted Code Browser

## Goal

Add syntax highlighting to the existing read-only code browser without replacing the current viewer shell.

This document is intentionally written as an implementation breakdown, not as a product pitch. A later developer should be able to follow it step by step and land the feature without guessing about data flow, ownership, or test coverage.

## Codebase Facts Confirmed On 2026-03-26

These points are already true in the current codebase and must shape the implementation:

1. `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx` is the shared read-only code viewer used by `ProjectCodeBrowser` and multiple audit/evidence surfaces.
2. `FindingCodeWindow` currently supports only plain string line content. There is no token-level rendering yet.
3. `FindingCodeWindow` currently ignores `focusLine` and `highlightStartLine` / `highlightEndLine` whenever `displayLines` is provided, because the component returns `displayLines` directly and does not merge line decorations back in.
4. `frontend/src/pages/ProjectCodeBrowser.tsx` currently passes raw `code` into `FindingCodeWindow`; it does not precompute highlighted lines.
5. `frontend/src/pages/project-code-browser/model.ts` currently returns a synchronous `"ready"` state containing `content`, `size`, and `encoding`, but no preview-line model or syntax metadata.
6. Existing tests for this area use `renderToStaticMarkup` in Node, especially `frontend/tests/projectCodeBrowserPage.test.tsx`. That means the highlighting path cannot rely on a browser-only `useEffect` enhancement if we want deterministic markup-level tests.
7. `frontend/src/pages/finding-detail/FindingDetailCodePanel.tsx` has its own separate line renderer and is not a `FindingCodeWindow` consumer. It is out of scope for v1 highlighting.

## Scope Locked For V1

### In Scope

- Add a shared syntax-highlighting module.
- Extend the shared code line contract to support token segments.
- Update `FindingCodeWindow` to render token spans while preserving the existing line grid and anchors.
- Enable real syntax highlighting only in `ProjectCodeBrowser`.
- Add lightweight syntax metadata to the project-browser preview header.
- Add tests for language resolution, fallback rules, token segmentation, viewer rendering, and project-browser integration.

### Explicitly Out Of Scope

- Monaco, CodeMirror, or any editor runtime
- editable code
- manual language switching
- theme switching
- content-based language auto-detection
- highlighting in `FindingDetailCodePanel`
- retrofitting every existing `FindingCodeWindow` caller in the same change

## Frozen Architectural Decisions

### 1. Highlight Output Is Built Before Render

Do not build syntax-highlighted markup inside `FindingCodeWindow` with `useEffect`.

Reason:

- `renderToStaticMarkup` tests need deterministic output.
- `ProjectCodeBrowser` already has an async file-loading pipeline.
- The preview state should already know whether highlighting succeeded or fell back.

Implementation consequence:

- the `"ready"` branch of `ProjectCodeBrowserFileViewState` must carry prebuilt `displayLines`
- `ProjectCodeBrowser` file loading becomes responsible for awaiting syntax processing before caching the `"ready"` state

### 2. Shared Highlight Module Owns Tokenization, Not Styling

The shared module must output token classification data, not viewer-specific Tailwind classes.

The viewer remains the owner of visual styling.

Implementation consequence:

- token segments store raw token class identifiers
- `FindingCodeWindow` maps those identifiers to Tailwind text-color classes

### 3. `FindingCodeWindow` Must Merge Decorations Even When `displayLines` Exists

This is a required fix to preserve search-hit and focus-line behavior once `ProjectCodeBrowser` starts passing highlighted lines.

Final rule:

- when `displayLines` is absent, build lines from `code` exactly as today
- when `displayLines` is present, use it as the base line model
- in both cases, overlay `focusLine` and `highlightStartLine` / `highlightEndLine` from props onto the final rendered lines
- line-level flags already present on a provided line are preserved and OR-ed with prop-derived flags

## Exact File-Level Ownership

### New Files

Create a new shared folder:

- `frontend/src/shared/code-highlighting/types.ts`
- `frontend/src/shared/code-highlighting/languageMap.ts`
- `frontend/src/shared/code-highlighting/index.ts`

### Existing Files To Update

- `frontend/package.json`
- `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`
- `frontend/src/pages/ProjectCodeBrowser.tsx`
- `frontend/src/pages/project-code-browser/model.ts`
- `frontend/tests/projectCodeBrowserModel.test.ts`
- `frontend/tests/projectCodeBrowserPage.test.tsx`

### New Tests

- `frontend/tests/codeHighlight.test.ts`
- `frontend/tests/findingCodeWindow.test.tsx`

### Files That Should Not Change In V1 Unless Type Imports Force It

- `frontend/src/pages/finding-detail/FindingDetailCodePanel.tsx`
- `frontend/src/pages/finding-detail/viewModel.ts`
- `frontend/tests/findingDetailCodePanel.test.tsx`
- `frontend/tests/toolEvidenceRendering.test.tsx`

Those surfaces should stay plain-text consumers. If they compile against the extended line type, that is enough.

## Dependency Decision

Add these runtime dependencies to `frontend/package.json`:

- `lowlight`
- `highlight.js`

Do not introduce any additional editor package.

## Shared Types Contract

Define the shared types in `frontend/src/shared/code-highlighting/types.ts`.

```ts
export interface FindingCodeTokenSegment {
  text: string;
  tokenClasses?: string[];
}

export interface FindingCodeWindowDisplayLine {
  lineNumber: number | null;
  content: string;
  kind?: "code" | "placeholder";
  isHighlighted?: boolean;
  isFocus?: boolean;
  segments?: FindingCodeTokenSegment[];
}

export type CodeHighlightFallbackReason =
  | "path-not-supported"
  | "content-too-large"
  | "line-count-too-large"
  | "engine-load-failed"
  | "tokenize-failed";

export interface CodeHighlightResult {
  lines: FindingCodeWindowDisplayLine[];
  languageKey: string | null;
  languageLabel: string | null;
  status: "highlighted" | "plain-text";
  fallbackReason: CodeHighlightFallbackReason | null;
}
```

Rules:

- `content` remains the plain-text source of truth for every line.
- `segments` is optional and may be omitted for plain-text fallback.
- `segments` must never change the original text content.
- `segments` must never carry background or layout styling concerns.

## `FindingCodeWindow` Type Migration

Do not leave the line type declared only inside `FindingCodeWindow.tsx`.

Required migration:

1. Move the shared line type into `frontend/src/shared/code-highlighting/types.ts`.
2. Update `FindingCodeWindow.tsx` to import the type.
3. Re-export the type from `FindingCodeWindow.tsx` so existing imports do not need to move in this feature branch.

Example:

```ts
import type { FindingCodeWindowDisplayLine } from "@/shared/code-highlighting/types";

export type { FindingCodeWindowDisplayLine } from "@/shared/code-highlighting/types";
```

## Shared Highlight Module API

Implement these exports in `frontend/src/shared/code-highlighting/index.ts`.

```ts
export interface ResolveCodeLanguageResult {
  languageKey: string;
  languageLabel: string;
}

export function resolveCodeLanguageFromPath(
  filePath: string,
): ResolveCodeLanguageResult | null;

export function buildPlainDisplayLines(params: {
  content: string;
  lineStart?: number;
}): FindingCodeWindowDisplayLine[];

export async function buildCodeHighlightResult(params: {
  filePath: string;
  content: string;
  lineStart?: number;
}): Promise<CodeHighlightResult>;
```

Responsibilities:

- `resolveCodeLanguageFromPath` handles deterministic path-based resolution only.
- `buildPlainDisplayLines` is the single shared plain-text line builder for this feature.
- `buildCodeHighlightResult` owns fallback rules, lazy engine loading, AST flattening, and per-line segment generation.

## Language Resolution Policy

### Resolution Order

Use this exact order:

1. special filename match
2. extension match
3. plain-text fallback with `fallbackReason = "path-not-supported"`

Do not use content-based auto-detection.

### Exact Initial Mapping Table

Implement these mappings in `frontend/src/shared/code-highlighting/languageMap.ts`.

#### Special Filenames

- `Dockerfile` -> `dockerfile` / label `Dockerfile`
- `Makefile` -> `makefile` / label `Makefile`
- `GNUmakefile` -> `makefile` / label `Makefile`
- `nginx.conf` -> `nginx` / label `Nginx`
- `pom.xml` -> `xml` / label `XML`

#### Extensions

- `.js` -> `javascript` / label `JavaScript`
- `.cjs` -> `javascript` / label `JavaScript`
- `.mjs` -> `javascript` / label `JavaScript`
- `.jsx` -> `jsx` / label `JSX`
- `.ts` -> `typescript` / label `TypeScript`
- `.cts` -> `typescript` / label `TypeScript`
- `.mts` -> `typescript` / label `TypeScript`
- `.tsx` -> `tsx` / label `TSX`
- `.json` -> `json` / label `JSON`
- `.jsonc` -> `json` / label `JSONC`
- `.yaml` -> `yaml` / label `YAML`
- `.yml` -> `yaml` / label `YAML`
- `.toml` -> `toml` / label `TOML`
- `.ini` -> `ini` / label `INI`
- `.properties` -> `properties` / label `Properties`
- `.md` -> `markdown` / label `Markdown`
- `.diff` -> `diff` / label `Diff`
- `.patch` -> `diff` / label `Diff`
- `.java` -> `java` / label `Java`
- `.kt` -> `kotlin` / label `Kotlin`
- `.kts` -> `kotlin` / label `Kotlin`
- `.py` -> `python` / label `Python`
- `.go` -> `go` / label `Go`
- `.php` -> `php` / label `PHP`
- `.rb` -> `ruby` / label `Ruby`
- `.rs` -> `rust` / label `Rust`
- `.c` -> `c` / label `C`
- `.h` -> `c` / label `C`
- `.cpp` -> `cpp` / label `C++`
- `.cc` -> `cpp` / label `C++`
- `.cxx` -> `cpp` / label `C++`
- `.hpp` -> `cpp` / label `C++`
- `.hh` -> `cpp` / label `C++`
- `.cs` -> `csharp` / label `C#`
- `.swift` -> `swift` / label `Swift`
- `.sh` -> `bash` / label `Shell`
- `.bash` -> `bash` / label `Shell`
- `.zsh` -> `bash` / label `Shell`
- `.sql` -> `sql` / label `SQL`
- `.html` -> `xml` / label `HTML`
- `.htm` -> `xml` / label `HTML`
- `.xml` -> `xml` / label `XML`
- `.css` -> `css` / label `CSS`
- `.scss` -> `scss` / label `SCSS`
- `.conf` -> `ini` / label `Config`

Notes:

- `.jsonc` intentionally reuses the JSON highlighter in v1.
- generic `.conf` intentionally falls back to `ini`; only `nginx.conf` receives the Nginx mapping.
- `.env` and `.env.*` files are intentionally plain text in v1 and must not receive a language mapping.

## Highlight Engine Loading

### Loader Rules

Implement lazy loading in `frontend/src/shared/code-highlighting/index.ts`.

Required behavior:

1. The highlighter is loaded on demand.
2. The module caches the in-flight promise and the resolved engine instance.
3. If loading fails, clear the cached promise so a later call can retry.
4. Do not import every language eagerly in the initial route bundle.

### Engine Shape

The loader should return an object with:

- a `lowlight` instance
- only the curated language registrations listed above

Do not rely on `highlightAuto`.

## Plain Text Line Builder Rules

`buildPlainDisplayLines` must normalize and split text exactly once using:

```ts
String(content || "").replace(/\r\n/g, "\n").split("\n")
```

This preserves current line-count behavior, including a trailing empty line when the source ends with `\n`.

Returned line model:

- `lineNumber` starts at `lineStart ?? 1`
- `kind` is always `"code"`
- `segments` is omitted
- `isHighlighted` and `isFocus` are omitted

## Fallback Rules

Apply these checks in `buildCodeHighlightResult` in this exact order:

1. Normalize content to `\n`
2. If `content.length > 200_000`, return plain text with `fallbackReason = "content-too-large"`
3. Compute line count
4. If `lineCount > 5_000`, return plain text with `fallbackReason = "line-count-too-large"`
5. Resolve language from path
6. If language resolution fails, return plain text with `fallbackReason = "path-not-supported"`
7. Load the highlight engine
8. If engine loading fails, return plain text with `fallbackReason = "engine-load-failed"`
9. Tokenize
10. If tokenization or line segmentation throws, return plain text with `fallbackReason = "tokenize-failed"`

For the project-browser flow, non-text file handling remains outside this module. `ProjectCodeBrowser` should continue mapping `response.is_text === false` to the existing `"unavailable"` state before any highlight work begins.

## Token Segmentation Rules

Flatten the lowlight AST into `FindingCodeTokenSegment[]` per line.

Required rules:

1. Recursively walk text nodes and element nodes.
2. Carry the active `className` stack from parent nodes down to leaf text.
3. Split text on `\n`.
4. Start a new output line each time a newline is encountered.
5. Preserve empty lines.
6. Merge adjacent segments when their `tokenClasses` arrays are equal after normalization.
7. Remove empty segments unless they are the only representation of an otherwise non-empty line fragment.
8. The final `lines.length` must exactly equal the plain-text line count produced by the same normalized source.
9. Every output line must still include the original plain `content`.

Do not let token segmentation alter the source text, trim whitespace, or collapse indentation.

## `FindingCodeWindow` Rendering Contract

### Header

Stop discarding the existing `meta` prop.

Render rule:

- left side: existing path header text
- right side: optional metadata chips or inline labels from `meta`
- if `meta` is empty, header layout should remain visually unchanged

This avoids inventing a new header prop for `ProjectCodeBrowser`.

### Line Decoration Merge

Implement a helper inside `FindingCodeWindow.tsx`:

```ts
function applyLineDecorations(
  lines: FindingCodeWindowDisplayLine[],
  options: {
    focusLine: number | null;
    highlightStartLine: number | null;
    highlightEndLine: number | null;
  },
): FindingCodeWindowDisplayLine[]
```

Rules:

- prop-derived highlight/focus flags are OR-ed with any existing line flags
- placeholder lines (`lineNumber === null`) never become focus or highlight lines
- this helper runs for both plain generated lines and provided `displayLines`

### Token Rendering

When `line.segments` is present and non-empty:

- render the `<pre>` exactly as today
- render child `<span>` elements for each segment
- use `segment.text`
- use a new token-class resolver in `FindingCodeWindow.tsx` to map `tokenClasses` to Tailwind text colors

When `line.segments` is absent:

- render `line.content || " "` exactly as today

### Styling Priority

Priority order is fixed:

1. focus-line background and focus-line readability
2. search-hit background and search-hit readability
3. syntax token hue
4. default plain-text color

Implementation rule:

- token spans may set text color only
- token spans must not set background color, border, font weight, or opacity that weakens the existing focus/highlight states

### Token Color Map

Add an explicit token-group map in `FindingCodeWindow.tsx`.

Required groups:

- `comment`, `quote`, `meta` -> muted slate text
- `keyword`, `selector-tag`, `doctag` -> sky text
- `string`, `regexp`, `template-variable` -> emerald text
- `number`, `literal`, `symbol`, `bullet` -> amber text
- `title`, `function`, `section`, `type`, `class` -> cyan text
- `attr`, `attribute`, `property`, `variable` -> blue text
- unknown token classes -> inherit current line text color

The implementation may support more classes, but the above groups must exist so the visual output stays deterministic.

## `ProjectCodeBrowser` State Contract

Update the `"ready"` variant in `frontend/src/pages/project-code-browser/model.ts` to carry prebuilt preview lines and syntax metadata.

Target shape:

```ts
| {
    status: "ready";
    filePath: string;
    content: string;
    size: number;
    encoding: string;
    displayLines: FindingCodeWindowDisplayLine[];
    syntaxLanguageKey: string | null;
    syntaxLanguageLabel: string | null;
    syntaxStatus: "highlighted" | "plain-text";
    syntaxFallbackReason: CodeHighlightFallbackReason | null;
  }
```

Rules:

- `displayLines` is always present for `"ready"` text files
- plain-text preview also uses `displayLines`; it is not a separate render path anymore
- `content` stays present for search and any future copy/export behavior

## `ProjectCodeBrowser` Ready-State Builder

Replace the existing one-step success mapping with an async ready-state builder.

Implement one exported helper in `frontend/src/pages/project-code-browser/model.ts`:

```ts
export async function buildProjectCodeBrowserFileSuccessState(
  response: ProjectFileContentResponse,
): Promise<ProjectCodeBrowserFileViewState>
```

Rules:

- if `response.is_text` is false, return the current `"unavailable"` state immediately
- otherwise call `buildCodeHighlightResult`
- map the result into the `"ready"` state shape above

`resolveProjectCodeBrowserFileFailure` stays unchanged.

## `ProjectCodeBrowser.tsx` Integration

### `loadFileState`

Update `loadFileState` so that the request pipeline is:

1. fetch file content
2. await `buildProjectCodeBrowserFileSuccessState(response)`
3. cache the returned state
4. return the cached state

Do not cache an intermediate raw-text `"ready"` state first and then patch in highlighting later. The preview should enter `"ready"` only once for a single file load.

### Preview Rendering

Update `ProjectCodeBrowserPreview`:

- compute `lineEnd` from `selectedFileState.displayLines.length`
- pass `displayLines={selectedFileState.displayLines}` into `FindingCodeWindow`
- continue passing `focusLine` and highlight props from `previewDecorations`
- pass `meta` based on syntax fields

### Header Metadata Rules

Build `meta` with these exact rules:

1. if `syntaxLanguageLabel` is present and `syntaxStatus === "highlighted"`, `meta = [syntaxLanguageLabel]`
2. if `syntaxLanguageLabel` is present and `syntaxStatus === "plain-text"`, `meta = [syntaxLanguageLabel, "纯文本回退"]`
3. if `syntaxLanguageLabel` is null and `syntaxStatus === "plain-text"`, `meta = ["纯文本"]`

Do not expose internal fallback reason strings in the UI in v1.

## Test Plan Locked To Concrete Files

### 1. New `frontend/tests/codeHighlight.test.ts`

Add direct tests for the shared module:

- resolves special filenames before extensions
- keeps `.env.local` as plain-text fallback
- resolves `.tsx` as TSX
- resolves `.jsonc` to JSONC label with JSON engine key
- returns `path-not-supported` for an unknown extension
- returns `content-too-large` when content length is `200_001`
- returns `line-count-too-large` when line count is `5_001`
- token segmentation preserves total line count
- token segmentation preserves empty lines
- token segmentation preserves trailing newline behavior

### 2. New `frontend/tests/findingCodeWindow.test.tsx`

Add direct viewer tests for `FindingCodeWindow`:

- plain-text rendering still works without `segments`
- token spans render when `segments` is provided
- focus-line classes still apply when `displayLines` is provided
- search-hit classes still apply when `displayLines` is provided
- prop-derived focus/highlight flags are merged with existing line flags
- `meta` renders in the header when provided
- `project-browser` preset still emits the full-height structure

### 3. Update `frontend/tests/projectCodeBrowserModel.test.ts`

Update or extend model tests for:

- `buildProjectCodeBrowserFileSuccessState` returns `"unavailable"` for non-text files
- `buildProjectCodeBrowserFileSuccessState` returns highlighted `"ready"` state for a supported file
- highlighted `"ready"` state includes `displayLines`
- plain-text fallback `"ready"` state still includes `displayLines`

### 4. Update `frontend/tests/projectCodeBrowserPage.test.tsx`

Update or add page-level tests for:

- supported files render token spans in preview markup
- preview header shows language metadata
- unsupported language fallback still renders readable plain text
- search-result focus decoration still lands on the correct line when `displayLines` is supplied
- `data-line-number` anchors are preserved in highlighted mode

### 5. No V1 Test Work Required Here

Do not add highlight-specific tests to:

- `frontend/tests/findingDetailCodePanel.test.tsx`
- `frontend/tests/toolEvidenceRendering.test.tsx`

Those surfaces are only regression watchers for backward compatibility in this feature.

## Implementation Sequence

Land the work in this order.

### Step 1. Shared types and shared highlight module

Done when:

- new shared folder exists
- language resolution is deterministic
- plain-text and highlighted line builders are implemented
- `codeHighlight.test.ts` passes

### Step 2. `FindingCodeWindow` token rendering and decoration merge

Done when:

- the component accepts `segments`
- `displayLines` no longer disables prop-driven focus/highlight decorations
- `meta` is rendered
- `findingCodeWindow.test.tsx` passes

### Step 3. `ProjectCodeBrowser` state integration

Done when:

- `"ready"` state carries `displayLines` and syntax metadata
- file loading awaits highlight result creation
- preview uses highlighted lines
- `projectCodeBrowserModel.test.ts` and `projectCodeBrowserPage.test.tsx` pass

### Step 4. Final regression pass

Run at least:

- `cd frontend && pnpm test:node tests/codeHighlight.test.ts`
- `cd frontend && pnpm test:node tests/findingCodeWindow.test.tsx`
- `cd frontend && pnpm test:node tests/projectCodeBrowserModel.test.ts`
- `cd frontend && pnpm test:node tests/projectCodeBrowserPage.test.tsx`

If time permits, run the full frontend Node test suite as a final regression check.

## Acceptance Criteria

The feature is complete only when all of the following are true:

- `ProjectCodeBrowser` preview renders syntax-highlighted token spans for supported text files
- unsupported-language, `.env` / `.env.*`, and oversized-file cases render plain-text preview through the same `displayLines` path
- search-hit and focus-line decorations still work after `displayLines` is introduced
- `data-line-number` anchors are preserved
- existing non-browser `FindingCodeWindow` consumers remain backward compatible
- the syntax engine is lazy-loaded and memoized
- new tests pass and existing project-browser tests remain green

## Confirmed Product Decisions

These choices are fixed for v1 and should not be revisited during implementation unless the product requirement changes:

1. `.env` and `.env.*` files render as plain text.
2. Only `nginx.conf` receives the Nginx mapping; generic `.conf` files stay on the generic config fallback path.
3. The preview header fallback copy must be localized to Chinese: `纯文本` and `纯文本回退`.

## Development Execution Checklist

Use this section as the actual implementation runbook. Each item should be completed in order and checked off before moving on.

### Phase 0. Prep

- [ ] Read this document end to end before editing code.
- [ ] Inspect current implementations in:
  - `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`
  - `frontend/src/pages/ProjectCodeBrowser.tsx`
  - `frontend/src/pages/project-code-browser/model.ts`
- [ ] Confirm `frontend/package.json` does not already contain `lowlight` or `highlight.js`.
- [ ] Confirm current project-browser tests still pass before starting:
  - `cd frontend && pnpm test:node tests/projectCodeBrowserModel.test.ts`
  - `cd frontend && pnpm test:node tests/projectCodeBrowserPage.test.tsx`

### Phase 1. Shared highlight foundation

**Files**

- Create: `frontend/src/shared/code-highlighting/types.ts`
- Create: `frontend/src/shared/code-highlighting/languageMap.ts`
- Create: `frontend/src/shared/code-highlighting/index.ts`
- Modify: `frontend/package.json`

- [ ] Add `lowlight` and `highlight.js` to `frontend/package.json`.
- [ ] Move the shared line type out of `FindingCodeWindow.tsx` into `types.ts`.
- [ ] Define `FindingCodeTokenSegment`, `FindingCodeWindowDisplayLine`, `CodeHighlightFallbackReason`, and `CodeHighlightResult`.
- [ ] Implement deterministic language resolution in `languageMap.ts`.
- [ ] Implement the plain-text line builder in `index.ts`.
- [ ] Implement lazy engine loading with in-memory promise caching in `index.ts`.
- [ ] Implement token flattening and per-line segment generation in `index.ts`.
- [ ] Implement `buildCodeHighlightResult` with the fallback order frozen in this document.
- [ ] Ensure `.env` and `.env.*` return plain-text fallback rather than a resolved language.

**Verification**

- [ ] Add `frontend/tests/codeHighlight.test.ts`.
- [ ] Write the failing tests first for:
  - language resolution
  - `.env.*` plain-text fallback
  - oversize fallbacks
  - line-count preservation
  - empty-line preservation
  - trailing-newline preservation
- [ ] Run: `cd frontend && pnpm test:node tests/codeHighlight.test.ts`
- [ ] Make the tests pass without touching `FindingCodeWindow` or `ProjectCodeBrowser` yet.

### Phase 2. Shared viewer upgrade

**Files**

- Modify: `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`
- Create: `frontend/tests/findingCodeWindow.test.tsx`

- [ ] Import the shared line type from `frontend/src/shared/code-highlighting/types.ts`.
- [ ] Re-export `FindingCodeWindowDisplayLine` from `FindingCodeWindow.tsx` to preserve existing imports.
- [ ] Stop discarding the `meta` prop.
- [ ] Add a helper that merges prop-based focus/highlight decorations onto both generated lines and provided `displayLines`.
- [ ] Keep placeholder lines immune to focus/highlight decoration.
- [ ] Add token-class-to-color resolution inside `FindingCodeWindow.tsx`.
- [ ] Render token spans only when `line.segments` exists and has content.
- [ ] Keep the existing outer DOM structure unchanged:
  - same line grid
  - same gutter
  - same `data-line-number`
  - same project-browser full-height shell
- [ ] Verify token spans never override focus/search-hit background treatment.

**Verification**

- [ ] Add `frontend/tests/findingCodeWindow.test.tsx`.
- [ ] Write the failing tests first for:
  - plain-text rendering
  - token rendering
  - focus and highlight merge with provided `displayLines`
  - `meta` rendering
  - project-browser preset structure
- [ ] Run: `cd frontend && pnpm test:node tests/findingCodeWindow.test.tsx`
- [ ] Make the tests pass before changing `ProjectCodeBrowser`.

### Phase 3. Project code browser integration

**Files**

- Modify: `frontend/src/pages/project-code-browser/model.ts`
- Modify: `frontend/src/pages/ProjectCodeBrowser.tsx`
- Modify: `frontend/tests/projectCodeBrowserModel.test.ts`
- Modify: `frontend/tests/projectCodeBrowserPage.test.tsx`

- [ ] Extend the `"ready"` branch of `ProjectCodeBrowserFileViewState` to carry:
  - `displayLines`
  - `syntaxLanguageKey`
  - `syntaxLanguageLabel`
  - `syntaxStatus`
  - `syntaxFallbackReason`
- [ ] Replace the synchronous text-file success helper with `buildProjectCodeBrowserFileSuccessState`.
- [ ] Keep the non-text `"unavailable"` path unchanged.
- [ ] Update `loadFileState` in `ProjectCodeBrowser.tsx` to await the new async success builder before caching the ready state.
- [ ] Update preview rendering to use `selectedFileState.displayLines`.
- [ ] Compute preview `lineEnd` from `displayLines.length`.
- [ ] Build preview header metadata using the fixed Chinese copy:
  - highlighted: language only
  - plain fallback with language: `语言名 + 纯文本回退`
  - plain fallback without language: `纯文本`
- [ ] Keep preview decorations flowing through `focusLine` and highlight props.
- [ ] Confirm search-result navigation still lands on the correct line after `displayLines` is introduced.

**Verification**

- [ ] Extend `frontend/tests/projectCodeBrowserModel.test.ts` first, then run:
  - `cd frontend && pnpm test:node tests/projectCodeBrowserModel.test.ts`
- [ ] Extend `frontend/tests/projectCodeBrowserPage.test.tsx` first, then run:
  - `cd frontend && pnpm test:node tests/projectCodeBrowserPage.test.tsx`
- [ ] Confirm page-level markup now includes:
  - token spans for supported languages
  - language metadata
  - preserved `data-line-number`
  - preserved focus/highlight classes

### Phase 4. Regression sweep

- [ ] Re-run the focused suite:
  - `cd frontend && pnpm test:node tests/codeHighlight.test.ts`
  - `cd frontend && pnpm test:node tests/findingCodeWindow.test.tsx`
  - `cd frontend && pnpm test:node tests/projectCodeBrowserModel.test.ts`
  - `cd frontend && pnpm test:node tests/projectCodeBrowserPage.test.tsx`
- [ ] Spot-check that these existing tests still pass if they are sensitive to shared viewer behavior:
  - `cd frontend && pnpm test:node tests/toolEvidenceRendering.test.tsx`
  - `cd frontend && pnpm test:node tests/findingDetailCodePanel.test.tsx`
- [ ] If time allows, run: `cd frontend && pnpm test:node`
- [ ] Do not merge if any failure is “explained away” by the new behavior without either updating the plan or explicitly confirming the change.

## Suggested Commit Order

Use small commits that each leave the branch in a testable state. The sequence below is the default unless implementation reveals a hard dependency that forces two adjacent commits to merge.

### Commit 1. Shared highlight primitives

**Message**

`feat(frontend): add shared code highlighting core`

**Include**

- `frontend/package.json`
- `frontend/src/shared/code-highlighting/types.ts`
- `frontend/src/shared/code-highlighting/languageMap.ts`
- `frontend/src/shared/code-highlighting/index.ts`
- `frontend/tests/codeHighlight.test.ts`

**Must pass before commit**

- `cd frontend && pnpm test:node tests/codeHighlight.test.ts`

### Commit 2. Viewer token rendering

**Message**

`feat(frontend): support tokenized lines in finding code window`

**Include**

- `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`
- `frontend/tests/findingCodeWindow.test.tsx`

**Must pass before commit**

- `cd frontend && pnpm test:node tests/findingCodeWindow.test.tsx`
- optionally rerun `tests/codeHighlight.test.ts`

### Commit 3. Project browser state integration

**Message**

`feat(frontend): enable syntax highlighted preview in project code browser`

**Include**

- `frontend/src/pages/project-code-browser/model.ts`
- `frontend/src/pages/ProjectCodeBrowser.tsx`
- `frontend/tests/projectCodeBrowserModel.test.ts`
- `frontend/tests/projectCodeBrowserPage.test.tsx`

**Must pass before commit**

- `cd frontend && pnpm test:node tests/projectCodeBrowserModel.test.ts`
- `cd frontend && pnpm test:node tests/projectCodeBrowserPage.test.tsx`
- rerun `tests/findingCodeWindow.test.tsx`

### Commit 4. Final stabilization commit if needed

Only create this commit if regression fixes are needed after the integration commit.

**Message**

`test(frontend): stabilize syntax highlight regressions`

**Include**

- only narrowly scoped follow-up fixes
- only tests or minimal regression patches discovered in Phase 4

**Must pass before commit**

- the full focused suite from Phase 4

## Handoff Rule

If another developer picks this up later, they should start at `Phase 1`, not by jumping into `ProjectCodeBrowser.tsx`. The architecture only stays clean if the shared layer lands before the page integration.
