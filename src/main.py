#!/usr/bin/env python3
"""
PlumFinder - Daily Plum Accent Piece Finder

This script:
1. Scrapes Craigslist and Facebook Marketplace for home goods
2. Analyzes images to detect plum/purple colors
3. Filters out previously seen items
4. Ranks items by recency, price, and proximity
5. Sends a daily email with the top 30 new items
"""

import sys
import os
from datetime import datetime
from geopy.distance import geodesic

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.scrapers import (
    CraigslistScraper,
    OfferUpScraper,
    MercariScraper,
    EbayScraper,
    EtsyScraper,
    PoshmarkScraper,
)
from src.analyzer import ColorAnalyzer
from src.database import ItemTracker
from src.mailer import EmailSender


def calculate_distance(location_str: str) -> float:
    """
    Estimate distance from target location.
    Returns MAX_DISTANCE_MILES if location can't be determined.
    """
    if not location_str:
        return config.MAX_DISTANCE_MILES

    # Simple heuristic: check for known nearby cities
    nearby_cities = {
        "palo alto": 0,
        "menlo park": 3,
        "stanford": 1,
        "mountain view": 5,
        "los altos": 4,
        "redwood city": 7,
        "sunnyvale": 8,
        "san jose": 15,
        "santa clara": 12,
        "cupertino": 10,
        "san mateo": 12,
        "fremont": 18,
        "oakland": 25,
        "san francisco": 30,
        "sf": 30,
    }

    location_lower = location_str.lower()

    for city, distance in nearby_cities.items():
        if city in location_lower:
            return distance

    # Default to max distance for unknown locations
    return config.MAX_DISTANCE_MILES


def calculate_score(item) -> float:
    """
    Calculate a composite score for ranking items.
    Higher scores are better.

    Factors:
    - Color match score (0-1): 40% weight
    - Recency (newer is better): 30% weight
    - Price value (lower is better, capped): 15% weight
    - Proximity (closer is better): 15% weight
    """
    # Color score (already 0-1)
    color_weight = 0.4
    color_score = item.color_score

    # Recency score (assume items from today are newest)
    recency_weight = 0.3
    if item.posted_date:
        hours_old = (datetime.now() - item.posted_date.replace(tzinfo=None)).total_seconds() / 3600
        recency_score = max(0, 1 - (hours_old / 168))  # 168 hours = 1 week
    else:
        recency_score = 0.5

    # Price score (lower is better, normalize to 0-1)
    price_weight = 0.15
    if item.price and item.price > 0:
        # Assume $0 is best, $500+ is worst for accent pieces
        price_score = max(0, 1 - (item.price / 500))
    else:
        price_score = 0.5  # Unknown price gets middle score

    # Proximity score (closer is better)
    proximity_weight = 0.15
    if item.shippable:
        proximity_score = 1.0  # Shippable items get full score
    elif item.distance_miles is not None:
        proximity_score = max(0, 1 - (item.distance_miles / config.MAX_DISTANCE_MILES))
    else:
        proximity_score = 0.5

    # Calculate weighted score
    total_score = (
        color_score * color_weight +
        recency_score * recency_weight +
        price_score * price_weight +
        proximity_score * proximity_weight
    )

    return total_score


