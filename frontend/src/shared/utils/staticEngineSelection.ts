import type {
	StaticTool,
	StaticToolSelection,
} from "@/components/agent/AgentModeSelector";

export const PRIMARY_STATIC_ENGINES = ["opengrep", "codeql"] as const;

export type PrimaryStaticEngine = (typeof PRIMARY_STATIC_ENGINES)[number];

export function isPrimaryStaticEngine(
	engine: StaticTool,
): engine is PrimaryStaticEngine {
	return engine === "opengrep" || engine === "codeql";
}

export function hasSelectedPrimaryStaticEngine(
	selection: Pick<StaticToolSelection, PrimaryStaticEngine>,
): boolean {
	return selection.opengrep || selection.codeql;
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
	};
}
