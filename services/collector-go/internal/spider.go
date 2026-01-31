package internal

import (
"strings"
)

// IsInterestingLink filters out useless links (css, js, images)
func IsInterestingLink(link string) bool {
if link == "" {
return false
}
if strings.HasPrefix(link, "javascript:") || strings.HasPrefix(link, "mailto:") {
return false
}
// Add more filters here later (e.g. reject .png, .jpg)
return true
}
