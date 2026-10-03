export function buildDefaultEndpoint(crType: string, namespace: string, isName: string): string {
  if (crType === 'llminferenceservice') {
    // KServe's per-LLMIS workload Service reaches vLLM directly, whichever gateway the LLMIS uses.
    return `https://${isName}-kserve-workload-svc.${namespace}.svc.cluster.local:8000`;
  }
  // KServe predictor Service listens on port 80 (HTTP default).
  return `http://${isName}-predictor.${namespace}.svc.cluster.local`;
}
