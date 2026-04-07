FROM rust:1.79-alpine AS builder
WORKDIR /app

COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM alpine:3.20
WORKDIR /app
COPY --from=builder /app/target/release/sanitizer ./sanitizer

CMD ["./sanitizer"]
