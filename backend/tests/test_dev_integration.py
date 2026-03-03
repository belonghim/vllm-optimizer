import os
import ssl
import time
import urllib.request
from urllib.error import URLError, HTTPError

def test_dev_integration_metrics_endpoint():
    # Dev integration 테스트는 선택적이며 DEV_INTEGRATION_ENABLED로 게이트합니다.
    if os.environ.get("DEV_INTEGRATION_ENABLED") != "1":
        return

    host = os.environ.get("DEV_METRICS_HOST", "localhost")
    port = int(os.environ.get("DEV_METRICS_PORT", "8000"))
    use_tls = os.environ.get("DEV_METRICS_USE_TLS", "0") == "1"
    scheme = "https" if use_tls else "http"
    url = f"{scheme}://{host}:{port}/metrics"

    ctx = None
    if use_tls:
        ctx = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
            status = resp.getcode()
            content_type = resp.headers.get('Content-Type', '')
            content = resp.read().decode('utf-8')
    except (URLError, HTTPError):
        return

    assert status == 200
    assert content_type.startswith("text/plain")

    lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    metric_names = set()
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if name.startswith("vllm:"):
            metric_names.add(name)
    # 최소 2개 이상의 vllm: 메트릭이 존재해야 함
    assert len(metric_names) >= 2, f"Expected at least 2 vllm: metrics, got {sorted(metric_names)}"

    # 각 메트릭에 최소 하나의 샘플 값이 존재하는지 확인
    def _has_numeric_value(l: str) -> bool:
        parts = l.split()
        if len(parts) < 2:
            return False
        try:
            float(parts[-1])
            return True
        except ValueError:
            return False

    has_value = any(_has_numeric_value(l) for l in lines if l.startswith("vllm:"))
    assert has_value, "No numeric sample values found for vllm: metrics"

def test_dev_integration_metrics_format_headers():
    if os.environ.get("DEV_INTEGRATION_ENABLED") != "1":
        return
    host = os.environ.get("DEV_METRICS_HOST", "localhost")
    port = int(os.environ.get("DEV_METRICS_PORT", "8000"))
    use_tls = os.environ.get("DEV_METRICS_USE_TLS", "0") == "1"
    scheme = "https" if use_tls else "http"
    url = f"{scheme}://{host}:{port}/metrics"
    ctx = None
    if use_tls:
        import ssl
        ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
            content = resp.read().decode('utf-8')
    except (URLError, HTTPError):
        return
    lines = content.splitlines()
    help_lines = [ln for ln in lines if ln.startswith("# HELP ")]
    type_lines = [ln for ln in lines if ln.startswith("# TYPE ")]
    assert any(line.startswith("# HELP vllm:") for line in help_lines), "Missing # HELP header for vllm: metrics"
    assert any(line.startswith("# TYPE vllm:") for line in type_lines), "Missing # TYPE for vllm: metrics"

def test_dev_integration_metrics_endpoint_multihost():
    if os.environ.get("DEV_INTEGRATION_ENABLED") != "1":
        return
    hosts_env = os.environ.get("DEV_METRICS_HOSTS", "")
    if not hosts_env:
        return
    hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]
    port = int(os.environ.get("DEV_METRICS_PORT", "8000"))
    use_tls = os.environ.get("DEV_METRICS_USE_TLS", "0") == "1"
    scheme = "https" if use_tls else "http"
    ctx = None
    if use_tls:
        import ssl
        ctx = ssl._create_unverified_context()
        for host in hosts:
            url = f"{scheme}://{host}:{port}/metrics"
            result = _fetch_metrics_with_retries(url, retries=2, delay=1, ctx=ctx)
            if result is None:
                continue
            status, content_type, content = result
            if status != 200:
                continue
            assert content_type.startswith("text/plain")
            lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
            assert any(line.split()[0].startswith("vllm:") for line in lines)

def test_dev_integration_metrics_endpoint_multihost_parallel():
    if os.environ.get("DEV_INTEGRATION_ENABLED") != "1":
        return
    hosts_env = os.environ.get("DEV_METRICS_HOSTS", "")
    if not hosts_env:
        return
    hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]
    port = int(os.environ.get("DEV_METRICS_PORT", "8000"))
    use_tls = os.environ.get("DEV_METRICS_USE_TLS", "0") == "1"
    scheme = "https" if use_tls else "http"
    ctx = None
    if use_tls:
        ctx = ssl._create_unverified_context()
    import concurrent.futures
    def fetch(host):
        url = f"{scheme}://{host}:{port}/metrics"
        r = _fetch_metrics_with_retries(url, retries=2, delay=1, ctx=ctx)
        return r is not None and r[0] == 200
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(hosts))) as executor:
        futures = [executor.submit(fetch, h) for h in hosts]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    assert any(results), f"No successful metrics fetch from any host in {hosts}"

def test_dev_integration_smoke_http_metrics_endpoint():
    # Simple smoke test for default dev/dev-host setup
    if os.environ.get("DEV_INTEGRATION_ENABLED") != "1":
        return
    host = os.environ.get("DEV_METRICS_HOST", "localhost")
    port = int(os.environ.get("DEV_METRICS_PORT", "8000"))
    url = f"http://{host}:{port}/metrics"
    result = _fetch_metrics_with_retries(url, retries=2, delay=1, ctx=None)
    if result is None:
        return
    status, content_type, content = result
    if status != 200:
        return
    if not content_type.startswith("text/plain"):
        return
    lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    assert any(line.split()[0].startswith("vllm:") for line in lines)

def _fetch_metrics_with_retries(url, retries=3, delay=2, ctx=None):
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
                status = resp.getcode()
                content_type = resp.headers.get('Content-Type', '')
                content = resp.read().decode('utf-8')
                return status, content_type, content
        except (URLError, HTTPError):
            if attempt < retries:
                time.sleep(delay)
                continue
            else:
                return None
    return None

def test_dev_integration_metrics_endpoint_with_retries():
    if os.environ.get("DEV_INTEGRATION_ENABLED") != "1":
        return
    host = os.environ.get("DEV_METRICS_HOST", "localhost")
    port = int(os.environ.get("DEV_METRICS_PORT", "8000"))
    use_tls = os.environ.get("DEV_METRICS_USE_TLS", "0") == "1"
    scheme = "https" if use_tls else "http"
    url = f"{scheme}://{host}:{port}/metrics"
    ctx = None
    if use_tls:
        ctx = ssl._create_unverified_context()

    result = _fetch_metrics_with_retries(url, retries=3, delay=2, ctx=ctx)
    if result is None:
        return
    status, content_type, content = result
    assert status == 200
    assert content_type.startswith("text/plain")
    lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    metric_names = {ln.split()[0] for ln in lines}
    assert any(name.startswith("vllm:") for name in metric_names)
