/**
 * Agent Audit State Hook
 * Centralized state management using useReducer
 */

import { useReducer, useCallback, useMemo, useRef } from "react";
import type {
  AgentAuditState,
  AgentAuditAction,
  LogItem,
  AgentTask,
  AgentFinding,
  AgentTreeResponse,
  ConnectionStatus,
} from "../types";
import { createLogItem, filterLogsByAgent, buildAgentTree } from "../utils";
import type { AgentTreeNode } from "@/shared/api/agentTasks";

// ============ Initial State ============

const initialState: AgentAuditState = {
  task: null,
  findings: [],
  agentTree: null,
  logs: [],
  selectedAgentId: null,
  showAllLogs: true,
  isLoading: false,
  error: null,
  connectionStatus: 'disconnected',
  isAutoScroll: true,
  expandedLogIds: new Set(),
};

// ============ Reducer ============

function agentAuditReducer(state: AgentAuditState, action: AgentAuditAction): AgentAuditState {
  switch (action.type) {
    case 'SET_TASK':
      return { ...state, task: action.payload };

    case 'SET_FINDINGS':
      return { ...state, findings: action.payload };

    case 'ADD_FINDING': {
      // 🔥 添加单个 finding，避免重复
      const newFinding = action.payload;
      const existingIds = new Set(state.findings.map(f => f.id));
      if (newFinding.id && existingIds.has(newFinding.id)) {
        return state; // 已存在，不添加
      }
      const normalizedFinding: AgentFinding = {
        id: newFinding.id,
        task_id: String(newFinding.task_id || ""),
        vulnerability_type: String(newFinding.vulnerability_type || "unknown"),
        severity: String(newFinding.severity || "medium"),
        title: String(newFinding.title || "发现漏洞"),
        description: (newFinding.description as string | null) ?? null,
        file_path: (newFinding.file_path as string | null) ?? null,
        line_start: (newFinding.line_start as number | null) ?? null,
        line_end: (newFinding.line_end as number | null) ?? null,
        code_snippet: (newFinding.code_snippet as string | null) ?? null,
        code_context: (newFinding.code_context as string | null) ?? null,
        context_start_line: (newFinding.context_start_line as number | null) ?? null,
        context_end_line: (newFinding.context_end_line as number | null) ?? null,
        status: String(newFinding.status || "new"),
        is_verified: Boolean(newFinding.is_verified),
        reachability: (newFinding.reachability as string | null) ?? null,
        authenticity: (newFinding.authenticity as string | null) ?? null,
        verification_evidence: (newFinding.verification_evidence as string | null) ?? null,
        has_poc: Boolean(newFinding.has_poc),
        poc_code: (newFinding.poc_code as string | null) ?? null,
        suggestion: (newFinding.suggestion as string | null) ?? null,
        fix_code: (newFinding.fix_code as string | null) ?? null,
        ai_explanation: (newFinding.ai_explanation as string | null) ?? null,
        ai_confidence: (newFinding.ai_confidence as number | null) ?? null,
        created_at: String(newFinding.created_at || new Date().toISOString()),
      };
      return { ...state, findings: [...state.findings, normalizedFinding] };
    }

    case 'SET_AGENT_TREE':
      return { ...state, agentTree: action.payload };

    case 'SET_LOGS':
      return { ...state, logs: action.payload };

    case 'ADD_LOG': {
      const { id: providedId, ...logData } = action.payload;
      const newLog = providedId
        ? { ...createLogItem(logData), id: providedId }
        : createLogItem(logData);
      return { ...state, logs: [...state.logs, newLog] };
    }

    case 'UPDATE_LOG': {
      const { id, updates } = action.payload;
      return {
        ...state,
        logs: state.logs.map(log =>
          log.id === id ? { ...log, ...updates } : log
        ),
      };
    }

    case 'REMOVE_LOG':
      return {
        ...state,
        logs: state.logs.filter(log => log.id !== action.payload),
      };

    case 'COMPLETE_TOOL_LOG': {
      const { toolName, output, duration } = action.payload;
      const updatedLogs = [...state.logs];
      for (let i = updatedLogs.length - 1; i >= 0; i--) {
        const log = updatedLogs[i];
        if (log.type === 'tool' && log.tool?.name === toolName && log.tool?.status === 'running') {
          const previousContent = log.content || '';
          updatedLogs[i] = {
            ...log,
            title: `Completed: ${toolName}`,
            content: `${previousContent}\n\nOutput:\n${output}`,
            tool: { name: toolName, duration, status: 'completed' },
          };
          break;
        }
      }
      return { ...state, logs: updatedLogs };
    }

    case 'UPDATE_OR_ADD_PROGRESS_LOG': {
      const { progressKey, title, agentName } = action.payload;
      // 查找是否已存在相同 progressKey 的进度日志
      const existingIndex = state.logs.findIndex(
        log => log.type === 'progress' && log.progressKey === progressKey
      );

      if (existingIndex >= 0) {
        // 更新现有日志的 title 和 time
        const updatedLogs = [...state.logs];
        updatedLogs[existingIndex] = {
          ...updatedLogs[existingIndex],
          title,
          time: new Date().toLocaleTimeString('en-US', { hour12: false }),
        };
        return { ...state, logs: updatedLogs };
      } else {
        // 添加新的进度日志
        const newLog = createLogItem({
          type: 'progress',
          title,
          progressKey,
          agentName,
        });
        return { ...state, logs: [...state.logs, newLog] };
      }
    }

    case 'SELECT_AGENT':
      return {
        ...state,
        selectedAgentId: action.payload,
        showAllLogs: action.payload === null,
      };

    case 'TOGGLE_SHOW_ALL_LOGS':
      return {
        ...state,
        showAllLogs: !state.showAllLogs,
        selectedAgentId: state.showAllLogs ? state.selectedAgentId : null,
      };

    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };

    case 'SET_ERROR':
      return { ...state, error: action.payload };

    case 'SET_CONNECTION_STATUS':
      return { ...state, connectionStatus: action.payload };

    case 'SET_AUTO_SCROLL':
      return { ...state, isAutoScroll: action.payload };

    case 'TOGGLE_LOG_EXPANDED': {
      const newExpanded = new Set(state.expandedLogIds);
      if (newExpanded.has(action.payload)) {
        newExpanded.delete(action.payload);
      } else {
        newExpanded.add(action.payload);
      }
      return { ...state, expandedLogIds: newExpanded };
    }

    case 'RESET':
      return { ...initialState };

    default:
      return state;
  }
}

