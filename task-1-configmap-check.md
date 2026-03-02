Title: Validation of vLLM ConfigMap structure (Wave 1 Task 1)
date: 2026-03-01
updated: 2026-03-01
tags: [vllm, config, validation]
---

Summary of inspected files:
- openshift/base/02-config.yaml
- backend/services/auto_tuner.py

What I checked and findings:
- In openshift/base/02-config.yaml, the ConfigMap data includes:
  - VLLM_DEPLOYMENT_NAME: "vllm-deployment"
  - VLLM_CONFIGMAP_NAME: "vllm-config"
  These values define the target Deployment and ConfigMap names used by the runtime components.
- In backend/services/auto_tuner.py, the code reads environment variables:
  - K8S_NAMESPACE (default: "default")
  - K8S_DEPLOYMENT_NAME (default: "vllm-deployment")
  - K8S_CONFIGMAP_NAME (default: "vllm-config")
  The patch/update logic uses the ConfigMap named by K8S_CONFIGMAP_NAME and patches it with:
  MAX_NUM_SEQS, GPU_MEMORY_UTILIZATION, MAX_MODEL_LEN, ENABLE_CHUNKED_PREFILL, and then rolls the Deployment by updating an annotation on the Deployment named K8S_DEPLOYMENT.
  This implies that the mapping should align: K8S_CONFIGMAP_NAME -> VLLM_CONFIGMAP_NAME and K8S_DEPLOYMENT_NAME -> VLLM_DEPLOYMENT_NAME.

Validation steps performed (as far as source inspection allows):
- Read 02-config.yaml to capture expected names:
  - VLLM_DEPLOYMENT_NAME = vllm-deployment
  - VLLM_CONFIGMAP_NAME = vllm-config
- Read auto_tuner.py to understand mapping and keys used for ConfigMap patch:
  - K8S_NAMESPACE default: default
  - K8S_DEPLOYMENT_NAME default: vllm-deployment
  - K8S_CONFIGMAP_NAME default: vllm-config
  - Patching keys: MAX_NUM_SEQS, GPU_MEMORY_UTILIZATION, MAX_MODEL_LEN, ENABLE_CHUNKED_PREFILL

Open question / next steps (environment-dependent):
- I could not perform a live cluster query (oc) to verify the existence of the ConfigMap named vllm-config in the vllm namespace from this environment. You should run the following command in the CI/CD or OpenShift cluster context to confirm existence and key alignment:
  oc get cm -n vllm vllm-config -o jsonpath='{.data}'
  If the CM exists, compare its keys with the ones updated by auto_tuner.py patch (MAX_NUM_SEQS, GPU_MEMORY_UTILIZATION, MAX_MODEL_LEN, ENABLE_CHUNKED_PREFILL).
- If the CM does not exist, note that the plan says it may be created by the vLLM deployment; in that case, alignment will be validated after deployment renders the CM.

Documentation mapping (documented changes):
- configmap_keys_mapping.md (existing in repo) should reflect: VLLM_CONFIGMAP_NAME maps to K8S_CONFIGMAP_NAME, VLLM_DEPLOYMENT_NAME maps to K8S_DEPLOYMENT_NAME for patch/rollback workflows.

Risks / caveats:
- If the deployment uses different namespace (K8S_NAMESPACE) than the ConfigMap namespace, patch/rollback may fail. Ensure K8S_NAMESPACE aligns with vllm namespace (as needed by your cluster setup).
- The patch assumes in-cluster config and a standard Kubernetes API; if running out-of-cluster, config loading must be provided (kubeconfig).

Conclusion:
- The sources show consistent intent for VLLM_DEPLOYMENT_NAME and VLLM_CONFIGMAP_NAME usage. Final validation requires a live cluster check to confirm the ConfigMap’s existence and key set alignment with the auto_tuner patch keys. No files were modified as requested in this task.
