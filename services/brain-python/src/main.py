import time
import json
import redis
from elasticsearch import Elasticsearch
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
ELASTIC_HOST = 'http://localhost:9200'

def connect_to_redis():
    print("[*] Connecting to Redis...")
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False) # raw bytes

def connect_to_elastic():
    print("[*] Connecting to Elasticsearch...")
    # No username/password needed because we disabled security for Tier 1
    return Elasticsearch(ELASTIC_HOST, request_timeout=60)

def main():
    print("🧠 INTEL-BRAIN: Initializing...")
    
    r = connect_to_redis()
    es = connect_to_elastic()

    # Create the search index if it doesn't exist
    if not es.indices.exists(index="intel-data"):
        es.indices.create(index="intel-data")
        print("[+] Created index 'intel-data'")

    print("[*] Waiting for data in queue 'raw_html'...")

    while True:
        # 1. POP from Queue (Blocking Pop - waits until data arrives)
        # Returns a tuple: (queue_name, data)
        packet = r.blpop("raw_html", timeout=0)
        
        if packet:
            raw_html = packet[1]
            print(f"[!] Received {len(raw_html)} bytes. Processing...")

            # 2. CLEAN raw HTML (Simple parsing)
            soup = BeautifulSoup(raw_html, "html.parser")
            title = soup.title.string if soup.title else "No Title"
            text_content = soup.get_text(separator=' ', strip=True)

            # 3. INDEX into Elasticsearch
            doc = {
                "title": title,
                "content": text_content,
                "length": len(text_content),
                "timestamp": time.time()
            }

            try:
                res = es.index(index="intel-data", document=doc)
                print(f"[+] INDEXED! ID: {res['_id']} | Title: {title}")
            except Exception as e:
                print(f"[-] Indexing Failed: {e}")

if __name__ == "__main__":
    main()