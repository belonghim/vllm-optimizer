export interface ClusterTarget {
  namespace: string;
  inferenceService: string;
  isDefault: boolean;
}

export interface ClusterConfig {
  version: number;
  endpoint: string;
  targets: ClusterTarget[];
  maxTargets: number;
}

export interface SSEState {
  status: 'idle' | 'running' | 'completed' | 'error' | 'stopped';
  isReconnecting: boolean;
  retryCount: number;
  error: string | null;
}

export interface SSEErrorPayload {
  error: string;
  error_type?: string;
}

export interface SSEWarningPayload {
  message: string;
  trial?: number;
}
