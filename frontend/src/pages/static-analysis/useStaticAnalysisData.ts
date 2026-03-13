import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  getBanditFindings,
  getBanditScanTask,
  interruptBanditScanTask,
  updateBanditFindingStatus,
  type BanditFinding,
  type BanditScanTask,
} from "@/shared/api/bandit";
import {
  getGitleaksFindings,
  getGitleaksScanTask,
  interruptGitleaksScanTask,
  updateGitleaksFindingStatus,
  type GitleaksFinding,
  type GitleaksScanTask,
} from "@/shared/api/gitleaks";
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
  isStaticAnalysisInterruptibleStatus,
  isStaticAnalysisPollableStatus,
} from "./viewModel";

const FINDING_BATCH_SIZE = 200;
const MAX_FINDING_BATCH_PAGES = 500;

async function fetchAllOpengrepFindings(taskId: string): Promise<OpengrepFinding[]> {
  const allFindings: OpengrepFinding[] = [];
  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    const batch = await getOpengrepScanFindings({
      taskId,
      skip: page * FINDING_BATCH_SIZE,
      limit: FINDING_BATCH_SIZE,
    });
    allFindings.push(...batch);
    if (batch.length < FINDING_BATCH_SIZE) break;
  }
  return allFindings;
}

async function fetchAllGitleaksFindings(taskId: string): Promise<GitleaksFinding[]> {
  const allFindings: GitleaksFinding[] = [];
  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    const batch = await getGitleaksFindings({
      taskId,
      skip: page * FINDING_BATCH_SIZE,
      limit: FINDING_BATCH_SIZE,
    });
    allFindings.push(...batch);
    if (batch.length < FINDING_BATCH_SIZE) break;
  }
  return allFindings;
}

async function fetchAllBanditFindings(taskId: string): Promise<BanditFinding[]> {
  const allFindings: BanditFinding[] = [];
  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    const batch = await getBanditFindings({
      taskId,
      skip: page * FINDING_BATCH_SIZE,
      limit: FINDING_BATCH_SIZE,
    });
    allFindings.push(...batch);
    if (batch.length < FINDING_BATCH_SIZE) break;
  }
  return allFindings;
}

