import { useEffect, useRef } from 'react';
import { API } from '../constants';
import { authFetch } from '../utils/authFetch';

const HEARTBEAT_INTERVAL = 4 * 60 * 1000;

export function useSessionKeepAlive() {
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
   const ping = async () => {
        try {
          const res = await authFetch(`${API}/metrics/latest`);
          if (res.status === 403) {
            window.location.href = '/oauth/sign_out';
          }
        } catch (e) {
          console.error('Session heartbeat failed', e);
        }
      };

    ping();
    timerRef.current = window.setInterval(ping, HEARTBEAT_INTERVAL);
    return () => {
      if (timerRef.current !== undefined) {
        window.clearInterval(timerRef.current);
      }
    };
  }, []);
}
