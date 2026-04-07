import json
import importlib
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import redis
import spacy
from elasticsearch import Elasticsearch

OTEL_AVAILABLE = False

class _NoopSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def set_attribute(self, *_args, **_kwargs):
        return None

    def record_exception(self, *_args, **_kwargs):
        return None

    def set_status(self, *_args, **_kwargs):
        return None

class _NoopTracer:
    def start_as_current_span(self, *_args, **_kwargs):
        return _NoopSpan()

class _NoopPropagator:
    @staticmethod
    def extract(carrier):
        return None

class _NoopStatus:
    def __init__(self, *_args, **_kwargs):
        pass

class _NoopStatusCode:
    ERROR = "ERROR"

TraceContextTextMapPropagator = _NoopPropagator
Status = _NoopStatus
StatusCode = _NoopStatusCode


REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")
ELASTIC_INDEX = os.getenv("ELASTIC_INDEX", "intel-data-v3")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "v1")
MODEL_VERSION = os.getenv("MODEL_VERSION", "risk-rules-v2")
SANITIZED_QUEUE_NAME = os.getenv("SANITIZED_QUEUE_NAME", "sanitized_text")
SANITIZED_DLQ_QUEUE = os.getenv("SANITIZED_DLQ_QUEUE", "sanitized_text_dlq")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8082"))

RISK_KEYWORDS = [
    "password",
    "admin",
    "login",
    "secret",
    "confidential",
    "leaked",
    "db_pass",
    "key",
]

RISK_MODEL_PATH = os.getenv("RISK_MODEL_PATH", "")
SCORING_STRATEGY = os.getenv("SCORING_STRATEGY", "auto")

HEALTH_STATE = {
    "status": "starting",
    "processed": 0,
    "index_failures": 0,
    "packet_parse_fallbacks": 0,
    "dlq_push_total": 0,
    "schema_version": SCHEMA_VERSION,
    "model_version": MODEL_VERSION,
    "scoring_strategy": "rules",
}

_NLP_MODEL = None
_TRACER = _NoopTracer()
_RISK_MODEL = None


def _load_risk_model():
    """Try to load a trained sklearn model from RISK_MODEL_PATH."""
    global _RISK_MODEL
    path = RISK_MODEL_PATH
    if not path:
        return None
    try:
        joblib = importlib.import_module("joblib")
        _RISK_MODEL = joblib.load(path)
        print(f"Loaded ML risk model from {path}")
        return _RISK_MODEL
    except Exception as exc:
        print(f"ML model load failed ({exc}), falling back to rules")
        return None


def setup_tracing():
    global _TRACER

    try:
        trace = importlib.import_module("opentelemetry.trace")
        OTLPSpanExporter = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
        ).OTLPSpanExporter
        Resource = importlib.import_module("opentelemetry.sdk.resources").Resource
        TracerProvider = importlib.import_module("opentelemetry.sdk.trace").TracerProvider
        BatchSpanProcessor = importlib.import_module(
            "opentelemetry.sdk.trace.export"
        ).BatchSpanProcessor
        _TraceContextTextMapPropagator = importlib.import_module(
            "opentelemetry.trace.propagation.tracecontext"
        ).TraceContextTextMapPropagator
        _Status = importlib.import_module("opentelemetry.trace.status").Status
        _StatusCode = importlib.import_module("opentelemetry.trace.status").StatusCode
    except ImportError:
        _TRACER = _NoopTracer()
        return

    global OTEL_AVAILABLE
    global TraceContextTextMapPropagator
    global Status
    global StatusCode

    OTEL_AVAILABLE = True
    TraceContextTextMapPropagator = _TraceContextTextMapPropagator
    Status = _Status
    StatusCode = _StatusCode

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    service_name = os.getenv("OTEL_SERVICE_NAME", "brain-python")

    if not endpoint:
        _TRACER = trace.get_tracer(service_name)
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)


