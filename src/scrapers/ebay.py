"""
eBay Scraper

Uses the official eBay Browse API for reliable, legal access to listings.
Falls back to HTML scraping if API key is not configured.

API Documentation: https://developer.ebay.com/api-docs/buy/browse/overview.html
"""

import httpx
import time
import random
import re
import base64
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
    API_BASE_URL = "https://api.ebay.com"
    AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = f"{BASE_URL}/sch/i.html"

    def __init__(self):
        self.app_id = config.EBAY_APP_ID
        self.use_api = bool(self.app_id)
        self._access_token = None
        self._token_expiry = 0

        self.client = httpx.Client(
            headers={
                "User-Agent": random.choice(config.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=30.0,
            follow_redirects=True,
        )

        if self.use_api:
            print("eBay scraper using official Browse API")
        else:
            print("eBay scraper using HTML fallback (set EBAY_APP_ID for API access)")

    def _get_access_token(self) -> Optional[str]:
        """
        Get OAuth access token using client credentials flow.
        eBay Browse API uses application-only authentication.
        """
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        if not self.app_id:
            return None

        try:
            # For Browse API, we use the App ID as both client_id
            # The Browse API guest access only requires the App ID
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {base64.b64encode(f'{self.app_id}:'.encode()).decode()}",
            }

            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            }

            response = self.client.post(self.AUTH_URL, headers=headers, data=data)

            if response.status_code == 200:
                token_data = response.json()
                self._access_token = token_data.get("access_token")
                # Token typically expires in 7200 seconds (2 hours)
                expires_in = token_data.get("expires_in", 7200)
                self._token_expiry = time.time() + expires_in - 60  # Refresh 1 min early
                return self._access_token
            else:
                print(f"eBay OAuth failed: {response.status_code} - {response.text[:200]}")
                self.use_api = False

        except Exception as e:
            print(f"eBay OAuth error: {e}")
            self.use_api = False

        return None

    def search(self, query: str) -> list[ListingItem]:
        """Search eBay for items matching the query."""
        if self.use_api:
            items = self._search_api(query)
            if items is not None:
                return items
            # Fall back to HTML if API fails
            print("Falling back to HTML scraping...")

        return self._search_html(query)

    def _search_api(self, query: str) -> Optional[list[ListingItem]]:
        """Search using the official eBay Browse API."""
        token = self._get_access_token()
        if not token:
            return None

        items = []

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country=US,zip={config.TARGET_ZIP}",
                "Accept": "application/json",
            }

            # Browse API search endpoint
            api_url = f"{self.API_BASE_URL}/buy/browse/v1/item_summary/search"

            params = {
                "q": query,
                "filter": ",".join([
                    "buyingOptions:{FIXED_PRICE}",  # Buy It Now only
                    "conditionIds:{3000|4000|5000|6000}",  # Used conditions
                    f"itemLocationCountry:US",
                ]),
                "sort": "newlyListed",
                "limit": "50",
            }

            response = self.client.get(api_url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                items = self._parse_api_response(data)
                time.sleep(config.REQUEST_DELAY)
            elif response.status_code == 401:
                # Token expired, clear it
                self._access_token = None
                self._token_expiry = 0
                print("eBay API token expired, will retry...")
                return None
            else:
                print(f"eBay API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"Error searching eBay API for '{query}': {e}")
            return None

        return items

    def _parse_api_response(self, data: dict) -> list[ListingItem]:
        """Parse eBay Browse API response."""
        items = []

        item_summaries = data.get("itemSummaries", [])

        for item_data in item_summaries:
            try:
                item_id = item_data.get("itemId", "")
                if not item_id:
                    continue

                title = item_data.get("title", "")
                if not title:
                    continue

                # Extract price
                price = None
                price_data = item_data.get("price", {})
                if price_data:
                    try:
                        price = float(price_data.get("value", 0))
                    except (ValueError, TypeError):
                        pass

                # Get item URL
                url = item_data.get("itemWebUrl", f"https://www.ebay.com/itm/{item_id}")

                # Get image
                image_urls = []
                image_data = item_data.get("image", {})
                if image_data:
                    img_url = image_data.get("imageUrl", "")
                    if img_url:
                        image_urls.append(img_url)

                # Get thumbnails as backup
                if not image_urls:
                    thumbnails = item_data.get("thumbnailImages", [])
                    for thumb in thumbnails:
                        if thumb.get("imageUrl"):
                            image_urls.append(thumb["imageUrl"])
                            break

                # Get location
                location = None
                item_location = item_data.get("itemLocation", {})
                if item_location:
                    city = item_location.get("city", "")
                    state = item_location.get("stateOrProvince", "")
                    location = f"{city}, {state}".strip(", ")

                # Check shipping
                shipping_options = item_data.get("shippingOptions", [])
                shippable = len(shipping_options) > 0

                items.append(ListingItem(
                    id=f"ebay_{item_id}",
                    title=title,
                    price=price,
                    url=url,
                    image_urls=image_urls,
                    location=location if location else None,
                    posted_date=datetime.now(),
                    source="ebay",
                    shippable=shippable,
                ))

            except Exception as e:
                continue

        return items

    def _search_html(self, query: str) -> list[ListingItem]:
        """Search eBay using HTML scraping (fallback)."""
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

            items = self._parse_html_results(response.text)
            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching eBay for '{query}': {e}")

        return items

    def _parse_html_results(self, html: str) -> list[ListingItem]:
        """Parse eBay search results from HTML."""
        items = []
        soup = BeautifulSoup(html, "lxml")

        # eBay uses .srp-results li for listings
        listings = soup.select('.srp-results li, .s-item, [data-view]')

        for listing in listings:
            try:
                item = self._parse_html_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _parse_html_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single eBay listing from HTML."""
        try:
            # Find the item link
            link = listing.select_one('a[href*="/itm/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url or "pulsar" in url or "ebay.com/itm/" not in url:
                return None

            match = re.search(r"/itm/(\d+)", url)
            item_id = match.group(1) if match else None
            if not item_id:
                return None

            # Get title from link or heading
            title_elem = listing.select_one('[role="heading"], .s-item__title, h3')
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Fallback: get title from link text or aria-label
            if not title:
                title = link.get("aria-label", "") or link.get_text(strip=True)

            if not title or "shop on ebay" in title.lower():
                return None

            # Get price
            price = None
            price_elem = listing.select_one('[class*="price"], .s-item__price')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r"\$?([\d,]+\.?\d*)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            # Get image - look for ebayimg.com URLs
            image_urls = []
            img = listing.select_one('img[src*="ebayimg"], img[data-src*="ebayimg"]')
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src and src.startswith("http") and "gif" not in src.lower():
                    # Convert to larger image size
                    src = re.sub(r'/s-l\d+\.', '/s-l500.', src)
                    image_urls.append(src)

            # Fallback: any img with http src
            if not image_urls:
                img = listing.select_one('img[src^="http"]')
                if img:
                    src = img.get("src", "")
                    if "gif" not in src.lower() and "svg" not in src.lower():
                        image_urls.append(src)

            location_elem = listing.select_one('[class*="location"], .s-item__location')
            location = location_elem.get_text(strip=True) if location_elem else None

            shipping_elem = listing.select_one('[class*="shipping"], .s-item__shipping')
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
