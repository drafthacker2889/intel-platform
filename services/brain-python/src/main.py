import time
import json
import redis
import spacy
from datetime import datetime
from elasticsearch import Elasticsearch

# --- CONFIGURATION ---
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
ELASTIC_HOST = 'http://localhost:9200'

# HIGH VALUE KEYWORDS
RISK_KEYWORDS = ["password", "admin", "login", "secret", "confidential", "leaked", "db_pass", "key"]

print("🧠 LOADING AI MODEL (spaCy)...")
nlp = spacy.load("en_core_web_sm")

def connect_to_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def connect_to_elastic():
    return Elasticsearch(ELASTIC_HOST, request_timeout=60)

def extract_entities(text):
    doc = nlp(text[:100000]) 
    entities = []
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE"]:
            entities.append({"text": ent.text, "type": ent.label_})
    return entities

def calculate_risk(text, entities):
    score = 0
    text_lower = text.lower()

    # 1. Keyword Scanning (+10 per keyword)
    for word in RISK_KEYWORDS:
        if word in text_lower:
            score += 10

    # 2. Entity Value (+5 per Person/Org found)
    score += len(entities) * 5

    # 3. Determine Label
    if score >= 50:
        label = "CRITICAL"
    elif score >= 20:
        label = "HIGH"
    elif score > 0:
        label = "MEDIUM"
    else:
        label = "LOW"
    
    return score, label

def main():
    print("🧠 INTEL-BRAIN: Risk Scoring Active...")
    r = connect_to_redis()
    es = connect_to_elastic()

    if not es.indices.exists(index="intel-data-v3"):
        es.indices.create(index="intel-data-v3")

    print("[*] Waiting for SCRUBBED data in 'sanitized_text'...")

    while True:
        packet = r.blpop("sanitized_text", timeout=0)
        
        if packet:
            clean_text = packet[1]
            print(f"[!] Processing {len(clean_text)} chars...")

            # 1. AI Analysis
            entities = extract_entities(clean_text)
            
            # 2. Risk Calculation (NEW)
            risk_score, risk_label = calculate_risk(clean_text, entities)

            # 3. Construct Intelligence Report
            doc = {
                "content": clean_text[:5000],
                "entities": entities,
                "entity_count": len(entities),
                "risk_score": risk_score,   # <--- NEW FIELD
                "risk_label": risk_label,   # <--- NEW FIELD
                "timestamp": datetime.utcnow().isoformat()
            }
            
            try:
                res = es.index(index="intel-data-v3", document=doc)
                print(f"[+] INTELLIGENCE: {len(entities)} Ents | Risk: {risk_score} ({risk_label})")
            except Exception as e:
                print(f"[-] Indexing Failed: {e}")

if __name__ == "__main__":
    main()