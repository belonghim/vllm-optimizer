# 작업 계획: Mock 데이터 토글 스위치 구현

**버전**: 1.0
**작성자**: Prometheus
**상태**: 준비 완료

## 1. 개요

사용자가 UI의 토글 스위치를 통해 Mock 데이터와 실제 API 데이터를 명시적으로 전환할 수 있는 기능을 구현합니다. 이 기능은 `localStorage`에 상태를 저장하여 브라우저를 새로고침해도 선택이 유지되도록 합니다. 스위치가 꺼져있을 때 API 호출에 실패하면, 기존의 자동 Mock 데이터 전환(fallback) 대신 에러 메시지를 표시합니다.

## 2. 주요 요구사항 및 결정사항

| 항목 | 결정 |
|------|------|
| UI 위치 | 애플리케이션 헤더 우측 상단 |
| 기본 상태 | Mock 데이터 사용 (활성화) |
| 상태 관리 | React Context API |
| 상태 영속성 | `localStorage`에 스위치 상태 저장 |
| 실패 시 동작 | Mock 자동전환(fallback) 안 함. 에러 메시지 표시 |
| 부하 테스트(OFF) | 실제 SSE 스트림 구독 |

## 3. 기술적 맥락

### 현재 Mock 데이터 사용 현황

| 파일 | 사용하는 Mock 함수 |
|------|-------------------|
| `frontend/src/App.jsx` | `mockMetrics`, `mockHistory`, `mockBenchmarks`, `mockTrials`, `simulateLoadTest` (import만 존재) |
| `frontend/src/pages/MonitorPage.jsx` | `mockMetrics`, `mockHistory`, `mockBenchmarks`, `mockTrials`, `simulateLoadTest` |
| `frontend/src/pages/LoadTestPage.jsx` | `simulateLoadTest` |
| `frontend/src/pages/BenchmarkPage.jsx` | `mockBenchmarks` |
| `frontend/src/pages/TunerPage.jsx` | `mockTrials` |

### 기존 디자인 시스템 참조

- **테마**: Industrial / Terminal aesthetic (어두운 배경 + 형광 앰버/시안 강조색)
- **색상 상수**: `COLORS` 객체 (`frontend/src/constants.js`)
- **폰트**: `font` 객체 — JetBrains Mono (코드), Barlow Condensed (헤더)

## 4. 작업 분할 (Tasks)

---

### Task 1: `MockDataContext` 생성 및 전역 적용

**목표**: 'Mock 데이터 사용' 상태(`isMockEnabled`)와 상태 변경 함수(`toggleMockEnabled`)를 전역으로 관리하는 React Context를 설정합니다.

**파일 생성**: `frontend/src/contexts/MockDataContext.jsx`

**구현 상세**:

```jsx
import { createContext, useState, useEffect, useMemo, useContext } from "react";

const STORAGE_KEY = "vllm-opt-mock-enabled";

const MockDataContext = createContext({
  isMockEnabled: true,
  toggleMockEnabled: () => {},
});

export function MockDataProvider({ children }) {
  const [isMockEnabled, setIsMockEnabled] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? true : stored === "true";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(isMockEnabled));
  }, [isMockEnabled]);

  const toggleMockEnabled = () => setIsMockEnabled(prev => !prev);

  const value = useMemo(
    () => ({ isMockEnabled, toggleMockEnabled }),
    [isMockEnabled]
  );

  return (
    <MockDataContext.Provider value={value}>
      {children}
    </MockDataContext.Provider>
  );
}

export function useMockData() {
  return useContext(MockDataContext);
}
```

**파일 수정**: `frontend/src/main.jsx`

- `MockDataProvider`를 임포트하고 `<App />` 컴포넌트를 감싸기:

```jsx
import { MockDataProvider } from "./contexts/MockDataContext";

// render 부분:
<MockDataProvider>
  <App />
</MockDataProvider>
```

**QA 시나리오**:
- `localStorage`에 `vllm-opt-mock-enabled` 키가 `"false"`로 저장된 상태에서 새로고침 → 스위치가 꺼진 상태로 시작되는지 확인
- `localStorage`에 값이 없을 때 새로고침 → 스위치가 켜진 상태(기본값 `true`)로 시작되는지 확인
- `toggleMockEnabled()` 호출 시 상태가 반전되고 `localStorage`도 업데이트되는지 확인

---

### Task 2: `MockDataSwitch` UI 컴포넌트 구현 및 헤더 배치

**목표**: 헤더에 배치될 UI 토글 스위치 컴포넌트를 생성하고 `App.jsx` 헤더에 배치합니다.

**파일 생성**: `frontend/src/components/MockDataSwitch.jsx`

**구현 상세**:

