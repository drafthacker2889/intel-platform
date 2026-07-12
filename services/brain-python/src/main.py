import hashlib
import importlib
import json
import logging
import os
import signal
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np
import redis
import spacy
from elasticsearch import Elasticsearch
from featurize import RISK_KEYWORDS, featurize as _featurize_shared

if TYPE_CHECKING:
    from language_pipeline import LanguageModelRouter as LanguageModelRouterType
    from language_pipeline import LanguagePipeline as LanguagePipelineType
    from multilingual_nlp import MultilingualNLPManager as MultilingualNLPManagerType
    from neo4j_manager import Neo4jGraphManager as Neo4jGraphManagerType

Neo4jGraphManagerClass: Any = None
MultilingualNLPManagerClass: Any = None
LanguageModelRouterClass: Any = None
LanguagePipelineClass: Any = None

try:
    from neo4j_manager import Neo4jGraphManager as Neo4jGraphManagerClass
except ImportError:
    pass

try:
    from multilingual_nlp import MultilingualNLPManager as MultilingualNLPManagerClass
except ImportError:
    pass

try:
    from language_pipeline import LanguageModelRouter as LanguageModelRouterClass
    from language_pipeline import LanguagePipeline as LanguagePipelineClass
except ImportError:
    pass

# The IOC/risk analysis core is published as the standalone `osintlens` package
# (extracted from this service). We consume it here to enrich indexed documents
# with structured indicators. Optional import so the service still starts if the
# library is absent.
osintlens_extract_iocs: Any = None
try:
    from osintlens import extract_iocs as osintlens_extract_iocs
except ImportError:
    pass

# ── Structured JSON logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("brain")

# ── OTEL no-op stubs (replaced when opentelemetry packages are present) ────────
class _NoopSpan:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def set_attribute(self, *_): return None
    def record_exception(self, *_): return None
    def set_status(self, *_): return None

class _NoopTracer:
    def start_as_current_span(self, *_): return _NoopSpan()

class _NoopPropagator:
    @staticmethod
    def extract(*_): return None

class _NoopStatus:
    def __init__(self, *_): pass

class _NoopStatusCode:
    ERROR = "ERROR"

TraceContextTextMapPropagator = _NoopPropagator
Status = _NoopStatus
StatusCode = _NoopStatusCode

# ── Configuration ──────────────────────────────────────────────────────────────
REDIS_HOST             = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT             = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD         = os.getenv("REDIS_PASSWORD") or None
ELASTIC_HOST           = os.getenv("ELASTIC_HOST", "http://localhost:9200")
ELASTIC_INDEX          = os.getenv("ELASTIC_INDEX", "intel-data-v3")
NEO4J_URI              = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER             = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD         = os.getenv("NEO4J_PASSWORD", "")
SCHEMA_VERSION         = os.getenv("SCHEMA_VERSION", "v1")
MODEL_VERSION          = os.getenv("MODEL_VERSION", "risk-rules-v2")
SANITIZED_QUEUE_NAME   = os.getenv("SANITIZED_QUEUE_NAME", "sanitized_text")
SANITIZED_DLQ_QUEUE    = os.getenv("SANITIZED_DLQ_QUEUE", "sanitized_text_dlq")
HEALTH_PORT            = int(os.getenv("HEALTH_PORT", "8082"))
RISK_MODEL_PATH        = os.getenv("RISK_MODEL_PATH", "")
SCORING_STRATEGY       = os.getenv("SCORING_STRATEGY", "auto")

# ── Named constants (no magic numbers) ────────────────────────────────────────
MAX_NLP_TEXT_LENGTH    = 100_000   # chars fed to spaCy NLP
MAX_INDEXED_TEXT_LENGTH = 5_000   # chars stored in Elasticsearch
ES_INDEX_SHARDS        = 1
ES_INDEX_REPLICAS      = 1        # at least 1 replica for HA
ES_REQUEST_TIMEOUT     = 30       # seconds
MAX_ES_RETRIES         = 5
ES_RETRY_BASE_DELAY    = 0.5      # seconds; doubles each attempt
BLPOP_TIMEOUT          = 5        # seconds; allows graceful shutdown

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

