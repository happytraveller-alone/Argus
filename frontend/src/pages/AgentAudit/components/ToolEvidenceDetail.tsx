import type { ToolEvidencePayload } from "@/pages/AgentAudit/toolEvidence";
import ToolEvidencePreview from "@/pages/AgentAudit/components/ToolEvidencePreview";

export interface ToolEvidenceDetailProps {
	toolName?: string | null;
	evidence?: ToolEvidencePayload | null;
	rawOutput?: unknown;
}

function objectSource(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;
}

function stringifyRaw(value: unknown): string {
	return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function entryLines(entry: Record<string, unknown>): string[] {
	if (Array.isArray(entry.files) || Array.isArray(entry.directories)) {
		const directories = Array.isArray(entry.directories)
			? entry.directories.map(String)
			: [];
		const files = Array.isArray(entry.files) ? entry.files.map(String) : [];
		const visibleFiles = files.slice(0, Math.max(0, 40 - directories.length));
		return [...directories, ...visibleFiles];
	}

	const code = objectSource(entry.code);
	const command = String(entry.executionCommand ?? "").trim();
	const prefix = command ? [command] : [];
	if (Array.isArray(code?.lines)) {
		return prefix.concat(code.lines
			.map((line) => {
				const lineObject = objectSource(line);
				return String(lineObject?.text ?? lineObject?.content ?? "");
			})
			.filter(Boolean));
	}

	const stderr = String(entry.stderrPreview ?? "").trim();
	if (String(entry.status ?? "").toLowerCase() === "failed" && stderr) return [stderr];
	const stdout = String(entry.stdoutPreview ?? "").trim();
	if (stdout) return [stdout];
	return [];
}

function overviewText(evidence: ToolEvidencePayload): string {
	const entries = Array.isArray(evidence.entries) ? evidence.entries : [];
	const first = objectSource(entries[0]) ?? {};
	if (evidence.renderType === "search_hits") {
		const suffix = entries.length > 8 ? "，仅展示前 8 条" : "";
		return `${entries.length} 条命中${suffix}`;
	}
	if (evidence.renderType === "file_list") {
		return [
			first.directory,
			first.fileCount !== undefined ? `${first.fileCount} 文件` : undefined,
			first.dirCount !== undefined ? `${first.dirCount} 目录` : undefined,
			first.truncated ? "结果已截断，仅展示前 40 行" : undefined,
		]
			.filter(Boolean)
			.join(" · ");
	}
	return String(first.title ?? evidence.displayCommand ?? evidence.renderType);
}

function evidenceBody(evidence: ToolEvidencePayload): string {
	const entries = Array.isArray(evidence.entries) ? evidence.entries : [];
	if (evidence.renderType === "search_hits") {
		return entries
			.slice(0, 8)
			.map((entry) => {
				const item = objectSource(entry) ?? {};
				return `${item.filePath}:${item.matchLine} ${item.matchText ?? ""}`.trim();
			})
			.join("\n");
	}
	return entries
		.flatMap((entry) => entryLines(objectSource(entry) ?? {}))
		.slice(0, 40)
		.join("\n");
}

export default function ToolEvidenceDetail({
	toolName,
	evidence,
	rawOutput,
}: ToolEvidenceDetailProps) {
	if (!evidence) {
		return null;
	}

	return (
		<div className="space-y-3 rounded border border-border/50 bg-background/40 p-3">
			{toolName ? (
				<div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
					{toolName}
				</div>
			) : null}
			<ToolEvidencePreview evidence={evidence} />
			<section className="space-y-2">
				<div className="text-xs font-semibold text-muted-foreground">概览</div>
				<pre className="whitespace-pre-wrap break-words rounded bg-black/30 p-3 text-xs text-foreground/80">
					{overviewText(evidence)}
				</pre>
			</section>
			{evidenceBody(evidence) ? (
				<section className="space-y-2">
					<pre className="whitespace-pre-wrap break-words rounded bg-black/30 p-3 text-xs text-foreground/80">
						{evidenceBody(evidence)}
					</pre>
				</section>
			) : null}
			{rawOutput !== undefined ? (
				<details>
					<summary className="cursor-pointer text-xs font-semibold text-muted-foreground">
						查看原始数据
					</summary>
					<pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-3 text-xs text-muted-foreground">
						{stringifyRaw(rawOutput)}
					</pre>
				</details>
			) : null}
		</div>
	);
}
