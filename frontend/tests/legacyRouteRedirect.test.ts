import test from "node:test";
import assert from "node:assert/strict";

import { buildOpengrepRulesRedirectPath } from "../src/shared/utils/legacyRouteRedirect.ts";

test("buildOpengrepRulesRedirectPath forces opengrep tab for the legacy rules entry", () => {
	assert.equal(
		buildOpengrepRulesRedirectPath(""),
		"/scan-config/engines?tab=opengrep",
	);

	assert.equal(
		buildOpengrepRulesRedirectPath("?tab=gitleaks"),
		"/scan-config/engines?tab=opengrep",
	);
});

test("buildOpengrepRulesRedirectPath preserves highlightRule and returnTo query params", () => {
	assert.equal(
		buildOpengrepRulesRedirectPath(
			"?highlightRule=python.sql&returnTo=%2Fstatic-analysis%2Ftask-1",
		),
		"/scan-config/engines?highlightRule=python.sql&returnTo=%2Fstatic-analysis%2Ftask-1&tab=opengrep",
	);
});
