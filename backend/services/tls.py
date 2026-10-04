"""TLS trust policy for the httpx clients.

Closed-network clusters use self-signed certificates everywhere (Thanos, LLMIS workload Services,
the MaaS gateway), so verification is off unless CA_BUNDLE points at a CA file.
"""

import os
import ssl


def tls_verify(ca_bundle: str | None = None) -> ssl.SSLContext | bool:
    bundle = ca_bundle if ca_bundle is not None else os.environ.get("CA_BUNDLE", "")
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    return False
