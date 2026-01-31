FROM rust:1.75-alpine as builder
WORKDIR /app
COPY . .
RUN cargo build --release

FROM alpine:latest
COPY --from=builder /app/target/release/sanitizer .
CMD ["./sanitizer"]
