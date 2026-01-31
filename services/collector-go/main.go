package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/gocolly/colly/v2"
	"github.com/gocolly/colly/v2/proxy"
	"github.com/redis/go-redis/v9"
)

// CONFIGURATION
var (
	// In Docker, Redis is "redis:6379". On host, it's "localhost:6379"
	redisAddr = "localhost:6379" 
	torProxy  = "socks5://127.0.0.1:9050"
	targetURL = "https://check.torproject.org" 
)

func main() {
	fmt.Println("[*] INTEL-COLLECTOR: Initializing...")

	// 1. CONNECT TO REDIS (The Nervous System)
	rdb := redis.NewClient(&redis.Options{
		Addr: redisAddr,
	})
	
	// Test Redis connection
	if _, err := rdb.Ping(context.Background()).Result(); err != nil {
		log.Fatalf("[-] CRITICAL: Cannot connect to Redis! Is Docker running? Error: %v", err)
	}
	fmt.Println("[+] Redis Connected.")

	// 2. CONFIGURE THE SPIDER (Colly)
	c := colly.NewCollector(
		colly.IgnoreRobotsTxt(), 
	)

	// 3. ATTACH THE TOR MASK
	rp, err := proxy.RoundRobinProxySwitcher(torProxy)
	if err != nil {
		log.Fatal(err)
	}
	c.SetProxyFunc(rp)

	// Set timeouts because Tor is slow
	c.SetRequestTimeout(60 * time.Second)

	// 4. DEFINE THE JOB
	c.OnResponse(func(r *colly.Response) {
		fmt.Printf("[+] CRAWLED: %s (Size: %d bytes)\n", r.Request.URL, len(r.Body))

		// PUSH TO REDIS QUEUE "raw_html"
		err := rdb.LPush(context.Background(), "raw_html", r.Body).Err()
		if err != nil {
			log.Printf("[-] Redis Push Failed: %v", err)
		} else {
			fmt.Println("[+] Data pushed to Queue 'raw_html'")
		}
	})

	c.OnError(func(r *colly.Response, err error) {
		fmt.Println("[-] CRAWL FAILED:", r.Request.URL, err)
	})

	// 5. LAUNCH
	fmt.Println("[*] Connecting to Tor Network...")
	fmt.Printf("[*] Target: %s\n", targetURL)
	
	c.Visit(targetURL)
}