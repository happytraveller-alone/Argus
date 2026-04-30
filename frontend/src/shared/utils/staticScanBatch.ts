const STATIC_SCAN_BATCH_MARKER_PREFIX = "[[STATIC_BATCH:";
const STATIC_SCAN_BATCH_MARKER_SUFFIX = "]]";

export function createStaticScanBatchId(): string {
	const randomPart = Math.random().toString(36).slice(2, 8);
	return `${Date.now().toString(36)}${randomPart}`;
}

export function appendStaticScanBatchMarker(
	baseName: string,
	batchId: string,
): string {
	return `${baseName} ${STATIC_SCAN_BATCH_MARKER_PREFIX}${batchId}${STATIC_SCAN_BATCH_MARKER_SUFFIX}`;
}

export function extractStaticScanBatchId(
	name: string | null | undefined,
): string | null {
	const text = String(name || "");
	const start = text.lastIndexOf(STATIC_SCAN_BATCH_MARKER_PREFIX);
	if (start === -1) return null;
	const contentStart = start + STATIC_SCAN_BATCH_MARKER_PREFIX.length;
	const end = text.indexOf(STATIC_SCAN_BATCH_MARKER_SUFFIX, contentStart);
	if (end === -1) return null;
	const batchId = text.slice(contentStart, end).trim();
	return batchId || null;
}
