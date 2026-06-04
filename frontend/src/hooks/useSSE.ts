import { useEffect, useRef } from 'react';
import { SSE_MAX_RETRIES, SSE_MAX_RETRY_DELAY_MS } from '../constants';

export interface UseSSEOptions {
  onError?: () => void;
  onOpen?: () => void;
  reconnect?: boolean;
}

export function useSSE(
  url: string | null,
  handlers: Record<string, (data: unknown) => void>,
  options: UseSSEOptions = {}
): void {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!url) return;

    let retryCount = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let currentEs: EventSource | null = null;
    let cancelled = false;

    const openConnection = () => {
      if (cancelled) return;
      const es = new EventSource(url);
      currentEs = es;

      es.onopen = () => {
        optionsRef.current.onOpen?.();
      };

      es.onmessage = (event) => {
        retryCount = 0;
        try {
          const msg = JSON.parse(event.data as string) as { type: string; data?: unknown };
          const handler = handlersRef.current[msg.type];
          if (handler) handler(msg.data);
        } catch (e) {
          if (import.meta.env.DEV) console.error('[useSSE] parse error:', e);
        }
      };

      es.onerror = () => {
        es.close();
        currentEs = null;
        if (cancelled) return;

        if (optionsRef.current.reconnect) {
          const count = retryCount + 1;
          retryCount = count;
          if (count <= SSE_MAX_RETRIES) {
            const delay = Math.min(1000 * Math.pow(2, count - 1), SSE_MAX_RETRY_DELAY_MS);
            retryTimer = setTimeout(openConnection, delay);
          } else {
            optionsRef.current.onError?.();
          }
        } else {
          optionsRef.current.onError?.();
        }
      };
    };

    openConnection();

    return () => {
      cancelled = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      if (currentEs) { currentEs.close(); currentEs = null; }
    };
  }, [url]);
}
