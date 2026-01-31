import time
import json
import redis
import spacy
from elasticsearch import Elasticsearch

# --- CONFIGURATION ---
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
ELASTIC_HOST = 'http://localhost:9200'

# Load the AI Model (Small English model)
print("🧠 LOADING AI MODEL (spaCy)...")
nlp = spacy.load("en_core_web_sm")

def connect_to_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def connect_to_elastic():
    return Elasticsearch(ELASTIC_HOST, request_timeout=60)

def extract_entities(text):
    """Uses NLP to find People, Orgs, and Locations"""
    doc = nlp(text[:100000]) # Limit to 100k chars to prevent crashes
    entities = []
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE", "MONEY"]:
            entities.append({"text": ent.text, "type": ent.label_})
    return entities

def main():
    print("🧠 INTEL-BRAIN: Intelligence Mode Active...")
    
    r = connect_to_redis()
    es = connect_to_elastic()

    # Create index with mapping for nested objects (if needed later)
    if not es.indices.exists(index="intel-data-v2"):
        es.indices.create(index="intel-data-v2")

    print("[*] Waiting for SCRUBBED data in 'sanitized_text'...")

    while True:
        # 1. Listen to the NEW queue from Rust
        packet = r.blpop("sanitized_text", timeout=0)
        
        if packet:
            clean_text = packet[1]
            print(f"[!] Processing {len(clean_text)} chars of text...")

            # 2. Perform AI Analysis
            entities = extract_entities(clean_text)
            
            # 3. Construct the Intelligence Report
            doc = {
                "content": clean_text[:5000], # Store snippet
                "entities": entities,         # The detected People/Orgs
                "entity_count": len(entities),
                "timestamp": time.time()
            }

            # 4. Index to Elastic
            try:
                res = es.index(index="intel-data-v2", document=doc)
                print(f"[+] INTELLIGENCE CAPTURED! Found {len(entities)} entities.")
            except Exception as e:
                print(f"[-] Indexing Failed: {e}")

if __name__ == "__main__":
    main()