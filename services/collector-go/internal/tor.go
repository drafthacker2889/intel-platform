package internal

import (
"log"
"github.com/gocolly/colly/v2"
"github.com/gocolly/colly/v2/proxy"
)

// SetupTorProxy forces the collector to route traffic through the SOCKS5 proxy
func SetupTorProxy(c *colly.Collector, proxyAddr string) {
rp, err := proxy.RoundRobinProxySwitcher(proxyAddr)
if err != nil {
log.Fatalf("[-] FATAL: Could not connect to Tor Proxy at %s: %v", proxyAddr, err)
}
c.SetProxyFunc(rp)
}
