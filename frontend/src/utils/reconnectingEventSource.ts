import { SSE_MAX_RETRIES, SSE_MAX_RETRY_DELAY_MS } from '../constants';

export interface SSEEventMessage<T = unknown> {
  type: string;
  data?: T;
}

export interface OpenReconnectingEventSourceOptions<T = unknown> {
  url: string;
  /** Invoked for every successfully parsed message. */
  onMessage: (message: SSEEventMessage<T>) => void;
  /** Invoked at the start of every message event, before parsing. */
  onMessageReceived?: () => void;
  /** Invoked when a message cannot be parsed as JSON. */
  onParseError?: (error: unknown) => void;
  onOpen?: () => void;
  /** Invoked when the connection permanently fails (retries disabled or exhausted). */
  onError?: () => void;
  /** Invoked when a retry has been scheduled, with the 1-based retry count. */
  onRetry?: (retryCount: number) => void;
  /** Evaluated on every connection error to decide whether to retry. */
  shouldReconnect?: () => boolean;
}

export interface ReconnectingEventSource {
  /** Closes the active connection without cancelling pending retries. */
  closeSocket: () => void;
  /** Closes the connection, clears any pending retry timer, and stops reconnecting. */
  dispose: () => void;
}

const RETRY_BASE_DELAY_MS = 1000;

export function openReconnectingEventSource<T = unknown>(
  options: OpenReconnectingEventSourceOptions<T>
): ReconnectingEventSource {
  let retryCount = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let currentEs: EventSource | null = null;
  let cancelled = false;

  const openConnection = (): void => {
    if (cancelled) return;
    const es = new EventSource(options.url);
    currentEs = es;

    es.onopen = (): void => {
      options.onOpen?.();
    };

    es.onmessage = (event): void => {
      retryCount = 0;
      options.onMessageReceived?.();
      try {
        const message = JSON.parse(event.data as string) as SSEEventMessage<T>;
        options.onMessage(message);
      } catch (parseError) {
        options.onParseError?.(parseError);
      }
    };

    es.onerror = (): void => {
      es.close();
      currentEs = null;
      if (cancelled) return;

      if (options.shouldReconnect?.()) {
        const count = retryCount + 1;
        retryCount = count;
        if (count <= SSE_MAX_RETRIES) {
          options.onRetry?.(count);
          const delay = Math.min(
            RETRY_BASE_DELAY_MS * Math.pow(2, count - 1),
            SSE_MAX_RETRY_DELAY_MS
          );
          retryTimer = setTimeout(openConnection, delay);
        } else {
          options.onError?.();
        }
      } else {
        options.onError?.();
      }
    };
  };

  openConnection();

  return {
    closeSocket: (): void => {
      if (currentEs) {
        currentEs.close();
        currentEs = null;
      }
    },
    dispose: (): void => {
      cancelled = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      if (currentEs) {
        currentEs.close();
        currentEs = null;
      }
    },
  };
}
