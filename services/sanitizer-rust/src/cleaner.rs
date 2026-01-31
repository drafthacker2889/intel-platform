use std::collections::HashSet;

pub fn clean_html(raw: &str) -> Option<String> {
    // 1. Strip ALL tags
    let cleaned = ammonia::Builder::new()
        .tags(HashSet::new()) 
        .clean(raw)
        .to_string();

    // 2. Trim whitespace (remove big gaps)
    let trimmed = cleaned.trim().to_string();

    // 3. JUNK FILTER: If it's less than 50 chars, ignore it.
    // This removes buttons, footers, and "Login" links.
    if trimmed.len() < 50 {
        return None;
    }

    Some(trimmed)
}