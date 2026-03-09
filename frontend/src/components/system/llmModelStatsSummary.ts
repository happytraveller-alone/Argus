export type LlmModelStatsStatus =
	| "static"
	| "loading"
	| "online"
	| "cached_online"
	| "empty";

export type LlmModelStatsSource = "online" | "cache" | "static" | "none";

export type LlmModelStatsFetchState = "idle" | "loading" | "failed" | "online";

export type LlmModelStatsCounts = {
	availableModelCount: number;
	availableModelMetadataCount: number;
};

export function resolvePreferredModelStats(input: {
	shouldPreferOnlineStats: boolean;
	staticStats: LlmModelStatsCounts;
	cachedOnlineStats: LlmModelStatsCounts | null;
	fetchState: LlmModelStatsFetchState;
}): LlmModelStatsCounts & {
	modelStatsStatus: LlmModelStatsStatus;
	modelStatsSource: LlmModelStatsSource;
} {
	const {
		shouldPreferOnlineStats,
		staticStats,
		cachedOnlineStats,
		fetchState,
	} = input;

	if (!shouldPreferOnlineStats) {
		return {
			...staticStats,
			modelStatsStatus: "static",
			modelStatsSource: "static",
		};
	}

	if (fetchState === "online" && cachedOnlineStats) {
		return {
			...cachedOnlineStats,
			modelStatsStatus: "online",
			modelStatsSource: "online",
		};
	}

	if (cachedOnlineStats) {
		return {
			...cachedOnlineStats,
			modelStatsStatus: "cached_online",
			modelStatsSource: "cache",
		};
	}

	if (fetchState === "loading") {
		return {
			availableModelCount: 0,
			availableModelMetadataCount: 0,
			modelStatsStatus: "loading",
			modelStatsSource: "none",
		};
	}

	return {
		availableModelCount: 0,
		availableModelMetadataCount: 0,
		modelStatsStatus: "empty",
		modelStatsSource: "none",
	};
}
