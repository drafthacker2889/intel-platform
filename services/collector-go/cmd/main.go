package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	mrand "math/rand"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"crawler/internal"

	"github.com/gocolly/colly/v2"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
)

var pagesVisitedTotal atomic.Int64
var queuePushErrorsTotal atomic.Int64
var crawlErrorsTotal atomic.Int64
var dlqPushTotal atomic.Int64

var userAgents = []string{
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
}

func envOrDefault(name, fallback string) string {
	v := os.Getenv(name)
	if strings.TrimSpace(v) == "" {
		return fallback
	}
	return v
}

func parseDomains(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		trimmed := strings.TrimSpace(p)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func generateTraceparent() string {
	traceID := make([]byte, 16)
	spanID := make([]byte, 8)
	if _, err := rand.Read(traceID); err != nil {
		return "00-00000000000000000000000000000000-0000000000000000-01"
	}
	if _, err := rand.Read(spanID); err != nil {
		return "00-00000000000000000000000000000000-0000000000000000-01"
	}
	return fmt.Sprintf("00-%s-%s-01", hex.EncodeToString(traceID), hex.EncodeToString(spanID))
}

func traceparentFromSpanContext(spanContext trace.SpanContext) string {
	if !spanContext.IsValid() {
		return generateTraceparent()
	}
	flags := "00"
	if spanContext.TraceFlags().IsSampled() {
		flags = "01"
	}
	return fmt.Sprintf("00-%s-%s-%s", spanContext.TraceID().String(), spanContext.SpanID().String(), flags)
}

func initTracerProvider(ctx context.Context, serviceName string) (*sdktrace.TracerProvider, error) {
	endpoint := strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
	if endpoint == "" {
		return nil, nil
	}

	exporter, err := otlptracegrpc.New(
		ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(
		ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String(serviceName),
		),
	)
	if err != nil {
		return nil, err
	}

	provider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(provider)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	return provider, nil
}

func runHealthServer(port string, maxPages int) {
	handler := http.NewServeMux()
	handler.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"status":"ok"}`)
	})
	handler.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		_, _ = fmt.Fprintf(
			w,
			"collector_pages_visited_total %d\ncollector_queue_push_errors_total %d\ncollector_crawl_errors_total %d\ncollector_dlq_push_total %d\ncollector_max_pages %d\n",
			pagesVisitedTotal.Load(),
			queuePushErrorsTotal.Load(),
			crawlErrorsTotal.Load(),
			dlqPushTotal.Load(),
			maxPages,
		)
	})
	_ = http.ListenAndServe(":"+port, handler)
}

func main() {
	redisAddr := envOrDefault("REDIS_ADDR", "localhost:6379")
	torProxy := envOrDefault("TOR_PROXY", "socks5://127.0.0.1:9050")
	otelServiceName := envOrDefault("OTEL_SERVICE_NAME", "collector-go")
	startURL := envOrDefault("START_URL", "https://www.torproject.org")
	rawQueueName := envOrDefault("RAW_QUEUE_NAME", "raw_html")
	rawDLQName := envOrDefault("RAW_DLQ_QUEUE", "raw_html_dlq")
	healthPort := envOrDefault("HEALTH_PORT", "8081")
	allowedDomains := parseDomains(envOrDefault("ALLOWED_DOMAINS", "www.torproject.org,support.torproject.org,community.torproject.org"))

	maxPages := 300
	if s := strings.TrimSpace(os.Getenv("MAX_PAGES")); s != "" {
		if parsed, err := strconv.Atoi(s); err == nil && parsed > 0 {
			maxPages = parsed
		}
	}

	go runHealthServer(healthPort, maxPages)
	fmt.Println("Collector starting")

	provider, tracerErr := initTracerProvider(context.Background(), otelServiceName)
	if tracerErr != nil {
		fmt.Printf("Collector tracer init failed: %v\n", tracerErr)
	} else if provider != nil {
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = provider.Shutdown(shutdownCtx)
		}()
	}
	tracer := otel.Tracer("collector-go")

	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})
	if _, err := rdb.Ping(context.Background()).Result(); err != nil {
		log.Fatalf("Redis unavailable: %v", err)
	}
	fmt.Println("Redis connected")

	c := colly.NewCollector(
		colly.IgnoreRobotsTxt(),
		colly.AllowedDomains(allowedDomains...),
		colly.Async(true),
	)

	c.Limit(&colly.LimitRule{
		DomainGlob:  "*",
		Parallelism: 2,
		RandomDelay: 2 * time.Second,
	})

	c.OnRequest(func(r *colly.Request) {
		agent := userAgents[mrand.Intn(len(userAgents))]
		r.Headers.Set("User-Agent", agent)
		r.Headers.Set("Accept-Language", "en-US,en;q=0.9")
	})

	internal.SetupTorProxy(c, torProxy)
	c.SetRequestTimeout(60 * time.Second)

	var visitedCount int64

	c.OnHTML("a[href]", func(e *colly.HTMLElement) {
		link := e.Attr("href")
		if !internal.IsInterestingLink(link) {
			return
		}

		absLink := e.Request.AbsoluteURL(link)
		if atomic.LoadInt64(&visitedCount) >= int64(maxPages) {
			return
		}

		if strings.HasPrefix(absLink, "http") {
			_ = e.Request.Visit(absLink)
		}
	})

	c.OnResponse(func(r *colly.Response) {
		spanCtx, span := tracer.Start(context.Background(), "collector.process_response")
		defer span.End()
		span.SetAttributes(
			attribute.String("source.url", r.Request.URL.String()),
			attribute.Int("payload.bytes", len(r.Body)),
		)

		current := atomic.AddInt64(&visitedCount, 1)
		pagesVisitedTotal.Store(current)
		fmt.Printf("VISITED %d/%d %s (%d bytes)\n", current, maxPages, r.Request.URL, len(r.Body))

		if current > int64(maxPages) {
			return
		}

		payload := map[string]string{
			"raw_html":     string(r.Body),
			"source_url":   r.Request.URL.String(),
			"collected_at": time.Now().UTC().Format(time.RFC3339Nano),
			"traceparent":  traceparentFromSpanContext(span.SpanContext()),
		}
		serializedPayload, err := json.Marshal(payload)
		if err != nil {
			queuePushErrorsTotal.Add(1)
			span.RecordError(err)
			span.SetStatus(codes.Error, "collector payload marshal failed")
			fmt.Printf("Collector payload marshal error: %v\n", err)
			return
		}

		err = rdb.LPush(spanCtx, rawQueueName, serializedPayload).Err()
		if err != nil {
			queuePushErrorsTotal.Add(1)
			span.RecordError(err)
			span.SetStatus(codes.Error, "redis lpush failed")
			fmt.Printf("Redis LPush error: %v\n", err)
			dlqPayload := map[string]string{
				"error":       err.Error(),
				"raw_payload": string(serializedPayload),
				"failed_at":   time.Now().UTC().Format(time.RFC3339Nano),
			}
			marshaledDLQ, marshalErr := json.Marshal(dlqPayload)
			if marshalErr == nil {
				if pushErr := rdb.LPush(context.Background(), rawDLQName, marshaledDLQ).Err(); pushErr == nil {
					dlqPushTotal.Add(1)
				}
			}
		}
	})

	c.OnError(func(r *colly.Response, err error) {
		crawlErrorsTotal.Add(1)
		_, span := tracer.Start(context.Background(), "collector.request_error")
		span.RecordError(err)
		span.SetStatus(codes.Error, "collector request failed")
		if r != nil && r.Request != nil {
			span.SetAttributes(attribute.String("source.url", r.Request.URL.String()))
		}
		span.End()
		if r != nil && r.Request != nil {
			fmt.Println("ERROR", r.Request.URL, err)
			return
		}
		fmt.Println("ERROR", err)
	})

	fmt.Println("Seeding crawler with", startURL)
	if err := c.Visit(startURL); err != nil {
		log.Fatalf("could not start crawler: %v", err)
	}
	c.Wait()
	fmt.Println("Crawl finished")
}
