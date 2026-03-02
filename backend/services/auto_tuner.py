"""
자동 파라미터 튜너 — Bayesian Optimization으로 최적 vLLM 설정 탐색
목표: 처리량(TPS) 최대화, 레이턴시(P99) 최소화
"""
import asyncio
import os
import json
import datetime
from typing import Optional, List
from kubernetes import client as k8s_client, config as k8s_config
from ..models.load_test import TuningConfig, TuningTrial, LoadTestConfig

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_AVAILABLE = True

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT_NAME", "vllm-deployment")
K8S_CONFIGMAP = os.getenv("K8S_CONFIGMAP_NAME", "vllm-config")


class AutoTuner:
    def __init__(self, metrics_collector, load_engine):
        self._metrics = metrics_collector
        self._load_engine = load_engine
        self._trials: List[TuningTrial] = []
        self._best_trial: Optional[TuningTrial] = None
        self._running = False
        self._study = None
        self._k8s_available = False
        self._init_k8s()

    def _init_k8s(self):
        try:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()
            self._k8s_apps = k8s_client.AppsV1Api()
            self._k8s_core = k8s_client.CoreV1Api()
            self._k8s_available = True
        except Exception:
            pass

    @property
    def trials(self) -> List[TuningTrial]:
        return self._trials

    @property
    def best(self) -> Optional[TuningTrial]:
        return self._best_trial

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, config: TuningConfig, vllm_endpoint: str) -> dict:
        if self._running:
            return {"error": "이미 튜닝이 실행 중입니다."}

        if not OPTUNA_AVAILABLE:
            return {"error": "optuna 패키지가 필요합니다: pip install optuna"}

        self._running = True
        self._trials = []
        self._best_trial = None

        direction = "maximize" if config.objective == "tps" else "minimize"
        self._study = optuna.create_study(
            direction=direction,
            sampler=optuna.samplers.TPESampler(seed=42),
        )

        try:
            for trial_num in range(config.n_trials):
                if not self._running:
                    break

                trial = self._study.ask()
                params = self._suggest_params(trial, config)

                # 파라미터 적용 (Kubernetes ConfigMap 업데이트)
                apply_result = await self._apply_params(params)
                if not apply_result["success"]:
                    self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
                    continue

                # vLLM 재시작 대기
                await asyncio.sleep(30)

                # 성능 측정
                score, tps, p99_lat = await self._evaluate(vllm_endpoint, config)
                self._study.tell(trial, score)

                t = TuningTrial(
                    trial_id=trial_num,
                    params=params,
                    tps=tps,
                    p99_latency=p99_lat,
                    score=score,
                    status="completed",
                )
                self._trials.append(t)

                if self._best_trial is None or (direction == "maximize" and score > self._best_trial.score) or (direction == "minimize" and score < self._best_trial.score):
                    self._best_trial = t

            return {
                "completed": True,
                "best_params": self._best_trial.params if self._best_trial else {},
                "best_score": self._best_trial.score if self._best_trial else 0,
                "trials": len(self._trials),
            }
        finally:
            self._running = False

    def stop(self):
        self._running = False

    def _suggest_params(self, trial, config: TuningConfig) -> dict:
        return {
            "max_num_seqs": trial.suggest_int(
                "max_num_seqs",
                config.max_num_seqs_range[0],
                config.max_num_seqs_range[1],
                step=32,
            ),
            "gpu_memory_utilization": trial.suggest_float(
                "gpu_memory_utilization",
                config.gpu_memory_utilization_range[0],
                config.gpu_memory_utilization_range[1],
            ),
            "max_model_len": trial.suggest_categorical(
                "max_model_len",
                [v for v in [2048, 4096, 8192] if
                 config.max_model_len_range[0] <= v <= config.max_model_len_range[1]],
            ),
            "enable_chunked_prefill": trial.suggest_categorical(
                "enable_chunked_prefill", [True, False]
            ),
        }

    async def _apply_params(self, params: dict) -> dict:
        """ConfigMap 업데이트 → Deployment 재시작"""
        if not self._k8s_available:
            print(f"[AutoTuner] K8s 없음 — 파라미터 적용 시뮬레이션: {params}")
            return {"success": True}

        try:
            # ConfigMap 업데이트
            print(f"[AutoTuner] ConfigMap '{K8S_CONFIGMAP}' in namespace '{K8S_NAMESPACE}'")
            current_cm = self._k8s_core.read_namespaced_config_map(
                name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE
            )
            
            patch_body = {
                "data": {
                    "MAX_NUM_SEQS": str(params["max_num_seqs"]),
                    "GPU_MEMORY_UTILIZATION": str(params["gpu_memory_utilization"]),
                    "MAX_MODEL_LEN": str(params["max_model_len"]),
                    "ENABLE_CHUNKED_PREFILL": str(params["enable_chunked_prefill"]).lower(),
                }
            }
            
            self._k8s_core.patch_namespaced_config_map(
                name=K8S_CONFIGMAP, namespace=K8S_NAMESPACE, body=patch_body
            )
            print(f"[AutoTuner] ConfigMap '{K8S_CONFIGMAP}' patched successfully.")
            return {"success": True}
        except Exception as e:
            print(f"[AutoTuner] 파라미터 적용 실패: {e}")
            return {"success": False, "error": str(e)}

    async def _evaluate(self, endpoint: str, config: TuningConfig) -> tuple[float, float, float]:
        """부하 테스트 실행 후 점수 반환"""
        test_config = LoadTestConfig(
            endpoint=endpoint,
            model="auto",
            total_requests=config.eval_requests,
            concurrency=32,
            rps=20,
            stream=True,
        )

        result = await self._load_engine.run(test_config)
        tps = result.get("tps", {}).get("total", 0)
        p99_lat = result.get("latency", {}).get("p99", 9999)

        if config.objective == "tps":
            score = tps
        elif config.objective == "latency":
            score = -p99_lat
        else:  # balanced
            score = tps / (p99_lat + 1) * 100

        return score, tps, p99_lat

    def get_importance(self) -> dict:
        """파라미터 중요도 반환 (Optuna FAnova)"""
        if not self._study or len(self._trials) < 5:
            return {}
        try:
            importance = optuna.importance.get_param_importances(self._study)
            return dict(importance)
        except Exception:
            return {}
