import os
from dotenv import load_dotenv

load_dotenv()

# Location settings
TARGET_ZIP = "94301"
TARGET_LAT = 37.4419
TARGET_LON = -122.1430
MAX_DISTANCE_MILES = 20

# Search settings - focused on living room accent pieces
SEARCH_TERMS = [
    # Pillows & cushions
    "plum throw pillow", "purple accent pillow", "violet decorative pillow",
    "plum cushion cover", "purple velvet pillow",
    # Throws & blankets
    "plum throw blanket", "purple throw", "violet blanket",
    # Vases & decor
    "plum vase", "purple ceramic vase", "violet glass vase",
    "plum decorative bowl", "purple accent decor",
    # Planters
    "plum planter", "purple plant pot", "violet ceramic pot",
    # Accent furniture
    "plum ottoman", "purple accent table", "plum side table",
    # Curtains & textiles
    "plum curtains", "purple drapes", "plum curtain panels",
]

CATEGORIES = ["pillows", "throws", "vases", "planters", "ottomans", "curtains", "decor"]

# Excluded terms - items to filter out
EXCLUDED_TERMS = [
    # Candles & fragrances
    "candle", "candles", "wax", "scented", "fragrance", "incense", "diffuser",
    # Footwear
    "shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "heel", "heels",
    "sandal", "sandals", "slipper", "slippers", "footwear",
    # Clothing & fashion
    "dress", "shirt", "blouse", "pants", "jeans", "skirt", "jacket", "coat",
    "sweater", "cardigan", "top", "shorts", "leggings", "romper", "jumpsuit",
    "hoodie", "sweatshirt", "t-shirt", "tee", "polo", "blazer", "suit",
    # Accessories
    "purse", "handbag", "wallet", "belt", "scarf", "hat", "cap", "gloves",
    "jewelry", "necklace", "bracelet", "earring", "ring", "watch",
    # Beauty & personal
    "makeup", "lipstick", "nail polish", "perfume", "lotion", "shampoo",
    # Kids & toys
    "toy", "toys", "stuffed animal", "plush", "doll", "action figure",
    "baby", "infant", "toddler", "kids", "children",
    # Electronics
    "phone", "case", "iphone", "android", "tablet", "laptop", "computer",
    # Food & consumables
    "food", "candy", "chocolate", "snack", "drink", "wine", "coffee",
    # Other non-living-room items
    "bathroom", "kitchen", "garage", "car", "automotive", "tool",
    "exercise", "fitness", "gym", "sports", "bike", "bicycle",
    "book", "books", "magazine", "cd", "dvd", "vinyl", "record",
    "pet", "dog", "cat", "fish", "bird",
]

# Color detection settings (HSV ranges for plum/purple)
PLUM_HUE_MIN = 270
PLUM_HUE_MAX = 330
PLUM_SAT_MIN = 0.15
PLUM_VAL_MIN = 0.15

# Color keywords to search for
COLOR_KEYWORDS = ["plum", "purple", "violet", "eggplant", "aubergine", "mauve", "lavender", "grape"]

# Email settings
RECIPIENT_EMAILS = [
    "aditi.b84@gmail.com",
]
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
