FROM rust:1.79-alpine AS builder
WORKDIR /app

COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM alpine:3.20
RUN addgroup -S appgroup && adduser -S -u 1000 -G appgroup appuser
WORKDIR /app
COPY --from=builder /app/target/release/sanitizer ./sanitizer
RUN chown appuser:appgroup ./sanitizer

USER appuser
EXPOSE 8083
CMD ["./sanitizer"]