def get_nlp_model():
    global _NLP_MODEL
    if _NLP_MODEL is not None:
        return _NLP_MODEL

    try:
        _NLP_MODEL = spacy.load("en_core_web_sm")
    except OSError:
        _NLP_MODEL = spacy.blank("en")
    return _NLP_MODEL


def connect_to_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def connect_to_elastic():
    return Elasticsearch(ELASTIC_HOST, request_timeout=60)


def concrete_index_name(alias, schema_version):
    return f"{alias}-{schema_version}"


def index_mapping(schema_version, model_version):
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "content": {"type": "text"},
                "entities": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "keyword"},
                        "type": {"type": "keyword"},
                    },
                },
                "entity_count": {"type": "integer"},
                "risk_score": {"type": "integer"},
                "risk_label": {"type": "keyword"},
                "traceparent": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "schema_version": {"type": "keyword"},
                "model_version": {"type": "keyword"},
                "timestamp": {"type": "date"},
            },
            "_meta": {
                "schema_version": schema_version,
                "model_version": model_version,
            },
        },
    }


def ensure_index(es_client, alias, schema_version, model_version):
    concrete_name = concrete_index_name(alias, schema_version)

    if not es_client.indices.exists(index=concrete_name):
        es_client.indices.create(
            index=concrete_name,
            mappings=index_mapping(schema_version, model_version)["mappings"],
            settings=index_mapping(schema_version, model_version)["settings"],
        )

    alias_exists = es_client.indices.exists_alias(name=alias)
    if not alias_exists:
        es_client.indices.put_alias(index=concrete_name, name=alias)
        return concrete_name

    alias_state = es_client.indices.get_alias(name=alias)
    if concrete_name not in alias_state:
        actions = []
        for index_name in alias_state:
            actions.append({"remove": {"index": index_name, "alias": alias}})
        actions.append({"add": {"index": concrete_name, "alias": alias}})
        es_client.indices.update_aliases(actions={"actions": actions})

    return concrete_name


def extract_entities(text):
    nlp = get_nlp_model()
    doc = nlp(text[:100000])
    entities = []
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE"]:
            entities.append({"text": ent.text, "type": ent.label_})
    return entities


def calculate_risk(text, entities):
    score = 0
    text_lower = text.lower()

    for word in RISK_KEYWORDS:
        if word in text_lower:
            score += 10

    score += len(entities) * 5

    if score >= 50:
        label = "CRITICAL"
    elif score >= 20:
        label = "HIGH"
    elif score > 0:
        label = "MEDIUM"
    else:
        label = "LOW"

    return score, label


def _featurize(text, entities):
    """Build numeric feature vector for ML model."""
    text_lower = text.lower()
    keyword_hits = sum(1 for w in RISK_KEYWORDS if w in text_lower)
    return [
        keyword_hits,
        len(entities),
        len(text),
        text_lower.count("http"),
        text_lower.count("@"),
    ]


LABEL_TO_SCORE = {"LOW": 0, "MEDIUM": 10, "HIGH": 30, "CRITICAL": 60}


def calculate_risk_ml(text, entities):
    """Score using trained sklearn model."""
    features = _featurize(text, entities)
    try:
        np = importlib.import_module("numpy")
        label = _RISK_MODEL.predict(np.array([features]))[0]
        return LABEL_TO_SCORE.get(label, 0), label
    except Exception:
        return calculate_risk(text, entities)


def score_risk(text, entities):
    """Unified risk scoring entry point respecting SCORING_STRATEGY."""
    if SCORING_STRATEGY == "rules":
        return calculate_risk(text, entities)
    if SCORING_STRATEGY == "ml" and _RISK_MODEL is not None:
        return calculate_risk_ml(text, entities)
    # auto: prefer ML if available, else rules
    if _RISK_MODEL is not None:
        return calculate_risk_ml(text, entities)
    return calculate_risk(text, entities)


def parse_packet(raw_payload):
    try:
        parsed = json.loads(raw_payload)
        return parsed.get("text") or raw_payload
    except json.JSONDecodeError:
        return raw_payload


