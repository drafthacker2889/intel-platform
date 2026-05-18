mod cleaner;
use redis::Commands;
use std::env;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::thread;
use std::time::Duration;

static SANITIZER_PROCESSED_TOTAL:        AtomicU64 = AtomicU64::new(0);
static SANITIZER_DROPPED_TOTAL:          AtomicU64 = AtomicU64::new(0);
static SANITIZER_ERRORS_TOTAL:           AtomicU64 = AtomicU64::new(0);
static SANITIZER_PARSE_FALLBACKS_TOTAL:  AtomicU64 = AtomicU64::new(0);
static SHUTDOWN:                         AtomicBool = AtomicBool::new(false);

// Returns (html, traceparent, source_url, collected_at, is_fallback).
fn parse_raw_packet(raw: &str) -> (String, Option<String>, Option<String>, Option<String>, bool) {
    match serde_json::from_str::<serde_json::Value>(raw) {
        Ok(v) => {
            let html = v
                .get("raw_html")
                .and_then(|x| x.as_str())
                .unwrap_or(raw)
                .to_string();
            let traceparent  = v.get("traceparent").and_then(|x| x.as_str()).map(str::to_owned);
            let source_url   = v.get("source_url").and_then(|x| x.as_str()).map(str::to_owned);
            let collected_at = v.get("collected_at").and_then(|x| x.as_str()).map(str::to_owned);
            (html, traceparent, source_url, collected_at, false)
        }
        Err(_) => (raw.to_string(), None, None, None, true),
    }
}

fn metrics_body() -> String {
    format!(
        "sanitizer_processed_total {}\n\
         sanitizer_dropped_total {}\n\
         sanitizer_errors_total {}\n\
         sanitizer_parse_fallbacks_total {}\n",
        SANITIZER_PROCESSED_TOTAL.load(Ordering::Relaxed),
        SANITIZER_DROPPED_TOTAL.load(Ordering::Relaxed),
        SANITIZER_ERRORS_TOTAL.load(Ordering::Relaxed),
        SANITIZER_PARSE_FALLBACKS_TOTAL.load(Ordering::Relaxed),
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
                let first_line = {
                    let mut reader = BufReader::new(&mut socket);
                    let mut line = String::new();
                    match reader.read_line(&mut line) {
                        Ok(0) | Err(_) => continue,
                        Ok(_) => line,
                    }
                };
                let first_line = first_line.trim_end();

                let (status, content_type, body) = if first_line.starts_with("GET /health") {
                    ("200 OK", "application/json", "{\"status\":\"ok\"}".to_owned())
                } else if first_line.starts_with("GET /metrics") {
                    ("200 OK", "text/plain; version=0.0.4", metrics_body())
                } else {
                    ("404 Not Found", "text/plain", "not found".to_owned())
                };

                let response = format!(
                    "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    status, content_type, body.len(), body,
                );
                if let Err(err) = socket.write_all(response.as_bytes()) {
                    eprintln!("Sanitizer HTTP write error: {}", err);
                }
            }
            Err(err) => {
                eprintln!("Sanitizer HTTP connection error: {}", err);
            }
        }
    }
}

