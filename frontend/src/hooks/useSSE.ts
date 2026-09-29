import { useEffect, useRef } from 'react';
import { openReconnectingEventSource } from '../utils/reconnectingEventSource';

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

    const handle = openReconnectingEventSource({
      url,
      onMessage: (message) => {
        const handler = handlersRef.current[message.type];
        if (handler) handler(message.data);
      },
      onOpen: () => optionsRef.current.onOpen?.(),
      onError: () => optionsRef.current.onError?.(),
      onParseError: (error) => {
        if (import.meta.env.DEV) console.error('[useSSE] parse error:', error);
      },
      shouldReconnect: () => Boolean(optionsRef.current.reconnect),
    });

    return () => handle.dispose();
  }, [url]);
}