def parse_packet_with_meta(raw_payload):
    try:
        parsed = json.loads(raw_payload)
        return {
            "text": parsed.get("text") or raw_payload,
            "traceparent": parsed.get("traceparent"),
            "source_url": parsed.get("source_url"),
            "fallback": False,
        }
    except json.JSONDecodeError:
        return {
            "text": raw_payload,
            "traceparent": None,
            "source_url": None,
            "fallback": True,
        }


def build_metrics_payload():
    return (
        f"brain_processed_total {HEALTH_STATE['processed']}\n"
        f"brain_index_failures_total {HEALTH_STATE['index_failures']}\n"
        f"brain_packet_parse_fallbacks_total {HEALTH_STATE['packet_parse_fallbacks']}\n"
        f"brain_dlq_push_total {HEALTH_STATE['dlq_push_total']}\n"
    )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            payload = json.dumps(HEALTH_STATE).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if self.path == "/metrics":
            payload = build_metrics_payload().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return


def run_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    server.serve_forever()


def main():
    print("INTEL-BRAIN starting")
    setup_tracing()
    _load_risk_model()
    if _RISK_MODEL is not None:
        HEALTH_STATE["scoring_strategy"] = "ml" if SCORING_STRATEGY != "rules" else "rules"
    else:
        HEALTH_STATE["scoring_strategy"] = "rules"
    threading.Thread(target=run_health_server, daemon=True).start()

    r = connect_to_redis()
    es = connect_to_elastic()
    get_nlp_model()

    concrete_index = ensure_index(es, ELASTIC_INDEX, SCHEMA_VERSION, MODEL_VERSION)

    HEALTH_STATE["status"] = "ready"
    print(
        f"Waiting for data in queue '{SANITIZED_QUEUE_NAME}' using index '{concrete_index}'"
    )

    while True:
        packet = r.blpop(SANITIZED_QUEUE_NAME, timeout=0)
        if not packet:
            continue

        parsed = parse_packet_with_meta(packet[1])
        clean_text = parsed["text"]

        parent_context = None
        if parsed["traceparent"]:
            parent_context = TraceContextTextMapPropagator().extract(
                carrier={"traceparent": parsed["traceparent"]}
            )

        with _TRACER.start_as_current_span(
            "brain.process_packet", context=parent_context
        ) as span:
            span.set_attribute("queue.name", SANITIZED_QUEUE_NAME)
            span.set_attribute("packet.length", len(clean_text))
            span.set_attribute("packet.fallback", parsed["fallback"])

            if parsed["source_url"]:
                span.set_attribute("source.url", parsed["source_url"])

            if parsed["fallback"]:
                HEALTH_STATE["packet_parse_fallbacks"] += 1

            entities = extract_entities(clean_text)
            risk_score, risk_label = score_risk(clean_text, entities)

            doc = {
                "content": clean_text[:5000],
                "entities": entities,
                "entity_count": len(entities),
                "risk_score": risk_score,
                "risk_label": risk_label,
                "traceparent": parsed["traceparent"],
                "source_url": parsed["source_url"],
                "schema_version": SCHEMA_VERSION,
                "model_version": MODEL_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            span.set_attribute("risk.score", risk_score)
            span.set_attribute("risk.label", risk_label)

            try:
                es.index(index=ELASTIC_INDEX, document=doc)
                HEALTH_STATE["processed"] += 1
            except Exception as exc:
                HEALTH_STATE["index_failures"] += 1
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, "elasticsearch index failed"))
                print(f"Indexing failed: {exc}")
                dlq_doc = {
                    "error": str(exc),
                    "payload": packet[1],
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "traceparent": parsed["traceparent"],
                    "source_url": parsed["source_url"],
                }
                try:
                    r.lpush(SANITIZED_DLQ_QUEUE, json.dumps(dlq_doc))
                    HEALTH_STATE["dlq_push_total"] += 1
                except Exception as push_exc:
                    span.record_exception(push_exc)
                    print(f"DLQ push failed: {push_exc}")


if __name__ == "__main__":
    main()