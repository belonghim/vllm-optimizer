# Learnings
- 2026-03-07: Added psutil-backed CPU/GPU sampling to LoadTestEngine via an async background task and surface backend_cpu_avg/gpu_utilization_avg/tokens_per_sec in the final load-test result.

- Added dedicated Tekton performance pipeline with UBI9 images, non-root security contexts, and a soft-fail pytest step to keep CI separate from benchmarks.
