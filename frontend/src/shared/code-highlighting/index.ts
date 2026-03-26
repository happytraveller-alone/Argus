import type { LanguageFn } from "highlight.js";
import { resolveCodeLanguageFromPath, type ResolveCodeLanguageResult } from "./languageMap";
import type {
	CodeHighlightResult,
	FindingCodeTokenSegment,
	FindingCodeWindowDisplayLine,
} from "./types";

interface BuildPlainDisplayLinesParams {
	content: string;
	lineStart?: number;
}

interface BuildCodeHighlightResultParams {
	filePath: string;
	content: string;
	lineStart?: number;
}

interface HighlightEngine {
	lowlight: {
		highlight: (language: string, value: string) => unknown;
		register: (grammars: Readonly<Record<string, LanguageFn>>) => undefined;
		registerAlias: (
			aliases: Readonly<Record<string, ReadonlyArray<string> | string>>,
		) => undefined;
	};
}

let cachedHighlightEngine: HighlightEngine | null = null;
let cachedHighlightEnginePromise: Promise<HighlightEngine> | null = null;

function normalizeCodeContent(content: string): string {
	return String(content || "").replace(/\r\n/g, "\n");
}

function normalizeTokenClassName(className: string): string {
	return String(className || "")
		.trim()
		.replace(/^hljs-/, "");
}

function normalizeTokenClasses(tokenClasses: string[]): string[] {
	if (tokenClasses.length === 0) return [];
	const deduped = new Set<string>();
	for (const tokenClass of tokenClasses) {
		const normalizedClass = normalizeTokenClassName(tokenClass);
		if (normalizedClass) {
			deduped.add(normalizedClass);
		}
	}
	return Array.from(deduped.values());
}

function tokenClassArraysEqual(left: string[] | undefined, right: string[] | undefined): boolean {
	if (!left?.length && !right?.length) return true;
	if (!left || !right) return false;
	if (left.length !== right.length) return false;
	for (let index = 0; index < left.length; index += 1) {
		if (left[index] !== right[index]) return false;
	}
	return true;
}

function appendTokenSegment(
	segments: FindingCodeTokenSegment[],
	text: string,
	tokenClasses: string[],
) {
	if (!text) return;
	const normalizedClasses = normalizeTokenClasses(tokenClasses);
	const nextTokenClasses = normalizedClasses.length > 0 ? normalizedClasses : undefined;
	const previousSegment = segments[segments.length - 1];
	if (
		previousSegment &&
		tokenClassArraysEqual(previousSegment.tokenClasses, nextTokenClasses)
	) {
		previousSegment.text += text;
		return;
	}
	segments.push({
		text,
		tokenClasses: nextTokenClasses,
	});
}

function asRecord(value: unknown): Record<string, unknown> | null {
	if (!value || typeof value !== "object" || Array.isArray(value)) return null;
	return value as Record<string, unknown>;
}

function getNodeType(node: unknown): string {
	const record = asRecord(node);
	return typeof record?.type === "string" ? record.type : "";
}

function getNodeValue(node: unknown): string {
	const record = asRecord(node);
	return typeof record?.value === "string" ? record.value : "";
}

function getNodeChildren(node: unknown): unknown[] {
	const record = asRecord(node);
	return Array.isArray(record?.children) ? record.children : [];
}

function getNodeClassNames(node: unknown): string[] {
	if (getNodeType(node) !== "element") return [];
	const record = asRecord(node);
	const properties = asRecord(record?.properties);
	const classNameValue = properties?.className;
	if (!classNameValue) return [];
	if (Array.isArray(classNameValue)) {
		return classNameValue
			.map((value) => String(value || "").trim())
			.filter(Boolean);
	}
	return [String(classNameValue)];
}

function buildHighlightedSegmentsByLine(root: unknown): FindingCodeTokenSegment[][] {
	const lines: FindingCodeTokenSegment[][] = [[]];

	const walk = (node: unknown, inheritedClasses: string[]) => {
		const nodeType = getNodeType(node);
		if (nodeType === "text") {
			const parts = getNodeValue(node).split("\n");
			for (let index = 0; index < parts.length; index += 1) {
				appendTokenSegment(lines[lines.length - 1], parts[index], inheritedClasses);
				if (index < parts.length - 1) {
					lines.push([]);
				}
			}
			return;
		}

		if (nodeType !== "element") return;
		const nextClasses = inheritedClasses.concat(getNodeClassNames(node));
		for (const child of getNodeChildren(node)) {
			walk(child, nextClasses);
		}
	};

	for (const child of getNodeChildren(root)) {
		walk(child, []);
	}

	return lines.map((segments) => segments.filter((segment) => segment.text.length > 0));
}

