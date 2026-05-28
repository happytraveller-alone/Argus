import assert from "node:assert/strict";
import test from "node:test";

import {
	CPP_GATE_COPY,
	CPP_PROJECT_THRESHOLD_DEFAULT,
	isCppProject,
} from "../src/shared/utils/projectLanguage";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

test("CPP_PROJECT_THRESHOLD_DEFAULT is 0.5", () => {
	assert.equal(CPP_PROJECT_THRESHOLD_DEFAULT, 0.5);
});

test("CPP_GATE_COPY exposes the two required Chinese copy strings", () => {
	assert.equal(CPP_GATE_COPY.pending, "项目语言检测未完成，完成后才可使用");
	assert.equal(CPP_GATE_COPY.not_cpp, "当前功能仅支持 C/C++ 项目");
});

// ---------------------------------------------------------------------------
// Pending branch (fail-closed)
// ---------------------------------------------------------------------------

test("isCppProject returns pending when info_status is not 'completed'", () => {
	const result = isCppProject({
		programming_languages: '["C"]',
		language_info: '{"languages":{"C":{"proportion":0.9}}}',
		info_status: "pending",
	});
	assert.deepEqual(result, { qualifies: false, reason: "pending" });
});

test("isCppProject returns pending when programming_languages is an empty JSON array", () => {
	const result = isCppProject({
		programming_languages: "[]",
		language_info: '{"languages":{"C":{"proportion":0.9}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "pending" });
});

test("isCppProject returns pending when programming_languages is not parseable", () => {
	const result = isCppProject({
		programming_languages: "not-json",
		language_info: '{"languages":{"C":{"proportion":0.9}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "pending" });
});

test("isCppProject returns pending when language_info is empty JSON object", () => {
	const result = isCppProject({
		programming_languages: '["C"]',
		language_info: "{}",
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "pending" });
});

test("isCppProject returns pending when language_info.languages is missing", () => {
	const result = isCppProject({
		programming_languages: '["C"]',
		language_info: '{"foo":"bar"}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "pending" });
});

// ---------------------------------------------------------------------------
// Qualifies branch
// ---------------------------------------------------------------------------

test("isCppProject qualifies when C alone meets the default threshold", () => {
	const result = isCppProject({
		programming_languages: '["C","Python"]',
		language_info:
			'{"languages":{"C":{"proportion":0.6},"Python":{"proportion":0.4}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: true, reason: "qualifies" });
});

test("isCppProject qualifies when C + C++ together meet the threshold", () => {
	const result = isCppProject({
		programming_languages: '["C","C++","Rust"]',
		language_info:
			'{"languages":{"C":{"proportion":0.3},"C++":{"proportion":0.3},"Rust":{"proportion":0.4}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: true, reason: "qualifies" });
});

test("isCppProject qualifies at the exact threshold (0.5 boundary)", () => {
	const result = isCppProject({
		programming_languages: '["C","Python"]',
		language_info:
			'{"languages":{"C":{"proportion":0.5},"Python":{"proportion":0.5}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: true, reason: "qualifies" });
});

// ---------------------------------------------------------------------------
// not_cpp branch
// ---------------------------------------------------------------------------

test("isCppProject returns not_cpp when C + C++ are below threshold", () => {
	const result = isCppProject({
		programming_languages: '["Python","C","C++"]',
		language_info:
			'{"languages":{"Python":{"proportion":0.7},"C":{"proportion":0.2},"C++":{"proportion":0.1}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "not_cpp" });
});

test("isCppProject returns not_cpp for pure Python project", () => {
	const result = isCppProject({
		programming_languages: '["Python"]',
		language_info: '{"languages":{"Python":{"proportion":1.0}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "not_cpp" });
});

// ---------------------------------------------------------------------------
// Custom threshold
// ---------------------------------------------------------------------------

test("isCppProject honors a custom threshold above the C+C++ proportion", () => {
	const result = isCppProject(
		{
			programming_languages: '["C","Python"]',
			language_info:
				'{"languages":{"C":{"proportion":0.6},"Python":{"proportion":0.4}}}',
			info_status: "completed",
		},
		0.7,
	);
	assert.deepEqual(result, { qualifies: false, reason: "not_cpp" });
});

test("isCppProject honors a custom threshold below the C+C++ proportion", () => {
	const result = isCppProject(
		{
			programming_languages: '["C","Python"]',
			language_info:
				'{"languages":{"C":{"proportion":0.3},"Python":{"proportion":0.7}}}',
			info_status: "completed",
		},
		0.2,
	);
	assert.deepEqual(result, { qualifies: true, reason: "qualifies" });
});

// ---------------------------------------------------------------------------
// Numeric edge cases
// ---------------------------------------------------------------------------

test("isCppProject treats non-numeric proportion as zero", () => {
	const result = isCppProject({
		programming_languages: '["C","Python"]',
		language_info:
			'{"languages":{"C":{"proportion":"0.9"},"Python":{"proportion":0.1}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "not_cpp" });
});

test("isCppProject treats missing C / C++ entries as zero", () => {
	const result = isCppProject({
		programming_languages: '["Python","Rust"]',
		language_info:
			'{"languages":{"Python":{"proportion":0.5},"Rust":{"proportion":0.5}}}',
		info_status: "completed",
	});
	assert.deepEqual(result, { qualifies: false, reason: "not_cpp" });
});
