export type FindingDetailCodeView = {
  id: string;
  title: string;
  filePath: string | null;
  code: string;
  lineStart: number | null;
  lineEnd: number | null;
  highlightStartLine: number | null;
  highlightEndLine: number | null;
  focusLine: number | null;
};

export function buildFindingDetailCodeSections(
  codeViews: FindingDetailCodeView[],
): FindingDetailCodeView[] {
  return [...codeViews];
}
