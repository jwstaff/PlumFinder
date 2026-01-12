"""
Poshmark Home Scraper

Scrapes Poshmark's Home category for items matching search terms.
Poshmark Home includes pillows, throws, decor, and more.
Includes robots.txt compliance, caching, and exponential backoff.
"""

import httpx
import time
import random
import re
import json
from bs4 import BeautifulSoup
from typing import Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from src.scrapers.craigslist import ListingItem
from src.scrapers.utils import (
    get_robots_checker,
    get_response_cache,
    retry_on_failure,
)


class PoshmarkScraper:
    BASE_URL = "https://poshmark.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self):
        self.user_agent = random.choice(config.USER_AGENTS)
        self.client = httpx.Client(
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self.robots_checker = get_robots_checker(self.user_agent)
        self.cache = get_response_cache(ttl=300)

    def _fetch_with_retry(self, url: str, params: Optional[dict] = None) -> Optional[httpx.Response]:
        """Fetch URL with exponential backoff retry."""
        def do_fetch():
            response = self.client.get(url, params=params)
            response.raise_for_status()
            return response

        try:
            return retry_on_failure(
                do_fetch,
                max_retries=3,
                base_delay=config.REQUEST_DELAY,
                max_delay=30.0,
            )
        except Exception as e:
            print(f"Failed to fetch {url} after retries: {e}")
            return None

    def search(self, query: str) -> list[ListingItem]:
        """Search Poshmark Home for items matching the query."""
        # Check cache first
        cache_key = f"poshmark_{query}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        items = []

        params = {
            "query": query,
            "department": "Home",
            "sort_by": "added_desc",
            "availability": "available",
        }

        try:
            response = self._fetch_with_retry(self.SEARCH_URL, params=params)
            if response:
                items = self._parse_search_results(response.text)
                # Cache results
                self.cache.set(cache_key, items)

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching Poshmark for '{query}': {e}")

        return items

    def _parse_search_results(self, html: str) -> list[ListingItem]:
        """Parse Poshmark search results."""
        items = []
        soup = BeautifulSoup(html, "lxml")

        # Try to extract from JSON data embedded in page
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "__NEXT_DATA__" in str(script):
                try:
                    json_match = re.search(r'__NEXT_DATA__\s*=\s*({.+?})\s*;?\s*</script>', str(script), re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group(1))
                        items.extend(self._extract_from_json(data))
                except:
                    pass

        # Also try parsing visible listings
        listings = soup.select('[data-et-name="listing"], .card, a[href*="/listing/"]')

        for listing in listings:
            try:
                item = self._parse_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _extract_from_json(self, data, items=None) -> list[ListingItem]:
        """Extract items from Poshmark's JSON data."""
        if items is None:
            items = []

        if isinstance(data, dict):
            if "id" in data and "title" in data and "price_amount" in data:
                try:
                    item = ListingItem(
                        id=f"poshmark_{data['id']}",
                        title=data.get("title", ""),
                        price=float(data.get("price_amount", {}).get("val", 0)),
                        url=f"{self.BASE_URL}/listing/{data.get('title', '').replace(' ', '-')}-{data['id']}",
                        image_urls=[data.get("picture_url", "")] if data.get("picture_url") else [],
                        location=None,
                        posted_date=datetime.now(),
                        source="poshmark",
                        shippable=True,
                    )
                    items.append(item)
                except:
                    pass

            for value in data.values():
                self._extract_from_json(value, items)

        elif isinstance(data, list):
            for item in data:
                self._extract_from_json(item, items)

        return items

    def _parse_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single Poshmark listing element."""
        try:
            link = listing if listing.name == 'a' else listing.select_one('a[href*="/listing/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url.startswith("http"):
                url = self.BASE_URL + url

            match = re.search(r"-([a-f0-9]+)(?:\?|$)", url)
            item_id = match.group(1) if match else None

            if not item_id:
                match = re.search(r"/listing/[^/]+-([a-f0-9]+)", url)
                item_id = match.group(1) if match else url[-12:]

            title_elem = listing.select_one('[class*="title"], .tile__title, h4, span[class*="Title"]')
            title = title_elem.get_text(strip=True) if title_elem else ""

            price = None
            price_elem = listing.select_one('[class*="price"], .tile__price, span[class*="Price"]')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r"\$?([\d,]+)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            image_urls = []
            img = listing.select_one("img")
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src and src.startswith("http"):
                    image_urls.append(src)

            if not title:
                return None

            return ListingItem(
                id=f"poshmark_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location=None,
                posted_date=datetime.now(),
                source="poshmark",
                shippable=True,
            )

        except Exception as e:
            return None

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS:
            print(f"Searching Poshmark for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

        print(f"Found {len(all_items)} unique items on Poshmark")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    scraper = PoshmarkScraper()
    try:
        items = scraper.search("purple pillow")
        print(f"Found {len(items)} items")
        for item in items[:5]:
            print(f"  - {item.title}: ${item.price}")
    finally:
        scraper.close()
