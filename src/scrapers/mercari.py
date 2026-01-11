"""
Mercari Scraper

Scrapes Mercari for items matching search terms.
Mercari is primarily a shipping-based marketplace.
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


class MercariScraper:
    BASE_URL = "https://www.mercari.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": random.choice(config.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def search(self, query: str) -> list[ListingItem]:
        """Search Mercari for items matching the query."""
        items = []

        params = {
            "keyword": query,
            "status": "on_sale",  # Only show available items
            "sortBy": "created_time",  # Newest first
        }

        try:
            response = self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            items = self._parse_search_results(response.text)
            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching Mercari for '{query}': {e}")

        return items

    def _parse_search_results(self, html: str) -> list[ListingItem]:
        """Parse Mercari search results."""
        items = []
        soup = BeautifulSoup(html, "lxml")

        # Try to find JSON data in script tags (Mercari often embeds data)
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                items.extend(self._extract_from_json(data))
            except:
                continue

        # Also try parsing visible listings
        listings = soup.select('[data-testid="ItemContainer"], [class*="ItemContainer"], a[href*="/item/"]')

        for listing in listings:
            try:
                item = self._parse_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _extract_from_json(self, data, items=None) -> list[ListingItem]:
        """Extract items from Mercari's JSON data."""
        if items is None:
            items = []

        if isinstance(data, dict):
            # Look for item patterns
            if "id" in data and "name" in data and "price" in data:
                try:
                    item = ListingItem(
                        id=f"mercari_{data['id']}",
                        title=data.get("name", ""),
                        price=float(data.get("price", 0)),
                        url=f"{self.BASE_URL}/item/{data['id']}",
                        image_urls=[data.get("thumbnails", [{}])[0].get("url", "")] if data.get("thumbnails") else [],
                        location=None,
                        posted_date=datetime.now(),
                        source="mercari",
                        shippable=True,  # Mercari items are always shippable
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
        """Parse a single Mercari listing element."""
        try:
            # Get the link
            link = listing if listing.name == 'a' else listing.select_one('a[href*="/item/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url.startswith("http"):
                url = self.BASE_URL + url

            # Extract ID from URL
            match = re.search(r"/item/([^/\?]+)", url)
            item_id = match.group(1) if match else url

            # Get title
            title_elem = listing.select_one('[class*="ItemName"], [data-testid="ItemName"], span, p')
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Get price
            price = None
            price_elem = listing.select_one('[class*="Price"], [data-testid="Price"]')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r"\$?([\d,]+)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            # Get image
            image_urls = []
            img = listing.select_one("img")
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src and src.startswith("http"):
                    image_urls.append(src)

            if not title:
                return None

            return ListingItem(
                id=f"mercari_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location=None,
                posted_date=datetime.now(),
                source="mercari",
                shippable=True,  # Mercari is shipping-only
            )

        except Exception as e:
            return None

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