1. `useMockData` 훅으로 `isMockEnabled`와 `toggleMockEnabled`에 접근
2. 기존 프로젝트의 `COLORS`와 `font` 상수를 사용하여 "Industrial / Terminal" 디자인에 맞는 스위치 스타일 적용
3. 웹 접근성: `role="switch"`, `aria-checked={isMockEnabled}`, `aria-label="Mock 데이터 사용 전환"` 추가
4. 스위치 옆에 라벨 텍스트 표시: `"MOCK"` (켜짐일 때 강조, 꺼짐일 때 muted)

**스타일 가이드라인** (기존 디자인 일관성):
- 토글 트랙: `COLORS.surface` 배경, `1px solid ${COLORS.border}` 테두리
- 활성 상태: 트랙 배경 `COLORS.accent` (형광 앰버), 썸(thumb)에 `boxShadow` glow 효과
- 비활성 상태: 트랙 배경 `COLORS.surface`, 썸 색상 `COLORS.muted`
- 라벨 텍스트: `fontSize: 9`, `letterSpacing: "0.1em"`, `textTransform: "uppercase"`, `fontFamily: font.mono`
- 전체 크기: 높이 약 16px, 너비 약 32px (소형 스위치, 헤더 공간에 맞게)

**파일 수정**: `frontend/src/App.jsx`

- `MockDataSwitch` 컴포넌트를 임포트
- 헤더의 "CONNECTED" 상태 표시등 **왼쪽**에 배치 (헤더 우측 영역의 `gap: 12` flex 컨테이너 내부)

```jsx
// 기존 헤더 우측 영역:
<div style={{ display: "flex", alignItems: "center", gap: 12 }}>
  <MockDataSwitch />                {/* ← 추가 */}
  <div style={{ width: 1, height: 16, background: COLORS.border }} />  {/* 구분선 */}
  <div style={{ width: 6, height: 6, borderRadius: "50%", ... }} />
  <span ...>CONNECTED</span>
</div>
```

- `App.jsx`에서 더 이상 사용되지 않는 `mockData` import 제거 (현재 import만 있고 실제 사용은 각 페이지에서 함)

**QA 시나리오**:
- 스위치가 헤더의 올바른 위치(CONNECTED 왼쪽)에 렌더링되는지 확인
- 스위치를 클릭하면 시각적 상태가 변경되는지 확인
- 키보드(Tab → Space/Enter)로 스위치를 조작할 수 있는지 확인
- 개발자 도구 Application > Local Storage에서 `vllm-opt-mock-enabled` 값이 변경되는지 확인

---

### Task 3: `MonitorPage` 데이터 로직 수정

**목표**: `MonitorPage`에서 `isMockEnabled`에 따라 Mock 데이터 또는 실제 API를 사용하도록 분기합니다.

**파일 수정**: `frontend/src/pages/MonitorPage.jsx`

**구현 상세**:

1. `useMockData` 훅을 임포트하여 `isMockEnabled` 상태를 가져옵니다.
2. `useState`로 `error` 상태를 추가합니다.
3. 데이터 페칭 로직을 수정합니다:
   - `isMockEnabled === true`: 기존처럼 `mockMetrics()`, `mockHistory()` 등을 사용
   - `isMockEnabled === false`: 실제 API 엔드포인트(`API` 상수 참조)를 `fetch`로 호출
     - 성공 시: 응답 데이터로 상태 업데이트, `setError(null)`
     - 실패 시: `setError(에러메시지)`, 데이터는 빈 상태로 유지 (Mock 전환 금지)
4. `isMockEnabled` 값이 변경되면 즉시 데이터를 새로 불러오도록 `useEffect`의 dependency에 `isMockEnabled`를 포함합니다.
5. UI에 에러 상태 표시 영역 추가:
   - 에러 발생 시: 붉은 테두리의 박스에 에러 메시지 표시
   - 스타일: `border: 1px solid ${COLORS.red}`, `color: ${COLORS.red}`, 기존 터미널 미학 유지

**QA 시나리오**:
- 스위치 ON → Mock 데이터가 정상 표시
- 스위치 OFF → 네트워크 탭에 실제 API 호출 확인
- 스위치 OFF + API 실패 → 에러 메시지 표시, Mock 데이터 미표시
- 스위치 ON → OFF → ON 전환 시 데이터가 즉시 갱신

---

### Task 4: `BenchmarkPage` 데이터 로직 수정

**목표**: `BenchmarkPage`에서 `isMockEnabled`에 따라 Mock 데이터 또는 실제 API를 사용하도록 분기합니다.

**파일 수정**: `frontend/src/pages/BenchmarkPage.jsx`

**구현 상세**:

1. `useMockData` 훅을 임포트하여 `isMockEnabled` 상태를 가져옵니다.
2. `useState`로 `error` 상태를 추가합니다.
3. 벤치마크 목록 로딩 시:
   - `isMockEnabled === true`: `mockBenchmarks()` 사용
   - `isMockEnabled === false`: `GET /api/benchmarks` API 호출
     - 성공 시: 응답 데이터로 상태 업데이트
     - 실패 시: `setError(에러메시지)`, Mock 전환 금지
4. 에러 UI 표시 (Task 3과 동일한 스타일)

