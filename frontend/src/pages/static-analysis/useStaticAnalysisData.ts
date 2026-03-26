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
  getPhpstanFindings,
  getPhpstanScanTask,
  interruptPhpstanScanTask,
  updatePhpstanFindingStatus,
  type PhpstanFinding,
  type PhpstanScanTask,
} from "@/shared/api/phpstan";
import {
  getPmdFindings,
  getPmdScanTask,
  interruptPmdScanTask,
  updatePmdFindingStatus,
  type PmdFinding,
  type PmdScanTask,
} from "@/shared/api/pmd";
import {
  getGitleaksFindings,
  getGitleaksScanTask,
  interruptGitleaksScanTask,
  updateGitleaksFindingStatus,
  type GitleaksFinding,
  type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import {
  getYasaFindings,
  getYasaScanTask,
  interruptYasaScanTask,
  updateYasaFindingStatus,
  type YasaFinding,
  type YasaScanTask,
} from "@/shared/api/yasa";
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

async function fetchAllPhpstanFindings(taskId: string): Promise<PhpstanFinding[]> {
  const allFindings: PhpstanFinding[] = [];
  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    const batch = await getPhpstanFindings({
      taskId,
      skip: page * FINDING_BATCH_SIZE,
      limit: FINDING_BATCH_SIZE,
    });
    allFindings.push(...batch);
    if (batch.length < FINDING_BATCH_SIZE) break;
  }
  return allFindings;
}

async function fetchAllPmdFindings(taskId: string): Promise<PmdFinding[]> {
  const allFindings: PmdFinding[] = [];
  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    const batch = await getPmdFindings({
      taskId,
      skip: page * FINDING_BATCH_SIZE,
      limit: FINDING_BATCH_SIZE,
    });
    allFindings.push(...batch);
    if (batch.length < FINDING_BATCH_SIZE) break;
  }
  return allFindings;
}


