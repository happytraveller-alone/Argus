import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  getCodeqlScanFindings,
  getCodeqlScanProgress,
  getCodeqlScanTask,
  getJoernScanFindings,
  getJoernScanProgress,
  getJoernScanTask,
  getOpengrepScanFindings,
  getOpengrepScanTask,
  interruptCodeqlScanTask,
  interruptJoernScanTask,
  interruptOpengrepScanTask,
  resetCodeqlProjectBuildPlan,
  updateCodeqlFindingStatus,
  updateJoernFindingStatus,
  updateOpengrepFindingStatus,
  type CodeqlExplorationProgressEvent,
  type OpengrepFinding,
  type OpengrepScanProgress,
  type OpengrepScanTask,
} from "@/shared/api/opengrep";
import type { Engine, FindingStatus, UnifiedFindingRow } from "./viewModel";
import {
  shouldRefreshStaticAnalysisResultsAfterCompletion,
  isStaticAnalysisInterruptibleStatus,
  isStaticAnalysisPollableStatus,
} from "./viewModel";

const FINDING_BATCH_SIZE = 200;
const MAX_FINDING_BATCH_PAGES = 500;

async function fetchFindingBatches<T>(
  fetchPage: (params: { skip: number; limit: number }) => Promise<T[]>,
  expectedTotal?: number | null,
): Promise<T[]> {
  const allFindings: T[] = [];
  const total = Math.max(Number(expectedTotal ?? 0), 0);
  const plannedPages =
    total > 0 ? Math.min(Math.ceil(total / FINDING_BATCH_SIZE), MAX_FINDING_BATCH_PAGES) : null;

  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    if (plannedPages !== null && page >= plannedPages) break;
    const batch = await fetchPage({
      skip: page * FINDING_BATCH_SIZE,
      limit: FINDING_BATCH_SIZE,
    });
    allFindings.push(...batch);
    if (batch.length < FINDING_BATCH_SIZE) break;
  }

  return allFindings;
}

async function fetchAllOpengrepFindings(
  taskId: string,
  expectedTotal?: number | null,
): Promise<OpengrepFinding[]> {
  return fetchFindingBatches(
    ({ skip, limit }) =>
      getOpengrepScanFindings({
        taskId,
        skip,
        limit,
      }),
    expectedTotal,
  );
}

