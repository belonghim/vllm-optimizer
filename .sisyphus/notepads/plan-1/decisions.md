Plan-1 Decisions
- Decision: Map ENABLE_CHUNKED_PREFILL to ENABLE_CHUNKED_PREFILL in patch_body; remove ENABLE_ENFORCE_EAGER from patch payload.
- Decision: Extend ServingRuntime args to include --enable-chunked-prefill when ENABLE_CHUNKED_PREFILL is set; keep existing --enforce-eager behavior controlled by ENABLE_ENFORCE_EAGER.
- Decision: Add ENABLE_CHUNKED_PREFILL: "" to vllm-config.yaml to represent default-disabled state.
- Next steps: If more flags are introduced, follow similar mapping rules and ensure tests cover new mappings.