_NLP_MODEL   = None
_TRACER      = _NoopTracer()
_RISK_MODEL  = None
_shutdown    = threading.Event()
_health_lock = threading.Lock()


# ── Graceful shutdown ──────────────────────────────────────────────────────────
def _handle_signal(*_):
    logger.info('"Received shutdown signal, draining queue…"')
    _shutdown.set()

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# ── ML model loading ───────────────────────────────────────────────────────────
def _load_risk_model():
    global _RISK_MODEL
    path = RISK_MODEL_PATH
    if not path:
        return None
    try:
        joblib = importlib.import_module("joblib")
        _RISK_MODEL = joblib.load(path)
        logger.info('"Loaded ML risk model from %s"', path)
        return _RISK_MODEL
    except Exception as exc:
        if SCORING_STRATEGY == "ml":
            raise RuntimeError(
                f"SCORING_STRATEGY=ml but model failed to load from '{path}': {exc}"
            ) from exc
        logger.warning('"ML model load failed (%s), falling back to rules"', exc)
        return None


# ── OpenTelemetry setup ────────────────────────────────────────────────────────
def setup_tracing():
    global _TRACER, TraceContextTextMapPropagator, Status, StatusCode

    try:
        trace            = importlib.import_module("opentelemetry.trace")
        OTLPSpanExporter = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
        ).OTLPSpanExporter
        Resource         = importlib.import_module("opentelemetry.sdk.resources").Resource
        TracerProvider   = importlib.import_module("opentelemetry.sdk.trace").TracerProvider
        BatchSpanProcessor = importlib.import_module(
            "opentelemetry.sdk.trace.export"
        ).BatchSpanProcessor
        _TCP = importlib.import_module(
            "opentelemetry.trace.propagation.tracecontext"
        ).TraceContextTextMapPropagator
        _Status     = importlib.import_module("opentelemetry.trace.status").Status
        _StatusCode = importlib.import_module("opentelemetry.trace.status").StatusCode
    except ImportError:
        return

    TraceContextTextMapPropagator = _TCP
    Status     = _Status
    StatusCode = _StatusCode

    endpoint     = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    service_name = os.getenv("OTEL_SERVICE_NAME", "brain-python")

    if not endpoint:
        _TRACER = trace.get_tracer(service_name)
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    # Use TLS when available; fall back to insecure only if endpoint is plaintext http://
    insecure = endpoint.startswith("http://")
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)


# ── NLP ────────────────────────────────────────────────────────────────────────
def get_nlp_model():
    global _NLP_MODEL
    if _NLP_MODEL is not None:
        return _NLP_MODEL
    try:
        _NLP_MODEL = spacy.load("en_core_web_sm")
    except OSError:
        _NLP_MODEL = spacy.blank("en")
    return _NLP_MODEL


# ── Datastores ─────────────────────────────────────────────────────────────────
def connect_to_redis():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
        retry_on_timeout=True,
    )


def connect_to_elastic():
    return Elasticsearch(
        ELASTIC_HOST,
        request_timeout=ES_REQUEST_TIMEOUT,
        retry_on_timeout=True,
        max_retries=3,
    )


# ── Index management ───────────────────────────────────────────────────────────
def concrete_index_name(alias, schema_version):
    return f"{alias}-{schema_version}"


def index_mapping(schema_version, model_version):
    return {
        "settings": {
            "number_of_shards":   ES_INDEX_SHARDS,
            "number_of_replicas": ES_INDEX_REPLICAS,
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "content":              {"type": "text"},
                "entities": {
                    "type": "nested",
                    "dynamic": True,
                    "properties": {
                        "text":     {"type": "keyword"},
                        "type":     {"type": "keyword"},
                        "language": {"type": "keyword"},
                    },
                },
                "entity_count":         {"type": "integer"},
                "risk_score":           {"type": "float"},
                "risk_label":           {"type": "keyword"},
                "language_code":        {"type": "keyword"},
                "language_name":        {"type": "keyword"},
                "language_confidence":  {"type": "float"},
                "content_hash":         {"type": "keyword"},
                "traceparent":          {"type": "keyword"},
                "source_url":           {"type": "keyword"},
                "collected_at":         {"type": "date"},
                "schema_version":       {"type": "keyword"},
                "model_version":        {"type": "keyword"},
                "timestamp":            {"type": "date"},
            },
            "_meta": {
                "schema_version": schema_version,
                "model_version":  model_version,
            },
        },
    }


