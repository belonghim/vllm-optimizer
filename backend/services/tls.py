"""TLS trust policy for the httpx clients.

Internal (in-cluster) traffic tolerates self-signed certificates unless CA_BUNDLE is set.
External (inference) traffic trusts public CAs plus the OpenShift service-serving CA, because
in-cluster HTTPS targets such as LLMIS workload Services are signed by that service CA.
"""

import os
import ssl

import certifi

SERVICE_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt"


def internal_verify(ca_bundle: str | None = None) -> ssl.SSLContext | bool:
    bundle = ca_bundle if ca_bundle is not None else os.environ.get("CA_BUNDLE", "")
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    return False


def external_verify(ca_bundle: str | None = None, service_ca_path: str = SERVICE_CA_PATH) -> ssl.SSLContext:
    bundle = ca_bundle if ca_bundle is not None else os.environ.get("CA_BUNDLE", "")
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    ctx = ssl.create_default_context(cafile=certifi.where())
    if os.path.exists(service_ca_path):
        ctx.load_verify_locations(service_ca_path)
    return ctx