// ============ Hook ============

export function useAgentAuditState() {
  const [state, dispatch] = useReducer(agentAuditReducer, initialState);
  const currentThinkingId = useRef<string | null>(null);
  const currentAgentName = useRef<string | null>(null);

  // ============ Action Creators ============

  const setTask = useCallback((task: AgentTask) => {
    dispatch({ type: 'SET_TASK', payload: task });
  }, []);

  const setFindings = useCallback((findings: AgentFinding[]) => {
    dispatch({ type: 'SET_FINDINGS', payload: findings });
  }, []);

  const setAgentTree = useCallback((tree: AgentTreeResponse) => {
    dispatch({ type: 'SET_AGENT_TREE', payload: tree });
  }, []);

  const addLog = useCallback((log: Omit<LogItem, 'id' | 'time'>): string => {
    const newLog = createLogItem(log);
    dispatch({ type: 'SET_LOGS', payload: [...state.logs, newLog] });
    return newLog.id;
  }, [state.logs]);

  const updateLog = useCallback((id: string, updates: Partial<LogItem>) => {
    dispatch({ type: 'UPDATE_LOG', payload: { id, updates } });
  }, []);

  const removeLog = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_LOG', payload: id });
  }, []);

  const selectAgent = useCallback((id: string | null) => {
    dispatch({ type: 'SELECT_AGENT', payload: id });
  }, []);

  const toggleShowAllLogs = useCallback(() => {
    dispatch({ type: 'TOGGLE_SHOW_ALL_LOGS' });
  }, []);

  const setLoading = useCallback((loading: boolean) => {
    dispatch({ type: 'SET_LOADING', payload: loading });
  }, []);

  const setError = useCallback((error: string | null) => {
    dispatch({ type: 'SET_ERROR', payload: error });
  }, []);

  const setConnectionStatus = useCallback((status: ConnectionStatus) => {
    dispatch({ type: 'SET_CONNECTION_STATUS', payload: status });
  }, []);

  const setAutoScroll = useCallback((enabled: boolean) => {
    dispatch({ type: 'SET_AUTO_SCROLL', payload: enabled });
  }, []);

  const toggleLogExpanded = useCallback((id: string) => {
    dispatch({ type: 'TOGGLE_LOG_EXPANDED', payload: id });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: 'RESET' });
    currentThinkingId.current = null;
    currentAgentName.current = null;
  }, []);

  // ============ Thinking State Management ============

  const setCurrentAgentName = useCallback((name: string | null) => {
    currentAgentName.current = name;
  }, []);

  const getCurrentAgentName = useCallback(() => {
    return currentAgentName.current;
  }, []);

  const setCurrentThinkingId = useCallback((id: string | null) => {
    currentThinkingId.current = id;
  }, []);

  const getCurrentThinkingId = useCallback(() => {
    return currentThinkingId.current;
  }, []);

  // ============ Computed Values ============

  const treeNodes = useMemo(() => {
    if (!state.agentTree?.nodes) return [];
    return buildAgentTree(state.agentTree.nodes);
  }, [state.agentTree?.nodes]);

  const filteredLogs = useMemo(() => {
    return filterLogsByAgent(
      state.logs,
      state.selectedAgentId,
      treeNodes,
      state.showAllLogs
    );
  }, [state.logs, state.selectedAgentId, treeNodes, state.showAllLogs]);

  const isRunning = useMemo(() => {
    return state.task?.status === 'running' || state.task?.status === 'pending';
  }, [state.task?.status]);

  const isComplete = useMemo(() => {
    const status = state.task?.status;
    return status === 'completed' || status === 'failed' || status === 'cancelled';
  }, [state.task?.status]);

  return {
    // State
    ...state,
    treeNodes,
    filteredLogs,
    isRunning,
    isComplete,

    // Actions
    setTask,
    setFindings,
    setAgentTree,
    addLog,
    updateLog,
    removeLog,
    selectAgent,
    toggleShowAllLogs,
    setLoading,
    setError,
    setConnectionStatus,
    setAutoScroll,
    toggleLogExpanded,
    reset,

    // Thinking state
    setCurrentAgentName,
    getCurrentAgentName,
    setCurrentThinkingId,
    getCurrentThinkingId,

    // Direct dispatch for complex operations
    dispatch,
  };
}

export type AgentAuditStateHook = ReturnType<typeof useAgentAuditState>;