def ensure_index(es_client, alias, schema_version, model_version):
    concrete_name = concrete_index_name(alias, schema_version)

    if not es_client.indices.exists(index=concrete_name):
        mapping = index_mapping(schema_version, model_version)
        es_client.indices.create(
            index=concrete_name,
            mappings=mapping["mappings"],
            settings=mapping["settings"],
        )

    if not es_client.indices.exists_alias(name=alias):
        es_client.indices.put_alias(index=concrete_name, name=alias)
        return concrete_name

    alias_state = es_client.indices.get_alias(name=alias)
    if concrete_name not in alias_state:
        actions = [{"remove": {"index": idx, "alias": alias}} for idx in alias_state]
        actions.append({"add": {"index": concrete_name, "alias": alias}})
        es_client.indices.update_aliases(actions={"actions": actions})

    return concrete_name


# ── NLP / scoring ──────────────────────────────────────────────────────────────
def extract_entities(text):
    """Extract entities using multilingual NLP if available, else fallback to English."""
    global _multilingual_nlp
    
    # Use multilingual NLP if available
    if _multilingual_nlp:
        return _multilingual_nlp.extract_entities(text)
    
    # Fallback to English spaCy model
    nlp = get_nlp_model()
    doc = nlp(text[:MAX_NLP_TEXT_LENGTH])
    return [
        {"text": ent.text, "type": ent.label_}
        for ent in doc.ents
        if ent.label_ in {"PERSON", "ORG", "GPE"}
    ]


def get_language_info(text):
    """Get language detection info for a document."""
    global _multilingual_nlp
    
    if _multilingual_nlp:
        return _multilingual_nlp.get_language_info(text)
    
    return {
        "language_code": "en",
        "language_name": "English",
        "detection_confidence": 0.0,
        "supported": True,
    }


def calculate_risk(text, entities, lang_code="en"):
    """Calculate risk with language-specific model routing if available."""
    global _language_router, _language_pipeline
    
    # Try language-specific routing first
    if _language_pipeline:
        try:
            features = np.array(_featurize(text, entities))
            result = _language_pipeline.process_document(text, lang_code, features)
            return result["risk_score"], result["risk_label"]
        except Exception as e:
            logger.warning('Language pipeline failed: %s, falling back to rules', e)
    
    # Fallback to rule-based scoring
    text_lower = text.lower()
    keyword_hits = sum(1 for w in RISK_KEYWORDS if w in text_lower)
    score = keyword_hits * 10 + len(entities) * 5

    # Escalate authentication-related exposure without making any single
    # sensitive keyword immediately high risk.
    auth_context_terms = ("login", "credential", "credentials", "auth")
    if keyword_hits > 0 and any(term in text_lower for term in auth_context_terms):
        score += 10
    if keyword_hits >= 4:
        score += 10
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
    return _featurize_shared(text, entities)


LABEL_TO_SCORE = {"LOW": 0, "MEDIUM": 10, "HIGH": 30, "CRITICAL": 60}


def calculate_risk_ml(text, entities):
    features = _featurize(text, entities)
    try:
        np    = importlib.import_module("numpy")
        label = _RISK_MODEL.predict(np.array([features]))[0]
        return LABEL_TO_SCORE.get(label, 0), label
    except Exception:
        return calculate_risk(text, entities)


def score_risk(text, entities):
    if SCORING_STRATEGY == "rules":
        return calculate_risk(text, entities)
    if SCORING_STRATEGY == "ml" and _RISK_MODEL is not None:
        return calculate_risk_ml(text, entities)
    if _RISK_MODEL is not None:
        return calculate_risk_ml(text, entities)
    return calculate_risk(text, entities)


# ── Packet parsing ─────────────────────────────────────────────────────────────
def parse_packet_with_meta(raw_payload):
    try:
        parsed = json.loads(raw_payload)
        return {
            "text":         parsed.get("text") or raw_payload,
            "traceparent":  parsed.get("traceparent"),
            "source_url":   parsed.get("source_url"),
            "collected_at": parsed.get("collected_at"),
            "fallback":     False,
        }
    except json.JSONDecodeError:
        return {
            "text":         raw_payload,
            "traceparent":  None,
            "source_url":   None,
            "collected_at": None,
            "fallback":     True,
        }


