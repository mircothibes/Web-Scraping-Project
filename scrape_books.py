"""
Simple Scraper — Books to Scrape
================================

Overview
--------
This is a beginner-friendly web scraping script that collects book data from the
public demo website **https://books.toscrape.com**. The site is explicitly built
for scraping practice, making it safe for learning. The script fetches multiple
catalog pages, extracts a few fields from each book card, and writes the result
to a CSV file.

What it does
------------
- Downloads up to N catalogue pages (configurable with `--pages`).
- Extracts, per book:
  - `title` (string)
  - `price_raw` (localized text, e.g., "£51.77")
  - `price_value` (float extracted from `price_raw`, e.g., 51.77)
  - `stock` (availability text shown on the page)
  - `url` (absolute URL to the product detail page)
- Optionally filters by price using `--max-price` (keeps only rows with
  `price_value <= max_price`).
- Writes everything to a CSV file (name configurable with `--out`).

Key features
------------
- **Requests + BeautifulSoup** only (no browser automation).
- **Pagination** via the "Next" link on the catalogue pages.
- **Polite scraping**: configurable inter-page delay via `--delay`.
- **Resilience**: HTTP errors raise early (via `raise_for_status()`).
- **Beginner friendly**: minimal, readable code.

How it works (high level)
-------------------------
1) `parse_args()` parses command-line flags (pages, max-price, out, delay, start-url).
2) `main()`:
   - Opens the output CSV and writes the header.
   - Starts from `args.start_url` (default: page 1 of the catalogue).
   - For each page (up to `args.pages`):
     a) Calls `scrape_one_page(current_url, args.max_price)` to collect rows and
        discover the next page URL.
     b) Appends the scraped rows to the CSV.
     c) Waits `args.delay` seconds before proceeding.
     d) Stops early if no "Next" link is present.
3) `scrape_one_page(url, max_price)`:
   - Downloads `url`, builds a BeautifulSoup tree (`lxml` parser).
   - Selects all book cards with CSS selector `article.product_pod`.
   - Extracts `title`, `price_raw`, `stock`, and builds an absolute `url`.
   - Calls `parse_price(price_raw)` to compute `price_value`.
   - Applies the optional filter: only appends rows when
     `max_price is None` **or** `price_value <= max_price`.
   - Returns a tuple `(rows, next_url)`.
4) `parse_price(raw)`:
   - Strips non-digit characters except decimal separators.
   - Handles both `,` and `.`; chooses a sensible decimal separator.
   - Returns `float` on success, `None` on failure.

Command-line arguments
----------------------
- `--pages INT` (default: 3)
    How many catalogue pages to scrape.
- `--max-price FLOAT` (optional)
    Keep only rows where `price_value <= max_price`.
    Omit the flag to disable the filter.
- `--out PATH` (default: `books.csv`)
    Output CSV filename.
- `--delay FLOAT` (default: 1.0)
    Seconds to wait between page requests (be polite).
- `--start-url URL`
    Starting URL for the catalogue (defaults to page 1).

Examples
--------
Basic (3 pages):
    python scrape_books.py

Filter and custom output:
    python scrape_books.py --pages 5 --max-price 25 --out cheap_books.csv --delay 1.5

Start from page 11 and scrape 2 pages:
    python scrape_books.py --start-url https://books.toscrape.com/catalogue/page-11.html --pages 2

CSV output schema
-----------------
The CSV file has the following columns, in order:
    title, price_raw, price_value, stock, url

Dependencies
------------
- Python 3.10+ (for `float | None` typing). For Python 3.8/3.9 use:
  `from typing import Optional` and replace `float | None` with `Optional[float]`.
- Third-party packages:
  - requests
  - beautifulsoup4
  - lxml

Error handling & limitations
----------------------------
- HTTP errors abort quickly via `response.raise_for_status()`.
- `parse_price()` returns `None` if normalization fails; rows without a
  numeric price are excluded **only** when `--max-price` is provided.
- This script assumes the demo site’s HTML structure:
  - Book cards: `article.product_pod`
  - Price selector: `.price_color`
  - Stock selector: `.instock.availability`
  - Next page link: `li.next a`
  If the site changes, selectors may need updates.

Ethics & safety
---------------
- Target site is a public demo designed for scraping practice.
- Keep a small delay between requests to avoid undue load.
- Do not use this script to scrape personal data or sites that forbid scraping.
- Always check a site’s `robots.txt` and Terms of Service before scraping.

Project status
--------------
This script is intentionally minimal for learning purposes. Possible next steps:
- JSON export and/or logging to a file
- Unit tests for `parse_price()`
- Packaging as a module with a console entry point
- CI linting/checks and a short tutorial in the README

License
-------
Choose a permissive license (e.g., MIT) for educational use in your repository.
"""

