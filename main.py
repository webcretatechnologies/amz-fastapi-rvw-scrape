import re
import logging

from fastapi import FastAPI, HTTPException, Security, Query
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from config import get_settings
from models import ReviewResponse, ErrorResponse, BatchReviewRequest, BatchReviewResponse
from scraper import AmazonReviewScraper

# ──────────────────────────────────────────────
# Logging configuration
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("amazon_scraper")

# ──────────────────────────────────────────────
# Rate limiter setup
# ──────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ──────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────
app = FastAPI(
    title="Amazon Review Scraper API",
    description=(
        "Scrape customer ratings and reviews from Amazon India "
        "by ASIN. Returns structured JSON with rating, author, date, "
        "verified purchase status, variation, title, review text, "
        "images, and videos."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# API Key authentication
# ──────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    """Validate the API key from the X-API-Key header."""
    settings = get_settings()
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide a valid key in the X-API-Key header.",
        )
    return api_key


# ──────────────────────────────────────────────
# ASIN validation
# ──────────────────────────────────────────────
ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


def validate_asin(asin: str) -> str:
    """Validate that the ASIN matches Amazon's 10-character alphanumeric format."""
    asin = asin.strip().upper()
    if not ASIN_PATTERN.match(asin):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ASIN '{asin}'. Must be exactly 10 alphanumeric characters (e.g., B0DY84N63N).",
        )
    return asin


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint — no authentication required."""
    return {"status": "healthy", "service": "Amazon Review Scraper API"}


@app.get(
    "/api/v1/reviews/{asin}",
    response_model=ReviewResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        400: {"model": ErrorResponse, "description": "Invalid ASIN format"},
        404: {"model": ErrorResponse, "description": "No reviews found"},
        429: {"description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Scraping failed"},
    },
    summary="Scrape Amazon reviews by ASIN",
    description=(
        "Scrape customer reviews from Amazon India for a given ASIN. "
        "Each page contains up to 10 reviews. Use `max_pages` to control "
        "how many pages to fetch."
    ),
)
@limiter.limit(lambda: get_settings().rate_limit)
async def get_reviews(
    request: Request,
    asin: str,
    max_pages: int | None = Query(
        default=None,
        ge=1,
        description="Number of review pages to fetch. If omitted, fetches all pages until 'Show 10 more' disappears.",
    ),
    api_key: str = Security(verify_api_key),
):
    """
    Scrape reviews for an Amazon product.

    - **asin**: The 10-character Amazon product identifier
    - **max_pages**: How many pages to fetch (default: all pages)
    """
    # Validate ASIN format
    asin = validate_asin(asin)

    logger.info(f"Request: ASIN={asin}, max_pages={max_pages}")

    try:
        scraper = AmazonReviewScraper()
        reviews = await scraper.scrape_reviews(asin=asin, max_pages=max_pages)
    except Exception as e:
        logger.error(f"Scraping failed for ASIN {asin}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scrape reviews: {str(e)}",
        )

    if not reviews:
        raise HTTPException(
            status_code=404,
            detail=f"No reviews found for ASIN '{asin}'. The product may have no reviews or Amazon may be blocking the request.",
        )

    return ReviewResponse(
        asin=asin,
        total_count=len(reviews),
        reviews=reviews,
    )


@app.post(
    "/api/v1/reviews/batch",
    response_model=BatchReviewResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        400: {"model": ErrorResponse, "description": "Invalid ASIN format"},
        429: {"description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Scraping failed"},
    },
    summary="Scrape Amazon reviews for multiple ASINs",
    description="Scrape customer reviews for a list of ASINs. ASINs are processed sequentially.",
)
@limiter.limit(lambda: get_settings().rate_limit)
async def get_reviews_batch(
    request: Request,
    batch_request: BatchReviewRequest,
    api_key: str = Security(verify_api_key),
):
    """
    Scrape reviews for multiple Amazon products.
    """
    # Validate all ASINs first
    valid_asins = []
    for asin in batch_request.asins:
        try:
            valid_asins.append(validate_asin(asin))
        except HTTPException as e:
            raise HTTPException(status_code=400, detail=f"ASIN '{asin}' validation failed: {e.detail}")

    logger.info(f"Batch Request: {len(valid_asins)} items, max_pages={batch_request.max_pages}")

    results = []
    scraper = AmazonReviewScraper()

    for asin in valid_asins:
        try:
            logger.info(f"Scraping ASIN {asin} (batch), max_pages={batch_request.max_pages}...")
            reviews = await scraper.scrape_reviews(asin=asin, max_pages=batch_request.max_pages)
            results.append(
                ReviewResponse(
                    asin=asin,
                    total_count=len(reviews),
                    reviews=reviews,
                )
            )
        except Exception as e:
            logger.error(f"Scraping failed for ASIN {asin} in batch: {e}")
            # Append empty results to allow batch to continue
            results.append(
                ReviewResponse(
                    asin=asin,
                    total_count=0,
                    reviews=[],
                )
            )

    return BatchReviewResponse(results=results)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
