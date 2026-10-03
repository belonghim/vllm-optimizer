export function buildDefaultEndpoint(crType: string, namespace: string, isName: string): string {
  if (crType === 'llminferenceservice') {
    return `https://openshift-ai-inference-openshift-default.openshift-ingress.svc/${namespace}/${isName}`;
  }
  return `http://${isName}-predictor.${namespace}.svc.cluster.local:8080`;
}
