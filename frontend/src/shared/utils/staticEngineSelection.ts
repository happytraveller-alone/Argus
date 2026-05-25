import type {
	StaticTool,
	StaticToolSelection,
} from "@/components/agent/AgentModeSelector";

export const PRIMARY_STATIC_ENGINES = ["opengrep", "codeql", "joern"] as const;

export type PrimaryStaticEngine = (typeof PRIMARY_STATIC_ENGINES)[number];

export function isPrimaryStaticEngine(
	engine: StaticTool,
): engine is PrimaryStaticEngine {
	return (
		engine === "opengrep" ||
		engine === "codeql" ||
		engine === "joern"
	);
}

export function hasSelectedPrimaryStaticEngine(
	selection: Pick<StaticToolSelection, PrimaryStaticEngine>,
): boolean {
	return selection.opengrep || selection.codeql || selection.joern;
}

export function selectPrimaryStaticEngine(
	current: StaticToolSelection,
	engine: PrimaryStaticEngine,
	checked: boolean,
): StaticToolSelection {
	return {
		...current,
		opengrep: engine === "opengrep" ? checked : false,
		codeql: engine === "codeql" ? checked : false,
		joern: engine === "joern" ? checked : false,
	};
}
