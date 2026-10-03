import { useEffect, useRef, useState } from 'react';
import { API } from '../constants';
import {
  openReconnectingEventSource,
  type ReconnectingEventSource,
} from '../utils/reconnectingEventSource';
import type { SSEState, SSEErrorPayload, LoadTestResult } from '../types';

interface LatencyPoint {
  t: number;
  lat: number;
  tps: number;
}

interface UseLoadTestSSEReturn {
  status: SSEState['status'];
  setStatus: React.Dispatch<React.SetStateAction<SSEState['status']>>;
  isReconnecting: boolean;
  retryCount: number;
  error: string | null;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  result: LoadTestResult | null;
  setResult: React.Dispatch<React.SetStateAction<LoadTestResult | null>>;
  progress: number;
  setProgress: React.Dispatch<React.SetStateAction<number>>;
  latencyData: LatencyPoint[];
  setLatencyData: React.Dispatch<React.SetStateAction<LatencyPoint[]>>;
  connect: (totalRequests: number) => void;
  disconnect: () => void;
}

export function useLoadTestSSE(): UseLoadTestSSEReturn {
  const handleRef = useRef<ReconnectingEventSource | null>(null);
  const [status, setStatus] = useState<SSEState['status']>('idle');
  const [isReconnecting, setIsReconnecting] = useState<boolean>(false);
  const [retryCount, setRetryCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LoadTestResult | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [latencyData, setLatencyData] = useState<LatencyPoint[]>([]);

  useEffect(
    () => () => {
      handleRef.current?.dispose();
    },
    []
  );

  const connect = (totalRequests: number): void => {
    handleRef.current?.dispose();
    handleRef.current = null;
    setRetryCount(0);
    setIsReconnecting(false);

    const handle = openReconnectingEventSource<LoadTestResult>({
      url: `${API}/load_test/stream`,
      onMessageReceived: () => {
        setRetryCount(0);
        setIsReconnecting(false);
      },
      onMessage: (data) => {
        if (data.type === 'error') {
          setError(
            (data.data as SSEErrorPayload | undefined)?.error ?? 'Load test error occurred.'
          );
          setStatus('error');
          handle.dispose();
          return;
        }
        if (data.type === 'progress' && data.data) {
          const d = data.data;
          if (d.total != null) {
            setProgress(Math.round((d.total / totalRequests) * 100));
          }
          setLatencyData((prev) => [
            ...prev.slice(-60),
            {
              t: prev.length,
              lat: ((d.latency?.mean ?? 0) * 1000) | 0,
              tps: (d.tps?.mean ?? 0) | 0,
            },
          ]);
          setResult(d);
        }
        if (data.type === 'completed') {
          setStatus('completed');
          setProgress(100);
          handle.dispose();
          setResult(data.data ?? null);
        }
      },
      onParseError: (err) => {
        console.error('Failed to parse SSE message data', err);
      },
      shouldReconnect: () => true,
      onRetry: (count) => {
        setIsReconnecting(true);
        setRetryCount(count);
      },
      onError: () => {
        setIsReconnecting(false);
        setError(
          'SSE connection failed: cannot connect to load test stream. (max retries exceeded)'
        );
        setStatus('error');
      },
    });

    handleRef.current = handle;
  };

  const disconnect = (): void => {
    handleRef.current?.dispose();
    handleRef.current = null;
  };

  return {
    status,
    setStatus,
    isReconnecting,
    retryCount,
    error,
    setError,
    result,
    setResult,
    progress,
    setProgress,
    latencyData,
    setLatencyData,
    connect,
    disconnect,
  };
}
