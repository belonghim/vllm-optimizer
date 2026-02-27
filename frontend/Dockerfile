# Stage 1: Builder
# Red Hat UBI9 Node.js builder for OpenShift compliance
FROM registry.access.redhat.com/ubi9/nodejs-20 AS builder
WORKDIR /build
COPY package*.json .
# Switch to root for npm install to avoid permission issues with node_modules
USER root
RUN npm install
COPY . /build
RUN npm run build

# Stage 2: nginx-unprivileged (OpenShift 준수: non-root, port 8080)
# Red Hat UBI9 nginx-124 runtime for enterprise support and security
FROM registry.access.redhat.com/ubi9/nginx-124 AS runtime
LABEL app="vllm-optimizer-frontend" version="1.0.0"
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /build/dist /usr/share/nginx/html
# curl is pre-installed in ubi9/nginx-124; no additional packages needed for healthchecks.
USER 1001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s CMD curl -sf http://localhost:8080/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
