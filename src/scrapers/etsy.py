"""
Etsy Scraper

Uses the official Etsy Open API v3 for reliable, legal access to listings.
Falls back to HTML scraping if API key is not configured.

API Documentation: https://developers.etsy.com/documentation/
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


class EtsyScraper:
    BASE_URL = "https://www.etsy.com"
    API_BASE_URL = "https://openapi.etsy.com/v3"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self):
        self.api_key = config.ETSY_API_KEY
        self.use_api = bool(self.api_key)

        # Use comprehensive browser-like headers for HTML fallback
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self._cookies_set = False

        if self.use_api:
            print("Etsy scraper using official Open API v3")
        else:
            print("Etsy scraper using HTML fallback (set ETSY_API_KEY for API access)")

    def search(self, query: str) -> list[ListingItem]:
        """Search Etsy for items matching the query."""
        if self.use_api:
            items = self._search_api(query)
            if items is not None:
                return items
            print("Falling back to HTML scraping...")

        return self._search_html(query)

    def _search_api(self, query: str) -> Optional[list[ListingItem]]:
        """Search using the official Etsy Open API v3."""
        items = []

        try:
            headers = {
                "x-api-key": self.api_key,
                "Accept": "application/json",
            }

            # Etsy Open API search endpoint
            api_url = f"{self.API_BASE_URL}/application/listings/active"

            params = {
                "keywords": query,
                "sort_on": "created",
                "sort_order": "desc",
                "limit": 50,
                "includes": "Images",
            }

            response = self.client.get(api_url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                items = self._parse_api_response(data)
                time.sleep(config.REQUEST_DELAY)
            elif response.status_code == 401:
                print("Etsy API key invalid or expired")
                self.use_api = False
                return None
            elif response.status_code == 403:
                print("Etsy API access forbidden - check API key permissions")
                self.use_api = False
                return None
            elif response.status_code == 429:
                print("Etsy API rate limited, waiting...")
                time.sleep(60)  # Wait a minute before retrying
                return None
            else:
                print(f"Etsy API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"Error searching Etsy API for '{query}': {e}")
            return None

        return items

    def _parse_api_response(self, data: dict) -> list[ListingItem]:
        """Parse Etsy Open API v3 response."""
        items = []

        results = data.get("results", [])

        for listing_data in results:
            try:
                listing_id = listing_data.get("listing_id")
                if not listing_id:
                    continue

                title = listing_data.get("title", "")
                if not title:
                    continue

                # Extract price (Etsy returns price in cents for some currencies)
                price = None
                price_data = listing_data.get("price", {})
                if price_data:
                    amount = price_data.get("amount")
                    divisor = price_data.get("divisor", 100)
                    if amount is not None:
                        price = float(amount) / float(divisor)

                # Build listing URL
                url = listing_data.get("url", f"{self.BASE_URL}/listing/{listing_id}")

                # Get images
                image_urls = []
                images = listing_data.get("images", [])
                if images:
                    for img in images[:3]:  # Get up to 3 images
                        # Prefer larger image sizes
                        img_url = (
                            img.get("url_570xN") or
                            img.get("url_fullxfull") or
                            img.get("url_170x135") or
                            img.get("url_75x75")
                        )
                        if img_url:
                            image_urls.append(img_url)

                # Get shop location
                location = None
                shop = listing_data.get("shop", {})
                if shop:
                    city = shop.get("city", "")
                    location = city if city else "Etsy Seller"
                else:
                    location = "Etsy Seller"

                # Parse creation timestamp
                posted_date = datetime.now()
                created_timestamp = listing_data.get("created_timestamp")
                if created_timestamp:
                    try:
                        posted_date = datetime.fromtimestamp(created_timestamp)
                    except:
                        pass

                items.append(ListingItem(
                    id=f"etsy_{listing_id}",
                    title=title,
                    price=price,
                    url=url,
                    image_urls=image_urls,
                    location=location,
                    posted_date=posted_date,
                    source="etsy",
                    shippable=True,  # Etsy is shipping-only
                ))

            except Exception as e:
                continue

        return items

    def _init_session(self):
        """Initialize session by visiting homepage first (for HTML fallback)."""
        if self._cookies_set:
            return

        try:
            response = self.client.get(self.BASE_URL)
            self._cookies_set = True
            time.sleep(1)
        except:
            pass

    def _search_html(self, query: str) -> list[ListingItem]:
        """Search Etsy using HTML scraping (fallback)."""
        items = []

        self._init_session()

        params = {
            "q": query,
            "explicit": "1",
            "ship_to": "US",
            "order": "date_desc",
            "ref": "search_bar",
        }

        try:
            response = self.client.get(self.SEARCH_URL, params=params)

            if response.status_code == 403:
                print("Etsy returned 403 for HTML scraping")
                return items
            elif response.status_code == 200:
                items = self._parse_html_results(response.text)

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching Etsy for '{query}': {e}")

        return items

    def _parse_html_results(self, html: str) -> list[ListingItem]:
        """Parse Etsy search results from HTML."""
        items = []

        # First try to extract from embedded JSON
        json_items = self._extract_json_from_html(html)
        if json_items:
            return json_items

        soup = BeautifulSoup(html, "lxml")

        listings = soup.select('[data-listing-id], .v2-listing-card, .listing-link, [data-listing-card-v2]')

        for listing in listings:
            try:
                item = self._parse_html_listing(listing)
                if item:
                    items.append(item)
            except Exception as e:
                continue

        return items

    def _extract_json_from_html(self, html: str) -> list[ListingItem]:
        """Extract listing data from embedded JSON in HTML."""
        items = []

        try:
            patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});',
                r'"listings":\s*(\[.+?\])',
                r'data-search-results=\'(\{.+?\})\'',
                r'"searchResults":\s*(\{.+?\})',
            ]

            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        if isinstance(data, list):
                            for item_data in data:
                                item = self._create_item_from_data(item_data)
                                if item:
                                    items.append(item)
                        elif isinstance(data, dict):
                            items.extend(self._extract_listings_recursive(data))
                        if items:
                            break
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            pass

        return items

    def _extract_listings_recursive(self, data, depth=0) -> list[ListingItem]:
        """Recursively extract listings from nested data."""
        items = []

        if depth > 8:
            return items

        if isinstance(data, dict):
            if "listing_id" in data or ("id" in data and "title" in data):
                item = self._create_item_from_data(data)
                if item:
                    items.append(item)
            else:
                for value in data.values():
                    items.extend(self._extract_listings_recursive(value, depth + 1))

        elif isinstance(data, list):
            for item in data:
                items.extend(self._extract_listings_recursive(item, depth + 1))

        return items

    def _create_item_from_data(self, data: dict) -> Optional[ListingItem]:
        """Create ListingItem from data dict."""
        try:
            item_id = data.get("listing_id") or data.get("id")
            if not item_id:
                return None

            title = data.get("title", "")
            if not title:
                return None

            price = None
            price_data = data.get("price") or data.get("Price")
            if price_data:
                if isinstance(price_data, dict):
                    price_data = price_data.get("amount") or price_data.get("raw")
                try:
                    price = float(str(price_data).replace("$", "").replace(",", ""))
                except:
                    pass

            image_urls = []
            img = data.get("image") or data.get("Images") or data.get("primary_image")
            if img:
                if isinstance(img, dict):
                    img = img.get("url_570xN") or img.get("url") or img.get("src")
                if isinstance(img, str) and img.startswith("http"):
                    image_urls.append(img)

            url = data.get("url", f"{self.BASE_URL}/listing/{item_id}")
            if not url.startswith("http"):
                url = self.BASE_URL + url

            return ListingItem(
                id=f"etsy_{item_id}",
                title=title,
                price=price,
                url=url,
                image_urls=image_urls,
                location="Etsy Seller",
                posted_date=datetime.now(),
                source="etsy",
                shippable=True,
            )

        except:
            return None

    def _parse_html_listing(self, listing) -> Optional[ListingItem]:
        """Parse a single Etsy listing from HTML."""
        try:
            item_id = listing.get("data-listing-id")

            link = listing if listing.name == 'a' else listing.select_one('a[href*="/listing/"]')
            if not link:
                return None

            url = link.get("href", "")
            if not url:
                return None

            if not item_id:
                match = re.search(r"/listing/(\d+)", url)
                item_id = match.group(1) if match else None

            if not item_id:
                return None

            if not url.startswith("http"):
                url = self.BASE_URL + url
            url = url.split("?")[0]

            title_elem = listing.select_one('[class*="title"], h3, h2, .v2-listing-card__title, [data-listing-card-title]')
            title = title_elem.get_text(strip=True) if title_elem else ""

            if not title:
                title = link.get("title", "") or link.get("aria-label", "")

            price = None
            price_elem = listing.select_one('[class*="price"], .currency-value, span[class*="Price"], [data-buy-box-region-price]')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r"([\d,]+\.?\d*)", price_text)
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))

            image_urls = []
            img = listing.select_one("img")
            if img:
                src = img.get("src", "") or img.get("data-src", "") or img.get("srcset", "").split()[0]
                if src and src.startswith("http"):
                    src = re.sub(r"_\d+x\d+", "_680x", src)
                    image_urls.append(src)

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
                shippable=True,
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
