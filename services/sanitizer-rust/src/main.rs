mod cleaner;
use redis::Commands;

fn main() -> redis::RedisResult<()> {
    println!("🦀 RUST SANITIZER: Initializing...");

    // 1. Connect to Redis
    let client = redis::Client::open("redis://127.0.0.1:6379/")?;
    let mut con = client.get_connection()?;
    println!("[+] Connected to Redis.");

    println!("[*] Waiting for data in queue 'raw_html'...");

    loop {
        // FIX: Changed '0' to '0.0' because Rust requires a float for timeout
        let result: Option<(String, String)> = con.blpop("raw_html", 0.0)?;

        if let Some((_key, raw_html)) = result {
            println!("[!] Received {} bytes. Scrubbing...", raw_html.len());

            // 2. Sanitize HTML
            let clean_text = cleaner::clean_html(&raw_html);

            // 3. Push to 'sanitized_text'
            let _: () = con.lpush("sanitized_text", &clean_text)?;
            println!("[+] Data scrubbed & moved to 'sanitized_text'");
        }
    }
}