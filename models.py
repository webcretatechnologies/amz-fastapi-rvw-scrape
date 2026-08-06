from pydantic import BaseModel, Field
from typing import Optional


class Review(BaseModel):
    """A single Amazon customer review."""

    rating: float = Field(..., description="Star rating (1.0 - 5.0)")
    author: str = Field(..., description="Reviewer's display name")
    date: str = Field(..., description="Review date as shown on Amazon")
    verified_purchase: bool = Field(
        False, description="Whether the reviewer is a verified buyer"
    )
    variation: Optional[str] = Field(
        None, description="Product variation (colour, size, etc.)"
    )
    title: str = Field(..., description="Review title / headline")
    review: str = Field(..., description="Review body text")
    images: list[str] = Field(
        default_factory=list, description="Full-size image URLs attached to the review"
    )
    videos: list[str] = Field(
        default_factory=list, description="Video URLs attached to the review"
    )


class ReviewResponse(BaseModel):
    """API response containing scraped reviews for an ASIN."""

    asin: str = Field(..., description="Amazon Standard Identification Number")
    total_count: int = Field(..., description="Number of reviews returned")
    reviews: list[Review] = Field(
        default_factory=list, description="List of scraped reviews"
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Error message")


class BatchReviewRequest(BaseModel):
    """Request model for scraping multiple ASINs."""
    asins: list[str] = Field(..., description="List of Amazon Standard Identification Numbers to scrape")
    max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Number of review pages to fetch per ASIN. If omitted, fetches all pages."
    )


class BatchReviewResponse(BaseModel):
    """API response containing scraped reviews for multiple ASINs."""
    results: list[ReviewResponse] = Field(
        default_factory=list, description="List of scraping results per ASIN"
    )
