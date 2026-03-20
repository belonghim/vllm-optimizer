import yaml
from pathlib import Path


def test_service_monitor_path_and_backend_port():
    base_dir = Path(__file__).resolve().parents[2]
    monitoring_yaml = base_dir / 'openshift' / 'base' / '05-monitoring.yaml'
    backend_yaml = base_dir / 'openshift' / 'base' / '03-backend.yaml'

    with monitoring_yaml.open() as f:
        docs = list(yaml.safe_load_all(f))
    monitor_data = docs[0] if docs else {}

    with backend_yaml.open() as f:
        docs2 = list(yaml.safe_load_all(f))
    backend_data = next(
        (doc for doc in docs2 if doc.get('kind') == 'Deployment'),
        {}
    )

    endpoints = []
    if isinstance(monitor_data.get('spec', {}), dict):
        endpoints = monitor_data['spec'].get('endpoints', [])
    if endpoints:
        path = endpoints[0].get('path')
        assert path == '/api/metrics'

    service = backend_data.get('spec', {}).get('template', {}).get('spec', {})
    found_http = False
    for c in service.get('containers', []):
        for p in c.get('ports', []):
            if p.get('name') == 'http':
                found_http = True
    assert found_http
