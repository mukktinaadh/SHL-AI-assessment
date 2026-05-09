#!/usr/bin/env python3
"""
One-time script: scrape SHL catalog → embed → persist to ChromaDB.

Usage:
    cd backend
    python scripts/build_index.py

Reads CATALOG_PATH and CHROMA_PATH from environment / .env file.
Falls back to default paths under backend/data/.
"""

import logging
import os
import sys

from dotenv import load_dotenv

# Ensure backend/ is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

load_dotenv()

from retriever import build_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)

if __name__ == "__main__":
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    data_dir = os.path.join(backend_dir, "data")

    catalog_path = os.getenv("CATALOG_PATH", os.path.join(data_dir, "catalog.json"))
    chroma_path = os.getenv("CHROMA_PATH", os.path.join(data_dir, "chroma_db"))

    if not os.path.exists(catalog_path):
        print(f"❌ catalog.json not found at {catalog_path}")
        print("   Run 'python scraper.py' first to generate the catalog.")
        sys.exit(1)

    print("=" * 60)
    print("Building ChromaDB index from catalog")
    print("=" * 60)
    print(f"  Catalog:  {catalog_path}")
    print(f"  ChromaDB: {chroma_path}")
    print()

    build_index(catalog_path, chroma_path)

    print()
    print("=" * 60)
    print("✅ Index built successfully")
    print("=" * 60)
