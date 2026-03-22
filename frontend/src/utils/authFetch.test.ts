import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('authFetch', () => {
  let authFetch: typeof import('./authFetch').authFetch;

  beforeEach(async () => {
    vi.resetModules();
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('location', { reload: vi.fn() });
    const mod = await import('./authFetch');
    authFetch = mod.authFetch;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('passes through 200 responses without reload', async () => {
    const mockResponse = { status: 200, ok: true } as Response;
    vi.mocked(fetch).mockResolvedValue(mockResponse);

    const result = await authFetch('/api/test');

    expect(result).toBe(mockResponse);
    expect(window.location.reload).not.toHaveBeenCalled();
  });

  it('triggers reload on 403', async () => {
    vi.mocked(fetch).mockResolvedValue({ status: 403 } as Response);

    await authFetch('/api/test');

    expect(window.location.reload).toHaveBeenCalledOnce();
  });

  it('passes through non-403 errors without reload', async () => {
    const mockResponse = { status: 500, ok: false } as Response;
    vi.mocked(fetch).mockResolvedValue(mockResponse);

    const result = await authFetch('/api/test');

    expect(result).toBe(mockResponse);
    expect(window.location.reload).not.toHaveBeenCalled();
  });

  it('does not double-reload on consecutive 403s', async () => {
    vi.mocked(fetch).mockResolvedValue({ status: 403 } as Response);

    await authFetch('/api/first');
    await authFetch('/api/second');

    expect(window.location.reload).toHaveBeenCalledOnce();
  });
});
