package main

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"strings"
	"time"

	"github.com/gocolly/colly/v2"
	"github.com/gocolly/colly/v2/proxy"
	"github.com/redis/go-redis/v9"
)

// CONFIGURATION
var (
	redisAddr = "localhost:6379"
	torProxy  = "socks5://127.0.0.1:9050"
	startURL  = "https://www.torproject.org"

	// SAFETY: Only crawl these domains to prevent it from trying to crawl the WHOLE internet.
	allowedDomains = []string{"www.torproject.org", "support.torproject.org", "community.torproject.org"}

	// LIST OF FAKE BROWSERS (Stealth Mode)
	userAgents = []string{
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
		"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
	}
)

func main() {
	fmt.Println("[*] TIER 2 SPIDER: Recursive Mode Initializing...")

	// 1. Redis Connection
	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})
	if _, err := rdb.Ping(context.Background()).Result(); err != nil {
		log.Fatalf("[-] Redis Dead: %v", err)
	}
	fmt.Println("[+] Redis Connected.")

	// 2. Configure Recursive Spider
	c := colly.NewCollector(
		colly.IgnoreRobotsTxt(),
		colly.AllowedDomains(allowedDomains...),
		colly.Async(true), // Enable multi-threading
	)

	// 3. Politeness (Don't get banned)
	c.Limit(&colly.LimitRule{
		DomainGlob:  "*",
		Parallelism: 2,               // Run 2 scrapers at once
		RandomDelay: 2 * time.Second, // Wait 2s between requests
	})

	// --- STEALTH MODE ---
	// Rotate User-Agent for every request to look like a real human
	c.OnRequest(func(r *colly.Request) {
		agent := userAgents[rand.Intn(len(userAgents))]
		r.Headers.Set("User-Agent", agent)
		// fmt.Printf("[*] Visiting with Agent: %s\n", agent) // Optional: debug agent selection
	})

	// 4. Attach Tor
	rp, err := proxy.RoundRobinProxySwitcher(torProxy)
	if err != nil {
		log.Fatal(err)
	}
	c.SetProxyFunc(rp)
	c.SetRequestTimeout(60 * time.Second)

	// 5. RECURSIVE LOGIC: Find Links
	c.OnHTML("a[href]", func(e *colly.HTMLElement) {
		link := e.Attr("href")
		// Make link absolute (e.g., /about -> https://torproject.org/about)
		absLink := e.Request.AbsoluteURL(link)

		// If it's a valid http link, VISIT IT
		if strings.HasPrefix(absLink, "http") {
			e.Request.Visit(absLink)
		}
	})

	// 6. ON RESPONSE: Push Data
	c.OnResponse(func(r *colly.Response) {
		fmt.Printf("[+] VISITED: %s (%d bytes)\n", r.Request.URL, len(r.Body))

		// Push to Redis
		err := rdb.LPush(context.Background(), "raw_html", r.Body).Err()
		if err != nil {
			fmt.Printf("[-] Redis LPush Error: %v\n", err)
		}
	})

	c.OnError(func(r *colly.Response, err error) {
		fmt.Println("[-] ERROR:", r.Request.URL, err)
	})

	// 7. Start
	fmt.Println("[*] Seeding crawler with:", startURL)
	c.Visit(startURL)
	c.Wait() // Keep running until all links are exhausted
	fmt.Println("[*] Crawl finished.")
}
