FROM golang:1.25-alpine AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/crawler ./cmd/main.go

FROM alpine:3.22
RUN apk upgrade --no-cache
RUN addgroup -S appgroup && adduser -S -u 1000 -G appgroup appuser
WORKDIR /app
COPY --from=builder /out/crawler ./crawler
RUN chown appuser:appgroup ./crawler

USER appuser
EXPOSE 8081
CMD ["./crawler"]