**QA 시나리오**:
- 스위치 ON → Mock 벤치마크 3개 항목 표시
- 스위치 OFF → 실제 API 호출 확인
- 스위치 OFF + API 실패 → 에러 메시지 표시

---

### Task 5: `TunerPage` 데이터 로직 수정

**목표**: `TunerPage`에서 `isMockEnabled`에 따라 Mock 데이터 또는 실제 API를 사용하도록 분기합니다.

**파일 수정**: `frontend/src/pages/TunerPage.jsx`

**구현 상세**:

1. `useMockData` 훅을 임포트하여 `isMockEnabled` 상태를 가져옵니다.
2. `useState`로 `error` 상태를 추가합니다.
3. 튜닝 트라이얼 목록 로딩 시:
   - `isMockEnabled === true`: `mockTrials()` 사용
   - `isMockEnabled === false`: `GET /api/tuner/trials` API 호출
     - 성공 시: 응답 데이터로 상태 업데이트
     - 실패 시: `setError(에러메시지)`, Mock 전환 금지
4. 에러 UI 표시 (Task 3과 동일한 스타일)

**QA 시나리오**:
- 스위치 ON → Mock 트라이얼 12개 항목 표시
- 스위치 OFF → 실제 API 호출 확인
- 스위치 OFF + API 실패 → 에러 메시지 표시

---

### Task 6: `LoadTestPage` 특별 처리 (Mock 시뮬레이션 ↔ 실제 SSE)

**목표**: `LoadTestPage`의 `simulateLoadTest` 함수와 실제 SSE 스트림 구독 로직을 `isMockEnabled` 상태에 따라 분기합니다.

**파일 수정**: `frontend/src/pages/LoadTestPage.jsx`

**구현 상세**:

1. `useMockData` 훅을 임포트하여 `isMockEnabled` 상태를 가져옵니다.
2. `useState`로 `error` 상태를 추가합니다.
3. '부하 테스트 시작' 버튼의 `onClick` 핸들러 로직을 수정합니다:
   - `isMockEnabled === true`: 기존 `simulateLoadTest(config, setProgress, setResult, setStatus, setLatencyData)` 호출
   - `isMockEnabled === false`: 실제 SSE 스트림 구독 로직 실행
     ```javascript
     const eventSource = new EventSource(`/api/load-test/stream?${queryParams}`);
     eventSource.onmessage = (event) => {
       const data = JSON.parse(event.data);
       // data로 progress, result, latencyData 상태 업데이트
     };
     eventSource.onerror = (err) => {
       setError("SSE 연결 실패: 부하 테스트 스트림에 연결할 수 없습니다.");
       setStatus("error");
       eventSource.close();
     };
     ```
4. `useRef`를 사용하여 `EventSource` 인스턴스를 참조에 저장합니다.
5. 컴포넌트 언마운트 시 또는 `isMockEnabled` 변경 시 `EventSource.close()` 호출하여 정리합니다.
6. `isMockEnabled`가 변경되는 시점에 진행 중인 테스트가 있으면:
   - Mock 시뮬레이션 중이면: `clearInterval`로 중단
   - SSE 스트림 중이면: `eventSource.close()`로 중단
   - 상태를 "idle"로 리셋

**QA 시나리오**:
- 스위치 ON → 부하 테스트 시작 시 Mock 시뮬레이션 동작 확인
- 스위치 OFF → 부하 테스트 시작 시 네트워크 탭에 SSE 연결 확인
- 스위치 OFF + SSE 연결 실패 → 에러 메시지 표시
- 테스트 진행 중 스위치 전환 → 진행 중인 테스트가 정리(cleanup)되는지 확인

---

## 5. 최종 검증 (Final Verification Wave)

모든 Task 완료 후 다음을 확인합니다:

1. **빌드 성공**: `npm run build` — 에러 없이 완료되는지 확인
2. **콘솔 클린**: 브라우저 개발자 도구 콘솔에 에러/경고 없음
3. **전체 페이지 순회**: 4개 탭(모니터링, 부하 테스트, 벤치마크, 튜너)을 모두 방문하며 스위치 ON/OFF 테스트
4. **상태 영속성**: 스위치를 OFF로 변경 후 새로고침 → OFF 상태 유지 확인
5. **import 정리**: `App.jsx`에서 불필요한 `mockData` import가 제거되었는지 확인

## 6. 의존성 그래프

```
Task 1 (Context 생성)
  ├── Task 2 (Switch UI + 헤더 배치) ─── depends on Task 1
  ├── Task 3 (MonitorPage) ──────────── depends on Task 1
  ├── Task 4 (BenchmarkPage) ────────── depends on Task 1
  ├── Task 5 (TunerPage) ───────────── depends on Task 1
  └── Task 6 (LoadTestPage) ─────────── depends on Task 1
       └── Final Verification ────────── depends on ALL
```

Task 1 완료 후, Task 2~6은 **병렬 실행 가능**합니다.
