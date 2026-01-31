mod cleaner;
use redis::Commands;
use std::{thread, time};

fn main() -> redis::RedisResult<()> {
    println!("🦀 RUST SANITIZER: Initializing...");

    // 1. Connect to Redis (Use '127.0.0.1' for local dev, 'redis' for Docker)
    // We try localhost first for your current setup
    let client = redis::Client::open("redis://127.0.0.1:6379/")?;
    let mut con = client.get_connection()?;
    println!("[+] Connected to Redis.");

    println!("[*] Waiting for data in queue 'raw_html'...");

    loop {
        // 2. Wait for data (BLPOP blocks until data arrives)
        // This returns a tuple: (queue_name, data)
        let result: Option<(String, String)> = con.blpop("raw_html", 0)?;

        if let Some((_key, raw_html)) = result {
            println!("[!] Received {} bytes. Scrubbing...", raw_html.len());

            // 3. The Heavy Lifting: Sanitize HTML
            let clean_text = cleaner::clean_html(&raw_html);

            // 4. Push to the NEXT queue for Python
            let _: () = con.lpush("sanitized_text", &clean_text)?;
            println!("[+] Data scrubbed & moved to 'sanitized_text'");
        }
    }
}