export const EXTERNAL_TOOLS_CARD_MIN_WIDTH = 300;
export const EXTERNAL_TOOLS_CARD_MIN_HEIGHT = 240;
export const EXTERNAL_TOOLS_GRID_GAP = 16;
export const EXTERNAL_TOOLS_MIN_PAGE_SIZE = 1;

export interface ResponsiveExternalToolsLayoutInput {
  width: number;
  height: number;
  minCardWidth?: number;
  minCardHeight?: number;
  gap?: number;
}

export interface ResponsiveExternalToolsLayout {
  columnCount: number;
  rowCount: number;
  pageSize: number;
}

function toSafePositiveNumber(value: number, fallback: number) {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function resolveResponsiveExternalToolsLayout({
  width,
  height,
  minCardWidth = EXTERNAL_TOOLS_CARD_MIN_WIDTH,
  minCardHeight = EXTERNAL_TOOLS_CARD_MIN_HEIGHT,
  gap = EXTERNAL_TOOLS_GRID_GAP,
}: ResponsiveExternalToolsLayoutInput): ResponsiveExternalToolsLayout {
  const safeWidth = Math.max(0, width);
  const safeHeight = Math.max(0, height);
  const safeMinCardWidth = toSafePositiveNumber(
    minCardWidth,
    EXTERNAL_TOOLS_CARD_MIN_WIDTH,
  );
  const safeMinCardHeight = toSafePositiveNumber(
    minCardHeight,
    EXTERNAL_TOOLS_CARD_MIN_HEIGHT,
  );
  const safeGap = Math.max(0, gap);
  const columnCount = Math.max(
    1,
    Math.floor((safeWidth + safeGap) / (safeMinCardWidth + safeGap)) || 1,
  );
  const rowCount = Math.max(
    1,
    Math.floor((safeHeight + safeGap) / (safeMinCardHeight + safeGap)) || 1,
  );

  return {
    columnCount,
    rowCount,
    pageSize: Math.max(EXTERNAL_TOOLS_MIN_PAGE_SIZE, columnCount * rowCount),
  };
}

export function resolveExternalToolsFirstVisibleIndex({
  page,
  pageSize,
}: {
  page: number;
  pageSize: number;
}) {
  const safePage = Math.max(1, Math.floor(page) || 1);
  const safePageSize = Math.max(
    EXTERNAL_TOOLS_MIN_PAGE_SIZE,
    Math.floor(pageSize) || EXTERNAL_TOOLS_MIN_PAGE_SIZE,
  );
  return (safePage - 1) * safePageSize;
}

export function resolveAnchoredExternalToolsPage({
  firstVisibleIndex,
  nextPageSize,
  totalRows,
}: {
  firstVisibleIndex: number;
  nextPageSize: number;
  totalRows: number;
}) {
  const safePageSize = Math.max(
    EXTERNAL_TOOLS_MIN_PAGE_SIZE,
    Math.floor(nextPageSize) || EXTERNAL_TOOLS_MIN_PAGE_SIZE,
  );
  const safeTotalRows = Math.max(0, Math.floor(totalRows) || 0);
  const lastIndex = Math.max(0, safeTotalRows - 1);
  const clampedIndex = Math.max(
    0,
    Math.min(Math.floor(firstVisibleIndex) || 0, lastIndex),
  );
  const totalPages = Math.max(1, Math.ceil(safeTotalRows / safePageSize));
  const nextPage = Math.floor(clampedIndex / safePageSize) + 1;

  return Math.min(totalPages, Math.max(1, nextPage));
}
