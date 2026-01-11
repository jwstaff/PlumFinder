"""
eBay Scraper

Scrapes eBay for items matching search terms.
Focuses on Buy It Now listings for immediate purchase.
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


class EbayScraper:
    BASE_URL = "https://www.ebay.com"
    SEARCH_URL = f"{BASE_URL}/sch/i.html"

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
        """Search eBay for items matching the query."""
        items = []

        params = {
            "_nkw": query,
            "_sop": "10",  # Sort by newly listed
            "LH_BIN": "1",  # Buy It Now only
            "LH_ItemCondition": "3000|4000|5000|6000",  # Used/Good/etc (not new)
            "_stpos": config.TARGET_ZIP,
            "_sadis": config.MAX_DISTANCE_MILES,
        }

        try:
            response = self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            items = self._parse_search_results(response.text)
            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching eBay for '{query}': {e}")

        return items

    def _parse_search_results(self, html: str) -> list[ListingItem]:
        """Parse eBay search results."""
        items = []
        soup = BeautifulSoup(html, "lxml")

        # eBay listing items
        listings = soup.select('.s-item, [data-viewport]')

        for listing in listings:
            try:
                item = self._parse_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _parse_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single eBay listing."""
        try:
            # Get the link
            link = listing.select_one('a.s-item__link, a[href*="/itm/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url or "pulsar" in url:  # Skip promoted/ad links
                return None

            # Extract ID from URL
            match = re.search(r"/itm/(\d+)", url)
            item_id = match.group(1) if match else None
            if not item_id:
                return None

            # Get title
            title_elem = listing.select_one('.s-item__title, [role="heading"]')
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Skip "Shop on eBay" placeholder items
            if not title or "shop on ebay" in title.lower():
                return None

            # Get price
            price = None
            price_elem = listing.select_one('.s-item__price')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Handle price ranges - take the lower price
                price_match = re.search(r"\$?([\d,]+\.?\d*)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            # Get image
            image_urls = []
            img = listing.select_one('.s-item__image-wrapper img, img.s-item__image-img')
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src and src.startswith("http") and "gif" not in src:
                    image_urls.append(src)

            # Get location/shipping info
            location_elem = listing.select_one('.s-item__location, .s-item__itemLocation')
            location = location_elem.get_text(strip=True) if location_elem else None

            # Check if shipping is free or available
            shipping_elem = listing.select_one('.s-item__shipping, .s-item__freeXDays')
            shipping_text = shipping_elem.get_text(strip=True).lower() if shipping_elem else ""
            shippable = "shipping" in shipping_text or "free" in shipping_text

            return ListingItem(
                id=f"ebay_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location=location,
                posted_date=datetime.now(),
                source="ebay",
                shippable=shippable,
            )

        except Exception as e:
            return None

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS:
            print(f"Searching eBay for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

        print(f"Found {len(all_items)} unique items on eBay")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    scraper = EbayScraper()
    try:
        items = scraper.search("purple pillow")
        print(f"Found {len(items)} items")
        for item in items[:5]:
            print(f"  - {item.title}: ${item.price}")
    finally:
        scraper.close()