# ── Health / metrics HTTP server ───────────────────────────────────────────────
def build_metrics_payload():
    with _health_lock:
        return (
            f"brain_processed_total {HEALTH_STATE['processed']}\n"
            f"brain_index_failures_total {HEALTH_STATE['index_failures']}\n"
            f"brain_packet_parse_fallbacks_total {HEALTH_STATE['packet_parse_fallbacks']}\n"
            f"brain_dlq_push_total {HEALTH_STATE['dlq_push_total']}\n"
        )


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if self.path != "/health":
            super().log_message(fmt, *args)

    def do_GET(self):
        if self.path == "/health":
            with _health_lock:
                payload = json.dumps(HEALTH_STATE).encode()
            self._write(200, "application/json", payload)
        elif self.path == "/metrics":
            payload = build_metrics_payload().encode()
            self._write(200, "text/plain; version=0.0.4", payload)
        else:
            self.send_response(404)
            self.end_headers()

    def _write(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    server.serve_forever()


# ── Global Neo4j manager ──────────────────────────────────────────────────────
_neo4j_manager: Any = None

# ── Global Multilingual NLP manager ────────────────────────────────────────────
_multilingual_nlp: Any = None

# ── Global Language Model Router ────────────────────────────────────────────────
_language_router: Any = None
_language_pipeline: Any = None

# ── Elasticsearch indexing with exponential backoff ────────────────────────────
def index_with_retry(es, r, doc, raw_packet, parsed, span, neo4j_mgr=None):
    for attempt in range(MAX_ES_RETRIES):
        try:
            # Index to Elasticsearch
            es.index(index=ELASTIC_INDEX, document=doc)
            with _health_lock:
                HEALTH_STATE["processed"] += 1
            
            # Ingest entities to Neo4j if available
            if neo4j_mgr and "entities" in doc:
                doc_id = str(uuid.uuid4())
                neo4j_mgr.ingest_document(
                    doc_id,
                    doc["entities"],
                    doc.get("source_url", ""),
                    doc.get("risk_label", "LOW"),
                )
            return
        except Exception as exc:
            if attempt < MAX_ES_RETRIES - 1:
                delay = ES_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    '"ES index attempt %d/%d failed (%s), retrying in %.1fs"',
                    attempt + 1, MAX_ES_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                with _health_lock:
                    HEALTH_STATE["index_failures"] += 1
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, "elasticsearch index failed"))
                logger.error('"Indexing failed after %d attempts: %s"', MAX_ES_RETRIES, exc)
                dlq_doc = {
                    "error":       str(exc),
                    "payload":     raw_packet,
                    "failed_at":   datetime.now(timezone.utc).isoformat(),
                    "traceparent": parsed.get("traceparent"),
                    "source_url":  parsed.get("source_url"),
                }
                try:
                    r.lpush(SANITIZED_DLQ_QUEUE, json.dumps(dlq_doc))
                    with _health_lock:
                        HEALTH_STATE["dlq_push_total"] += 1
                except Exception as push_exc:
                    span.record_exception(push_exc)
                    logger.error('"DLQ push failed: %s"', push_exc)