export function useStaticAnalysisData({
  hasEnabledEngine,
  opengrepTaskId,
  codeqlTaskId,
  joernTaskId,
}: {
  hasEnabledEngine: boolean;
  opengrepTaskId: string;
  codeqlTaskId?: string;
  joernTaskId?: string;
}) {
  const [opengrepTask, setOpengrepTask] = useState<OpengrepScanTask | null>(null);
  const [codeqlTask, setCodeqlTask] = useState<OpengrepScanTask | null>(null);
  const [joernTask, setJoernTask] = useState<OpengrepScanTask | null>(null);
  const [opengrepFindings, setOpengrepFindings] = useState<OpengrepFinding[]>([]);
  const [codeqlFindings, setCodeqlFindings] = useState<OpengrepFinding[]>([]);
  const [joernFindings, setJoernFindings] = useState<OpengrepFinding[]>([]);
  const [codeqlProgress, setCodeqlProgress] = useState<OpengrepScanProgress | null>(null);
  const [joernProgress, setJoernProgress] = useState<OpengrepScanProgress | null>(null);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [interruptTarget, setInterruptTarget] = useState<Engine | null>(null);
  const [interrupting, setInterrupting] = useState(false);
  const [resettingCodeqlPlan, setResettingCodeqlPlan] = useState(false);

  const opengrepSilentRefreshRef = useRef(false);
  const opengrepCompletionResultsRefreshRef = useRef<string | null>(null);
  const codeqlSilentRefreshRef = useRef(false);
  const codeqlCompletionResultsRefreshRef = useRef<string | null>(null);
  const joernSilentRefreshRef = useRef(false);
  const joernCompletionResultsRefreshRef = useRef<string | null>(null);

  const loadOpengrepTask = useCallback(async (silent = false) => {
    if (!opengrepTaskId) {
      setOpengrepTask(null);
      return null;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getOpengrepScanTask(opengrepTaskId);
      setOpengrepTask(task);
      return task;
    } catch {
      setOpengrepTask(null);
      if (!silent) {
        toast.error("加载 Opengrep 任务失败");
      }
      return null;
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [opengrepTaskId]);

  const loadCodeqlTask = useCallback(async (silent = false) => {
    if (!codeqlTaskId) {
      setCodeqlTask(null);
      return null;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getCodeqlScanTask(codeqlTaskId);
      setCodeqlTask(task);
      return task;
    } catch {
      setCodeqlTask(null);
      if (!silent) {
        toast.error("加载 CodeQL 任务失败");
      }
      return null;
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [codeqlTaskId]);

  const loadJoernTask = useCallback(async (silent = false) => {
    if (!joernTaskId) {
      setJoernTask(null);
      return null;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getJoernScanTask(joernTaskId);
      setJoernTask(task);
      return task;
    } catch {
      setJoernTask(null);
      if (!silent) {
        toast.error("加载 Joern 任务失败");
      }
      return null;
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [joernTaskId]);

  const loadCodeqlProgress = useCallback(async (silent = false) => {
    if (!codeqlTaskId) {
      setCodeqlProgress(null);
      return null;
    }
    try {
      if (!silent) setLoadingTask(true);
      const progress = await getCodeqlScanProgress(codeqlTaskId, true);
      setCodeqlProgress(progress);
      return progress;
    } catch {
      setCodeqlProgress(null);
      return null;
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [codeqlTaskId]);

  const loadJoernProgress = useCallback(async (silent = false) => {
    if (!joernTaskId) {
      setJoernProgress(null);
      return null;
    }
    try {
      if (!silent) setLoadingTask(true);
      const progress = await getJoernScanProgress(joernTaskId, true);
      setJoernProgress(progress);
      return progress;
    } catch {
      setJoernProgress(null);
      return null;
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [joernTaskId]);

  const loadOpengrepFindings = useCallback(async (silent = false, expectedTotal?: number | null) => {
    if (!opengrepTaskId) {
      setOpengrepFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setOpengrepFindings(await fetchAllOpengrepFindings(opengrepTaskId, expectedTotal));
    } catch {
      setOpengrepFindings([]);
      if (!silent) {
        toast.error("加载 Opengrep 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [opengrepTaskId]);

  const loadCodeqlFindings = useCallback(async (silent = false, expectedTotal?: number | null) => {
    if (!codeqlTaskId) {
      setCodeqlFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setCodeqlFindings(
        await fetchFindingBatches(
          ({ skip, limit }) =>
            getCodeqlScanFindings({
              taskId: codeqlTaskId,
              skip,
              limit,
            }),
          expectedTotal,
        ),
      );
    } catch {
      setCodeqlFindings([]);
      if (!silent) {
        toast.error("加载 CodeQL 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [codeqlTaskId]);

  const loadJoernFindings = useCallback(async (silent = false, expectedTotal?: number | null) => {
    if (!joernTaskId) {
      setJoernFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setJoernFindings(
        await fetchFindingBatches(
          ({ skip, limit }) =>
            getJoernScanFindings({
              taskId: joernTaskId,
              skip,
              limit,
            }),
          expectedTotal,
        ),
      );
    } catch {
      setJoernFindings([]);
      if (!silent) {
        toast.error("加载 Joern 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [joernTaskId]);

  const refreshAll = useCallback(async (silent = false) => {
    if (!hasEnabledEngine) {
      setLoadingInitial(false);
      return;
    }
    if (!silent) setLoadingInitial(true);
    try {
      const nextOpengrepTask = await loadOpengrepTask(silent);
      const nextCodeqlTask = await loadCodeqlTask(silent);
      const nextJoernTask = await loadJoernTask(silent);
      await Promise.all([
        loadOpengrepFindings(silent, nextOpengrepTask?.total_findings),
        loadCodeqlFindings(silent, nextCodeqlTask?.total_findings),
        loadJoernFindings(silent, nextJoernTask?.total_findings),
        loadCodeqlProgress(silent),
        loadJoernProgress(silent),
      ]);
    } finally {
      if (!silent) setLoadingInitial(false);
    }
  }, [
    hasEnabledEngine,
    loadOpengrepFindings,
    loadOpengrepTask,
    loadCodeqlFindings,
    loadCodeqlTask,
    loadCodeqlProgress,
    loadJoernFindings,
    loadJoernTask,
    loadJoernProgress,
  ]);

  const refreshOpengrepSilently = useCallback(async () => {
    if (!opengrepTaskId || opengrepSilentRefreshRef.current) return;
    opengrepSilentRefreshRef.current = true;
    try {
      const nextOpengrepTask = await loadOpengrepTask(true);
      if (
        shouldRefreshStaticAnalysisResultsAfterCompletion({
          taskId: opengrepTaskId,
          status: nextOpengrepTask?.status,
          refreshedTaskId: opengrepCompletionResultsRefreshRef.current,
        })
      ) {
        opengrepCompletionResultsRefreshRef.current = opengrepTaskId;
        await loadOpengrepFindings(true, nextOpengrepTask?.total_findings);
      }
    } finally {
      opengrepSilentRefreshRef.current = false;
    }
  }, [
    loadOpengrepFindings,
    loadOpengrepTask,
    opengrepTaskId,
  ]);

  const refreshCodeqlSilently = useCallback(async () => {
    if (!codeqlTaskId || codeqlSilentRefreshRef.current) return;
    codeqlSilentRefreshRef.current = true;
    try {
      const nextCodeqlTask = await loadCodeqlTask(true);
      await loadCodeqlProgress(true);
      if (
        shouldRefreshStaticAnalysisResultsAfterCompletion({
          taskId: codeqlTaskId,
          status: nextCodeqlTask?.status,
          refreshedTaskId: codeqlCompletionResultsRefreshRef.current,
        })
      ) {
        codeqlCompletionResultsRefreshRef.current = codeqlTaskId;
        await loadCodeqlFindings(true, nextCodeqlTask?.total_findings);
      }
    } finally {
      codeqlSilentRefreshRef.current = false;
    }
  }, [
    codeqlTaskId,
    loadCodeqlFindings,
    loadCodeqlProgress,
    loadCodeqlTask,
  ]);

  const refreshJoernSilently = useCallback(async () => {
    if (!joernTaskId || joernSilentRefreshRef.current) return;
    joernSilentRefreshRef.current = true;
    try {
      const nextJoernTask = await loadJoernTask(true);
      await loadJoernProgress(true);
      if (
        shouldRefreshStaticAnalysisResultsAfterCompletion({
          taskId: joernTaskId,
          status: nextJoernTask?.status,
          refreshedTaskId: joernCompletionResultsRefreshRef.current,
        })
      ) {
        joernCompletionResultsRefreshRef.current = joernTaskId;
        await loadJoernFindings(true, nextJoernTask?.total_findings);
      }
    } finally {
      joernSilentRefreshRef.current = false;
    }
  }, [
    joernTaskId,
    loadJoernFindings,
    loadJoernProgress,
    loadJoernTask,
  ]);

  const handleInterrupt = useCallback(async () => {
    if (!interruptTarget) return;
    setInterrupting(true);
    try {
      if (interruptTarget === "opengrep" && opengrepTaskId) {
        await interruptOpengrepScanTask(opengrepTaskId);
        toast.success("Opengrep 任务已中止");
      } else if (interruptTarget === "codeql" && codeqlTaskId) {
        await interruptCodeqlScanTask(codeqlTaskId);
        toast.success("CodeQL 任务已中止");
      } else if (interruptTarget === "joern" && joernTaskId) {
        await interruptJoernScanTask(joernTaskId);
        toast.success("Joern 任务已中止");
      }
      await refreshAll(true);
    } catch {
      toast.error("中止任务失败");
    } finally {
      setInterrupting(false);
      setInterruptTarget(null);
    }
  }, [
    interruptTarget,
    codeqlTaskId,
    joernTaskId,
    opengrepTaskId,
    refreshAll,
  ]);

  const handleResetCodeqlBuildPlan = useCallback(async () => {
    const projectId = String(codeqlTask?.project_id || "").trim();
    if (!projectId) return;
    setResettingCodeqlPlan(true);
    try {
      await resetCodeqlProjectBuildPlan(projectId);
      toast.success("CodeQL 构建方案已重置");
      await refreshAll(true);
    } catch {
      toast.error("重置 CodeQL 构建方案失败");
    } finally {
      setResettingCodeqlPlan(false);
    }
  }, [codeqlTask?.project_id, refreshAll]);

  const handleToggleStatus = useCallback(async (
    row: UnifiedFindingRow,
    target: FindingStatus,
  ) => {
    const currentStatus = String(row.status || "open").toLowerCase();
    const nextStatus: FindingStatus = currentStatus === target ? "open" : target;
    const updateKey = `${row.engine}:${row.id}:${target}`;
    setUpdatingKey(updateKey);
    try {
      if (row.engine === "opengrep") {
        await updateOpengrepFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setOpengrepFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else if (row.engine === "codeql") {
        await updateCodeqlFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setCodeqlFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else if (row.engine === "joern") {
        await updateJoernFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setJoernFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      }
    } catch {
      toast.error("更新状态失败");
    } finally {
      setUpdatingKey(null);
    }
  }, []);

  useEffect(() => {
    void refreshAll(false);
  }, [refreshAll]);

  useEffect(() => {
    if (!opengrepTaskId || !isStaticAnalysisPollableStatus(opengrepTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshOpengrepSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [opengrepTask?.status, opengrepTaskId, refreshOpengrepSilently]);

  useEffect(() => {
    if (!codeqlTaskId || !isStaticAnalysisPollableStatus(codeqlTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshCodeqlSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [codeqlTask?.status, codeqlTaskId, refreshCodeqlSilently]);

  useEffect(() => {
    if (!joernTaskId || !isStaticAnalysisPollableStatus(joernTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshJoernSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [joernTask?.status, joernTaskId, refreshJoernSilently]);

  return {
    opengrepTask,
    codeqlTask,
    joernTask,
    codeqlProgress,
    joernProgress,
    codeqlExplorationEvents: (codeqlProgress?.events ?? []) as CodeqlExplorationProgressEvent[],
    opengrepFindings,
    codeqlFindings,
    joernFindings,
    loadingInitial,
    loadingTask,
    loadingFindings,
    updatingKey,
    interruptTarget,
    setInterruptTarget,
    interrupting,
    resettingCodeqlPlan,
    refreshAll,
    handleInterrupt,
    handleResetCodeqlBuildPlan,
    handleToggleStatus,
    canInterruptOpengrep: Boolean(
      opengrepTaskId && isStaticAnalysisInterruptibleStatus(opengrepTask?.status),
    ),
    canInterruptCodeql: Boolean(
      codeqlTaskId && isStaticAnalysisInterruptibleStatus(codeqlTask?.status),
    ),
    canInterruptJoern: Boolean(
      joernTaskId && isStaticAnalysisInterruptibleStatus(joernTask?.status),
    ),
    canResetCodeqlBuildPlan: Boolean(codeqlTask?.project_id),
  };
}
