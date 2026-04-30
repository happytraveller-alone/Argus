
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  AgentStreamHandler,
  StreamEventData,
  StreamOptions,
  AgentStreamState,
} from '../shared/api/agentStream';

export interface UseAgentStreamOptions extends StreamOptions {
  autoConnect?: boolean;
  maxEvents?: number;
}

export interface UseAgentStreamReturn extends AgentStreamState {
  connect: () => void;
  disconnect: () => void;
  isConnected: boolean;
  clearEvents: () => void;
}

export function useAgentStream(
  taskId: string | null,
  options: UseAgentStreamOptions = {}
): UseAgentStreamReturn {
  const {
    autoConnect = false,
    maxEvents = 500,
    includeThinking = true,
    includeToolCalls = true,
    afterSequence = 0,
    ...callbackOptions
  } = options;

  const callbackOptionsRef = useRef(callbackOptions);
  callbackOptionsRef.current = callbackOptions;

  const [events, setEvents] = useState<StreamEventData[]>([]);
  const [thinking, setThinking] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [toolCalls, setToolCalls] = useState<AgentStreamState['toolCalls']>([]);
  const [currentPhase, setCurrentPhase] = useState('');
  const [progress, setProgress] = useState({ current: 0, total: 100, percentage: 0 });
  const [findings, setFindings] = useState<Record<string, unknown>[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const handlerRef = useRef<AgentStreamHandler | null>(null);
  const thinkingBufferRef = useRef<string[]>([]);

  const afterSequenceRef = useRef(afterSequence);
  afterSequenceRef.current = afterSequence;

  const connect = useCallback(() => {
    if (!taskId) return;

    if (handlerRef.current) {
      handlerRef.current.disconnect();
    }

    setEvents([]);
    setThinking('');
    setIsThinking(false);
    setToolCalls([]);
    setCurrentPhase('');
    setProgress({ current: 0, total: 100, percentage: 0 });
    setFindings([]);
    setIsComplete(false);
    setError(null);
    thinkingBufferRef.current = [];

    const currentAfterSequence = afterSequenceRef.current;
    console.log(`[useAgentStream] Creating handler with afterSequence=${currentAfterSequence}`);

    handlerRef.current = new AgentStreamHandler(taskId, {
      includeThinking,
      includeToolCalls,
      afterSequence: currentAfterSequence,

      onEvent: (event) => {
        callbackOptionsRef.current.onEvent?.(event);

        if (
          event.type === 'thinking_token' ||
          event.type === 'thinking_start' ||
          event.type === 'thinking_end'
        ) return;
        setEvents((prev) => [...prev.slice(-maxEvents + 1), event]);
      },

      onThinkingStart: () => {
        thinkingBufferRef.current = [];
        setIsThinking(true);
        setThinking('');
        callbackOptionsRef.current.onThinkingStart?.();
      },

      onThinkingToken: (token, accumulated) => {
        thinkingBufferRef.current.push(token);
        setThinking(accumulated);
        callbackOptionsRef.current.onThinkingToken?.(token, accumulated);
      },

      onThinkingEnd: (response) => {
        setIsThinking(false);
        setThinking(response);
        thinkingBufferRef.current = [];
        callbackOptionsRef.current.onThinkingEnd?.(response);
      },

      onToolStart: (name, input) => {
        setToolCalls((prev) => [
          ...prev,
          { name, input, status: 'running' as const },
        ]);
        callbackOptionsRef.current.onToolStart?.(name, input);
      },

      onToolEnd: (name, output, durationMs) => {
        setToolCalls((prev) =>
          prev.map((tc) =>
            tc.name === name && tc.status === 'running'
              ? { ...tc, output, durationMs, status: 'success' as const }
              : tc
          )
        );
        callbackOptionsRef.current.onToolEnd?.(name, output, durationMs);
      },

      onNodeStart: (nodeName, phase) => {
        setCurrentPhase(phase);
        callbackOptionsRef.current.onNodeStart?.(nodeName, phase);
      },

      onNodeEnd: (nodeName, summary) => {
        callbackOptionsRef.current.onNodeEnd?.(nodeName, summary);
      },

      onProgress: (current, total, message) => {
        setProgress({
          current,
          total,
          percentage: total > 0 ? Math.round((current / total) * 100) : 0,
        });
        callbackOptionsRef.current.onProgress?.(current, total, message);
      },

      onFinding: (finding, isVerified) => {
        setFindings((prev) => [...prev, finding]);
        callbackOptionsRef.current.onFinding?.(finding, isVerified);
      },

      onComplete: (data) => {
        setIsComplete(true);
        setIsConnected(false);
        callbackOptionsRef.current.onComplete?.(data);
      },

      onError: (err, context) => {
        setError(err);
        if (context.terminal) {
          setIsComplete(true);
          setIsConnected(false);
        } else if (context.source === 'transport' || context.source === 'stream_end') {
          setIsConnected(false);
        }
        callbackOptionsRef.current.onError?.(err, context);
      },

      onHeartbeat: () => {
        callbackOptionsRef.current.onHeartbeat?.();
      },
    });

    handlerRef.current.connect();
    setIsConnected(true);
  }, [taskId, includeThinking, includeToolCalls, maxEvents]); //  移除 afterSequence 依赖，使用 ref 代替

  const disconnect = useCallback(() => {
    if (handlerRef.current) {
      handlerRef.current.disconnect();
      handlerRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  useEffect(() => {
    if (autoConnect && taskId) {
      connect();
    }
    return () => {
      disconnect();
    };
  }, [taskId, autoConnect, connect, disconnect]);

  useEffect(() => {
    return () => {
      if (handlerRef.current) {
        handlerRef.current.disconnect();
      }
    };
  }, []);

  return {
    events,
    thinking,
    isThinking,
    toolCalls,
    currentPhase,
    progress,
    findings,
    isComplete,
    error,
    connect,
    disconnect,
    isConnected,
    clearEvents,
  };
}

export function useAgentThinking(taskId: string | null) {
  const { thinking, isThinking, connect, disconnect } = useAgentStream(taskId, {
    includeToolCalls: false,
  });

  return { thinking, isThinking, connect, disconnect };
}

export function useAgentToolCalls(taskId: string | null) {
  const { toolCalls, connect, disconnect } = useAgentStream(taskId, {
    includeThinking: false,
  });

  return { toolCalls, connect, disconnect };
}

export default useAgentStream;
