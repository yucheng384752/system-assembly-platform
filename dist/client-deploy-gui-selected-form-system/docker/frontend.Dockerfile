FROM node:20-slim AS builder
WORKDIR /app
COPY system/frontend/ .
RUN NPM_CACHE_ARGS=""; \
    if [ -d .npm-cache ]; then NPM_CACHE_ARGS="--cache .npm-cache --offline"; fi; \
    if [ -f package-lock.json ]; then npm ci --silent $NPM_CACHE_ARGS; else npm install --silent $NPM_CACHE_ARGS; fi; \
    npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80