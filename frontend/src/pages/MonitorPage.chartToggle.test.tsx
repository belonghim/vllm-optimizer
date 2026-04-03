import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string): string | null => store[key] ?? null),
    setItem: vi.fn((key: string, val: string) => { store[key] = val; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
    _getStore: () => store,
    _setStore: (s: Record<string, string>) => { store = s; },
  };
})();

Object.defineProperty(global, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

const LS_KEY = 'vllm-optimizer-chart-config';
const DEFAULT_IDS = ['tps', 'latency', 'ttft', 'kv', 'kv_hit', 'queue', 'rps', 'gpu_util', 'gpu_mem'];

interface StoredChartConfig {
  order?: string[];
  hidden?: string[];
}

function loadChartConfig(): { order: string[]; hidden: string[] } {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { order: DEFAULT_IDS, hidden: [] };
    const parsed: StoredChartConfig = JSON.parse(raw);
    const validIds = new Set(DEFAULT_IDS);
    const order = Array.isArray(parsed.order)
      ? parsed.order.filter((id: string) => validIds.has(id))
      : DEFAULT_IDS;
    const hidden = Array.isArray(parsed.hidden)
      ? parsed.hidden.filter((id: string) => validIds.has(id))
      : [];
    const inOrder = new Set(order);
    DEFAULT_IDS.forEach((id: string) => { if (!inOrder.has(id)) order.push(id); });
    return { order, hidden };
  } catch {
    return { order: DEFAULT_IDS, hidden: [] };
  }
}

function saveChartConfig(order: string[], hidden: string[]): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ order, hidden }));
  } catch {
    // ignore storage errors
  }
}

describe('loadChartConfig', () => {
  beforeEach(() => {
    localStorageMock._setStore({});
    vi.clearAllMocks();
  });

  it('returns default config when localStorage is empty', () => {
    localStorageMock.getItem.mockReturnValue(null);
    const config = loadChartConfig();
    expect(config.order).toEqual(DEFAULT_IDS);
    expect(config.hidden).toEqual([]);
  });

  it('returns parsed config from localStorage', () => {
    const stored = { order: ['rps', 'tps', 'latency', 'ttft', 'kv', 'kv_hit', 'queue', 'gpu_util', 'gpu_mem'], hidden: ['gpu_mem'] };
    localStorageMock.getItem.mockReturnValue(JSON.stringify(stored));
    const config = loadChartConfig();
    expect(config.hidden).toContain('gpu_mem');
    expect(config.order[0]).toBe('rps');
  });

  it('falls back to default on invalid JSON', () => {
    localStorageMock.getItem.mockReturnValue('INVALID_JSON{{{');
    const config = loadChartConfig();
    expect(config.order).toEqual(DEFAULT_IDS);
    expect(config.hidden).toEqual([]);
  });

  it('filters out unknown chart IDs', () => {
    const stored = { order: ['tps', 'unknown_chart', 'latency'], hidden: ['bad_id'] };
    localStorageMock.getItem.mockReturnValue(JSON.stringify(stored));
    const config = loadChartConfig();
    expect(config.order).not.toContain('unknown_chart');
    expect(config.hidden).not.toContain('bad_id');
  });

  it('adds missing IDs to order when stored order is partial', () => {
    const stored = { order: ['tps'], hidden: [] };
    localStorageMock.getItem.mockReturnValue(JSON.stringify(stored));
    const config = loadChartConfig();
    // All 9 IDs must be in order
    DEFAULT_IDS.forEach(id => expect(config.order).toContain(id));
  });

  it('preserves order of valid IDs in stored config', () => {
    const stored = { order: ['gpu_mem', 'latency', 'tps'], hidden: [] };
    localStorageMock.getItem.mockReturnValue(JSON.stringify(stored));
    const config = loadChartConfig();
    expect(config.order[0]).toBe('gpu_mem');
    expect(config.order[1]).toBe('latency');
    expect(config.order[2]).toBe('tps');
  });
});

describe('saveChartConfig', () => {
  beforeEach(() => {
    localStorageMock._setStore({});
    vi.clearAllMocks();
  });

  it('saves config to localStorage', () => {
    const order = ['tps', 'latency'];
    const hidden = ['gpu_mem'];
    saveChartConfig(order, hidden);
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      LS_KEY,
      JSON.stringify({ order, hidden })
    );
  });

   it('handles empty arrays', () => {
     saveChartConfig([], []);
     const stored = JSON.parse(localStorageMock._getStore()[LS_KEY]!);
     expect(stored.order).toEqual([]);
     expect(stored.hidden).toEqual([]);
   });
});

describe('chart config integration', () => {
  beforeEach(() => {
    localStorageMock._setStore({});
    vi.clearAllMocks();
  });

  it('saveChartConfig stores correct structure in localStorage', () => {
    saveChartConfig(['tps', 'latency'], ['gpu_mem']);
    
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      LS_KEY,
      JSON.stringify({ order: ['tps', 'latency'], hidden: ['gpu_mem'] })
    );
  });

  it('loadChartConfig returns stored order and hidden arrays', () => {
    const stored = { order: ['tps', 'latency'], hidden: ['gpu_mem'] };
    // Directly set the store for getItem to return
    localStorageMock.getItem.mockReturnValueOnce(JSON.stringify(stored));
    
    const loaded = loadChartConfig();
    
    expect(loaded.hidden).toContain('gpu_mem');
    expect(loaded.order).toContain('tps');
    expect(loaded.order).toContain('latency');
  });
});
