"""
OfferUp Scraper

Scrapes OfferUp for items matching search terms near the target location.
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


class OfferUpScraper:
    BASE_URL = "https://offerup.com"
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
        """Search OfferUp for items matching the query."""
        items = []

        # OfferUp uses location-based URLs
        params = {
            "q": query,
            "location": "palo-alto-ca",
            "radius": config.MAX_DISTANCE_MILES,
        }

        try:
            response = self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            items = self._parse_search_results(response.text)
            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching OfferUp for '{query}': {e}")

        return items

    def _parse_search_results(self, html: str) -> list[ListingItem]:
        """Parse OfferUp search results."""
        items = []
        soup = BeautifulSoup(html, "lxml")

        # OfferUp uses various listing card formats
        listings = soup.select('[data-testid="listing-card"], .listing-card, a[href*="/item/"]')

        for listing in listings:
            try:
                item = self._parse_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _parse_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single OfferUp listing."""
        try:
            # Get the link
            link = listing if listing.name == 'a' else listing.select_one('a[href*="/item/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url.startswith("http"):
                url = self.BASE_URL + url

            # Extract ID from URL
            match = re.search(r"/item/([^/]+)", url)
            item_id = match.group(1) if match else url

            # Get title
            title_elem = listing.select_one('[class*="title"], h2, h3, span[class*="Title"]')
            title = title_elem.get_text(strip=True) if title_elem else ""

            if not title:
                # Try getting text from the link itself
                title = link.get_text(strip=True)[:100]

            # Get price
            price = None
            price_elem = listing.select_one('[class*="price"], span[class*="Price"]')
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

            # Get location
            location_elem = listing.select_one('[class*="location"], span[class*="Location"]')
            location = location_elem.get_text(strip=True) if location_elem else None

            if not title:
                return None

            return ListingItem(
                id=f"offerup_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location=location,
                posted_date=datetime.now(),
                source="offerup",
                shippable="ship" in title.lower(),
            )

        except Exception as e:
            return None

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS:
            print(f"Searching OfferUp for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

        print(f"Found {len(all_items)} unique items on OfferUp")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    scraper = OfferUpScraper()
    try:
        items = scraper.search("purple pillow")
        print(f"Found {len(items)} items")
        for item in items[:5]:
            print(f"  - {item.title}: ${item.price}")
    finally:
        scraper.close()