fn main() -> redis::RedisResult<()> {
    let redis_url             = env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379/".to_string());
    let raw_queue             = env::var("RAW_QUEUE_NAME").unwrap_or_else(|_| "raw_html".to_string());
    let raw_dlq_queue         = env::var("RAW_DLQ_QUEUE").unwrap_or_else(|_| "raw_html_dlq".to_string());
    let sanitized_queue       = env::var("SANITIZED_QUEUE_NAME").unwrap_or_else(|_| "sanitized_text".to_string());
    let sanitized_dlq_queue   = env::var("SANITIZED_DLQ_QUEUE").unwrap_or_else(|_| "sanitized_text_dlq".to_string());
    let health_port           = env::var("HEALTH_PORT").unwrap_or_else(|_| "8083".to_string());
    let min_text_len          = env::var("MIN_TEXT_LEN")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(50);

    ctrlc::set_handler(|| {
        eprintln!("Sanitizer received shutdown signal, draining queue…");
        SHUTDOWN.store(true, Ordering::Relaxed);
    })
    .expect("Failed to set SIGTERM/SIGINT handler");

    println!("RUST SANITIZER starting");

    let server_port = health_port.clone();
    thread::spawn(move || run_http_server(&server_port));

    let client = redis::Client::open(redis_url.clone())?;
    let mut con = client.get_connection()?;
    println!("Connected to Redis");
    println!("Waiting for data in queue '{}'", raw_queue);

    while !SHUTDOWN.load(Ordering::Relaxed) {
        // 1-second BLPOP timeout allows the shutdown flag to be checked each iteration.
        let result: Option<(String, String)> = match con.blpop(&raw_queue, 1.0) {
            Ok(value) => value,
            Err(err) => {
                SANITIZER_ERRORS_TOTAL.fetch_add(1, Ordering::Relaxed);
                eprintln!("Redis BLPOP error: {}. Reconnecting in 5s…", err);
                thread::sleep(Duration::from_secs(5));
                match client.get_connection() {
                    Ok(new_con) => {
                        con = new_con;
                        println!("Redis reconnected successfully");
                    }
                    Err(reconnect_err) => {
                        eprintln!("Redis reconnect failed: {}", reconnect_err);
                    }
                }
                continue;
            }
        };

        if let Some((_key, raw_html)) = result {
            println!("Received {} bytes", raw_html.len());

            let (packet_html, traceparent, source_url, collected_at, parse_fallback) =
                parse_raw_packet(&raw_html);

            if parse_fallback {
                SANITIZER_PARSE_FALLBACKS_TOTAL.fetch_add(1, Ordering::Relaxed);
            }

            if packet_html.trim().is_empty() {
                let dlq_payload = serde_json::json!({
                    "error": "empty_raw_html",
                    "raw_payload": raw_html,
                })
                .to_string();
                if let Err(dlq_err) = con.lpush::<_, _, ()>(&raw_dlq_queue, &dlq_payload) {
                    eprintln!("CRITICAL: empty-payload DLQ push failed: {}", dlq_err);
                }
                SANITIZER_DROPPED_TOTAL.fetch_add(1, Ordering::Relaxed);
                continue;
            }

            if let Some(clean_text) = cleaner::clean_html(&packet_html, min_text_len) {
                let payload = serde_json::json!({
                    "text":         clean_text,
                    "length":       packet_html.len(),
                    "source_url":   source_url,
                    "traceparent":  traceparent,
                    "collected_at": collected_at,
                })
                .to_string();

                match con.lpush::<_, _, ()>(&sanitized_queue, &payload) {
                    Ok(_) => {
                        SANITIZER_PROCESSED_TOTAL.fetch_add(1, Ordering::Relaxed);
                        println!("Sanitized payload pushed to '{}'", sanitized_queue);
                    }
                    Err(err) => {
                        SANITIZER_ERRORS_TOTAL.fetch_add(1, Ordering::Relaxed);
                        eprintln!("Redis LPUSH error: {}", err);
                        let dlq_payload = serde_json::json!({
                            "error":        err.to_string(),
                            "raw_payload":  raw_html,
                            "failed_queue": sanitized_queue,
                        })
                        .to_string();
                        if let Err(dlq_err) = con.lpush::<_, _, ()>(&sanitized_dlq_queue, &dlq_payload) {
                            eprintln!("CRITICAL: sanitized DLQ push failed: {}", dlq_err);
                        }
                    }
                }
            } else {
                SANITIZER_DROPPED_TOTAL.fetch_add(1, Ordering::Relaxed);
                println!("Dropped payload: below minimum length guard ({} chars)", min_text_len);
            }
        }
    }

    println!("Sanitizer shutdown complete");
    Ok(())
}
