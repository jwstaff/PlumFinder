"""
Mercari Scraper

Scrapes Mercari for items matching search terms.
Uses Mercari's internal API for reliable results.
Includes robots.txt compliance, caching, and exponential backoff.
"""

import httpx
import time
import random
import re
import json
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


class MercariScraper:
    BASE_URL = "https://www.mercari.com"
    API_URL = "https://www.mercari.com/v1/api"

    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.client = httpx.Client(
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Origin": "https://www.mercari.com",
                "Referer": "https://www.mercari.com/",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
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
        """Search Mercari for items matching the query."""
        # Check cache first
        cache_key = f"mercari_{query}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        items = []

        # Try multiple API approaches
        items = self._search_api(query)

        if not items:
            items = self._search_html_fallback(query)

        # Cache results
        if items:
            self.cache.set(cache_key, items)

        time.sleep(config.REQUEST_DELAY)
        return items

    def _search_api(self, query: str) -> list[ListingItem]:
        """Search using Mercari's internal API."""
        items = []

        api_url = f"{self.BASE_URL}/api/search/public/v1/items"

        # Check robots.txt
        if not self.robots_checker.can_fetch(api_url, self.client):
            print("Mercari API disallowed by robots.txt")
            return items

        params = {
            "query": query,
            "status": "active",
            "sort": "created_at_desc",
            "limit": 50,
        }

        try:
            response = self._fetch_with_retry(api_url, params=params)

            if response and response.status_code == 200:
                data = response.json()
                items = self._parse_api_response(data)
            else:
                items = self._search_graphql(query)

        except Exception as e:
            print(f"Mercari API error: {e}")

        return items

    def _search_graphql(self, query: str) -> list[ListingItem]:
        """Try GraphQL-style search."""
        items = []

        search_url = f"{self.BASE_URL}/search/?keyword={query}"

        # Check robots.txt
        if not self.robots_checker.can_fetch(search_url, self.client):
            return items

        try:
            response = self._fetch_with_retry(search_url)
            if response and response.status_code == 200:
                text = response.text

                patterns = [
                    r'window\.__NUXT__\s*=\s*(\{.+?\});?\s*</script>',
                    r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>',
                    r'"searchResults":\s*(\[.+?\])',
                    r'"items":\s*(\[.+?\])',
                ]

                for pattern in patterns:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            extracted = self._extract_items_from_json(data)
                            if extracted:
                                items.extend(extracted)
                                break
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            print(f"Mercari GraphQL search error: {e}")

        return items

    def _parse_api_response(self, data: dict) -> list[ListingItem]:
        """Parse Mercari API response."""
        items = []

        item_list = data.get("items", []) or data.get("data", []) or []

        for item_data in item_list:
            try:
                item = self._create_item_from_data(item_data)
                if item:
                    items.append(item)
            except:
                continue

        return items

    def _extract_items_from_json(self, data, depth=0) -> list[ListingItem]:
        """Recursively extract items from nested JSON."""
        items = []

        if depth > 10:
            return items

        if isinstance(data, dict):
            if self._looks_like_item(data):
                item = self._create_item_from_data(data)
                if item:
                    items.append(item)
            else:
                for value in data.values():
                    items.extend(self._extract_items_from_json(value, depth + 1))

        elif isinstance(data, list):
            for item in data:
                items.extend(self._extract_items_from_json(item, depth + 1))

        return items

    def _looks_like_item(self, data: dict) -> bool:
        """Check if dict looks like a Mercari item."""
        has_id = any(k in data for k in ["id", "itemId", "item_id"])
        has_name = any(k in data for k in ["name", "title", "itemName"])
        has_price = any(k in data for k in ["price", "itemPrice"])
        return has_id and (has_name or has_price)

    def _create_item_from_data(self, data: dict) -> Optional[ListingItem]:
        """Create ListingItem from item data."""
        try:
            item_id = data.get("id") or data.get("itemId") or data.get("item_id")
            if not item_id:
                return None

            title = data.get("name") or data.get("title") or data.get("itemName") or ""
            if not title:
                return None

            price = None
            price_val = data.get("price") or data.get("itemPrice")
            if price_val:
                if isinstance(price_val, dict):
                    price_val = price_val.get("amount") or price_val.get("value")
                try:
                    price = float(str(price_val).replace("$", "").replace(",", ""))
                except:
                    pass

            image_urls = []
            img = data.get("image") or data.get("photo") or data.get("thumbnail")
            if img:
                if isinstance(img, dict):
                    img = img.get("url") or img.get("imageUrl")
                if isinstance(img, str) and img.startswith("http"):
                    image_urls.append(img)

            thumbs = data.get("thumbnails", [])
            if thumbs and isinstance(thumbs, list):
                for t in thumbs[:1]:
                    url = t.get("url") if isinstance(t, dict) else t
                    if url and str(url).startswith("http"):
                        image_urls.append(str(url))

            return ListingItem(
                id=f"mercari_{item_id}",
                title=title,
                price=price,
                url=f"{self.BASE_URL}/item/{item_id}",
                image_urls=image_urls,
                location=None,
                posted_date=datetime.now(),
                source="mercari",
                shippable=True,
            )

        except Exception as e:
            return None

    def _search_html_fallback(self, query: str) -> list[ListingItem]:
        """Fallback HTML parsing for search results."""
        items = []

        search_url = f"{self.BASE_URL}/search/?keyword={query}&status=on_sale"

        # Check robots.txt
        if not self.robots_checker.can_fetch(search_url, self.client):
            return items

        try:
            from bs4 import BeautifulSoup

            response = self._fetch_with_retry(search_url)

            if not response or response.status_code != 200:
                return items

            soup = BeautifulSoup(response.text, "lxml")

            links = soup.select('a[href*="/item/m"]')

            for link in links:
                try:
                    url = link.get("href", "")
                    if not url:
                        continue

                    if not url.startswith("http"):
                        url = self.BASE_URL + url

                    match = re.search(r"/item/(m\d+)", url)
                    if not match:
                        continue
                    item_id = match.group(1)

                    title = link.get("aria-label", "") or link.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    parent = link.parent
                    price = None
                    price_elem = parent.select_one('[class*="price"], [class*="Price"]') if parent else None
                    if price_elem:
                        price_text = price_elem.get_text()
                        price_match = re.search(r"\$?([\d,]+)", price_text)
                        if price_match:
                            price = float(price_match.group(1).replace(",", ""))

                    image_urls = []
                    img = link.select_one("img")
                    if img:
                        src = img.get("src") or img.get("data-src")
                        if src and src.startswith("http"):
                            image_urls.append(src)

                    items.append(ListingItem(
                        id=f"mercari_{item_id}",
                        title=title[:200],
                        price=price,
                        url=url,
                        image_urls=image_urls,
                        location=None,
                        posted_date=datetime.now(),
                        source="mercari",
                        shippable=True,
                    ))

                except:
                    continue

        except Exception as e:
            print(f"Mercari HTML fallback error: {e}")

        return items

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS:
            print(f"Searching Mercari for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

        print(f"Found {len(all_items)} unique items on Mercari")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    scraper = MercariScraper()
    try:
        items = scraper.search("purple pillow")
        print(f"Found {len(items)} items")
        for item in items[:5]:
            print(f"  - {item.title}: ${item.price}")
    finally:
        scraper.close()
