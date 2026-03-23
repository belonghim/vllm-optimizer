import { useEffect, useRef } from 'react';
import { API } from '../constants';

const HEARTBEAT_INTERVAL = 15 * 60 * 1000;

export function useSessionKeepAlive() {
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const ping = async () => {
      try {
        const res = await fetch(`${API}/metrics/latest`);
        if (res.status === 403) {
          window.location.href = '/oauth/sign_out';
        }
      } catch {
      }
    };

    timerRef.current = window.setInterval(ping, HEARTBEAT_INTERVAL);
    return () => {
      if (timerRef.current !== undefined) {
        window.clearInterval(timerRef.current);
      }
    };
  }, []);
}