# ── Main processing loop ───────────────────────────────────────────────────────
def main():
    logger.info('"INTEL-BRAIN starting"')
    setup_tracing()
    _load_risk_model()

    with _health_lock:
        if _RISK_MODEL is not None:
            HEALTH_STATE["scoring_strategy"] = "ml" if SCORING_STRATEGY != "rules" else "rules"
        else:
            HEALTH_STATE["scoring_strategy"] = "rules"

    threading.Thread(target=run_health_server, daemon=True).start()

    r  = connect_to_redis()
    es = connect_to_elastic()
    get_nlp_model()
    
    # Initialize Neo4j graph manager if available
    global _neo4j_manager
    if Neo4jGraphManagerClass is not None:
        try:
            _neo4j_manager = Neo4jGraphManagerClass(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, logger)
        except Exception as e:
            logger.warning('"Neo4j initialization failed: %s"', e)
            _neo4j_manager = None
    
    # Initialize Multilingual NLP manager if available
    global _multilingual_nlp
    if MultilingualNLPManagerClass is not None:
        try:
            _multilingual_nlp = MultilingualNLPManagerClass(logger)
            logger.info('"Multilingual NLP manager initialized"')
        except Exception as e:
            logger.warning('"Multilingual NLP initialization failed: %s"', e)
            _multilingual_nlp = None
    
    # Initialize Language-Specific Model Router if available
    global _language_router, _language_pipeline
    if LanguageModelRouterClass is not None and LanguagePipelineClass is not None:
        try:
            model_path = Path(os.getenv("RISK_MODEL_PATH", "/app/models")).parent
            _language_router = LanguageModelRouterClass(model_path, logger)
            _language_pipeline = LanguagePipelineClass(_language_router, logger)
            logger.info('"Language model router initialized"')
        except Exception as e:
            logger.warning('"Language model router initialization failed: %s"', e)
            _language_router = None
            _language_pipeline = None

    concrete_index = ensure_index(es, ELASTIC_INDEX, SCHEMA_VERSION, MODEL_VERSION)
    with _health_lock:
        HEALTH_STATE["status"] = "ready"
    logger.info(
        '"Waiting for data in queue \'%s\' using index \'%s\'"',
        SANITIZED_QUEUE_NAME, concrete_index,
    )

    while not _shutdown.is_set():
        # Use a finite timeout so the loop checks _shutdown periodically.
        try:
            packet = r.blpop(SANITIZED_QUEUE_NAME, timeout=BLPOP_TIMEOUT)
        except redis.ConnectionError:
            logger.warning('"Redis connection lost, reconnecting in 5s"')
            time.sleep(5)
            try:
                r = connect_to_redis()
                logger.info('"Redis reconnected"')
            except Exception as reconnect_exc:
                logger.error('"Redis reconnect failed: %s"', reconnect_exc)
            continue
        except Exception as exc:
            logger.error('"Unexpected error during blpop: %s"', exc)
            time.sleep(1)
            continue

        if not packet:
            continue

        raw_packet = packet[1]
        parsed     = parse_packet_with_meta(raw_packet)
        clean_text = parsed["text"]

        parent_context = None
        if parsed["traceparent"]:
            parent_context = TraceContextTextMapPropagator().extract(
                carrier={"traceparent": parsed["traceparent"]}
            )

        with _TRACER.start_as_current_span(
            "brain.process_packet", context=parent_context
        ) as span:
            span.set_attribute("queue.name",      SANITIZED_QUEUE_NAME)
            span.set_attribute("packet.length",   len(clean_text))
            span.set_attribute("packet.fallback", parsed["fallback"])
            if parsed["source_url"]:
                span.set_attribute("source.url", parsed["source_url"])

            if parsed["fallback"]:
                with _health_lock:
                    HEALTH_STATE["packet_parse_fallbacks"] += 1

            lang_info              = get_language_info(clean_text)
            entities               = extract_entities(clean_text)
            risk_score, risk_label = calculate_risk(clean_text, entities, lang_info["language_code"])
            content_hash           = hashlib.sha256(clean_text.encode("utf-8", errors="replace")).hexdigest()

            doc = {
                "content":              clean_text[:MAX_INDEXED_TEXT_LENGTH],
                "entities":             entities,
                "entity_count":         len(entities),
                "risk_score":           risk_score,
                "risk_label":           risk_label,
                "language_code":        lang_info["language_code"],
                "language_name":        lang_info["language_name"],
                "language_confidence":  lang_info["detection_confidence"],
                "content_hash":         content_hash,
                "traceparent":          parsed["traceparent"],
                "source_url":           parsed["source_url"],
                "collected_at":         parsed["collected_at"],
                "schema_version":       SCHEMA_VERSION,
                "model_version":        MODEL_VERSION,
                "timestamp":            datetime.now(timezone.utc).isoformat(),
            }

            if osintlens_extract_iocs is not None:
                doc["iocs"] = osintlens_extract_iocs(clean_text)

            span.set_attribute("risk.score", risk_score)
            span.set_attribute("risk.label", risk_label)

            index_with_retry(es, r, doc, raw_packet, parsed, span, _neo4j_manager)

    logger.info('"Shutdown complete"')


if __name__ == "__main__":
    main()