async function loadHighlightEngine(): Promise<HighlightEngine> {
	if (cachedHighlightEngine) {
		return cachedHighlightEngine;
	}
	if (cachedHighlightEnginePromise) {
		return cachedHighlightEnginePromise;
	}

	cachedHighlightEnginePromise = (async () => {
		const [{ createLowlight }, languageModules] = await Promise.all([
			import("lowlight"),
			Promise.all([
				import("highlight.js/lib/languages/bash"),
				import("highlight.js/lib/languages/c"),
				import("highlight.js/lib/languages/cpp"),
				import("highlight.js/lib/languages/csharp"),
				import("highlight.js/lib/languages/css"),
				import("highlight.js/lib/languages/diff"),
				import("highlight.js/lib/languages/dockerfile"),
				import("highlight.js/lib/languages/go"),
				import("highlight.js/lib/languages/ini"),
				import("highlight.js/lib/languages/java"),
				import("highlight.js/lib/languages/javascript"),
				import("highlight.js/lib/languages/json"),
				import("highlight.js/lib/languages/kotlin"),
				import("highlight.js/lib/languages/makefile"),
				import("highlight.js/lib/languages/markdown"),
				import("highlight.js/lib/languages/nginx"),
				import("highlight.js/lib/languages/php"),
				import("highlight.js/lib/languages/properties"),
				import("highlight.js/lib/languages/python"),
				import("highlight.js/lib/languages/ruby"),
				import("highlight.js/lib/languages/rust"),
				import("highlight.js/lib/languages/scss"),
				import("highlight.js/lib/languages/sql"),
				import("highlight.js/lib/languages/swift"),
				import("highlight.js/lib/languages/typescript"),
				import("highlight.js/lib/languages/xml"),
				import("highlight.js/lib/languages/yaml"),
			]),
		]);

		const lowlight = createLowlight();
		const [
			bash,
			c,
			cpp,
			csharp,
			css,
			diff,
			dockerfile,
			go,
			ini,
			java,
			javascript,
			json,
			kotlin,
			makefile,
			markdown,
			nginx,
			php,
			properties,
			python,
			ruby,
			rust,
			scss,
			sql,
			swift,
			typescript,
			xml,
			yaml,
		] = languageModules.map((module) => module.default);

		lowlight.register({
			bash,
			c,
			cpp,
			csharp,
			css,
			diff,
			dockerfile,
			go,
			ini,
			java,
			javascript,
			json,
			kotlin,
			makefile,
			markdown,
			nginx,
			php,
			properties,
			python,
			ruby,
			rust,
			scss,
			sql,
			swift,
			typescript,
			xml,
			yaml,
		});
		lowlight.registerAlias({
			javascript: "jsx",
			typescript: "tsx",
			ini: "toml",
		});

			const nextEngine: HighlightEngine = { lowlight };
			cachedHighlightEngine = nextEngine;
			return nextEngine;
		})();

	try {
		return await cachedHighlightEnginePromise;
	} catch (error) {
		cachedHighlightEnginePromise = null;
		cachedHighlightEngine = null;
		throw error;
	}
}

function createPlainTextFallbackResult(params: {
	lines: FindingCodeWindowDisplayLine[];
	resolvedLanguage: ResolveCodeLanguageResult | null;
	fallbackReason: CodeHighlightResult["fallbackReason"];
}): CodeHighlightResult {
	return {
		lines: params.lines,
		languageKey: params.resolvedLanguage?.languageKey ?? null,
		languageLabel: params.resolvedLanguage?.languageLabel ?? null,
		status: "plain-text",
		fallbackReason: params.fallbackReason,
	};
}

export { resolveCodeLanguageFromPath, type ResolveCodeLanguageResult };

export function buildPlainDisplayLines(
	params: BuildPlainDisplayLinesParams,
): FindingCodeWindowDisplayLine[] {
	const normalizedContent = normalizeCodeContent(params.content);
	const rawLines = normalizedContent.split("\n");
	const firstLine =
		typeof params.lineStart === "number" && Number.isFinite(params.lineStart)
			? params.lineStart
			: 1;
	return rawLines.map((line, index) => ({
		lineNumber: firstLine + index,
		content: line,
		kind: "code" as const,
	}));
}

export async function buildCodeHighlightResult(
	params: BuildCodeHighlightResultParams,
): Promise<CodeHighlightResult> {
	const normalizedContent = normalizeCodeContent(params.content);
	const plainLines = buildPlainDisplayLines({
		content: normalizedContent,
		lineStart: params.lineStart,
	});

	if (normalizedContent.length > 200_000) {
		return createPlainTextFallbackResult({
			lines: plainLines,
			resolvedLanguage: null,
			fallbackReason: "content-too-large",
		});
	}

	if (plainLines.length > 5_000) {
		return createPlainTextFallbackResult({
			lines: plainLines,
			resolvedLanguage: null,
			fallbackReason: "line-count-too-large",
		});
	}

	const resolvedLanguage = resolveCodeLanguageFromPath(params.filePath);
	if (!resolvedLanguage) {
		return createPlainTextFallbackResult({
			lines: plainLines,
			resolvedLanguage: null,
			fallbackReason: "path-not-supported",
		});
	}

	let engine: HighlightEngine;
	try {
		engine = await loadHighlightEngine();
	} catch {
		return createPlainTextFallbackResult({
			lines: plainLines,
			resolvedLanguage,
			fallbackReason: "engine-load-failed",
		});
	}

	try {
		const highlightedRoot = engine.lowlight.highlight(
			resolvedLanguage.languageKey,
			normalizedContent,
		);
		const segmentedLines = buildHighlightedSegmentsByLine(highlightedRoot);
		if (segmentedLines.length !== plainLines.length) {
			throw new Error(
				`segmented line count mismatch: ${segmentedLines.length} !== ${plainLines.length}`,
			);
		}

		return {
			lines: plainLines.map((line, index) => {
				const segments = segmentedLines[index];
				return segments?.length
					? {
							...line,
							segments,
					  }
					: line;
			}),
			languageKey: resolvedLanguage.languageKey,
			languageLabel: resolvedLanguage.languageLabel,
			status: "highlighted",
			fallbackReason: null,
		};
	} catch {
		return createPlainTextFallbackResult({
			lines: plainLines,
			resolvedLanguage,
			fallbackReason: "tokenize-failed",
		});
	}
}
