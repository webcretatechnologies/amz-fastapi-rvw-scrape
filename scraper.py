import re
import random
import asyncio
import logging
from html import unescape

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from bs4 import BeautifulSoup

from config import get_settings
from models import Review

logger = logging.getLogger("amazon_scraper")

# ──────────────────────────────────────────────
# Rotating User-Agent pool (real browser strings)
# ──────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


class AmazonReviewScraper:
    """
    Scrapes customer reviews from Amazon India's review portal pages
    using Playwright headless browser with automatic sign-in support.

    The /portal/customer-reviews/ URL requires authenticated access.
    When a sign-in redirect is detected, the scraper automatically
    logs in with configured Amazon credentials.

    Anti-blocking measures:
    - Headless Chromium with stealth settings
    - Rotating User-Agent per session
    - Random delays between page interactions
    - Viewport randomization to avoid fingerprinting
    - WebDriver flag removal
    - Human-like typing with random delays
    """

    def __init__(self):
        settings = get_settings()
        self.base_domain = settings.base_domain.rstrip("/")
        self.min_delay = settings.min_delay
        self.max_delay = settings.max_delay
        self.amazon_email = settings.amazon_email
        self.amazon_password = settings.amazon_password

    # ──────────────────────────────────────────
    # Random delay helper
    # ──────────────────────────────────────────
    async def _random_delay(self, min_s: float | None = None, max_s: float | None = None):
        """Sleep for a random duration."""
        low = min_s if min_s is not None else self.min_delay
        high = max_s if max_s is not None else self.max_delay
        delay = random.uniform(low, high)
        logger.info(f"Waiting {delay:.1f}s...")
        await asyncio.sleep(delay)

    # ──────────────────────────────────────────
    # Amazon sign-in handler
    # ──────────────────────────────────────────
    async def _handle_signin(self, page) -> bool:
        """
        Handle Amazon sign-in if redirected to login page.
        Returns True if sign-in was successful, False otherwise.
        """
        current_url = page.url

        if "ap/signin" not in current_url and "ap/signin" not in current_url:
            return True  # Not on sign-in page, no action needed

        if not self.amazon_email or not self.amazon_password:
            logger.error(
                "Sign-in page detected but no credentials configured. "
                "Set AMAZON_EMAIL and AMAZON_PASSWORD in .env"
            )
            return False

        logger.info("Sign-in page detected — logging in...")

        try:
            # Step 1: Enter email
            email_field = page.locator('input[type="email"], input[name="email"]')
            await email_field.wait_for(state="visible", timeout=10000)
            await self._random_delay(0.5, 1.0)

            # Type email with human-like speed
            await email_field.fill("")
            await email_field.type(self.amazon_email, delay=random.randint(50, 120))

            await self._random_delay(0.3, 0.8)

            # Click continue button
            continue_btn = page.locator('input#continue, input[type="submit"]').first
            await continue_btn.click()

            await self._random_delay(1.0, 2.0)

            # Step 2: Enter password
            password_field = page.locator('input[type="password"], input[name="password"]')
            await password_field.wait_for(state="visible", timeout=10000)

            await password_field.fill("")
            await password_field.type(self.amazon_password, delay=random.randint(50, 120))

            await self._random_delay(0.3, 0.8)

            # Click sign-in button
            signin_btn = page.locator('input#signInSubmit, input[type="submit"]').first
            await signin_btn.click()

            # Wait for navigation after sign-in
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await self._random_delay(1.5, 3.0)

            # Check if we successfully navigated away from sign-in
            new_url = page.url
            if "ap/signin" in new_url:
                logger.error("Sign-in failed — still on login page. Check credentials.")
                return False

            logger.info("Sign-in successful!")
            return True

        except Exception as e:
            logger.error(f"Error during sign-in: {e}")
            return False

    # ──────────────────────────────────────────
    # Parse reviews from HTML
    # ──────────────────────────────────────────
    def _parse_reviews(self, html: str) -> list[Review]:
        """Parse all reviews from the page HTML."""
        soup = BeautifulSoup(html, "lxml")
        reviews = []

        review_elements = soup.select('li[data-hook="review"]')

        for element in review_elements:
            try:
                review = self._parse_single_review(element)
                if review:
                    reviews.append(review)
            except Exception as e:
                logger.warning(f"Failed to parse a review: {e}")
                continue

        return reviews

    def _parse_single_review(self, element) -> Review | None:
        """Parse a single review <li> element into a Review model."""

        # ── Rating ──
        rating = 0.0
        rating_el = element.select_one(
            'i[data-hook="review-star-rating"] span.a-icon-alt'
        )
        if rating_el:
            match = re.search(r"([\d.]+)\s*out of\s*5", rating_el.get_text())
            if match:
                rating = float(match.group(1))

        # ── Author ──
        author = "Unknown"
        author_el = element.select_one("span.a-profile-name")
        if author_el:
            author = author_el.get_text(strip=True)

        # ── Title ──
        title = ""
        title_el = element.select_one('a[data-hook="review-title"]')
        if title_el:
            # The title text is in the last <span> child (not the star rating span)
            spans = title_el.find_all("span")
            for span in reversed(spans):
                text = span.get_text(strip=True)
                # Skip the star-rating text
                if text and "out of 5 stars" not in text:
                    title = text
                    break

        # ── Date ──
        date = ""
        date_el = element.select_one('span[data-hook="review-date"]')
        if date_el:
            date_text = date_el.get_text(strip=True)
            # Extract just the date portion: "Reviewed in India on 1 November 2025"
            match = re.search(r"on\s+(.+)$", date_text)
            if match:
                date = match.group(1)
            else:
                date = date_text

        # ── Verified Purchase ──
        verified_purchase = False
        verified_el = element.select_one('span[data-hook="avp-badge"]')
        if verified_el:
            verified_purchase = True

        # ── Variation (Colour, Size, etc.) ──
        variation = None
        variation_el = element.select_one('a[data-hook="format-strip"]')
        if variation_el:
            # Raw text contains HTML entities and separator icons
            raw = variation_el.get_text(separator="|", strip=True)
            # Clean up: unescape HTML entities, normalize separators
            raw = unescape(raw)
            # Replace the pipe-separated format with a cleaner version
            parts = [p.strip() for p in raw.split("|") if p.strip()]
            if parts:
                variation = " | ".join(parts)

        # ── Review Body ──
        review_text = ""
        body_el = element.select_one('span[data-hook="review-body"]')
        if body_el:
            # Get the inner <span> text
            inner_span = body_el.find("span")
            if inner_span:
                review_text = inner_span.get_text(strip=True)
            else:
                review_text = body_el.get_text(strip=True)

        # ── Images ──
        images = []
        # Method 1: Extract full-size URLs from the initImagePopover script
        scripts = element.find_all("script")
        for script in scripts:
            script_text = script.string or ""
            if "initImagePopover" in script_text:
                img_match = re.search(
                    r'initImagePopover\([^,]+,\s*"(\[.*?\])"', script_text
                )
                if img_match:
                    urls_str = img_match.group(1)
                    urls_str = urls_str.strip("[]")
                    for url in urls_str.split(","):
                        url = url.strip().strip('"').strip("'")
                        if url and url.startswith("http"):
                            images.append(url)

        # Method 2: Fallback — extract from thumbnail tiles
        if not images:
            tile_imgs = element.select('img[data-hook="review-image-tile"]')
            for img in tile_imgs:
                src = img.get("src", "")
                if src and "transparent-pixel" not in src:
                    # Convert thumbnail URL to full-size
                    full_url = re.sub(r"\._[A-Z]+\d+_?\.", ".", src)
                    images.append(full_url)

        # ── Videos ──
        videos = []
        video_els = element.select("video source")
        for v in video_els:
            src = v.get("src", "")
            if src:
                videos.append(src)

        # Check for Amazon's custom video player data attributes
        video_containers = element.select('[data-hook="review-video-tile"]')
        for vc in video_containers:
            video_url = vc.get("data-video-url", "") or vc.get("data-src", "")
            if video_url:
                videos.append(video_url)

        return Review(
            rating=rating,
            author=author,
            date=date,
            verified_purchase=verified_purchase,
            variation=variation,
            title=title,
            review=review_text,
            images=images,
            videos=videos,
        )

    # ──────────────────────────────────────────
    # Main scrape orchestrator (Playwright)
    # ──────────────────────────────────────────
    async def scrape_reviews(
        self, asin: str, max_pages: int | None = None
    ) -> list[Review]:
        """
        Scrape all reviews for a given ASIN using Playwright headless browser.

        Navigates to the review portal page, handles sign-in if needed,
        parses the first page, then clicks "Show 10 more" to load more.

        Args:
            asin: Amazon Standard Identification Number
            max_pages: Maximum number of pages to fetch (None = use config default)

        Returns:
            List of Review objects
        """
        settings = get_settings()

        all_reviews: list[Review] = []
        url = f"{self.base_domain}/portal/customer-reviews/{asin}/"
        user_agent = random.choice(USER_AGENTS)

        # Randomize viewport to reduce fingerprinting
        viewport_width = random.randint(1280, 1920)
        viewport_height = random.randint(800, 1080)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": viewport_width, "height": viewport_height},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                extra_http_headers={
                    "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )

            page = await context.new_page()
            # Apply advanced stealth to evade headless detection
            await stealth_async(page)

            try:
                logger.info(f"Navigating to review page for ASIN {asin}...")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._random_delay(1.0, 2.0)

                # ── Handle sign-in if redirected ──
                current_url = page.url
                if "ap/signin" in current_url or "signin" in current_url:
                    signin_ok = await self._handle_signin(page)
                    if not signin_ok:
                        logger.error("Cannot proceed — sign-in failed.")
                        await browser.close()
                        return []

                    # After sign-in, we should be redirected back to reviews page
                    # Wait for reviews to appear
                    logger.info("Waiting for reviews page to load after sign-in...")

                # Wait for reviews to render
                try:
                    await page.wait_for_selector(
                        'li[data-hook="review"]', timeout=15000
                    )
                except Exception:
                    logger.warning(
                        "Reviews not found after waiting. Checking page state..."
                    )
                    final_url = page.url
                    page_title = await page.title()
                    page_content = await page.content()
                    
                    if "signin" in final_url:
                        logger.error("Still on sign-in page after login attempt.")
                    elif "Robot Check" in page_title or "captcha" in final_url.lower():
                        logger.error("🚨 Amazon triggered a Captcha/Anti-Bot check! The datacenter IP is blocked.")
                    else:
                        logger.error(f"Reviews not found on page. URL: {final_url} | Title: {page_title}")
                        # Print a snippet of the HTML body to understand what Amazon served
                        snippet = page_content[:500].replace('\n', ' ')
                        logger.debug(f"HTML Snippet: {snippet}")
                        
                    await browser.close()
                    return []

                # Small delay after reviews load
                await self._random_delay(0.5, 1.5)

                page_num = 1
                while True:
                    if max_pages is not None and page_num > max_pages:
                        break

                    logger.info(
                        f"Parsing page {page_num}{f'/{max_pages}' if max_pages else ''} for ASIN {asin}..."
                    )

                    # Get current page HTML
                    html = await page.content()
                    page_reviews = self._parse_reviews(html)

                    # Only add NEW reviews (avoid duplicates from appended pages)
                    existing_count = len(all_reviews)
                    new_reviews = page_reviews[existing_count:]

                    if not new_reviews:
                        logger.info("No new reviews found on this page, stopping.")
                        break

                    logger.info(
                        f"Page {page_num}: found {len(new_reviews)} new reviews"
                    )
                    all_reviews.extend(new_reviews)

                    # Look for and click "Show 10 more reviews" button
                    show_more_button = page.locator(
                        'a[data-hook="show-more-button"]'
                    )

                    try:
                        button_visible = await show_more_button.is_visible(
                            timeout=3000
                        )
                    except Exception:
                        button_visible = False

                    if not button_visible:
                        logger.info(
                            "No 'Show 10 more' button found — all reviews loaded."
                        )
                        break

                    logger.info("Clicking 'Show 10 more reviews'...")

                    # Scroll to button first (human-like behavior)
                    await show_more_button.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.3, 0.8))

                    await show_more_button.click()

                    # Wait for new reviews to load
                    try:
                        expected_count = len(all_reviews) + 1
                        await page.wait_for_function(
                            f'document.querySelectorAll(\'li[data-hook="review"]\').length >= {expected_count}',
                            timeout=15000,
                        )
                    except Exception:
                        logger.warning(
                            "Timeout waiting for new reviews after clicking 'Show more'"
                        )

                    # Random delay between page interactions
                    await self._random_delay()

                    page_num += 1

            except Exception as e:
                logger.error(f"Error during scraping: {e}")
            finally:
                await browser.close()

        logger.info(
            f"Scraping complete for ASIN {asin}: {len(all_reviews)} total reviews"
        )
        return all_reviews
