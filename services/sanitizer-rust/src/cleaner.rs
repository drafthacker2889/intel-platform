use std::collections::HashSet;

pub fn clean_html(raw: &str, min_length: usize) -> Option<String> {
    let cleaned = ammonia::Builder::new()
        .tags(HashSet::new())
        .clean(raw)
        .to_string();

    let trimmed = cleaned.trim().to_string();

    if trimmed.len() < min_length {
        return None;
    }

    Some(trimmed)
}

#[cfg(test)]
mod tests {
    use super::clean_html;

    #[test]
    fn removes_html_tags() {
        let input = "<html><body><h1>Hello</h1><p>world</p></body></html>";
        let out = clean_html(input, 3).expect("expected cleaned text");
        assert!(out.contains("Hello"));
        assert!(!out.contains("<h1>"));
    }

    #[test]
    fn filters_too_short_content() {
        let input = "<p>short</p>";
        assert!(clean_html(input, 10).is_none());
    }
}