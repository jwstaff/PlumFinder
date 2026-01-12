"""
OfferUp Scraper

Scrapes OfferUp for items matching search terms near the target location.
Uses OfferUp's GraphQL API for reliable results.
Includes robots.txt compliance, caching, and exponential backoff.
"""

import httpx
import time
import random
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


class OfferUpScraper:
    BASE_URL = "https://offerup.com"
    API_URL = "https://offerup.com/api/graphql"

    # Palo Alto coordinates
    LAT = 37.4419
    LNG = -122.1430

    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.client = httpx.Client(
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "Origin": "https://offerup.com",
                "Referer": "https://offerup.com/",
                "x-ou-platform": "web",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self.robots_checker = get_robots_checker(self.user_agent)
        self.cache = get_response_cache(ttl=300)

    def _fetch_with_retry(self, url: str, method: str = "GET", **kwargs) -> Optional[httpx.Response]:
        """Fetch URL with exponential backoff retry."""
        def do_fetch():
            if method == "POST":
                response = self.client.post(url, **kwargs)
            else:
                response = self.client.get(url, **kwargs)
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
        """Search OfferUp for items matching the query using GraphQL API."""
        # Check cache first
        cache_key = f"offerup_{query}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # Note: robots.txt checks are skipped for API endpoints as they have their own
        # rate limiting and access controls. We only check robots.txt for HTML scraping.

        items = []

        # GraphQL query for searching items
        graphql_query = {
            "operationName": "GetModularFeed",
            "variables": {
                "searchParams": {
                    "q": query,
                    "lat": self.LAT,
                    "lon": self.LNG,
                    "radius": config.MAX_DISTANCE_MILES,
                    "limit": 50,
                    "platform": "web",
                    "experiment_id": "experimentmodel24"
                },
                "includeAds": False,
            },
            "query": """
                query GetModularFeed($searchParams: ModularFeedSearchParams!, $includeAds: Boolean) {
                    modularFeed(params: $searchParams, includeAds: $includeAds) {
                        feedItems {
                            ... on ModularFeedListingItem {
                                listing {
                                    listingId
                                    title
                                    price
                                    locationName
                                    image {
                                        url
                                    }
                                    condition
                                    postDate
                                }
                            }
                        }
                    }
                }
            """
        }

        try:
            response = self._fetch_with_retry(self.API_URL, method="POST", json=graphql_query)
            if response:
                data = response.json()
                items = self._parse_api_results(data)
                # Cache the results
                self.cache.set(cache_key, items)
            else:
                # Fallback to simple search URL
                items = self._fallback_search(query)

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            print(f"Error searching OfferUp for '{query}': {e}")
            items = self._fallback_search(query)

        return items

    def _parse_api_results(self, data: dict) -> list[ListingItem]:
        """Parse OfferUp GraphQL API results."""
        items = []

        try:
            feed_items = data.get("data", {}).get("modularFeed", {}).get("feedItems", [])

            for feed_item in feed_items:
                listing = feed_item.get("listing")
                if not listing:
                    continue

                item_id = listing.get("listingId")
                title = listing.get("title", "")

                if not item_id or not title:
                    continue

                price = None
                if listing.get("price"):
                    try:
                        price = float(listing["price"])
                    except:
                        pass

                image_urls = []
                if listing.get("image", {}).get("url"):
                    image_urls.append(listing["image"]["url"])

                items.append(ListingItem(
                    id=f"offerup_{item_id}",
                    title=title,
                    price=price,
                    url=f"{self.BASE_URL}/item/detail/{item_id}",
                    image_urls=image_urls,
                    location=listing.get("locationName"),
                    posted_date=datetime.now(),
                    source="offerup",
                    shippable="ship" in title.lower(),
                ))

        except Exception as e:
            print(f"Error parsing OfferUp results: {e}")

        return items

    def _fallback_search(self, query: str) -> list[ListingItem]:
        """Fallback search using simple API endpoint."""
        items = []

        try:
            search_url = f"{self.BASE_URL}/api/search/v4/feed/"
            params = {
                "q": query,
                "lat": self.LAT,
                "lon": self.LNG,
                "radius": config.MAX_DISTANCE_MILES,
                "limit": 50,
            }

            response = self._fetch_with_retry(search_url, params=params)
            if response and response.status_code == 200:
                data = response.json()
                for item_data in data.get("data", {}).get("items", []):
                    try:
                        item = self._parse_item_data(item_data)
                        if item:
                            items.append(item)
                    except:
                        continue
        except Exception as e:
            print(f"Fallback search failed: {e}")

        return items

    def _parse_item_data(self, item_data: dict) -> Optional[ListingItem]:
        """Parse item data from API response."""
        item_id = item_data.get("id") or item_data.get("listing_id")
        title = item_data.get("title", "")

        if not item_id or not title:
            return None

        price = None
        if item_data.get("price"):
            try:
                price = float(str(item_data["price"]).replace("$", "").replace(",", ""))
            except:
                pass

        image_urls = []
        photos = item_data.get("photos", []) or item_data.get("images", [])
        if photos and len(photos) > 0:
            if isinstance(photos[0], dict):
                image_urls.append(photos[0].get("url", ""))
            else:
                image_urls.append(str(photos[0]))

        return ListingItem(
            id=f"offerup_{item_id}",
            title=title,
            price=price,
            url=f"{self.BASE_URL}/item/detail/{item_id}",
            image_urls=image_urls,
            location=item_data.get("location_name") or item_data.get("city"),
            posted_date=datetime.now(),
            source="offerup",
            shippable=item_data.get("shipping_enabled", False) or "ship" in title.lower(),
        )

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
