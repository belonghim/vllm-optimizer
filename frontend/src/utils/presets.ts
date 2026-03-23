interface LoadTestPresetData {
  total_requests: number;
  concurrency: number;
  rps: number;
  max_tokens: number;
  temperature: number;
  stream: boolean;
}

const STORAGE_KEY = 'vllm-loadtest-presets';

export const BUILTIN_PRESETS: Record<string, LoadTestPresetData> = {
  '경량': {
    total_requests: 50,
    concurrency: 5,
    rps: 5,
    max_tokens: 128,
    temperature: 0.7,
    stream: true,
  },
  '표준': {
    total_requests: 200,
    concurrency: 20,
    rps: 10,
    max_tokens: 256,
    temperature: 0.7,
    stream: true,
  },
  '스트레스': {
    total_requests: 1000,
    concurrency: 100,
    rps: 50,
    max_tokens: 512,
    temperature: 0.7,
    stream: true,
  },
};

export function savePreset(name: string, config: Partial<LoadTestPresetData>): void {
  if (BUILTIN_PRESETS[name]) {
    throw new Error('Cannot overwrite builtin preset');
  }
  const userPresets = getUserPresets();
  userPresets[name] = {
    total_requests: config.total_requests ?? 200,
    concurrency: config.concurrency ?? 20,
    rps: config.rps ?? 10,
    max_tokens: config.max_tokens ?? 256,
    temperature: config.temperature ?? 0.7,
    stream: config.stream ?? true,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(userPresets));
}

export function loadPresets(): Record<string, LoadTestPresetData> {
  return { ...BUILTIN_PRESETS, ...getUserPresets() };
}

export function deletePreset(name: string): void {
  if (BUILTIN_PRESETS[name]) {
    throw new Error('Cannot delete builtin preset');
  }
  const userPresets = getUserPresets();
  delete userPresets[name];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(userPresets));
}

function getUserPresets(): Record<string, LoadTestPresetData> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

export function isBuiltinPreset(name: string): boolean {
  return name in BUILTIN_PRESETS;
}
