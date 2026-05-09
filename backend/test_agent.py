import json
import logging
import chromadb
from agent import classify_intent, _synthesize_query, generate_response
from llm import call_llm
from prompts import AGENT_SYSTEM_TEMPLATE, TASK_RECOMMEND, format_messages
from agent import _build_catalog_context
from schemas import Message

def test():
    messages = [
        {"role": "user", "content": "I need an assessment"},
        {"role": "assistant", "content": "To help me recommend the best assessment, could you tell me what job level this role is, for example, entry-level, mid-professional, or managerial?"},
        {"role": "user", "content": "I am hiring a mid-level Java developer"}
    ]
    
    msg_objs = [Message(**m) for m in messages]
    
    client = chromadb.PersistentClient(path="data/chroma_db")
    collection = client.get_collection("shl_catalog")
    with open("data/catalog.json", "r") as f:
        catalog = json.load(f)
        
    query = _synthesize_query(msg_objs)
    retrieved = retrieve(collection, query, n=20)
    
    ctx = _build_catalog_context(retrieved)
    conv = format_messages(msg_objs)
    prompt = AGENT_SYSTEM_TEMPLATE.format(catalog_context=ctx, messages=conv, task_instruction=TASK_RECOMMEND)
    
    raw = call_llm(prompt, conv, temperature=0.4)
    print("--- RAW OUTPUT ---")
    print(raw)
    print("--- END RAW ---")

def retrieve(collection, query: str, n: int = 20):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    query_emb = model.encode(query).tolist()
    results = collection.query(query_embeddings=[query_emb], n_results=n)
    docs = []
    if results and results['metadatas']:
        for meta in results['metadatas'][0]:
            docs.append(meta)
    return docs

if __name__ == "__main__":
    test()
