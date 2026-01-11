"""
Etsy Scraper

Scrapes Etsy for vintage and handmade items matching search terms.
Great for unique accent pieces.
"""

import httpx
import time
import random
import re
from bs4 import BeautifulSoup
from typing import Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
from src.scrapers.craigslist import ListingItem


class EtsyScraper:
    BASE_URL = "https://www.etsy.com"
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
        """Search Etsy for items matching the query."""
        items = []

        params = {
            "q": query,
            "explicit": "1",
            "ship_to": "US",
            "order": "date_desc",  # Newest first
        }

        try:
            response = self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            items = self._parse_search_results(response.text)
            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching Etsy for '{query}': {e}")

        return items

    def _parse_search_results(self, html: str) -> list[ListingItem]:
        """Parse Etsy search results."""
        items = []
        soup = BeautifulSoup(html, "lxml")

        # Etsy listing cards
        listings = soup.select('[data-listing-id], .v2-listing-card, .listing-link')

        for listing in listings:
            try:
                item = self._parse_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _parse_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single Etsy listing."""
        try:
            # Get listing ID
            item_id = listing.get("data-listing-id")

            # Get the link
            link = listing if listing.name == 'a' else listing.select_one('a[href*="/listing/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url:
                return None

            # Extract ID from URL if not found in data attribute
            if not item_id:
                match = re.search(r"/listing/(\d+)", url)
                item_id = match.group(1) if match else None

            if not item_id:
                return None

            # Clean up URL
            if not url.startswith("http"):
                url = self.BASE_URL + url
            # Remove tracking parameters
            url = url.split("?")[0]

            # Get title
            title_elem = listing.select_one('[class*="title"], h3, h2, .v2-listing-card__title')
            title = title_elem.get_text(strip=True) if title_elem else ""

            if not title:
                title = link.get("title", "")

            # Get price
            price = None
            price_elem = listing.select_one('[class*="price"], .currency-value, span[class*="Price"]')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r"([\d,]+\.?\d*)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            # Get image
            image_urls = []
            img = listing.select_one("img")
            if img:
                # Etsy uses data-src for lazy loading
                src = img.get("src", "") or img.get("data-src", "")
                if src and src.startswith("http"):
                    # Get larger image version
                    src = re.sub(r"_\d+x\d+", "_680x", src)
                    image_urls.append(src)

            # Check for free shipping badge
            shipping_elem = listing.select_one('[class*="free-shipping"], [class*="FreeShipping"]')
            free_shipping = shipping_elem is not None

            if not title:
                return None

            return ListingItem(
                id=f"etsy_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location="Etsy Seller",
                posted_date=datetime.now(),
                source="etsy",
                shippable=True,  # Etsy items ship
            )

        except Exception as e:
            return None

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS:
            print(f"Searching Etsy for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

        print(f"Found {len(all_items)} unique items on Etsy")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    scraper = EtsyScraper()
    try:
        items = scraper.search("plum throw pillow")
        print(f"Found {len(items)} items")
        for item in items[:5]:
            print(f"  - {item.title}: ${item.price}")
    finally:
        scraper.close()
