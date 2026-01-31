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
        let result: Option<(String, String)> = con.blpop("raw_html", 0.0)?;

        if let Some((_key, raw_html)) = result {
            println!("[!] Received {} bytes...", raw_html.len());

            // 2. Clean and Check for Junk
            if let Some(clean_text) = cleaner::clean_html(&raw_html) {
                // 3. Push ONLY if it's good data
                let _: () = con.lpush("sanitized_text", &clean_text)?;
                println!("[+] Valid Data ({} chars) -> Moved to 'sanitized_text'", clean_text.len());
            } else {
                // 4. Drop the junk
                println!("[-] Dropped junk data (Too short/Empty).");
            }
        }
    }
}