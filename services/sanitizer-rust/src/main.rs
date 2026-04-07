mod cleaner;
use redis::Commands;
use std::env;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;

static SANITIZER_PROCESSED_TOTAL: AtomicU64 = AtomicU64::new(0);
static SANITIZER_DROPPED_TOTAL: AtomicU64 = AtomicU64::new(0);
static SANITIZER_ERRORS_TOTAL: AtomicU64 = AtomicU64::new(0);
static SANITIZER_PARSE_FALLBACKS_TOTAL: AtomicU64 = AtomicU64::new(0);

fn parse_raw_packet(raw: &str) -> (String, Option<String>, Option<String>, bool) {
    match serde_json::from_str::<serde_json::Value>(raw) {
        Ok(v) => {
            let html = v
                .get("raw_html")
                .and_then(|x| x.as_str())
                .unwrap_or(raw)
                .to_string();
            let traceparent = v
                .get("traceparent")
                .and_then(|x| x.as_str())
                .map(|s| s.to_string());
            let source_url = v
                .get("source_url")
                .and_then(|x| x.as_str())
                .map(|s| s.to_string());
            (html, traceparent, source_url, false)
        }
        Err(_) => (raw.to_string(), None, None, true),
    }
}

fn metrics_body() -> String {
    format!(
        "sanitizer_processed_total {}\nsanitizer_dropped_total {}\nsanitizer_errors_total {}\nsanitizer_parse_fallbacks_total {}\n",
        SANITIZER_PROCESSED_TOTAL.load(Ordering::Relaxed),
        SANITIZER_DROPPED_TOTAL.load(Ordering::Relaxed),
        SANITIZER_ERRORS_TOTAL.load(Ordering::Relaxed),
        SANITIZER_PARSE_FALLBACKS_TOTAL.load(Ordering::Relaxed)
    )
}

fn run_http_server(port: &str) {
    let bind_addr = format!("0.0.0.0:{}", port);
    let listener = match TcpListener::bind(&bind_addr) {
        Ok(l) => l,
        Err(err) => {
            eprintln!("Failed to bind sanitizer HTTP server on {}: {}", bind_addr, err);
            return;
        }
    };

    for stream in listener.incoming() {
        match stream {
            Ok(mut socket) => {
                let mut buffer = [0_u8; 2048];
                let read_size = match socket.read(&mut buffer) {
                    Ok(n) => n,
                    Err(_) => continue,
                };

                let request = String::from_utf8_lossy(&buffer[..read_size]);
                let first_line = request.lines().next().unwrap_or_default();

                if first_line.starts_with("GET /health") {
                    let body = "{\"status\":\"ok\"}";
                    let response = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    );
                    let _ = socket.write_all(response.as_bytes());
                    continue;
                }

                if first_line.starts_with("GET /metrics") {
                    let body = metrics_body();
                    let response = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: text/plain; version=0.0.4\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    );
                    let _ = socket.write_all(response.as_bytes());
                    continue;
                }

                let body = "not found";
                let response = format!(
                    "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = socket.write_all(response.as_bytes());
            }
            Err(err) => {
                eprintln!("Sanitizer HTTP connection error: {}", err);
            }
        }
    }
}

fn main() -> redis::RedisResult<()> {
    let redis_url = env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379/".to_string());
    let raw_queue = env::var("RAW_QUEUE_NAME").unwrap_or_else(|_| "raw_html".to_string());
    let raw_dlq_queue = env::var("RAW_DLQ_QUEUE").unwrap_or_else(|_| "raw_html_dlq".to_string());
    let sanitized_queue = env::var("SANITIZED_QUEUE_NAME").unwrap_or_else(|_| "sanitized_text".to_string());
    let sanitized_dlq_queue =
        env::var("SANITIZED_DLQ_QUEUE").unwrap_or_else(|_| "sanitized_text_dlq".to_string());
    let health_port = env::var("HEALTH_PORT").unwrap_or_else(|_| "8083".to_string());
    let min_text_len = env::var("MIN_TEXT_LEN")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(50);

    println!("RUST SANITIZER starting");

    let server_port = health_port.clone();
    thread::spawn(move || run_http_server(&server_port));

    let client = redis::Client::open(redis_url)?;
    let mut con = client.get_connection()?;
    println!("Connected to Redis");

    println!("Waiting for data in queue '{}'", raw_queue);

    loop {
        let result: Option<(String, String)> = match con.blpop(&raw_queue, 0.0) {
            Ok(value) => value,
            Err(err) => {
                SANITIZER_ERRORS_TOTAL.fetch_add(1, Ordering::Relaxed);
                eprintln!("Redis BLPOP error: {}", err);
                continue;
            }
        };

        if let Some((_key, raw_html)) = result {
            println!("Received {} bytes", raw_html.len());

            let (packet_html, traceparent, source_url, parse_fallback) = parse_raw_packet(&raw_html);
            if parse_fallback {
                SANITIZER_PARSE_FALLBACKS_TOTAL.fetch_add(1, Ordering::Relaxed);
            }

            if packet_html.trim().is_empty() {
                let dlq_payload = serde_json::json!({
                    "error": "empty_raw_html",
                    "raw_payload": raw_html,
                })
                .to_string();
                let _ = con.lpush::<_, _, ()>(&raw_dlq_queue, dlq_payload);
                SANITIZER_DROPPED_TOTAL.fetch_add(1, Ordering::Relaxed);
                continue;
            }

            if let Some(clean_text) = cleaner::clean_html(&packet_html, min_text_len) {
                let payload = serde_json::json!({
                    "text": clean_text,
                    "length": packet_html.len(),
                    "source_url": source_url,
                    "traceparent": traceparent,
                })
                .to_string();
                match con.lpush::<_, _, ()>(&sanitized_queue, payload) {
                    Ok(_) => {
                        SANITIZER_PROCESSED_TOTAL.fetch_add(1, Ordering::Relaxed);
                        println!("Sanitized payload pushed to '{}'", sanitized_queue);
                    }
                    Err(err) => {
                        SANITIZER_ERRORS_TOTAL.fetch_add(1, Ordering::Relaxed);
                        eprintln!("Redis LPUSH error: {}", err);
                        let dlq_payload = serde_json::json!({
                            "error": err.to_string(),
                            "raw_payload": raw_html,
                            "failed_queue": sanitized_queue,
                        })
                        .to_string();
                        let _ = con.lpush::<_, _, ()>(&sanitized_dlq_queue, dlq_payload);
                    }
                }
            } else {
                SANITIZER_DROPPED_TOTAL.fetch_add(1, Ordering::Relaxed);
                println!("Dropped payload due to minimum length guard");
            }
        }
    }
}