import csv
import time
import requests
import re 
import argparse
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Simple Books to Scrape scraper")
    p.add_argument("--pages", type=int, default=3, help="How many pages to scrape (default: 3)")
    p.add_argument("--max-price", type=float, default=None, dest="max_price",
                   help="Keep only items with price <= this value (e.g., 30.0). Omit to disable.")
    p.add_argument("--out", default="books.csv", help="Output CSV filename (default: books.csv)")
    p.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between pages (default: 1.0)")
    p.add_argument("--start-url", default="https://books.toscrape.com/catalogue/page-1.html", dest="start_url",
                   help="Start URL (default: page-1 of the catalogue)")
    p.add_argument("--sep", default=";", help="CSV delimiter (default: ';'). Use ',' for US-style CSV.")
    return p.parse_args() 


def parse_price(raw: str) -> float | None:
    """
    Convert '£51.77' (or similar) to a float 51.77.
    Returns None if parsing fails.
    """
    if not raw:
        return None
    try:
        # keep only digits and decimal separator
        s = re.sub(r"[^0-9.,]", "", raw)
        # Books to Scrape uses '.' as decimal separator
        # if both separators appear, assume last one is decimal
        if s.count(",") and s.count("."):
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36"
}

def scrape_one_page(url: str, max_price: float | None):
    """Download one page, return (rows, next_url)."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    # Feed raw bytes so the parser reads the correct encoding from the HTML
    soup = BeautifulSoup(resp.content, "lxml")

    rows = []
    for card in soup.select("article.product_pod"):
        title = card.h3.a.get("title", "").strip()
        price = card.select_one(".price_color").get_text(strip=True)
        # Fix pound sign if mojibake slipped in
        if "Â£" in price:
            price = price.replace("Â£", "£")
        price = price.replace("\xa3", "£")  # ensure U+00A3 is normalized
        stock = card.select_one(".instock.availability").get_text(strip=True)
        rel_link = card.h3.a.get("href", "")
        full_url = urljoin(url, rel_link)
        price_value = parse_price(price)
        # apply optional filter
        if (max_price is None) or (price_value is not None and price_value <= max_price):
            rows.append([title, price, price_value, stock, full_url])


    # find "Next" link
    next_a = soup.select_one("li.next a")
    next_url = urljoin(url, next_a["href"]) if next_a else None
    return rows, next_url

def resolve_output_path(arg_out: str) -> Path:
    """
    Resolve the output path to live inside the script folder if a relative path is given.
    Ensures the parent directory exists.
    """
    base_dir = Path(__file__).resolve().parent  # folder where scrape_books.py lives
    out = Path(arg_out)
    if not out.is_absolute():
        out = (base_dir / out.name).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def main():
    args = parse_args()

    total = 0
    current = args.start_url

    out_path = resolve_output_path(args.out)  # <— ensures saving in simple-scraper
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=args.sep)  # ';' by default (Excel-friendly)
        writer.writerow(["title", "price_raw", "price_value", "stock", "url"])

        for page_num in range(1, args.pages + 1):
            rows, next_url = scrape_one_page(current, args.max_price)
            writer.writerows(rows)
            total += len(rows)
            print(f"Page {page_num}: {len(rows)} rows")

            if not next_url:
                break
            time.sleep(args.delay)
            current = next_url

    print(f"Saved {total} rows to {out_path}")

if __name__ == "__main__":
    main()

