# Learnings from T1: OpenShift YAML adjustments

- Updated OpenShift dev-only configurations to surface auto-tuner parameters to runtime and to persist defaults in ConfigMap.
- Files touched:
  - openshift/dev-only/vllm-runtime.yaml: Added 4 runtime args after enable-chunked-prefill; ensured shell line continuation with trailing backslashes.
  - openshift/dev-only/vllm-config.yaml: Added 3 new keys (MAX_NUM_BATCHED_TOKENS, BLOCK_SIZE, SWAP_SPACE) and set ENABLE_ENFORCE_EAGER to empty string. Kept ENABLE_CHUNKED_PREFILL unchanged (empty).
- Build verification: kustomize build could not be executed due to missing kustomize binary in environment; instructions provided to run locally.
- Evidence file: plan to generate under .sisyphus/evidence/task-1-kustomize-build.txt after running kustomize.

Next steps (for you to run):
- Run: ./kustomize build openshift/dev-only/ and capture output to .sisyphus/evidence/task-1-kustomize-build.txt
- Commit results and re-run lsp_diagnostics for changed files when environment has language servers and test framework.