async function fetchAllYasaFindings(taskId: string): Promise<YasaFinding[]> {
  const allFindings: YasaFinding[] = [];
  for (let page = 0; page < MAX_FINDING_BATCH_PAGES; page += 1) {
    const batch = await getYasaFindings({
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
  phpstanTaskId,
  yasaTaskId,
  pmdTaskId,
}: {
  hasEnabledEngine: boolean;
  opengrepTaskId: string;
  gitleaksTaskId: string;
  banditTaskId: string;
  phpstanTaskId: string;
  yasaTaskId: string;
  pmdTaskId: string;
}) {
  // PHPStan integration: keep task/findings lifecycle aligned with existing engines.
  const [opengrepTask, setOpengrepTask] = useState<OpengrepScanTask | null>(null);
  const [gitleaksTask, setGitleaksTask] = useState<GitleaksScanTask | null>(null);
  const [banditTask, setBanditTask] = useState<BanditScanTask | null>(null);
  const [phpstanTask, setPhpstanTask] = useState<PhpstanScanTask | null>(null);
  const [yasaTask, setYasaTask] = useState<YasaScanTask | null>(null);
  const [pmdTask, setPmdTask] = useState<PmdScanTask | null>(null);
  const [opengrepFindings, setOpengrepFindings] = useState<OpengrepFinding[]>([]);
  const [gitleaksFindings, setGitleaksFindings] = useState<GitleaksFinding[]>([]);
  const [banditFindings, setBanditFindings] = useState<BanditFinding[]>([]);
  const [phpstanFindings, setPhpstanFindings] = useState<PhpstanFinding[]>([]);
  const [yasaFindings, setYasaFindings] = useState<YasaFinding[]>([]);
  const [pmdFindings, setPmdFindings] = useState<PmdFinding[]>([]);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [interruptTarget, setInterruptTarget] = useState<Engine | null>(null);
  const [interrupting, setInterrupting] = useState(false);

  const opengrepSilentRefreshRef = useRef(false);
  const gitleaksSilentRefreshRef = useRef(false);
  const banditSilentRefreshRef = useRef(false);
  const phpstanSilentRefreshRef = useRef(false);
  const yasaSilentRefreshRef = useRef(false);
  const pmdSilentRefreshRef = useRef(false);

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

  const loadPhpstanTask = useCallback(async (silent = false) => {
    if (!phpstanTaskId) {
      setPhpstanTask(null);
      return;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getPhpstanScanTask(phpstanTaskId);
      setPhpstanTask(task);
    } catch {
      setPhpstanTask(null);
      if (!silent) {
        toast.error("加载 PHPStan 任务失败");
      }
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [phpstanTaskId]);

  const loadPmdTask = useCallback(async (silent = false) => {
    if (!pmdTaskId) {
      setPmdTask(null);
      return;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getPmdScanTask(pmdTaskId);
      setPmdTask(task);
    } catch {
      setPmdTask(null);
      if (!silent) {
        toast.error("加载 PMD 任务失败");
      }
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [pmdTaskId]);

  const loadYasaTask = useCallback(async (silent = false) => {
    if (!yasaTaskId) {
      setYasaTask(null);
      return;
    }
    try {
      if (!silent) setLoadingTask(true);
      const task = await getYasaScanTask(yasaTaskId);
      setYasaTask(task);
    } catch {
      setYasaTask(null);
      if (!silent) {
        toast.error("加载 YASA 任务失败");
      }
    } finally {
      if (!silent) setLoadingTask(false);
    }
  }, [yasaTaskId]);

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

  const loadPhpstanFindings = useCallback(async (silent = false) => {
    if (!phpstanTaskId) {
      setPhpstanFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setPhpstanFindings(await fetchAllPhpstanFindings(phpstanTaskId));
    } catch {
      setPhpstanFindings([]);
      if (!silent) {
        toast.error("加载 PHPStan 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [phpstanTaskId]);

  const loadPmdFindings = useCallback(async (silent = false) => {
    if (!pmdTaskId) {
      setPmdFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setPmdFindings(await fetchAllPmdFindings(pmdTaskId));
    } catch {
      setPmdFindings([]);
      if (!silent) {
        toast.error("加载 PMD 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [pmdTaskId]);

  const loadYasaFindings = useCallback(async (silent = false) => {
    if (!yasaTaskId) {
      setYasaFindings([]);
      return;
    }
    try {
      if (!silent) setLoadingFindings(true);
      setYasaFindings(await fetchAllYasaFindings(yasaTaskId));
    } catch {
      setYasaFindings([]);
      if (!silent) {
        toast.error("加载 YASA 漏洞失败");
      }
    } finally {
      if (!silent) setLoadingFindings(false);
    }
  }, [yasaTaskId]);

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
        loadPhpstanTask(silent),
        loadPmdTask(silent),
        loadYasaTask(silent),
        loadOpengrepFindings(silent),
        loadGitleaksFindings(silent),
        loadBanditFindings(silent),
        loadPhpstanFindings(silent),
        loadPmdFindings(silent),
        loadYasaFindings(silent),
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
    loadPmdFindings,
    loadPmdTask,
    loadPhpstanFindings,
    loadYasaFindings,
    loadPhpstanTask,
    loadYasaTask,
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

  const refreshPhpstanSilently = useCallback(async () => {
    if (!phpstanTaskId || phpstanSilentRefreshRef.current) return;
    phpstanSilentRefreshRef.current = true;
    try {
      await loadPhpstanTask(true);
      await loadPhpstanFindings(true);
    } finally {
      phpstanSilentRefreshRef.current = false;
    }
  }, [loadPhpstanFindings, loadPhpstanTask, phpstanTaskId]);

  const refreshPmdSilently = useCallback(async () => {
    if (!pmdTaskId || pmdSilentRefreshRef.current) return;
    pmdSilentRefreshRef.current = true;
    try {
      await loadPmdTask(true);
      await loadPmdFindings(true);
    } finally {
      pmdSilentRefreshRef.current = false;
    }
  }, [loadPmdFindings, loadPmdTask, pmdTaskId]);

  const refreshYasaSilently = useCallback(async () => {
    if (!yasaTaskId || yasaSilentRefreshRef.current) return;
    yasaSilentRefreshRef.current = true;
    try {
      await loadYasaTask(true);
      await loadYasaFindings(true);
    } finally {
      yasaSilentRefreshRef.current = false;
    }
  }, [loadYasaFindings, loadYasaTask, yasaTaskId]);

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
      if (interruptTarget === "phpstan" && phpstanTaskId) {
        await interruptPhpstanScanTask(phpstanTaskId);
        toast.success("PHPStan 任务已中止");
      }
      if (interruptTarget === "pmd" && pmdTaskId) {
        await interruptPmdScanTask(pmdTaskId);
        toast.success("PMD 任务已中止");
      }
      if (interruptTarget === "yasa" && yasaTaskId) {
        await interruptYasaScanTask(yasaTaskId);
        toast.success("YASA 任务已中止");
      }
      await refreshAll(true);
    } catch {
      toast.error("中止任务失败");
    } finally {
      setInterrupting(false);
      setInterruptTarget(null);
    }
  }, [
    banditTaskId,
    gitleaksTaskId,
    interruptTarget,
    opengrepTaskId,
    phpstanTaskId,
    pmdTaskId,
    yasaTaskId,
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
      } else if (row.engine === "bandit") {
        await updateBanditFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setBanditFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else if (row.engine === "phpstan") {
        await updatePhpstanFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setPhpstanFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else if (row.engine === "pmd") {
        await updatePmdFindingStatus(row.id, nextStatus);
        setPmdFindings((prev) =>
          prev.map((finding) =>
            finding.id === row.id ? { ...finding, status: nextStatus } : finding,
          ),
        );
      } else {
        await updateYasaFindingStatus({
          findingId: row.id,
          status: nextStatus,
        });
        setYasaFindings((prev) =>
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

  useEffect(() => {
    if (!phpstanTaskId || !isStaticAnalysisPollableStatus(phpstanTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshPhpstanSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [phpstanTask?.status, phpstanTaskId, refreshPhpstanSilently]);

  useEffect(() => {
    if (!pmdTaskId || !isStaticAnalysisPollableStatus(pmdTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshPmdSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [pmdTask?.status, pmdTaskId, refreshPmdSilently]);

  useEffect(() => {
    if (!yasaTaskId || !isStaticAnalysisPollableStatus(yasaTask?.status)) {
      return;
    }
    const timer = setInterval(() => {
      void refreshYasaSilently();
    }, 5000);
    return () => clearInterval(timer);
  }, [refreshYasaSilently, yasaTask?.status, yasaTaskId]);

  return {
    opengrepTask,
    gitleaksTask,
    banditTask,
    phpstanTask,
    pmdTask,
    yasaTask,
    opengrepFindings,
    gitleaksFindings,
    banditFindings,
    phpstanFindings,
    pmdFindings,
    yasaFindings,
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
    canInterruptPhpstan: Boolean(
      phpstanTaskId && isStaticAnalysisInterruptibleStatus(phpstanTask?.status),
    ),
    canInterruptPmd: Boolean(
      pmdTaskId && isStaticAnalysisInterruptibleStatus(pmdTask?.status),
    ),
    canInterruptYasa: Boolean(
      yasaTaskId && isStaticAnalysisInterruptibleStatus(yasaTask?.status),
    ),
  };
}
