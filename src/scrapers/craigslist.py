import httpx
import time
import random
import re
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


@dataclass
class ListingItem:
    id: str
    title: str
    price: Optional[float]
    url: str
    image_urls: list[str]
    location: Optional[str]
    posted_date: Optional[datetime]
    source: str
    distance_miles: Optional[float] = None
    color_score: float = 0.0
    shippable: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "price": self.price,
            "url": self.url,
            "image_urls": self.image_urls,
            "location": self.location,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "source": self.source,
            "distance_miles": self.distance_miles,
            "color_score": self.color_score,
            "shippable": self.shippable,
        }


class CraigslistScraper:
    BASE_URL = "https://sfbay.craigslist.org"
    SEARCH_URL = f"{BASE_URL}/search/sss"

    def __init__(self):
        self.client = httpx.Client(
            headers={"User-Agent": random.choice(config.USER_AGENTS)},
            timeout=30.0,
            follow_redirects=True,
        )

    def search(self, query: str, postal: str = config.TARGET_ZIP, miles: int = config.MAX_DISTANCE_MILES) -> list[ListingItem]:
        """Search Craigslist for items matching the query."""
        items = []

        params = {
            "query": query,
            "postal": postal,
            "search_distance": miles,
            "sort": "date",
            "purveyor": "owner",  # Filter to owner listings, skip dealers
        }

        try:
            response = self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            listings = soup.select("li.cl-static-search-result, div.cl-search-result")

            for listing in listings:
                item = self._parse_listing(listing)
                if item:
                    items.append(item)

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching Craigslist for '{query}': {e}")

        return items

    def _parse_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single Craigslist listing."""
        try:
            # Get the link and title
            link = listing.select_one("a")
            if not link:
                return None

            url = link.get("href", "")
            if not url.startswith("http"):
                url = self.BASE_URL + url

            title = link.get_text(strip=True)

            # Extract ID from URL
            match = re.search(r"/(\d+)\.html", url)
            item_id = match.group(1) if match else url

            # Get price
            price_elem = listing.select_one(".priceinfo, .price")
            price = None
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r"\$?([\d,]+)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            # Get location
            location_elem = listing.select_one(".meta, .location")
            location = location_elem.get_text(strip=True) if location_elem else None

            # Get image (if available in search results)
            image_urls = []
            img = listing.select_one("img")
            if img:
                src = img.get("src", "")
                if src and "craigslist" in src:
                    image_urls.append(src)

            # Check for shipping keywords in title
            shippable = any(word in title.lower() for word in ["ship", "shipping", "mail", "deliver"])

            return ListingItem(
                id=f"cl_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location=location,
                posted_date=datetime.now(),  # Will be updated when fetching details
                source="craigslist",
                shippable=shippable,
            )

        except Exception as e:
            print(f"Error parsing listing: {e}")
            return None

    def get_listing_details(self, item: ListingItem) -> ListingItem:
        """Fetch full details for a listing including all images."""
        try:
            response = self.client.get(item.url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # Get all images
            gallery = soup.select("div.gallery img, div.swipe img, a.thumb img")
            image_urls = []
            for img in gallery:
                src = img.get("src", "") or img.get("data-src", "")
                if src and src not in image_urls:
                    # Get full-size image URL
                    src = src.replace("50x50c", "600x450")
                    src = src.replace("300x300", "600x450")
                    image_urls.append(src)

            if image_urls:
                item.image_urls = image_urls

            # Get posted date
            time_elem = soup.select_one("time.date")
            if time_elem:
                datetime_str = time_elem.get("datetime")
                if datetime_str:
                    item.posted_date = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))

            # Check description for shipping info
            body = soup.select_one("section#postingbody")
            if body:
                body_text = body.get_text().lower()
                if any(word in body_text for word in ["ship", "shipping", "mail", "deliver", "usps", "fedex", "ups"]):
                    item.shippable = True

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error fetching details for {item.url}: {e}")

        return item

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS:
            print(f"Searching Craigslist for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

        print(f"Found {len(all_items)} unique items on Craigslist")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    # Test the scraper
    scraper = CraigslistScraper()
    try:
        items = scraper.search("purple pillow")
        print(f"Found {len(items)} items")
        for item in items[:5]:
            print(f"  - {item.title}: ${item.price} - {item.url}")
    finally:
        scraper.close()
