import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSessionKeepAlive } from './useSessionKeepAlive';

describe('useSessionKeepAlive', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 200 }));
    vi.stubGlobal('location', { reload: vi.fn() });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('calls heartbeat API at 15-minute interval', async () => {
    renderHook(() => useSessionKeepAlive());

    await vi.advanceTimersByTimeAsync(15 * 60 * 1000);

    expect(fetch).toHaveBeenCalledWith('/api/metrics/latest');
  });

  it('triggers reload on 403 heartbeat response', async () => {
    vi.mocked(fetch).mockResolvedValue({ status: 403 });

    renderHook(() => useSessionKeepAlive());

    await vi.advanceTimersByTimeAsync(15 * 60 * 1000);

    expect(window.location.reload).toHaveBeenCalled();
  });

  it('clears interval on unmount', async () => {
    const { unmount } = renderHook(() => useSessionKeepAlive());

    unmount();

    vi.mocked(fetch).mockClear();
    await vi.advanceTimersByTimeAsync(15 * 60 * 1000);

    expect(fetch).not.toHaveBeenCalled();
  });
});
