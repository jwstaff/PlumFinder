"""
Facebook Marketplace Scraper (Best Effort)

IMPORTANT: Facebook actively blocks automated access. This scraper may break frequently.
To use it, you need to:
1. Log into Facebook in your browser
2. Open Developer Tools (F12) -> Application -> Cookies
3. Copy the value of the 'c_user' and 'xs' cookies
4. Set them in the FB_SESSION_COOKIE environment variable as: "c_user=XXX; xs=YYY"

This is a best-effort implementation and may stop working at any time.
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


class FacebookMarketplaceScraper:
    BASE_URL = "https://www.facebook.com"
    MARKETPLACE_URL = f"{BASE_URL}/marketplace"

    def __init__(self):
        cookies = self._parse_cookies(config.FB_SESSION_COOKIE)
        self.client = httpx.Client(
            headers={
                "User-Agent": random.choice(config.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            cookies=cookies,
            timeout=30.0,
            follow_redirects=True,
        )
        self.enabled = bool(cookies)
        if not self.enabled:
            print("Facebook Marketplace scraper disabled: No session cookie configured")
            print("Set FB_SESSION_COOKIE environment variable to enable")

    def _parse_cookies(self, cookie_string: Optional[str]) -> dict:
        """Parse cookie string into dictionary."""
        if not cookie_string:
            return {}

        cookies = {}
        try:
            for pair in cookie_string.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    cookies[key.strip()] = value.strip()
        except Exception as e:
            print(f"Error parsing cookies: {e}")

        return cookies

    def search(self, query: str, location: str = "palo alto", radius_km: int = 32) -> list[ListingItem]:
        """
        Search Facebook Marketplace.
        Note: This may not work due to Facebook's anti-bot measures.
        """
        if not self.enabled:
            return []

        items = []

        # Try to search using the marketplace search URL
        search_url = f"{self.MARKETPLACE_URL}/search"
        params = {
            "query": query,
            "exact": "false",
        }

        try:
            response = self.client.get(search_url, params=params)

            # Check if we got a login redirect (blocked)
            if "login" in response.url.path.lower() or response.status_code == 403:
                print(f"Facebook blocked access (login required). Session may have expired.")
                self.enabled = False
                return []

            # Try to parse the response
            items = self._parse_search_results(response.text, query)
            time.sleep(config.REQUEST_DELAY * 2)  # Extra delay for Facebook

        except Exception as e:
            print(f"Error searching Facebook Marketplace for '{query}': {e}")
            self.enabled = False

        return items

    def _parse_search_results(self, html: str, query: str) -> list[ListingItem]:
        """
        Parse Facebook Marketplace search results.
        Facebook uses heavily obfuscated JavaScript-rendered content,
        so this is best-effort parsing.
        """
        items = []

        try:
            soup = BeautifulSoup(html, "lxml")

            # Try to find JSON data embedded in the page
            scripts = soup.find_all("script", type="application/json")
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    items.extend(self._extract_items_from_json(data))
                except:
                    continue

            # Also try parsing visible listing elements (fallback)
            listings = soup.select('[data-testid="marketplace_search_feed_item"]')
            for listing in listings:
                item = self._parse_listing_element(listing)
                if item:
                    items.append(item)

        except Exception as e:
            print(f"Error parsing Facebook results: {e}")

        return items

    def _extract_items_from_json(self, data: dict, items: list = None) -> list[ListingItem]:
        """Recursively extract listing items from Facebook's JSON data."""
        if items is None:
            items = []

        if isinstance(data, dict):
            # Look for marketplace listing patterns
            if "marketplace_listing_title" in data or "listing_title" in data:
                try:
                    item = self._json_to_listing(data)
                    if item:
                        items.append(item)
                except:
                    pass

            # Recurse into nested structures
            for value in data.values():
                self._extract_items_from_json(value, items)

        elif isinstance(data, list):
            for item in data:
                self._extract_items_from_json(item, items)

        return items

    def _json_to_listing(self, data: dict) -> Optional[ListingItem]:
        """Convert Facebook JSON data to ListingItem."""
        try:
            listing_id = data.get("id", data.get("listing_id", ""))
            title = data.get("marketplace_listing_title", data.get("listing_title", ""))
            price_data = data.get("listing_price", {})

            if isinstance(price_data, dict):
                price_str = price_data.get("formatted_amount", price_data.get("amount", "0"))
            else:
                price_str = str(price_data)

            price_match = re.search(r"[\d,]+", price_str)
            price = float(price_match.group().replace(",", "")) if price_match else None

            # Get images
            image_urls = []
            photos = data.get("listing_photos", data.get("primary_listing_photo", []))
            if isinstance(photos, dict):
                photos = [photos]
            for photo in photos:
                if isinstance(photo, dict):
                    url = photo.get("image", {}).get("uri", "")
                    if url:
                        image_urls.append(url)

            location = data.get("location", {})
            if isinstance(location, dict):
                location = location.get("reverse_geocode", {}).get("city", "")

            return ListingItem(
                id=f"fb_{listing_id}",
                title=title,
                price=price,
                url=f"https://www.facebook.com/marketplace/item/{listing_id}",
                image_urls=image_urls,
                location=location if isinstance(location, str) else None,
                posted_date=datetime.now(),
                source="facebook",
                shippable=False,  # Would need to check listing details
            )

        except Exception as e:
            print(f"Error converting Facebook JSON to listing: {e}")
            return None

    def _parse_listing_element(self, element) -> Optional[ListingItem]:
        """Parse a listing from HTML element (fallback method)."""
        try:
            link = element.select_one("a[href*='/marketplace/item/']")
            if not link:
                return None

            url = link.get("href", "")
            if not url.startswith("http"):
                url = self.BASE_URL + url

            # Extract ID from URL
            match = re.search(r"/item/(\d+)", url)
            item_id = match.group(1) if match else url

            # Get title and price from text content
            text = element.get_text(" ", strip=True)
            # Facebook often shows "TitlePrice" together
            price_match = re.search(r"\$[\d,]+", text)
            price = None
            if price_match:
                price = float(price_match.group().replace("$", "").replace(",", ""))
                title = text[:text.find(price_match.group())].strip()
            else:
                title = text[:100]  # Truncate if no price found

            # Get image
            img = element.select_one("img")
            image_urls = [img.get("src")] if img and img.get("src") else []

            return ListingItem(
                id=f"fb_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location=None,
                posted_date=datetime.now(),
                source="facebook",
                shippable=False,
            )

        except Exception as e:
            print(f"Error parsing Facebook listing element: {e}")
            return None

    def search_all_terms(self) -> list[ListingItem]:
        """Search for all configured search terms."""
        if not self.enabled:
            print("Facebook Marketplace scraper is disabled")
            return []

        all_items = []
        seen_ids = set()

        for term in config.SEARCH_TERMS[:5]:  # Limit to avoid rate limiting
            print(f"Searching Facebook Marketplace for: {term}")
            items = self.search(term)

            for item in items:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    all_items.append(item)

            if not self.enabled:  # Stop if we got blocked
                break

        print(f"Found {len(all_items)} unique items on Facebook Marketplace")
        return all_items

    def close(self):
        self.client.close()


if __name__ == "__main__":
    # Test the scraper
    scraper = FacebookMarketplaceScraper()
    try:
        if scraper.enabled:
            items = scraper.search("purple pillow")
            print(f"Found {len(items)} items")
            for item in items[:5]:
                print(f"  - {item.title}: ${item.price}")
        else:
            print("Scraper not enabled - set FB_SESSION_COOKIE to test")
    finally:
        scraper.close()
