# Stage 1: Builder
FROM node:20-slim AS builder
WORKDIR /build
COPY package*.json ./
 RUN npm install
COPY . .
RUN npm run build

# Stage 2: nginx-unprivileged (OpenShift 준수: non-root, port 8080)
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
LABEL app="vllm-optimizer-frontend" version="1.0.0"
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /build/dist /usr/share/nginx/html
USER 1001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s CMD curl -sf http://localhost:8080/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
