"""
SHL Individual Test Solutions Catalog Scraper

Scrapes https://www.shl.com/solutions/products/product-catalog/ to extract
Individual Test Solutions (skipping Pre-packaged Job Solutions).

Uses requests + BeautifulSoup4 only. Saves output to backend/data/catalog.json.
"""

import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://www.shl.com/solutions/products/product-catalog/"
DETAIL_BASE = "https://www.shl.com"
ITEMS_PER_PAGE = 12
CATALOG_TYPE = 1  # 1 = Individual Test Solutions, 2 = Pre-packaged Job Solutions

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

# Where to save the output
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "catalog.json")

# Test type code → label mapping (from PRD Section 9)
TEST_TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "M": "Motivation",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fetch_page(url: str, params: dict | None = None, retries: int = 3) -> BeautifulSoup:
    """Fetch a page and return a BeautifulSoup object. Retries on failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            wait = 2 ** attempt
            print(f"  [WARN] Attempt {attempt + 1} failed for {url}: {exc}. Retrying in {wait}s...")
            time.sleep(wait)
    print(f"  [ERROR] Failed to fetch {url} after {retries} attempts. Skipping.")
    return None


def find_individual_tests_table(soup: BeautifulSoup):
    """
    Locate the 'Individual Test Solutions' table on the page.
    
    On page 1 there are two tables: 'Pre-packaged Job Solutions' and
    'Individual Test Solutions'. On subsequent pages there is only one table.
    We identify the correct table by its header text.
    """
    tables = soup.find_all("table")
    for table in tables:
        first_row = table.find("tr")
        if first_row:
            first_th = first_row.find("th")
            if first_th and "Individual Test Solutions" in first_th.get_text(strip=True):
                return table
    # Fallback: if only one table and no "Pre-packaged" header, use it
    if len(tables) == 1:
        return tables[0]
    return None


def parse_listing_rows(table) -> list[dict]:
    """
    Parse rows from the listing table. Each row has 4 cells:
      0 - Name + link
      1 - Remote Testing (green circle = yes)
      2 - Adaptive/IRT (green circle = yes)
      3 - Test Type codes (letter badges)
    """
    items = []
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue  # skip header row or malformed rows

        # Cell 0: Name + URL
        link = cells[0].find("a")
        if not link:
            continue
        name = link.get_text(strip=True)
        href = link.get("href", "")
        url = href if href.startswith("http") else DETAIL_BASE + href

        # Cell 1: Remote Testing — presence of span.catalogue__circle.-yes
        remote_span = cells[1].find("span", class_=lambda c: c and "catalogue__circle" in c)
        remote_testing = remote_span is not None and "-yes" in " ".join(remote_span.get("class", []))

        # Cell 2: Adaptive/IRT
        adaptive_span = cells[2].find("span", class_=lambda c: c and "catalogue__circle" in c)
        adaptive = adaptive_span is not None and "-yes" in " ".join(adaptive_span.get("class", []))

        # Cell 3: Test Type codes
        test_type_spans = cells[3].find_all("span", class_="product-catalogue__key")
        test_types = [s.get_text(strip=True) for s in test_type_spans]

        items.append({
            "name": name,
            "url": url,
            "remote_testing": remote_testing,
            "adaptive": adaptive,
            "test_type": test_types,
        })

    return items


def get_total_pages(soup: BeautifulSoup) -> int:
    """
    Determine total pages for the Individual Test Solutions section
    by finding the highest page number in the pagination links.
    Pagination links use pattern: ?start=N&type=1
    """
    max_page = 1
    pagination_links = soup.find_all("a", href=re.compile(r"type=1"))
    for link in pagination_links:
        href = link.get("href", "")
        match = re.search(r"start=(\d+)", href)
        if match:
            start = int(match.group(1))
            page = (start // ITEMS_PER_PAGE) + 1
            max_page = max(max_page, page)
    return max_page


# ---------------------------------------------------------------------------
# Detail page scraper
# ---------------------------------------------------------------------------
def scrape_detail_page(url: str) -> dict:
    """
    Scrape a product detail page to extract description and job_levels.
    
    Detail pages have sections under h4 headings:
      - Description  → text content
      - Job levels   → comma-separated text
    """
    result = {"description": "", "job_levels": []}

    soup = fetch_page(url)
    if soup is None:
        return result

    # Find the product-catalogue module div
    module = soup.find("div", class_="product-catalogue")
    if not module:
        # Fallback: try OG description meta tag
        og = soup.find("meta", attrs={"property": "og:description"})
        if og:
            desc = og.get("content", "")
            # OG desc often starts with "ProductName: actual description"
            if ":" in desc:
                desc = desc.split(":", 1)[1].strip()
            result["description"] = desc
        return result

    # Iterate h4-labeled sections
    rows = module.find_all("div", class_=re.compile(r"product-catalogue-training-calendar__row"))
    for row in rows:
        h4 = row.find("h4")
        if not h4:
            continue
        label = h4.get_text(strip=True).lower()

        if label == "description":
            # Get the paragraph(s) following the h4
            paragraphs = row.find_all("p")
            result["description"] = " ".join(p.get_text(strip=True) for p in paragraphs).strip()

        elif label == "job levels":
            p = row.find("p")
            if p:
                raw = p.get_text(strip=True)
                # Parse comma-separated job levels, strip trailing comma
                levels = [lev.strip() for lev in raw.split(",") if lev.strip()]
                result["job_levels"] = levels

    return result


# ---------------------------------------------------------------------------
# Main scraping orchestration
# ---------------------------------------------------------------------------
def scrape_catalog() -> list[dict]:
    """
    Scrape all Individual Test Solutions from the SHL product catalog.
    
    Strategy:
      1. Fetch the first page to determine total pages and get initial items.
      2. Paginate through all remaining pages to collect all listing items.
      3. For each item, fetch its detail page to get description + job_levels.
      4. Return the complete catalog as a list of dicts.
    """
    all_items = []

    # ---- Step 1: Fetch first page ----
    print("Fetching catalog page 1...")
    soup = fetch_page(BASE_URL, params={"start": 0, "type": CATALOG_TYPE})
    if soup is None:
        print("[FATAL] Cannot fetch the catalog page. Exiting.")
        sys.exit(1)

    table = find_individual_tests_table(soup)
    if table is None:
        print("[FATAL] Cannot find 'Individual Test Solutions' table. Exiting.")
        sys.exit(1)

    items = parse_listing_rows(table)
    all_items.extend(items)
    print(f"  Page 1: {len(items)} items")

    total_pages = get_total_pages(soup)
    print(f"  Total pages detected: {total_pages}")

    # ---- Step 2: Paginate through remaining pages ----
    for page in range(2, total_pages + 1):
        start = (page - 1) * ITEMS_PER_PAGE
        print(f"Fetching catalog page {page} (start={start})...")
        soup = fetch_page(BASE_URL, params={"start": start, "type": CATALOG_TYPE})
        if soup is None:
            continue

        table = find_individual_tests_table(soup)
        if table is None:
            print(f"  [WARN] No table found on page {page}. Skipping.")
            continue

        items = parse_listing_rows(table)
        all_items.extend(items)
        print(f"  Page {page}: {len(items)} items")

        # Be respectful — small delay between listing page requests
        time.sleep(0.5)

    print(f"\nTotal items from listing pages: {len(all_items)}")

    # ---- Step 3: Enrich each item with detail page data ----
    print("\nFetching detail pages for descriptions & job levels...")
    for i, item in enumerate(all_items):
        detail = scrape_detail_page(item["url"])
        item["description"] = detail["description"]
        item["job_levels"] = detail["job_levels"]

        if (i + 1) % 20 == 0 or (i + 1) == len(all_items):
            print(f"  Progress: {i + 1}/{len(all_items)} detail pages fetched")

        # Be respectful — delay between detail page requests
        time.sleep(0.3)

    return all_items


def save_catalog(catalog: list[dict], path: str) -> None:
    """Save the catalog to a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"\nCatalog saved to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("SHL Individual Test Solutions Catalog Scraper")
    print("=" * 60)
    print()

    catalog = scrape_catalog()
    save_catalog(catalog, OUTPUT_PATH)

    print(f"\n{'=' * 60}")
    print(f"DONE — Scraped {len(catalog)} Individual Test Solutions")
    print(f"{'=' * 60}")
