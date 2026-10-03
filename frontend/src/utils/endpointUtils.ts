export function buildDefaultEndpoint(crType: string, namespace: string, isName: string): string {
  if (crType === 'llminferenceservice') {
    return `https://openshift-ai-inference-openshift-default.openshift-ingress.svc/${namespace}/${isName}`;
  }
  // KServe predictor Service listens on port 80 (HTTP default).
  return `http://${isName}-predictor.${namespace}.svc.cluster.local`;
}
