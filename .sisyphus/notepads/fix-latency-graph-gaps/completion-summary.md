# Completion Summary — fix-latency-graph-gaps

**Date**: 2026-03-08  
**Status**: ✅ COMPLETE  
**Plan**: `.sisyphus/plans/fix-latency-graph-gaps.md`  
**Branch**: `fix/latency-graph-gaps`  
**Commits**: 2 atomic commits

---

## Executive Summary

대시보드의 Latency 그래프가 중간중간 끊어지는 문제를 완전히 해결했습니다.

**근본 원인**: vLLM idle 시 `histogram_quantile()` PromQL이 NaN을 반환 → JSON 직렬화 실패 (HTTP 500) → 차트 데이터 갱신 중단

**해결책**: 
1. NaN/Infinity 필터링으로 API 500 방지
2. idle latency를 0 대신 null로 표현
3. Recharts `connectNulls`로 null 구간 선 연결

---

## Deliverables

### Code Changes (2 commits)

**Commit 1**: `fix(metrics): filter NaN/Infinity from Prometheus responses to prevent HTTP 500`
- `backend/services/metrics_collector.py`: `import math` 추가, NaN/Inf 필터링 로직
- `backend/tests/test_metrics_collector.py`: 4개 회귀 테스트 (NaN, +Inf, -Inf, valid)
- `backend/tests/test_metrics.py`: history 엔드포인트 NaN 주입 통합 테스트

**Commit 2**: `fix(dashboard): represent idle latency as null and bridge chart gaps with connectNulls`
- `backend/models/load_test.py`: MetricsSnapshot의 4개 latency 필드를 `Optional[float]`로 변경
- `backend/services/metrics_collector.py`: `get_history_dict`에서 latency 0.0 → None 변환
- `backend/routers/metrics.py`: `_convert_to_snapshot`에 /latest vs /history 불일치 문서화
- `frontend/src/components/Chart.jsx`: `<Line>` 컴포넌트에 `connectNulls={true}` 추가

### Test Results

```
Backend Tests: 45 passed, 0 failures ✅
- All existing tests pass (회귀 없음)
- 4개 NaN 필터링 테스트 추가 및 통과
- 1개 history 엔드포인트 NaN 주입 테스트 추가 및 통과
```

### Verification

✅ NaN/Infinity 필터링 동작 확인
```bash
$ python3 -m pytest tests/test_metrics_collector.py::TestMetricsCollectorNaNFiltering -v
4 passed
```

✅ Optional 직렬화 동작 확인
```bash
$ python3 -c "from models.load_test import MetricsSnapshot; s = MetricsSnapshot(timestamp=1.0, ttft_mean=None); print(s.model_dump_json())"
{"timestamp":1.0,...,"ttft_mean":null,...}
```

✅ connectNulls prop 추가 확인
```bash
$ grep -n "connectNulls" frontend/src/components/Chart.jsx
23:               dot={false} strokeWidth={1.5} name={l.label} connectNulls={true} />
```

---

## Plan Completion

**Total Checkboxes**: 29/29 ✅

| Section | Count | Status |
|---------|-------|--------|
| Definition of Done | 4 | ✅ |
| Task 1 Acceptance Criteria | 5 | ✅ |
| Task 2 Acceptance Criteria | 5 | ✅ |
| Task 3 Acceptance Criteria | 2 | ✅ |
| Main Tasks | 3 | ✅ |
| Final Verification Wave | 4 | ✅ |
| Final Checklist | 6 | ✅ |

---

## Technical Details

### Task 1: NaN/Infinity 필터링

**File**: `backend/services/metrics_collector.py`

```python
# Before
value = float(data["data"]["result"][0]["value"][1])
return metric_name, round(value, 3)

# After
value = float(data["data"]["result"][0]["value"][1])
if math.isnan(value) or math.isinf(value):
    return metric_name, None
return metric_name, round(value, 3)
```

**Why**: Prometheus의 `histogram_quantile()` 쿼리는 idle 시 NaN을 반환. 이를 필터링하지 않으면 JSON 직렬화 실패 (HTTP 500).

### Task 2: Latency Optional + 0→null 변환

**Files**: 
- `backend/models/load_test.py`: MetricsSnapshot 모델
- `backend/services/metrics_collector.py`: get_history_dict 메서드
- `backend/routers/metrics.py`: _convert_to_snapshot 함수

**Key Pattern**: `m.mean_ttft_ms or None`
- 0.0 → None (falsy)
- 500.0 → 500.0 (truthy)

**Why**: idle latency (0ms)는 물리적으로 불가능한 값. null로 표현하면 차트가 의미 있게 렌더링됨.

### Task 3: Recharts connectNulls

**File**: `frontend/src/components/Chart.jsx`

```jsx
<Line key={l.key} type="monotone" dataKey={l.key} stroke={l.color}
  dot={false} strokeWidth={1.5} name={l.label} connectNulls={true} />
```

**Why**: Recharts는 기본적으로 null 데이터 포인트에서 선을 끊음. `connectNulls={true}`를 추가하면 null을 건너뛰고 앞뒤 유효한 포인트를 연결.

---

## Scope Compliance

### Must Have ✅
- [x] NaN과 Infinity 모두 필터링
- [x] NaN 필터링은 `float()` 후, `round()` 전에 위치
- [x] latency 전용 4개 필드만 Optional
- [x] MetricsSnapshot 모델 변경 → get_history_dict 변경 순서 엄수
- [x] 각 수정에 대한 회귀 테스트

### Must NOT Have ✅
- [x] VLLMMetrics dataclass 필드 타입 변경 안 함
- [x] tps, rps, kv_cache 등 비-latency 필드 Optional 안 함
- [x] _convert_to_snapshot 로직 변경 안 함 (코멘트만 추가)
- [x] Chart.jsx에서 <Area>, <Bar> 등 다른 컴포넌트 수정 안 함
- [x] TPS/RPS의 idle 표시 변경 안 함

---

## Evidence

- `.sisyphus/evidence/task-1/nan-filter-test.txt` — NaN 필터링 테스트 결과
- `.sisyphus/evidence/task-1/regression.txt` — 전체 회귀 테스트 결과
- `.sisyphus/evidence/task-3/connect-nulls-grep.txt` — connectNulls prop 확인

---

## Next Steps

이 수정사항은 다음과 같이 배포됩니다:

1. **Branch**: `fix/latency-graph-gaps` (현재 상태)
2. **PR**: main으로 merge 준비 완료
3. **Testing**: 모든 단위 테스트 통과 (45/45)
4. **Deployment**: OpenShift 배포 시 자동 적용

---

## Lessons Learned

1. **NaN 처리**: JSON 직렬화 전에 NaN을 필터링해야 함. `nan is not None` 체크 필수.
2. **Optional 타입**: Pydantic v2에서 float 필드에 None을 넘기려면 `Optional[float]`로 선언 필수.
3. **Falsy 패턴**: Python의 `0.0 or None` → None 패턴은 idle 감지에 유용.
4. **Recharts**: `connectNulls` prop은 null 데이터 포인트 사이의 선 연결을 제어.

---

**Status**: ✅ COMPLETE AND READY FOR MERGE
