import json
from backend.agent import classify_intent, _synthesize_query, generate_response
from backend.retriever import retrieve
from backend.main import app

def test():
    import os
    os.chdir('backend')
    import backend.main
    messages = [
        {"role": "user", "content": "I need an assessment"},
        {"role": "assistant", "content": "To help me recommend the best assessment, could you tell me what job level this role is, for example, entry-level, mid-professional, or managerial?"},
        {"role": "user", "content": "I am hiring a mid-level Java developer"}
    ]
    
    from backend.schemas import Message
    msg_objs = [Message(**m) for m in messages]
    
    intent = classify_intent(msg_objs)
    print("Intent:", intent)
    
    import chromadb
    client = chromadb.PersistentClient(path="data/chroma_db")
    collection = client.get_collection("shl_catalog")
    with open("data/catalog.json", "r") as f:
        catalog = json.load(f)
        
    query = _synthesize_query(msg_objs)
    retrieved = retrieve(collection, query, n=20)
    
    from backend.llm import call_llm
    from backend.prompts import AGENT_SYSTEM_TEMPLATE, TASK_RECOMMEND, format_messages
    from backend.agent import _build_catalog_context
    
    ctx = _build_catalog_context(retrieved)
    conv = format_messages(msg_objs)
    prompt = AGENT_SYSTEM_TEMPLATE.format(catalog_context=ctx, messages=conv, task_instruction=TASK_RECOMMEND)
    
    raw = call_llm(prompt, conv, temperature=0.4)
    print("--- RAW OUTPUT ---")
    print(raw)
    print("--- END RAW ---")

if __name__ == "__main__":
    test()
