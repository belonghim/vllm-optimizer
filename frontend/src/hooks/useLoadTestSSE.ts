import { useRef, useState } from 'react';
import { API } from '../constants';
import type { SSEState, SSEErrorPayload } from '../types';

interface LatencyPoint {
  t: number;
  lat: number;
  tps: number;
}

interface SSEProgressData {
  total?: number;
  latency?: { mean: number };
  tps?: { mean: number };
  [key: string]: unknown;
}

interface SSEMessage {
  type: string;
  data?: SSEProgressData;
}

interface UseLoadTestSSEReturn {
  status: SSEState['status'];
  setStatus: React.Dispatch<React.SetStateAction<SSEState['status']>>;
  isReconnecting: boolean;
  retryCount: number;
  error: string | null;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  result: Record<string, unknown> | null;
  setResult: React.Dispatch<React.SetStateAction<Record<string, unknown> | null>>;
  progress: number;
  setProgress: React.Dispatch<React.SetStateAction<number>>;
  latencyData: LatencyPoint[];
  setLatencyData: React.Dispatch<React.SetStateAction<LatencyPoint[]>>;
  connect: (totalRequests: number) => void;
  disconnect: () => void;
}

export function useLoadTestSSE(): UseLoadTestSSEReturn {
  const esRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef<number>(0);
  const [status, setStatus] = useState<SSEState['status']>('idle');
  const [isReconnecting, setIsReconnecting] = useState<boolean>(false);
  const [retryCount, setRetryCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [latencyData, setLatencyData] = useState<LatencyPoint[]>([]);

  const connectRef = useRef<((reqCount: number) => void) | null>(null);

  const connect = (totalRequests: number): void => {
    retryCountRef.current = 0;
    setRetryCount(0);
    setIsReconnecting(false);

    const openConnection = (reqCount: number): void => {
      const es = new EventSource(`${API}/load_test/stream`);
      esRef.current = es;

      es.onmessage = (e: MessageEvent) => {
        retryCountRef.current = 0;
        setRetryCount(0);
        setIsReconnecting(false);
        let data: SSEMessage;
        try {
          data = JSON.parse(e.data as string) as SSEMessage;
        } catch {
          return;
        }
        if (data.type === 'error') {
           setError((data.data as SSEErrorPayload | undefined)?.error ?? "Load test error occurred.");
          setStatus('error');
          es.close();
          esRef.current = null;
          return;
        }
        if (data.type === 'progress' && data.data) {
          const d = data.data;
          if (d.total != null) {
            setProgress(Math.round((d.total / reqCount) * 100));
          }
          setLatencyData(prev => [...prev.slice(-60), {
            t: prev.length,
            lat: (d.latency?.mean ?? 0) * 1000 | 0,
            tps: d.tps?.mean ?? 0 | 0,
          }]);
          setResult(d as Record<string, unknown>);
        }
        if (data.type === 'completed') {
          setStatus('completed');
          setProgress(100);
          es.close();
          esRef.current = null;
          setResult((data.data ?? null) as Record<string, unknown> | null);
        }
      };

      es.onerror = () => {
        es.close();
        esRef.current = null;
        const count = retryCountRef.current + 1;
        retryCountRef.current = count;
        if (count <= 3) {
          setIsReconnecting(true);
          setRetryCount(count);
          const delay = Math.min(1000 * Math.pow(2, count - 1), 8000);
          setTimeout(() => { openConnection(reqCount); }, delay);
        } else {
          setIsReconnecting(false);
          setError('SSE connection failed: cannot connect to load test stream. (max retries exceeded)');
          setStatus('error');
        }
      };
    };

    connectRef.current = openConnection;
    openConnection(totalRequests);
  };

  const disconnect = (): void => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  };

  return {
    status, setStatus,
    isReconnecting, retryCount,
    error, setError,
    result, setResult,
    progress, setProgress,
    latencyData, setLatencyData,
    connect, disconnect,
  };
}
