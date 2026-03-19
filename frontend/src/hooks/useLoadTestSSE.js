import { useRef, useState } from 'react';
import { API } from '../constants';

export function useLoadTestSSE() {
  const esRef = useRef(null);
  const retryCountRef = useRef(0);
  const [status, setStatus] = useState('idle');
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);
  const [latencyData, setLatencyData] = useState([]);

  const connect = (totalRequests) => {
    retryCountRef.current = 0;
    setRetryCount(0);
    setIsReconnecting(false);

    const es = new EventSource(`${API}/load_test/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      retryCountRef.current = 0;
      setRetryCount(0);
      setIsReconnecting(false);
      let data;
      try {
        data = JSON.parse(e.data);
      } catch {
        return;
      }
      if (data.type === 'progress' && data.data) {
        const d = data.data;
        if (d.total != null) {
          setProgress(Math.round((d.total / totalRequests) * 100));
        }
        setLatencyData(prev => [...prev.slice(-60), {
          t: prev.length,
          lat: d.latency?.mean * 1000 | 0,
          tps: d.tps?.mean | 0,
        }]);
        setResult(d);
      }
      if (data.type === 'completed') {
        setStatus('completed');
        setProgress(100);
        es.close();
        esRef.current = null;
        setResult(data.data);
      }
    };

    es.onerror = () => {
      if (es.readyState === EventSource.CONNECTING) {
        retryCountRef.current += 1;
        setRetryCount(retryCountRef.current);
        if (retryCountRef.current <= 3) {
          setIsReconnecting(true);
          return;
        }
      }
      setIsReconnecting(false);
      setError('SSE 연결 실패: 부하 테스트 스트림에 연결할 수 없습니다. (최대 재시도 횟수 초과)');
      setStatus('error');
      es.close();
      esRef.current = null;
    };
  };

  const disconnect = () => {
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
