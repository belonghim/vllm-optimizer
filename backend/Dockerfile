# Stage 1: Builder
FROM registry.access.redhat.com/ubi9/python-311 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
USER root

# Stage 2: Runtime
# OpenShift SCC restricted-v2 준수:
#   USER 1001, PORT 8000, g+rwX for arbitrary UID
FROM registry.access.redhat.com/ubi9/python-311 AS runtime
LABEL app="vllm-optimizer-backend" version="1.0.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PORT=8000 PATH="/usr/local/bin:$PATH"
WORKDIR /app
USER root
# curl is pre-installed in ubi9/python-311; no additional packages needed for healthchecks.
COPY --from=builder /usr/local /usr/local
COPY . /app
RUN chown -R 1001:0 /app && chmod -R g+rwX /app
USER 1001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3     CMD curl -f http://localhost:8000/health || exit 1
CMD uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
