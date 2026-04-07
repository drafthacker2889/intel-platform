FROM golang:1.22-alpine AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/crawler ./cmd/main.go

FROM alpine:3.20
WORKDIR /app
COPY --from=builder /out/crawler ./crawler

EXPOSE 8081
CMD ["./crawler"]
