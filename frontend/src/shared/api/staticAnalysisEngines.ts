export const STATIC_ANALYSIS_ENGINE_IDS = [
  "opengrep",
  "codeql",
  "joern",
] as const;

export type StaticAnalysisEngine = (typeof STATIC_ANALYSIS_ENGINE_IDS)[number];

export interface StaticAnalysisEngineDescriptor {
  id: StaticAnalysisEngine;
  label: string;
  taskQueryParam: `${StaticAnalysisEngine}TaskId`;
  taskBasePath: string;
  scanSchemeLabel: string;
}

export const STATIC_ANALYSIS_ENGINES: Record<
  StaticAnalysisEngine,
  StaticAnalysisEngineDescriptor
> = {
  opengrep: {
    id: "opengrep",
    label: "Opengrep",
    taskQueryParam: "opengrepTaskId",
    taskBasePath: "/static-tasks/tasks",
    scanSchemeLabel: "Podman 容器方案",
  },
  codeql: {
    id: "codeql",
    label: "CodeQL",
    taskQueryParam: "codeqlTaskId",
    taskBasePath: "/static-tasks/codeql/tasks",
    scanSchemeLabel: "CodeQL 语义方案",
  },
  joern: {
    id: "joern",
    label: "Joern",
    taskQueryParam: "joernTaskId",
    taskBasePath: "/static-tasks/joern/tasks",
    scanSchemeLabel: "Joern CPG 方案",
  },
};

export const STATIC_ANALYSIS_ENGINE_DESCRIPTORS =
  STATIC_ANALYSIS_ENGINE_IDS.map((id) => STATIC_ANALYSIS_ENGINES[id]);

export function isStaticAnalysisEngine(
  value: string | null | undefined,
): value is StaticAnalysisEngine {
  return STATIC_ANALYSIS_ENGINE_IDS.includes(value as StaticAnalysisEngine);
}

export function getStaticAnalysisEngineDescriptor(
  engine: StaticAnalysisEngine,
): StaticAnalysisEngineDescriptor {
  return STATIC_ANALYSIS_ENGINES[engine];
}

export function getStaticAnalysisEngineLabel(
  engine: StaticAnalysisEngine,
): string {
  return getStaticAnalysisEngineDescriptor(engine).label;
}

export function getStaticAnalysisTaskBasePath(
  engine: StaticAnalysisEngine,
): string {
  return getStaticAnalysisEngineDescriptor(engine).taskBasePath;
}

export function getStaticAnalysisTaskQueryParam(
  engine: StaticAnalysisEngine,
): StaticAnalysisEngineDescriptor["taskQueryParam"] {
  return getStaticAnalysisEngineDescriptor(engine).taskQueryParam;
}
