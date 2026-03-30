import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSessionKeepAlive } from './useSessionKeepAlive';

describe('useSessionKeepAlive', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200 } as Response));
    vi.stubGlobal('location', { href: '' });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('calls heartbeat API immediately on mount', async () => {
    renderHook(() => useSessionKeepAlive());

    await vi.advanceTimersByTimeAsync(0);

    expect(fetch).toHaveBeenCalledWith('/api/metrics/latest', undefined);
  });

  it('calls heartbeat API again at 4-minute interval', async () => {
    renderHook(() => useSessionKeepAlive());

    await vi.advanceTimersByTimeAsync(4 * 60 * 1000);

    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('redirects to /oauth/sign_out on 403 heartbeat response', async () => {
    vi.mocked(fetch).mockResolvedValue({ status: 403 } as Response);

    renderHook(() => useSessionKeepAlive());

    await vi.advanceTimersByTimeAsync(0);

    expect(window.location.href).toBe('/oauth/sign_out');
  });

  it('clears interval on unmount', async () => {
    const { unmount } = renderHook(() => useSessionKeepAlive());

    await vi.advanceTimersByTimeAsync(0);
    vi.mocked(fetch).mockClear();
    unmount();

    await vi.advanceTimersByTimeAsync(4 * 60 * 1000);

    expect(fetch).not.toHaveBeenCalled();
  });
});
