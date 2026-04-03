export function buildDefaultEndpoint(crType: string, namespace: string, isName: string): string {
  if (crType === "llminferenceservice") {
    return `http://${isName}-openshift-default.${namespace}.svc.cluster.local:80`;
  }
  return `http://${isName}-predictor.${namespace}.svc.cluster.local:8080`;
}
