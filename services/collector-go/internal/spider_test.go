package internal

import "testing"

func TestIsInterestingLink(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want bool
	}{
		{name: "empty", in: "", want: false},
		{name: "mailto", in: "mailto:test@example.com", want: false},
		{name: "javascript", in: "javascript:void(0)", want: false},
		{name: "image", in: "https://example.org/file.png", want: false},
		{name: "html", in: "https://example.org/page", want: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := IsInterestingLink(tt.in)
			if got != tt.want {
				t.Fatalf("IsInterestingLink(%q) = %v, want %v", tt.in, got, tt.want)
			}
		})
	}
}
