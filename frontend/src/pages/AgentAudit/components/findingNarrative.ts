export interface FindingNarrativeInput {
  description?: string | null;
  description_markdown?: string | null;
  code_snippet?: string | null;
  code_context?: string | null;
  file_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  function_trigger_flow?: string[] | null;
  verification_evidence?: string | null;
  reachability_file?: string | null;
  reachability_function?: string | null;
  reachability_function_start_line?: number | null;
  reachability_function_end_line?: number | null;
}

export type NarrativeInlineToken =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "code"; text: string }
  | { kind: "latex_inline"; text: string };

export type NarrativeBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; inlines: NarrativeInlineToken[] }
  | { kind: "code_block"; language: string; code: string }
  | { kind: "latex_block"; formula: string };

export interface RawEvidenceEntry {
  key: string;
  label: string;
  value: string;
  truncated: boolean;
}

const RAW_EVIDENCE_FIELDS: Array<{ key: string; label: string }> = [
  { key: "description", label: "description" },
  { key: "verification_evidence", label: "verification_evidence" },
  { key: "function_trigger_flow", label: "function_trigger_flow" },
  { key: "reachability_file", label: "reachability_file" },
  { key: "reachability_function", label: "reachability_function" },
  {
    key: "reachability_function_start_line",
    label: "reachability_function_start_line",
  },
  {
    key: "reachability_function_end_line",
    label: "reachability_function_end_line",
  },
];

function asTrimmedText(value: unknown): string {
  return String(value ?? "").trim();
}

export function buildFindingNarrativeMarkdown(input: FindingNarrativeInput): string {
  const existingMarkdown = asTrimmedText(input.description_markdown);
  if (existingMarkdown) {
    return existingMarkdown;
  }

  const rootCause =
    asTrimmedText(input.description) || "当前证据不足，请补充上下文代码与可达性分析结果后复核。";
  // const codeSource =
  //   asTrimmedText(input.code_context) ||
  //   asTrimmedText(input.code_snippet) ||
  //   "（暂无可展示代码片段，请结合原始文件复核。）";
  // const safeCode = codeSource.replace(/```/g, "``");
  // const flowSummary =
  //   Array.isArray(input.function_trigger_flow) && input.function_trigger_flow.length > 0
  //     ? input.function_trigger_flow.map((item) => String(item)).join(" -> ")
  //     : "当前未提供完整触发路径，请结合 flow 证据继续验证。";
  return [
    rootCause,
  ].join("\n");
}

function findNextSpecialTokenIndex(source: string, startIndex: number): number {
  const indexes = [
    source.indexOf("**", startIndex),
    source.indexOf("`", startIndex),
    source.indexOf("$", startIndex),
  ].filter((index) => index >= 0);
  if (!indexes.length) {
    return -1;
  }
  return Math.min(...indexes);
}

function parseInlineTokens(text: string): NarrativeInlineToken[] {
  const source = String(text || "");
  const tokens: NarrativeInlineToken[] = [];
  let cursor = 0;

  while (cursor < source.length) {
    const next = findNextSpecialTokenIndex(source, cursor);
    if (next < 0) {
      const plainTail = source.slice(cursor);
      if (plainTail) tokens.push({ kind: "text", text: plainTail });
      break;
    }

    if (next > cursor) {
      tokens.push({ kind: "text", text: source.slice(cursor, next) });
    }

    if (source.startsWith("**", next)) {
      const end = source.indexOf("**", next + 2);
      if (end > next + 2) {
        tokens.push({ kind: "bold", text: source.slice(next + 2, end) });
        cursor = end + 2;
        continue;
      }
    }

    if (source[next] === "`") {
      const end = source.indexOf("`", next + 1);
      if (end > next + 1) {
        tokens.push({ kind: "code", text: source.slice(next + 1, end) });
        cursor = end + 1;
        continue;
      }
    }

    if (source[next] === "$" && source[next + 1] !== "$") {
      const end = source.indexOf("$", next + 1);
      if (end > next + 1 && source[end + 1] !== "$") {
        tokens.push({ kind: "latex_inline", text: source.slice(next + 1, end) });
        cursor = end + 1;
        continue;
      }
    }

    tokens.push({ kind: "text", text: source[next] });
    cursor = next + 1;
  }

  return tokens.length ? tokens : [{ kind: "text", text: source }];
}

export function parseFindingNarrativeMarkdown(content: string): NarrativeBlock[] {
  const source = String(content || "").replace(/\r\n/g, "\n");
  const lines = source.split("\n");
  const blocks: NarrativeBlock[] = [];
  let index = 0;

  const flushParagraph = (paragraphLines: string[]) => {
    const merged = paragraphLines.join("\n").trim();
    if (!merged) return;
    blocks.push({ kind: "paragraph", inlines: parseInlineTokens(merged) });
  };

  while (index < lines.length) {
    const rawLine = lines[index] ?? "";
    const trimmedLine = rawLine.trim();

    if (!trimmedLine) {
      index += 1;
      continue;
    }

    if (trimmedLine.startsWith("```")) {
      const language = trimmedLine.slice(3).trim() || "text";
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !String(lines[index] || "").trim().startsWith("```")) {
        codeLines.push(lines[index] || "");
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({ kind: "code_block", language, code: codeLines.join("\n") });
      continue;
    }

    if (trimmedLine.startsWith("$$")) {
      const blockLines: string[] = [];
      const inlineFormula = trimmedLine.endsWith("$$") && trimmedLine.length > 4;
      if (inlineFormula) {
        blockLines.push(trimmedLine.slice(2, -2));
        index += 1;
      } else {
        const firstLine = trimmedLine.slice(2);
        if (firstLine) blockLines.push(firstLine);
        index += 1;
        while (index < lines.length && !String(lines[index] || "").trim().endsWith("$$")) {
          blockLines.push(lines[index] || "");
          index += 1;
        }
        if (index < lines.length) {
          const last = String(lines[index] || "").trim();
          blockLines.push(last.slice(0, Math.max(last.length - 2, 0)));
          index += 1;
        }
      }
      const formula = blockLines.join("\n").trim();
      if (formula) {
        blocks.push({ kind: "latex_block", formula });
      }
      continue;
    }

    const headingMatch = trimmedLine.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      index += 1;
      continue;
    }

    const paragraphLines: string[] = [rawLine];
    index += 1;
    while (index < lines.length) {
      const nextLine = String(lines[index] || "");
      const nextTrimmed = nextLine.trim();
      if (!nextTrimmed) {
        index += 1;
        break;
      }
      if (nextTrimmed.startsWith("```") || nextTrimmed.startsWith("$$") || /^(#{1,6})\s+/.test(nextTrimmed)) {
        break;
      }
      paragraphLines.push(nextLine);
      index += 1;
    }
    flushParagraph(paragraphLines);
  }

  return blocks;
}

function normalizeEvidenceValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean).join("\n");
  }
  return String(value).trim();
}

export function collectRawEvidenceEntries(
  source: FindingNarrativeInput,
  maxLength = 2000,
): RawEvidenceEntry[] {
  const output: RawEvidenceEntry[] = [];
  for (const field of RAW_EVIDENCE_FIELDS) {
    const raw = normalizeEvidenceValue((source as Record<string, unknown>)[field.key]);
    if (!raw) continue;
    const truncated = raw.length > maxLength;
    const value = truncated ? `${raw.slice(0, maxLength)}…` : raw;
    output.push({
      key: field.key,
      label: field.label,
      value,
      truncated,
    });
  }
  return output;
}
