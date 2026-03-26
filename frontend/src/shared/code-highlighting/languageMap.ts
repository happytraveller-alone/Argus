export interface ResolveCodeLanguageResult {
	languageKey: string;
	languageLabel: string;
}

interface LanguageMappingEntry extends ResolveCodeLanguageResult {
	key: string;
}

const SPECIAL_FILENAME_LANGUAGE_MAP: Record<string, ResolveCodeLanguageResult> = {
	Dockerfile: { languageKey: "dockerfile", languageLabel: "Dockerfile" },
	Makefile: { languageKey: "makefile", languageLabel: "Makefile" },
	GNUmakefile: { languageKey: "makefile", languageLabel: "Makefile" },
	"nginx.conf": { languageKey: "nginx", languageLabel: "Nginx" },
	"pom.xml": { languageKey: "xml", languageLabel: "XML" },
};

const EXTENSION_LANGUAGE_MAP: LanguageMappingEntry[] = [
	{ key: ".js", languageKey: "javascript", languageLabel: "JavaScript" },
	{ key: ".cjs", languageKey: "javascript", languageLabel: "JavaScript" },
	{ key: ".mjs", languageKey: "javascript", languageLabel: "JavaScript" },
	{ key: ".jsx", languageKey: "jsx", languageLabel: "JSX" },
	{ key: ".ts", languageKey: "typescript", languageLabel: "TypeScript" },
	{ key: ".cts", languageKey: "typescript", languageLabel: "TypeScript" },
	{ key: ".mts", languageKey: "typescript", languageLabel: "TypeScript" },
	{ key: ".tsx", languageKey: "tsx", languageLabel: "TSX" },
	{ key: ".json", languageKey: "json", languageLabel: "JSON" },
	{ key: ".jsonc", languageKey: "json", languageLabel: "JSONC" },
	{ key: ".yaml", languageKey: "yaml", languageLabel: "YAML" },
	{ key: ".yml", languageKey: "yaml", languageLabel: "YAML" },
	{ key: ".toml", languageKey: "toml", languageLabel: "TOML" },
	{ key: ".ini", languageKey: "ini", languageLabel: "INI" },
	{ key: ".properties", languageKey: "properties", languageLabel: "Properties" },
	{ key: ".md", languageKey: "markdown", languageLabel: "Markdown" },
	{ key: ".diff", languageKey: "diff", languageLabel: "Diff" },
	{ key: ".patch", languageKey: "diff", languageLabel: "Diff" },
	{ key: ".java", languageKey: "java", languageLabel: "Java" },
	{ key: ".kt", languageKey: "kotlin", languageLabel: "Kotlin" },
	{ key: ".kts", languageKey: "kotlin", languageLabel: "Kotlin" },
	{ key: ".py", languageKey: "python", languageLabel: "Python" },
	{ key: ".go", languageKey: "go", languageLabel: "Go" },
	{ key: ".php", languageKey: "php", languageLabel: "PHP" },
	{ key: ".rb", languageKey: "ruby", languageLabel: "Ruby" },
	{ key: ".rs", languageKey: "rust", languageLabel: "Rust" },
	{ key: ".c", languageKey: "c", languageLabel: "C" },
	{ key: ".h", languageKey: "c", languageLabel: "C" },
	{ key: ".cpp", languageKey: "cpp", languageLabel: "C++" },
	{ key: ".cc", languageKey: "cpp", languageLabel: "C++" },
	{ key: ".cxx", languageKey: "cpp", languageLabel: "C++" },
	{ key: ".hpp", languageKey: "cpp", languageLabel: "C++" },
	{ key: ".hh", languageKey: "cpp", languageLabel: "C++" },
	{ key: ".cs", languageKey: "csharp", languageLabel: "C#" },
	{ key: ".swift", languageKey: "swift", languageLabel: "Swift" },
	{ key: ".sh", languageKey: "bash", languageLabel: "Shell" },
	{ key: ".bash", languageKey: "bash", languageLabel: "Shell" },
	{ key: ".zsh", languageKey: "bash", languageLabel: "Shell" },
	{ key: ".sql", languageKey: "sql", languageLabel: "SQL" },
	{ key: ".html", languageKey: "xml", languageLabel: "HTML" },
	{ key: ".htm", languageKey: "xml", languageLabel: "HTML" },
	{ key: ".xml", languageKey: "xml", languageLabel: "XML" },
	{ key: ".css", languageKey: "css", languageLabel: "CSS" },
	{ key: ".scss", languageKey: "scss", languageLabel: "SCSS" },
	{ key: ".conf", languageKey: "ini", languageLabel: "Config" },
];

function getBaseName(filePath: string): string {
	const normalizedPath = String(filePath || "").trim().replace(/\\/g, "/");
	if (!normalizedPath) return "";
	const segments = normalizedPath.split("/");
	return segments[segments.length - 1] || "";
}

function getLowerCasePath(filePath: string): string {
	return String(filePath || "").trim().replace(/\\/g, "/").toLowerCase();
}

function isDotEnvFile(baseName: string): boolean {
	const loweredBaseName = baseName.toLowerCase();
	return loweredBaseName === ".env" || loweredBaseName.startsWith(".env.");
}

export function resolveCodeLanguageFromPath(
	filePath: string,
): ResolveCodeLanguageResult | null {
	const baseName = getBaseName(filePath);
	if (!baseName) return null;
	if (isDotEnvFile(baseName)) return null;

	const special = SPECIAL_FILENAME_LANGUAGE_MAP[baseName];
	if (special) {
		return special;
	}

	const loweredPath = getLowerCasePath(filePath);
	for (const extensionEntry of EXTENSION_LANGUAGE_MAP) {
		if (loweredPath.endsWith(extensionEntry.key)) {
			return {
				languageKey: extensionEntry.languageKey,
				languageLabel: extensionEntry.languageLabel,
			};
		}
	}

	return null;
}