def run_pipeline():
    """Run the full PlumFinder pipeline."""
    print("=" * 60)
    print(f"PlumFinder - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Initialize components
    scrapers = {
        "craigslist": CraigslistScraper(),
        "offerup": OfferUpScraper(),
        "mercari": MercariScraper(),
        "ebay": EbayScraper(),
        "etsy": EtsyScraper(),
        "poshmark": PoshmarkScraper(),
    }
    color_analyzer = ColorAnalyzer()
    tracker = ItemTracker()
    email_sender = EmailSender()

    try:
        # Step 1: Scrape listings from all sources
        print("\n[1/6] Scraping listings from all sources...")
        all_items = []

        for name, scraper in scrapers.items():
            try:
                items = scraper.search_all_terms()
                all_items.extend(items)
            except Exception as e:
                print(f"Error scraping {name}: {e}")

        print(f"Total items found: {len(all_items)}")

        if not all_items:
            print("No items found. Exiting.")
            return

        # Step 2: Filter out previously seen items
        print("\n[2/6] Filtering seen items...")
        new_items = tracker.filter_new_items(all_items)
        print(f"New items: {len(new_items)} (filtered {len(all_items) - len(new_items)} duplicates)")

        if not new_items:
            print("No new items found. Exiting.")
            return

        # Step 3: Analyze colors
        print("\n[3/6] Analyzing colors...")
        for i, item in enumerate(new_items):
            if i % 10 == 0:
                print(f"  Analyzing item {i+1}/{len(new_items)}...")

            item.color_score = color_analyzer.analyze_item(item)

            # Calculate distance
            item.distance_miles = calculate_distance(item.location)

        # Step 4: Filter by color score threshold
        print("\n[4/6] Filtering by color match...")
        COLOR_THRESHOLD = 0.3
        plum_items = [item for item in new_items if item.color_score >= COLOR_THRESHOLD]
        print(f"Items with plum colors: {len(plum_items)}")

        if not plum_items:
            print("No plum-colored items found. Exiting.")
            return

        # Step 5: Rank and select top items
        print("\n[5/6] Ranking items...")
        for item in plum_items:
            item._score = calculate_score(item)

        # Sort by score (descending)
        plum_items.sort(key=lambda x: x._score, reverse=True)

        # Select top N items
        top_items = plum_items[:config.MAX_ITEMS_PER_EMAIL]
        print(f"Selected top {len(top_items)} items")

        # Fetch additional details for top items (images, etc.)
        print("  Fetching listing details...")
        for item in top_items:
            if item.source == "craigslist" and hasattr(scrapers.get("craigslist"), "get_listing_details"):
                scrapers["craigslist"].get_listing_details(item)

        # Step 6: Mark items as seen and send email
        print("\n[6/6] Sending email...")
        for item in top_items:
            tracker.mark_seen(item)

        success = email_sender.send_digest(top_items)

        if success:
            tracker.mark_sent([item.id for item in top_items])
            tracker.record_email_sent(len(top_items), config.RECIPIENT_EMAIL)
            print(f"Successfully sent email with {len(top_items)} items!")
        else:
            print("Failed to send email")

        # Cleanup old items periodically
        tracker.cleanup_old_items(days=90)

        # Print stats
        print("\n" + "=" * 60)
        print("Stats:", tracker.get_stats())
        print("=" * 60)

    finally:
        # Cleanup
        for scraper in scrapers.values():
            try:
                scraper.close()
            except:
                pass
        color_analyzer.close()
        tracker.close()


def test_mode():
    """Run a quick test without sending email."""
    print("Running in TEST mode...")

    craigslist = CraigslistScraper()
    color_analyzer = ColorAnalyzer()

    try:
        # Just search for a couple terms
        items = craigslist.search("purple pillow")
        print(f"Found {len(items)} items")

        for item in items[:5]:
            item.color_score = color_analyzer.analyze_item(item)
            print(f"  - {item.title[:50]}: ${item.price}, color={item.color_score:.2f}")

    finally:
        craigslist.close()
        color_analyzer.close()


def reset_database():
    """Reset the database to start fresh."""
    print("Resetting database...")
    tracker = ItemTracker()
    cursor = tracker.connection.cursor()
    cursor.execute("DELETE FROM seen_items")
    cursor.execute("DELETE FROM email_history")
    tracker.connection.commit()
    print("Database reset complete")
    tracker.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_mode()
    elif len(sys.argv) > 1 and sys.argv[1] == "--reset":
        reset_database()
    elif os.getenv("RESET_DB") == "true":
        reset_database()
        run_pipeline()
    else:
        run_pipeline()
