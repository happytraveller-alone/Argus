import assert from "node:assert/strict";

export const RECHARTS_DIMENSION_WARNING =
	/The width\(-1\) and height\(-1\) of chart should be greater than 0/;

export function collectConsoleWarnings(render: () => void) {
	const warnings: string[] = [];
	const originalWarn = console.warn;
	console.warn = (...args: unknown[]) => {
		warnings.push(args.map(String).join(" "));
	};
	try {
		render();
	} finally {
		console.warn = originalWarn;
	}
	return warnings;
}

export function assertNoConsoleWarning(render: () => void, pattern: RegExp) {
	const warnings = collectConsoleWarnings(render);
	assert.equal(
		warnings.some((warning) => pattern.test(warning)),
		false,
		warnings.join("\n"),
	);
}
