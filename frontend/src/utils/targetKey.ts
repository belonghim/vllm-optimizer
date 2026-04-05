import type { ClusterTarget } from '../types';

export const CR_TYPE_DEFAULT = 'inferenceservice';

export function getTargetKey(target: ClusterTarget): string {
  return `${target.namespace}/${target.inferenceService}/${target.crType || CR_TYPE_DEFAULT}`;
}

export function parseTargetKey(key: string): { namespace: string; inferenceService: string; crType: string } | null {
  const parts = key.split('/');
  if (parts.length !== 3) return null;
  const [namespace, inferenceService, crType] = parts;
  return { namespace, inferenceService, crType };
}
