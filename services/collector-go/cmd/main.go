package main

import (
	"context"
	"fmt"
	"log"
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
	startURL  = "https://www.torproject.org" // Changed to the main site (more links to find)

	// SAFETY: Only crawl these domains.
	// If we don't set this, it will try to crawl the WHOLE internet.
	allowedDomains = []string{"www.torproject.org", "support.torproject.org", "community.torproject.org"}
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
		rdb.LPush(context.Background(), "raw_html", r.Body)
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
