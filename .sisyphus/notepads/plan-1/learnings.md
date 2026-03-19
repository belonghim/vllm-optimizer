Plan-1 Learnings
- Action: Fix mapping bug in backend auto_tuner to map ENABLE_CHUNKED_PREFILL correctly and remove ENABLE_ENFORCE_EAGER usage.
- Approach: Updated patch_body to include ENABLE_CHUNKED_PREFILL and removed ENABLE_ENFORCE_EAGER. Updated OpenShift runtime and config to reflect new flag. Added unit test to validate mapping.
- Verification mindset: Ensure changes align with existing ConfigMap and ServingRuntime annotation patterns. Validate with pytest for tuner tests.
- Outcome: Patch applied, tests pass (13 passed, 4 warnings). See evidence files for commands and outputs.
