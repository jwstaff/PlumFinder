# PlumFinder

An automated daily web scraper that searches multiple marketplaces for plum/purple-colored home accent pieces and delivers curated findings via email.

## Overview

PlumFinder scans Craigslist, eBay, and Etsy daily for interior design pieces (pillows, throws, vases, planters, ottomans, curtains) in plum/purple colors within 20 miles of Palo Alto, CA. It uses image analysis and keyword matching to detect colors, ranks items by relevance, and sends a daily email digest.

## Features

- **Multi-Source Scraping** - Craigslist, eBay (API + fallback), Etsy (API + fallback)
- **Intelligent Color Detection** - Combines keyword matching with image analysis (ColorThief, histogram analysis, HSV filtering)
- **Smart Ranking** - Composite score based on color match, recency, price, and proximity
- **Deduplication** - Tracks seen items to never send duplicates
- **Daily Email Digest** - Top 30 ranked items with images, prices, and direct links
- **Automated Scheduling** - GitHub Actions runs daily at 8 PM PST
- **Ethical Scraping** - robots.txt compliance, rate limiting, exponential backoff

## Tech Stack

- Python 3.11
- httpx (HTTP client)
- BeautifulSoup4 (HTML parsing)
- ColorThief + Pillow (image analysis)
- Resend (email delivery)
- Turso/SQLite (item tracking)
- GitHub Actions (automation)

## Installation

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
cd PlumFinder
pip install -r requirements.txt
cp .env.example .env
```

### Configure Environment Variables

Edit `.env` with your API keys:

```env
# Required
RESEND_API_KEY=your-resend-api-key

# Optional (improves reliability)
EBAY_APP_ID=your-ebay-app-id
ETSY_API_KEY=your-etsy-api-key

# Optional (cloud database, falls back to local SQLite)
TURSO_DATABASE_URL=libsql://your-db.turso.io
TURSO_AUTH_TOKEN=your-auth-token
```

## Usage

### Run Locally

```bash
# Full pipeline with email
python src/main.py

# Test mode (no email)
python src/main.py --test

# Reset database
python src/main.py --reset
```

### Automated Daily Runs

The included GitHub Actions workflow runs daily at 4 AM UTC (8 PM PST). Configure these GitHub secrets:
- `RESEND_API_KEY`
- `EBAY_APP_ID` (optional)
- `ETSY_API_KEY` (optional)
- `TURSO_DATABASE_URL` (optional)
- `TURSO_AUTH_TOKEN` (optional)

## Project Structure

```
PlumFinder/
├── src/
│   ├── main.py              # Pipeline orchestrator
│   ├── scrapers/
│   │   ├── craigslist.py    # Craigslist scraper
│   │   ├── ebay.py          # eBay API + fallback
│   │   ├── etsy.py          # Etsy API + fallback
│   │   └── utils.py         # Rate limiting, caching
│   ├── analyzer/
│   │   └── color_detection.py  # Image & keyword analysis
│   ├── database/
│   │   └── tracker.py       # Item tracking & dedup
│   └── mailer/
│       └── sender.py        # Email generation
├── config.py                # Search terms, filters, settings
├── data/
│   └── seen_items.db        # Local SQLite database
└── .github/workflows/
    └── daily-scan.yml       # GitHub Actions workflow
```

## How It Works

1. Scrape all marketplace sources
2. Filter by excluded categories (candles, shoes, etc.)
3. Remove previously seen items
4. Analyze images for plum/purple colors
5. Calculate composite ranking score
6. Select top 30 items
7. Send HTML email digest
8. Track items to prevent duplicates

## Configuration

Edit `config.py` to customize:
- Target location and distance radius
- Search terms (28 predefined home accent categories)
- Exclusion terms (60+ non-relevant items)
- Color detection thresholds
- Email settings
