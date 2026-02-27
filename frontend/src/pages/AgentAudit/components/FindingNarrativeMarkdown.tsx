import { useMemo } from "react";
import type { ReactNode } from "react";
import {
  buildFindingNarrativeMarkdown,
  parseFindingNarrativeMarkdown,
  type FindingNarrativeInput,
  type NarrativeInlineToken,
} from "./findingNarrative";

interface FindingNarrativeMarkdownProps {
  finding: FindingNarrativeInput;
  searchQuery?: string;
  className?: string;
}

function renderHighlightedText(text: string, query: string): ReactNode {
  const plain = String(text || "");
  if (!query) return plain;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(${escaped})`, "gi");
  const parts = plain.split(pattern);
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <mark key={`${part}-${index}`} className="bg-primary/35 text-foreground px-0.5 rounded">
        {part}
      </mark>
    ) : (
      <span key={`${part}-${index}`}>{part}</span>
    ),
  );
}

function renderInlineToken(token: NarrativeInlineToken, query: string, key: string): ReactNode {
  if (token.kind === "bold") {
    return (
      <strong key={key} className="font-semibold text-foreground">
        {renderHighlightedText(token.text, query)}
      </strong>
    );
  }
  if (token.kind === "code") {
    return (
      <code key={key} className="font-mono text-[12px] px-1.5 py-0.5 rounded bg-muted border border-border">
        {token.text}
      </code>
    );
  }
  if (token.kind === "latex_inline") {
    return (
      <span
        key={key}
        className="font-mono text-[12px] px-1.5 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary"
      >
        {`$${token.text}$`}
      </span>
    );
  }
  return <span key={key}>{renderHighlightedText(token.text, query)}</span>;
}

export default function FindingNarrativeMarkdown({
  finding,
  searchQuery = "",
  className = "",
}: FindingNarrativeMarkdownProps) {
  const markdown = useMemo(() => buildFindingNarrativeMarkdown(finding), [finding]);
  const blocks = useMemo(() => parseFindingNarrativeMarkdown(markdown), [markdown]);

  return (
    <div className={`space-y-3 ${className}`.trim()}>
      {blocks.map((block, index) => {
        const key = `block-${index}`;
        if (block.kind === "heading") {
          const headingClass =
            block.level <= 2
              ? "text-base"
              : block.level === 3
                ? "text-sm"
                : "text-xs";
          return (
            <h4
              key={key}
              className={`${headingClass} font-semibold text-foreground mt-1 mb-1 tracking-wide`}
            >
              {renderHighlightedText(block.text, searchQuery)}
            </h4>
          );
        }

        if (block.kind === "code_block") {
          return (
            <div key={key} className="rounded-md border border-border overflow-hidden bg-card/60">
              <div className="px-3 py-1.5 text-[11px] text-muted-foreground border-b border-border uppercase tracking-wide">
                {block.language || "text"}
              </div>
              <pre className="text-xs font-mono p-3 whitespace-pre-wrap break-words overflow-auto max-h-[38vh]">
                {block.code}
              </pre>
            </div>
          );
        }

        if (block.kind === "latex_block") {
          return (
            <div
              key={key}
              className="rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-xs font-mono text-primary whitespace-pre-wrap break-words"
            >
              {`$$${block.formula}$$`}
            </div>
          );
        }

        return (
          <p key={key} className="text-sm leading-6 whitespace-pre-wrap break-words text-foreground/95">
            {block.inlines.map((token, tokenIndex) =>
              renderInlineToken(token, searchQuery, `${key}-token-${tokenIndex}`),
            )}
          </p>
        );
      })}
    </div>
  );
}
