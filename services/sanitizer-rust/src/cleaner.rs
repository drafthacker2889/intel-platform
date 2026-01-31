use std::collections::HashSet;

pub fn clean_html(raw: &str) -> String {
    // Configure Ammonia to allow NO tags (empty list)
    // This strips <div>, <p>, <a> but keeps the text inside them.
    ammonia::Builder::new()
        .tags(HashSet::new()) 
        .clean(raw)
        .to_string()
}