import json
import os
from typing import Any


def load_baseline(env: str = "dev") -> dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", f"baseline.{env}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_baseline(env: str, metrics: dict[str, Any]) -> None:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", f"baseline.{env}.json")
    bak = path + ".bak"
    if os.path.exists(path):
        os.rename(path, bak)
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)


def compare_metrics(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, dict]:
    result = {}
    for key in baseline:
        if key in current and isinstance(baseline[key], (int, float)) and isinstance(current[key], (int, float)):
            base_val = baseline[key]
            curr_val = current[key]
            if base_val != 0:
                pct_change = ((curr_val - base_val) / abs(base_val)) * 100
            else:
                pct_change = 0.0
            result[key] = {
                "baseline": base_val,
                "current": curr_val,
                "pct_change": round(pct_change, 2),
            }
    return result