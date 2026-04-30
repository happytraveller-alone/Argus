import { stripArchiveSuffix } from "../constants";

export type ZipBatchItemStatus = "idle" | "creating" | "success" | "failed";

export interface ZipBatchItem {
	id: string;
	file: File;
	fileName: string;
	size: number;
	derivedName: string;
	editableName: string;
	status: ZipBatchItemStatus;
	errorMessage?: string;
}

export interface ZipBatchFileRejection {
	fileName: string;
	message: string;
}

export interface ZipBatchValidationResult {
	valid: boolean;
	invalidItemIds: string[];
}

function normalizeCandidateName(value: string) {
	const trimmed = value.trim();
	return trimmed || "未命名项目";
}

function buildUniqueProjectName(baseName: string, usedNames: Set<string>) {
	const normalizedBase = normalizeCandidateName(baseName);
	let candidate = normalizedBase;
	let counter = 2;

	while (usedNames.has(candidate.toLowerCase())) {
		candidate = `${normalizedBase} (${counter})`;
		counter += 1;
	}

	usedNames.add(candidate.toLowerCase());
	return candidate;
}

export function appendZipBatchFiles(params: {
	existingItems: ZipBatchItem[];
	files: File[];
	validateFile: (file: File) => { valid: boolean; error?: string };
}) {
	const { existingItems, files, validateFile } = params;
	const usedNames = new Set(
		existingItems.map((item) => normalizeCandidateName(item.editableName).toLowerCase()),
	);
	const nextItems = [...existingItems];
	const rejections: ZipBatchFileRejection[] = [];

	for (const file of files) {
		const validation = validateFile(file);
		if (!validation.valid) {
			rejections.push({
				fileName: file.name,
				message: validation.error || "文件无效",
			});
			continue;
		}

		const rawName = stripArchiveSuffix(file.name).trim() || file.name.trim();
		const derivedName = buildUniqueProjectName(rawName, usedNames);
		nextItems.push({
			id: crypto.randomUUID(),
			file,
			fileName: file.name,
			size: file.size,
			derivedName,
			editableName: derivedName,
			status: "idle",
		});
	}

	return {
		items: nextItems,
		rejections,
	};
}

export function validateZipBatchItems(items: ZipBatchItem[]): ZipBatchValidationResult {
	const invalidItemIds = items
		.filter((item) => item.editableName.trim().length === 0)
		.map((item) => item.id);

	return {
		valid: invalidItemIds.length === 0,
		invalidItemIds,
	};
}
