FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM alpine:3.22
# Serve with Alpine's nginx package plus a full upgrade. The official
# nginx:alpine image can lag behind Alpine's security repo, leaving fixed CVEs
# (e.g. in the nginx package itself) unpatched; building on alpine + apk gets
# the current patched versions.
RUN apk add --no-cache nginx && apk upgrade --no-cache
COPY nginx.default.conf /etc/nginx/http.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
