import { useEffect, useRef } from 'react';
import { API } from '../constants';

const HEARTBEAT_INTERVAL = 15 * 60 * 1000;

export function useSessionKeepAlive() {
  const timerRef = useRef<number>();

  useEffect(() => {
    const ping = async () => {
      try {
        const res = await fetch(`${API}/metrics/latest`);
        if (res.status === 403) {
          window.location.reload();
        }
      } catch {
      }
    };

    timerRef.current = window.setInterval(ping, HEARTBEAT_INTERVAL);
    return () => window.clearInterval(timerRef.current);
  }, []);
}
