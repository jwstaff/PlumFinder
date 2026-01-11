import os
from dotenv import load_dotenv

load_dotenv()

# Location settings
TARGET_ZIP = "94301"
TARGET_LAT = 37.4419
TARGET_LON = -122.1430
MAX_DISTANCE_MILES = 20

# Search settings
SEARCH_TERMS = [
    "plum pillow", "purple pillow", "violet pillow", "eggplant pillow",
    "plum vase", "purple vase", "violet vase",
    "plum plant pot", "purple planter", "violet pot",
    "plum side table", "purple accent table", "plum end table",
    "plum decor", "purple home decor", "plum accent",
    "plum throw", "purple throw blanket",
    "plum cushion", "purple cushion"
]

CATEGORIES = ["pillows", "vases", "planters", "tables", "decor", "home goods"]

# Color detection settings (HSV ranges for plum/purple)
PLUM_HUE_MIN = 270
PLUM_HUE_MAX = 330
PLUM_SAT_MIN = 0.15
PLUM_VAL_MIN = 0.15

# Color keywords to search for
COLOR_KEYWORDS = ["plum", "purple", "violet", "eggplant", "aubergine", "mauve", "lavender", "grape"]

# Email settings
RECIPIENT_EMAIL = "y2z18tu5h@mozmail.com"
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "plumfinder@resend.dev")

# API Keys (from environment)
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Official API keys for marketplace sites
EBAY_APP_ID = os.getenv("EBAY_APP_ID")  # eBay Browse API
ETSY_API_KEY = os.getenv("ETSY_API_KEY")  # Etsy Open API v3

# Scraping settings
REQUEST_DELAY = 2  # seconds between requests
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

# Output settings
MAX_ITEMS_PER_EMAIL = 30
