FROM node:20-slim AS builder
WORKDIR /app
COPY system/frontend/ .
RUN npm install --silent && npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80