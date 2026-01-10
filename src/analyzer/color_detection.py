"""
Color Detection Module

Analyzes images to detect plum/purple colors using:
1. Dominant color extraction with colorthief
2. Color histogram analysis
3. Keyword matching in titles/descriptions
"""

import httpx
import colorsys
from io import BytesIO
from PIL import Image
from colorthief import ColorThief
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


class ColorAnalyzer:
    # Plum/purple HSV ranges (0-360 for hue, 0-1 for sat/val)
    PLUM_RANGES = [
        {"hue_min": 270, "hue_max": 330, "name": "purple/plum"},
        {"hue_min": 330, "hue_max": 360, "name": "magenta/plum"},
        {"hue_min": 0, "hue_max": 15, "name": "red-violet"},
    ]

    def __init__(self):
        self.client = httpx.Client(timeout=15.0, follow_redirects=True)

    def analyze_item(self, item) -> float:
        """
        Analyze an item and return a color score (0.0 to 1.0).
        Combines image analysis with keyword matching.
        """
        scores = []

        # Check title for color keywords
        keyword_score = self._check_keywords(item.title)
        if keyword_score > 0:
            scores.append(keyword_score)

        # Analyze images
        for image_url in item.image_urls[:3]:  # Limit to first 3 images
            try:
                image_score = self._analyze_image(image_url)
                if image_score > 0:
                    scores.append(image_score)
            except Exception as e:
                print(f"Error analyzing image {image_url}: {e}")
                continue

        if not scores:
            return 0.0

        # Return weighted average (image analysis weighted higher)
        if len(scores) == 1 and keyword_score > 0:
            return keyword_score * 0.7  # Keyword only = lower confidence

        return max(scores)  # Return best match

    def _check_keywords(self, text: str) -> float:
        """Check text for color keywords and return a score."""
        if not text:
            return 0.0

        text_lower = text.lower()

        # Strong matches
        strong_keywords = ["plum", "eggplant", "aubergine"]
        for kw in strong_keywords:
            if kw in text_lower:
                return 0.9

        # Medium matches
        medium_keywords = ["purple", "violet", "grape"]
        for kw in medium_keywords:
            if kw in text_lower:
                return 0.7

        # Weak matches (could be plum-adjacent)
        weak_keywords = ["mauve", "lavender", "burgundy", "wine", "berry"]
        for kw in weak_keywords:
            if kw in text_lower:
                return 0.5

        return 0.0

    def _analyze_image(self, image_url: str) -> float:
        """Download and analyze an image for plum/purple colors."""
        try:
            response = self.client.get(image_url)
            response.raise_for_status()

            image_data = BytesIO(response.content)

            # Get dominant colors using ColorThief
            color_thief = ColorThief(image_data)

            # Get the dominant color
            dominant_color = color_thief.get_color(quality=5)
            dominant_score = self._score_color(dominant_color)

            # Get palette for more thorough analysis
            try:
                palette = color_thief.get_palette(color_count=6, quality=5)
                palette_scores = [self._score_color(color) for color in palette]
                best_palette_score = max(palette_scores) if palette_scores else 0
            except:
                best_palette_score = 0

            # Also do histogram-based analysis for more accuracy
            histogram_score = self._analyze_histogram(image_data)

            # Combine scores
            return max(dominant_score, best_palette_score * 0.9, histogram_score * 0.8)

        except Exception as e:
            print(f"Error in image analysis: {e}")
            return 0.0

    def _score_color(self, rgb: tuple) -> float:
        """Score an RGB color for how plum/purple it is."""
        r, g, b = [x / 255.0 for x in rgb]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        h = h * 360  # Convert to degrees

        # Check if color is too desaturated or too dark/light
        if s < 0.15 or v < 0.15 or v > 0.95:
            return 0.0

        # Check if hue is in plum/purple range
        for range_def in self.PLUM_RANGES:
            if range_def["hue_min"] <= h <= range_def["hue_max"]:
                # Score based on saturation and value
                # Plum is typically medium saturation and value
                sat_score = 1.0 - abs(s - 0.5) * 0.5  # Prefer medium saturation
                val_score = 1.0 - abs(v - 0.5) * 0.5  # Prefer medium value

                base_score = 0.8
                return base_score * sat_score * val_score

        return 0.0

    def _analyze_histogram(self, image_data: BytesIO) -> float:
        """Analyze image histogram for purple pixels."""
        try:
            image_data.seek(0)
            img = Image.open(image_data)
            img = img.convert("RGB")

            # Resize for faster processing
            img.thumbnail((100, 100))

            pixels = list(img.getdata())
            total_pixels = len(pixels)

            if total_pixels == 0:
                return 0.0

            purple_pixels = 0

            for r, g, b in pixels:
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                h = h * 360

                # Check if pixel is in purple range with decent saturation
                if s > 0.2 and v > 0.2:
                    for range_def in self.PLUM_RANGES:
                        if range_def["hue_min"] <= h <= range_def["hue_max"]:
                            purple_pixels += 1
                            break

            purple_ratio = purple_pixels / total_pixels

            # Score based on percentage of purple pixels
            if purple_ratio > 0.3:
                return 0.95
            elif purple_ratio > 0.2:
                return 0.85
            elif purple_ratio > 0.1:
                return 0.7
            elif purple_ratio > 0.05:
                return 0.5
            elif purple_ratio > 0.02:
                return 0.3

            return 0.0

        except Exception as e:
            print(f"Error in histogram analysis: {e}")
            return 0.0

    def close(self):
        self.client.close()


if __name__ == "__main__":
    # Test with a sample purple image
    analyzer = ColorAnalyzer()

    # Test keyword matching
    print("Keyword tests:")
    print(f"  'Plum velvet pillow': {analyzer._check_keywords('Plum velvet pillow')}")
    print(f"  'Purple throw blanket': {analyzer._check_keywords('Purple throw blanket')}")
    print(f"  'Blue pillow': {analyzer._check_keywords('Blue pillow')}")

    analyzer.close()
