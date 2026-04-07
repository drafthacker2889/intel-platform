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
	blockedSuffixes := []string{".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".svg", ".woff", ".woff2"}
	lower := strings.ToLower(link)
	for _, suffix := range blockedSuffixes {
		if strings.Contains(lower, suffix) {
			return false
		}
	}
	return true
}