export function useStaticAnalysisData({
  hasEnabledEngine,
  opengrepTaskId,
  gitleaksTaskId,
  banditTaskId,
}: {
  hasEnabledEngine: boolean;
  opengrepTaskId: string;
  gitleaksTaskId: string;
  banditTaskId: string;
}) {
  const [opengrepTask, setOpengrepTask] = useState<OpengrepScanTask | null>(null);
  const [gitleaksTask, setGitleaksTask] = useState<GitleaksScanTask | null>(null);
  const [banditTask, setBanditTask] = useState<BanditScanTask | null>(null);
  const [opengrepFindings, setOpengrepFindings] = useState<OpengrepFinding[]>([]);
  const [gitleaksFindings, setGitleaksFindings] = useState<GitleaksFinding[]>([]);
  const [banditFindings, setBanditFindings] = useState<BanditFinding[]>([]);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [interruptTarget, setInterruptTarget] = useState<Engine | null>(null);
  const [interrupting, setInterrupting] = useState(false);

  const opengrepSilentRefreshRef = useRef(false);
  const gitleaksSilentRefreshRef = useRef(false);
  const banditSilentRefreshRef = useRef(false);

  const loadOpengrepTask = useCallback(async (silent = false) => {
    if (!opengrepTaskId) {
      setOpengrepTask(null);
      return;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getOpengrepScanTask(opengrepTaskId);
      setOpengrepTask(task);
    } catch {
      setOpengrepTask(null);
      if (!silent) {
        toast.error("加载 Opengrep 任务失败");
      }
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [opengrepTaskId]);

  const loadGitleaksTask = useCallback(async (silent = false) => {
    if (!gitleaksTaskId) {
      setGitleaksTask(null);
      return;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getGitleaksScanTask(gitleaksTaskId);
      setGitleaksTask(task);
    } catch {
      setGitleaksTask(null);
      if (!silent) {
        toast.error("加载 Gitleaks 任务失败");
      }
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [gitleaksTaskId]);

  const loadBanditTask = useCallback(async (silent = false) => {
    if (!banditTaskId) {
      setBanditTask(null);
      return;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getBanditScanTask(banditTaskId);
      setBanditTask(task);
    } catch {
      setBanditTask(null);
      if (!silent) {
        toast.error("加载 Bandit 任务失败");
      }
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [banditTaskId]);

  const loadOpengrepFindings = useCallback(async (silent = false) => {
    if (!opengrepTaskId) {
      setOpengrepFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setOpengrepFindings(await fetchAllOpengrepFindings(opengrepTaskId));
    } catch {
      setOpengrepFindings([]);
      if (!silent) {
        toast.error("加载 Opengrep 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [opengrepTaskId]);

  const loadGitleaksFindings = useCallback(async (silent = false) => {
    if (!gitleaksTaskId) {
      setGitleaksFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setGitleaksFindings(await fetchAllGitleaksFindings(gitleaksTaskId));
    } catch {
      setGitleaksFindings([]);
      if (!silent) {
        toast.error("加载 Gitleaks 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [gitleaksTaskId]);

  const loadBanditFindings = useCallback(async (silent = false) => {
    if (!banditTaskId) {
      setBanditFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setBanditFindings(await fetchAllBanditFindings(banditTaskId));
    } catch {
      setBanditFindings([]);
      if (!silent) {
        toast.error("加载 Bandit 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [banditTaskId]);

  const refreshAll = useCallback(async (silent = false) => {
    if (!hasEnabledEngine) {
      setLoadingInitial(false);
      return;
    }
    if (!silent) setLoadingInitial(true);
    try {
      await Promise.all([
        loadOpengrepTask(silent),
        loadGitleaksTask(silent),
        loadBanditTask(silent),
        loadOpengrepFindings(silent),
        loadGitleaksFindings(silent),
        loadBanditFindings(silent),
      ]);
    } finally {
      if (!silent) setLoadingInitial(false);
    }
  }, [
    hasEnabledEngine,
    loadGitleaksFindings,
    loadGitleaksTask,
    loadBanditFindings,
    loadBanditTask,
    loadOpengrepFindings,
    loadOpengrepTask,
  ]);

  const refreshOpengrepSilently = useCallback(async () => {
    if (!opengrepTaskId || opengrepSilentRefreshRef.current) return;
    opengrepSilentRefreshRef.current = true;
    try {
      await loadOpengrepTask(true);
      await loadOpengrepFindings(true);
    } finally {
      opengrepSilentRefreshRef.current = false;
    }
  }, [loadOpengrepFindings, loadOpengrepTask, opengrepTaskId]);

  const refreshGitleaksSilently = useCallback(async () => {
    if (!gitleaksTaskId || gitleaksSilentRefreshRef.current) return;
    gitleaksSilentRefreshRef.current = true;
    try {
      await loadGitleaksTask(true);
      await loadGitleaksFindings(true);
    } finally {
      gitleaksSilentRefreshRef.current = false;
    }
  }, [gitleaksTaskId, loadGitleaksFindings, loadGitleaksTask]);

  const refreshBanditSilently = useCallback(async () => {
    if (!banditTaskId || banditSilentRefreshRef.current) return;
    banditSilentRefreshRef.current = true;
    try {
      await loadBanditTask(true);
      await loadBanditFindings(true);
    } finally {
      banditSilentRefreshRef.current = false;
    }
  }, [banditTaskId, loadBanditFindings, loadBanditTask]);

  const handleInterrupt = useCallback(async () => {
    if (!interruptTarget) return;
    setInterrupting(true);
    try {
      if (interruptTarget === "opengrep" && opengrepTaskId) {
        await interruptOpengrepScanTask(opengrepTaskId);
        toast.success("Opengrep 任务已中止");
      }
      if (interruptTarget === "gitleaks" && gitleaksTaskId) {
        await interruptGitleaksScanTask(gitleaksTaskId);
        toast.success("Gitleaks 任务已中止");
      }
      if (interruptTarget === "bandit" && banditTaskId) {
        await interruptBanditScanTask(banditTaskId);
        toast.success("Bandit 任务已中止");
      }
      await refreshAll(true);
    } catch {
      toast.error("中止任务失败");
    } finally {
      setInterrupting(false);
      setInterruptTarget(null);
    }
  }, [banditTaskId, gitleaksTaskId, interruptTarget, opengrepTaskId, refreshAll]);

  const handleToggleStatus = useCallback(async (
    row: UnifiedFindingRow,
    target: FindingStatus,
  ) => {
    if (row.engine === "opengrep" && target === "fixed") return;
    const currentStatus = String(row.status || "open").toLowerCase();
    const nextStatus: FindingStatus = currentStatus === target ? "open" : target;
    const updateKey = `${row.engine}:${row.id}:${target}`;
    setUpdatingKey(updateKey);
    try {
      if (row.engine === "opengrep") {
        await updateOpengrepFindingStatus({
          findingId: row.id,
          status: nextStatus === "fixed" ? "open" : nextStatus,
        });
        setOpengrepFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else if (row.engine === "gitleaks") {
        await updateGitleaksFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setGitleaksFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else {
        await updateBanditFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setBanditFindings((prev) =>
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
    if (!gitleaksTaskId || !isStaticAnalysisPollableStatus(gitleaksTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshGitleaksSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [gitleaksTask?.status, gitleaksTaskId, refreshGitleaksSilently]);

  useEffect(() => {
    if (!banditTaskId || !isStaticAnalysisPollableStatus(banditTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshBanditSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [banditTask?.status, banditTaskId, refreshBanditSilently]);

  return {
    opengrepTask,
    gitleaksTask,
    banditTask,
    opengrepFindings,
    gitleaksFindings,
    banditFindings,
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
    canInterruptGitleaks: Boolean(
      gitleaksTaskId && isStaticAnalysisInterruptibleStatus(gitleaksTask?.status),
    ),
    canInterruptBandit: Boolean(
      banditTaskId && isStaticAnalysisInterruptibleStatus(banditTask?.status),
    ),
  };
}
