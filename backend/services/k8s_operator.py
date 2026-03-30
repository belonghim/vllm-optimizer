import asyncio
import logging
import time
from typing import Any, cast

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException

from services.cr_adapter import CRAdapter, args_list_to_config_dict, get_cr_adapter  # pyright: ignore[reportImplicitRelativeImport]
from services.shared import runtime_config  # pyright: ignore[reportImplicitRelativeImport]

logger = logging.getLogger(__name__)


def _get_k8s_namespace() -> str:
    namespace = runtime_config.vllm_namespace
    return namespace if namespace else "default"


def _get_vllm_is_name() -> str:
    return runtime_config.vllm_is_name or "llm-ov"


class K8sOperator:
    def __init__(self) -> None:
        self._k8s_available = False
        self._k8s_apps: k8s_client.AppsV1Api | None = None
        self._k8s_custom: k8s_client.CustomObjectsApi | None = None
        self._is_args_snapshot: dict[str, Any] | None = None
        self._last_rollback_trial: int | None = None
        self._wait_durations: list[float] = []
        self._total_wait_seconds: float = 0.0
        self._poll_count: int = 0
        self._cooldown_secs: int = 30
        self._init_k8s()

    @property
    def _cr_adapter(self) -> CRAdapter:
        return get_cr_adapter()

    @property
    def k8s_available(self) -> bool:
        return self._k8s_available

    @property
    def wait_metrics(self) -> dict[str, Any]:
        return {
            "total_wait_seconds": round(self._total_wait_seconds, 2),
            "poll_count": self._poll_count,
            "per_trial_waits": [round(d, 2) for d in self._wait_durations],
        }

    def _init_k8s(self) -> None:
        try:
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()
            self._k8s_apps = k8s_client.AppsV1Api()
            self._k8s_custom = k8s_client.CustomObjectsApi()
            self._k8s_available = True
        except k8s_config.ConfigException as e:
            logger.warning("K8s client unavailable: %s", e)

    async def wait_for_ready(self, cancel_event: asyncio.Event, timeout: int = 300, interval: int = 5) -> bool:
        namespace = _get_k8s_namespace()
        is_name = _get_vllm_is_name()
        custom_api = cast(Any, self._k8s_custom)
        logger.info(f"[AutoTuner] InferenceService '{is_name}' 준비 대기 중...")
        wait_start = time.monotonic()
        start_time = asyncio.get_event_loop().time()
        result = False
        while asyncio.get_event_loop().time() - start_time < timeout:
            if cancel_event.is_set():
                logger.info("[AutoTuner] 준비 대기가 취소되었습니다.")
                break

            self._poll_count += 1
            try:
                inferenceservice = await asyncio.to_thread(
                    custom_api.get_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    name=is_name,
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                )
                _isvc: dict[str, Any] = cast(dict[str, Any], inferenceservice) if inferenceservice else {}
                if self._cr_adapter.check_ready(_isvc.get("status", {})):
                    logger.info(f"[AutoTuner] InferenceService '{is_name}' 준비 완료.")
                    result = True
                    break
            except ApiException as e:
                if e.status == 403:
                    logger.error(f"[AutoTuner] IS 상태 확인 403 Forbidden: {e}. 즉시 중단.")
                    break
                logger.warning(f"[AutoTuner] IS 상태 확인 오류: {e}")

            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=interval)
                logger.info("[AutoTuner] 준비 대기 중 취소 신호를 감지했습니다.")
                break
            except TimeoutError:
                await asyncio.sleep(0)

        wait_duration = time.monotonic() - wait_start
        self._wait_durations.append(round(wait_duration, 2))
        self._total_wait_seconds += wait_duration

        if not result and not cancel_event.is_set():
            logger.error(f"[AutoTuner] InferenceService '{is_name}' 시간 초과: {timeout}초.")

        if result and not cancel_event.is_set():
            cooldown = self._cooldown_secs
            logger.info(f"[AutoTuner] 메트릭 안정화를 위해 {cooldown}초 대기 중...")
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=cooldown)
                logger.info("[AutoTuner] 쿨다운 중 취소 신호를 감지했습니다.")
                return False
            except TimeoutError:
                pass

        return result

    async def preflight_check(self) -> dict[str, Any]:
        if not self._k8s_available:
            return {
                "success": False,
                "error": "K8s 클라이언트를 초기화할 수 없습니다. 클러스터 연결을 확인하세요.",
                "error_type": "k8s_unavailable",
            }
        namespace = _get_k8s_namespace()
        is_name = _get_vllm_is_name()
        custom_api = cast(Any, self._k8s_custom)
        try:
            await asyncio.to_thread(
                custom_api.get_namespaced_custom_object,
                group=self._cr_adapter.api_group(),
                version=self._cr_adapter.api_version(),
                name=is_name,
                namespace=namespace,
                plural=self._cr_adapter.api_plural(),
            )
            return {"success": True}
        except ApiException as e:
            if e.status == 403:
                return {
                    "success": False,
                    "error": "InferenceService 접근 권한이 없습니다 (403 Forbidden). Role/RoleBinding 설정을 확인하세요.",
                    "error_type": "rbac",
                }
            if e.status == 404:
                return {
                    "success": False,
                    "error": f"InferenceService '{is_name}'을(를) '{namespace}'에서 찾을 수 없습니다.",
                    "error_type": "not_found",
                }
            return {
                "success": False,
                "error": f"K8s API 오류: {e}",
                "error_type": "k8s_error",
            }

    async def get_model_name(self) -> str:
        """Resolve the model name from the InferenceService spec."""
        if not self._k8s_available or self._k8s_custom is None:
            return _get_vllm_is_name()
        namespace = _get_k8s_namespace()
        is_name = _get_vllm_is_name()
        custom_api = cast(Any, self._k8s_custom)
        try:
            cr_obj = await asyncio.to_thread(
                custom_api.get_namespaced_custom_object,
                group=self._cr_adapter.api_group(),
                version=self._cr_adapter.api_version(),
                name=is_name,
                namespace=namespace,
                plural=self._cr_adapter.api_plural(),
            )
            spec = cast(dict[str, Any], cr_obj).get("spec", {}) if cr_obj else {}
            return self._cr_adapter.resolve_model_name(spec, is_name)
        except ApiException:
            return is_name

    def params_to_args(self, params: dict[str, Any]) -> list[str]:
        args: list[str] = []

        if "max_num_seqs" in params:
            args.append(f"--max-num-seqs={params['max_num_seqs']}")

        if "gpu_memory_utilization" in params:
            args.append(f"--gpu-memory-utilization={params['gpu_memory_utilization']}")

        if "max_model_len" in params:
            args.append(f"--max-model-len={params['max_model_len']}")

        if "max_num_batched_tokens" in params:
            args.append(f"--max-num-batched-tokens={params['max_num_batched_tokens']}")

        if "block_size" in params:
            args.append(f"--block-size={params['block_size']}")

        if "swap_space" in params:
            args.append(f"--swap-space={params['swap_space']}")

        if params.get("enable_chunked_prefill"):
            args.append("--enable-chunked-prefill")

        if params.get("enable_enforce_eager"):
            args.append("--enforce-eager")

        return args

    async def apply_params(self, params: dict[str, Any], k8s_lock: asyncio.Lock) -> dict[str, Any]:
        if not self._k8s_available:
            logger.error("[AutoTuner] K8s 클라이언트가 초기화되지 않아 파라미터를 적용할 수 없습니다.")
            return {
                "success": False,
                "error": "K8s 클라이언트가 초기화되지 않았습니다.",
                "error_type": "k8s_unavailable",
            }

        try:
            async with k8s_lock:
                namespace = _get_k8s_namespace()
                is_name = _get_vllm_is_name()
                custom_api = cast(Any, self._k8s_custom)
                logger.info(f"[AutoTuner] InferenceService '{is_name}' in namespace '{namespace}'")
                isvc = await asyncio.to_thread(
                    custom_api.get_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    name=is_name,
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                )
                _isvc2: dict[str, Any] = cast(dict[str, Any], isvc) if isvc else {}
                self._is_args_snapshot = self._cr_adapter.snapshot_args(_isvc2.get("spec", {}))

                tuning_args = self.params_to_args(params)
                params_config_dict = args_list_to_config_dict(tuning_args)
                patch_body = self._cr_adapter.build_args_patch(_isvc2.get("spec", {}), params_config_dict)

                await asyncio.to_thread(
                    custom_api.patch_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                    name=is_name,
                    body=patch_body,
                )
                logger.info(f"[AutoTuner] InferenceService '{is_name}' args patched successfully: {tuning_args}")

            return {"success": True}
        except ApiException as e:
            logger.error(f"[AutoTuner] InferenceService args patch failed: {e}")
            if e.status == 403:
                return {
                    "success": False,
                    "error": "InferenceService 패치 권한 없음 (403 Forbidden)",
                    "error_type": "rbac",
                }
            if e.status == 404:
                namespace = _get_k8s_namespace()
                is_name = _get_vllm_is_name()
                return {
                    "success": False,
                    "error": f"InferenceService '{is_name}'을(를) '{namespace}'에서 찾을 수 없습니다.",
                    "error_type": "not_found",
                }
            return {"success": False, "error": f"InferenceService args patch failed: {e}"}
        except Exception as e:  # intentional: K8s operation fallback (fail-open)
            logger.error(f"[AutoTuner] 파라미터 적용 실패: {e}")
            return {"success": False, "error": str(e)}

    async def rollback_to_snapshot(self, trial_num: int, k8s_lock: asyncio.Lock) -> bool:
        if not self._k8s_available or self._is_args_snapshot is None:
            logger.warning("[AutoTuner] Rollback requested but no snapshot available (trial %d)", trial_num)
            return False
        try:
            async with k8s_lock:
                namespace = _get_k8s_namespace()
                is_name = _get_vllm_is_name()
                custom_api = cast(Any, self._k8s_custom)
                patch_body = self._cr_adapter.build_rollback_patch(self._is_args_snapshot)
                await asyncio.to_thread(
                    custom_api.patch_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                    name=is_name,
                    body=patch_body,
                )
            self._last_rollback_trial = trial_num
            logger.info("[AutoTuner] Rollback to snapshot completed for trial %d", trial_num)
            return True
        except ApiException as e:
            logger.error("[AutoTuner] Rollback failed for trial %d: %s", trial_num, e)
            return False
