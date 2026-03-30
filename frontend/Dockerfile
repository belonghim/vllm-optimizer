# Stage 1: Builder
# Red Hat UBI9 Node.js builder for OpenShift compliance
FROM registry.access.redhat.com/ubi9/nodejs-20 AS builder
WORKDIR /build
COPY package*.json . bun.lockb* .npmrc* .yarnrc* 2>/dev/null || true
# Switch to root for npm install to avoid permission issues with node_modules
USER root
RUN npm install
COPY . /build
RUN npm run build

# Stage 2: Runtime
FROM registry.access.redhat.com/ubi9/nginx-124 AS runtime
LABEL app="vllm-optimizer-frontend" version="1.0.0"
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /build/dist /usr/share/nginx/html
USER 1001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s CMD curl -sf http://localhost:8080/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
