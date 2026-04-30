import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  getOpengrepScanFindings,
  getOpengrepScanTask,
  interruptOpengrepScanTask,
  updateOpengrepFindingStatus,
  type OpengrepFinding,
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
}: {
  hasEnabledEngine: boolean;
  opengrepTaskId: string;
}) {
  const [opengrepTask, setOpengrepTask] = useState<OpengrepScanTask | null>(null);
  const [opengrepFindings, setOpengrepFindings] = useState<OpengrepFinding[]>([]);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [interruptTarget, setInterruptTarget] = useState<Engine | null>(null);
  const [interrupting, setInterrupting] = useState(false);

  const opengrepSilentRefreshRef = useRef(false);
  const opengrepCompletionResultsRefreshRef = useRef<string | null>(null);

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

  const refreshAll = useCallback(async (silent = false) => {
    if (!hasEnabledEngine) {
      setLoadingInitial(false);
      return;
    }
    if (!silent) setLoadingInitial(true);
    try {
      const nextOpengrepTask = await loadOpengrepTask(silent);
      await Promise.all([
        loadOpengrepFindings(silent, nextOpengrepTask?.total_findings),
      ]);
    } finally {
      if (!silent) setLoadingInitial(false);
    }
  }, [
    hasEnabledEngine,
    loadOpengrepFindings,
    loadOpengrepTask,
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

  const handleInterrupt = useCallback(async () => {
    if (!interruptTarget) return;
    setInterrupting(true);
    try {
      if (interruptTarget === "opengrep" && opengrepTaskId) {
        await interruptOpengrepScanTask(opengrepTaskId);
        toast.success("Opengrep 任务已中止");
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
    opengrepTaskId,
    refreshAll,
  ]);

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

  return {
    opengrepTask,
    gitleaksTask: null,
    banditTask: null,
    phpstanTask: null,
    pmdTask: null,
    opengrepFindings,
    gitleaksFindings: [],
    banditFindings: [],
    phpstanFindings: [],
    pmdFindings: [],
    loadingInitial,
    loadingTask,
    loadingFindings,
    updatingKey,
    interruptTarget,
    setInterruptTarget,
    interrupting,
    refreshAll,
    handleInterrupt,
    handleToggleStatus,
    canInterruptOpengrep: Boolean(
      opengrepTaskId && isStaticAnalysisInterruptibleStatus(opengrepTask?.status),
    ),
    canInterruptGitleaks: false,
    canInterruptBandit: false,
    canInterruptPhpstan: false,
    canInterruptPmd: false,
  };
}
