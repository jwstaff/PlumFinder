"""
Email Sender Module

Sends daily digest emails with found items using Resend.
"""

import resend
from datetime import datetime
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


class EmailSender:
    def __init__(self):
        if config.RESEND_API_KEY:
            resend.api_key = config.RESEND_API_KEY
            self.enabled = True
        else:
            print("Email sender disabled: No RESEND_API_KEY configured")
            self.enabled = False

    def send_digest(self, items: list, recipients: list = None) -> bool:
        """Send the daily digest email with found items."""
        if not self.enabled:
            print("Email sending is disabled")
            return False

        if not items:
            print("No items to send")
            return False

        if recipients is None:
            recipients = config.RECIPIENT_EMAILS

        html_content = self._generate_html(items)
        plain_content = self._generate_plain_text(items)

        try:
            response = resend.Emails.send({
                "from": config.SENDER_EMAIL,
                "to": recipients,
                "subject": f"Plum Finds - {len(items)} New Items ({datetime.now().strftime('%B %d')})",
                "html": html_content,
                "text": plain_content,
            })

            print(f"Email sent successfully: {response}")
            return True

        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def _generate_html(self, items: list) -> str:
        """Generate HTML email content."""
        items_html = ""

        for i, item in enumerate(items, 1):
            price_str = f"${item.price:,.0f}" if item.price else "Price not listed"
            location_str = item.location or "Location not specified"
            source_badge = "CL" if item.source == "craigslist" else "FB"
            source_color = "#ff6600" if item.source == "craigslist" else "#1877f2"

            # Get first image or placeholder
            image_url = item.image_urls[0] if item.image_urls else "https://via.placeholder.com/200x150/4a0080/ffffff?text=No+Image"

            # Color score indicator
            score_percent = int(item.color_score * 100)
            score_color = "#9b59b6" if score_percent >= 70 else "#8e44ad" if score_percent >= 50 else "#7f8c8d"

            items_html += f"""
            <div style="background: #ffffff; border-radius: 12px; overflow: hidden; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="display: flex; flex-wrap: wrap;">
                    <div style="flex: 0 0 200px; max-width: 200px;">
                        <a href="{item.url}" target="_blank">
                            <img src="{image_url}" alt="{item.title[:50]}" style="width: 200px; height: 150px; object-fit: cover;">
                        </a>
                    </div>
                    <div style="flex: 1; padding: 15px; min-width: 200px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <span style="background: {source_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{source_badge}</span>
                            <span style="background: {score_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{score_percent}% plum</span>
                        </div>
                        <h3 style="margin: 0 0 8px 0; font-size: 16px; color: #333;">
                            <a href="{item.url}" target="_blank" style="color: #4a0080; text-decoration: none;">{item.title[:80]}</a>
                        </h3>
                        <p style="margin: 0 0 5px 0; font-size: 20px; font-weight: bold; color: #2c3e50;">{price_str}</p>
                        <p style="margin: 0; font-size: 13px; color: #7f8c8d;">{location_str}</p>
                        {"<span style='background: #27ae60; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-top: 5px; display: inline-block;'>Ships</span>" if item.shippable else ""}
                    </div>
                </div>
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f0f7; margin: 0; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto;">
                <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, #4a0080, #7b1fa2); border-radius: 12px 12px 0 0;">
                    <h1 style="margin: 0; color: white; font-size: 28px;">Plum Finds</h1>
                    <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">
                        {len(items)} new plum accent pieces found today
                    </p>
                </div>

                <div style="background: #f9f5fb; padding: 20px; border-radius: 0 0 12px 12px;">
                    <p style="color: #666; font-size: 14px; margin: 0 0 20px 0;">
                        Here are today's finds within 20 miles of Palo Alto (94301) or available for shipping:
                    </p>

                    {items_html}

                    <div style="text-align: center; padding: 20px; color: #888; font-size: 12px;">
                        <p style="margin: 0;">
                            Sent with care by PlumFinder<br>
                            <a href="https://github.com/jwstaff/PlumFinder" style="color: #7b1fa2;">View on GitHub</a>
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _generate_plain_text(self, items: list) -> str:
        """Generate plain text email content."""
        lines = [
            f"PLUM FINDS - {len(items)} New Items",
            f"Date: {datetime.now().strftime('%B %d, %Y')}",
            "",
            "=" * 50,
            "",
        ]

        for i, item in enumerate(items, 1):
            price_str = f"${item.price:,.0f}" if item.price else "Price not listed"
            location_str = item.location or "Location not specified"

            lines.extend([
                f"{i}. {item.title[:60]}",
                f"   Price: {price_str}",
                f"   Location: {location_str}",
                f"   Source: {item.source.title()}",
                f"   Link: {item.url}",
                "",
            ])

        lines.extend([
            "=" * 50,
            "",
            "Sent by PlumFinder",
        ])

        return "\n".join(lines)

    def send_test_email(self, recipients: list = None) -> bool:
        """Send a test email to verify configuration."""
        if not self.enabled:
            print("Email sending is disabled")
            return False

        if recipients is None:
            recipients = config.RECIPIENT_EMAILS

        try:
            response = resend.Emails.send({
                "from": config.SENDER_EMAIL,
                "to": recipients,
                "subject": "PlumFinder Test Email",
                "html": """
                    <div style="font-family: sans-serif; padding: 20px;">
                        <h1 style="color: #4a0080;">PlumFinder is working!</h1>
                        <p>Your email configuration is set up correctly.</p>
                        <p>You'll start receiving daily plum finds at 8 PM PT.</p>
                    </div>
                """,
                "text": "PlumFinder is working! Your email configuration is set up correctly.",
            })

            print(f"Test email sent successfully: {response}")
            return True

        except Exception as e:
            print(f"Error sending test email: {e}")
            return False


if __name__ == "__main__":
    # Test the email sender
    sender = EmailSender()

    if sender.enabled:
        print("Email sender is configured")
        # Uncomment to send a test email:
        # sender.send_test_email()
    else:
        print("Email sender is not configured - set RESEND_API_KEY")
