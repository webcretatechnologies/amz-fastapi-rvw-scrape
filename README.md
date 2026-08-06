# 🛒 Amazon Review Scraper API

A FastAPI-powered REST API that scrapes customer ratings and reviews from Amazon India's review portal. Extracts structured data including rating, author, date, verified purchase status, product variation, title, review text, images, and videos.

Uses **Playwright** (headless Chromium) with automatic Amazon sign-in to access the `/portal/customer-reviews/` pages.

---

## ⚡ Quick Start

### 1. Install Dependencies

```bash
cd "Amazon Review Scrapper"
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Copy the example env file and edit your settings:

```bash
cp .env.example .env
```

Edit `.env`:

```env
API_KEY=your-secret-api-key-here
AMAZON_EMAIL=your-amazon-email@example.com
AMAZON_PASSWORD=your-amazon-password
```

### 3. Start the Server

```bash
python main.py
```

The API will be available at `http://localhost:8000`.

### Option B: Using Docker

1. Build the Docker image:
```bash
docker build -t amazon-scraper-api .
```

2. Run the container (make sure your `.env` file is present):
```bash
docker run -d -p 8000:8000 --env-file .env amazon-scraper-api
```

---

## 📖 API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🔌 Endpoints

### Health Check

```
GET /api/v1/health
```

No authentication required.

### Scrape Reviews (Single ASIN)

```
GET /api/v1/reviews/{asin}?max_pages=1
```

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `X-API-Key` | ✅ | Your API key from `.env` |

**Path Parameters:**
| Parameter | Description |
|-----------|-------------|
| `asin` | Amazon product ASIN (10-character alphanumeric) |

**Query Parameters:**
| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `max_pages` | `1` | `1-50` | Number of review pages to fetch (10 reviews per page) |

### Scrape Reviews (Batch)

```
POST /api/v1/reviews/batch
```

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `X-API-Key` | ✅ | Your API key from `.env` |
| `Content-Type` | ✅ | `application/json` |

**Body:**
```json
{
  "asins": ["B0DY84N63N", "B0GWJHLVS7", "B082MM2T4M"]
}
```

---

## 📋 Usage Examples

### cURL

```bash
# Fetch first page (10 reviews) for a single ASIN
curl -H "X-API-Key: your-api-key" \
  "http://localhost:8000/api/v1/reviews/B0DY84N63N"

# Fetch multiple ASINs (Batch)
curl -X POST -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"asins": ["B0DY84N63N", "B0GWJHLVS7", "B082MM2T4M"]}' \
  "http://localhost:8000/api/v1/reviews/batch"
```

### Python

```python
import requests

headers = {"X-API-Key": "your-api-key"}
response = requests.get(
    "http://localhost:8000/api/v1/reviews/B0DY84N63N",
    headers=headers,
    params={"max_pages": 2},
)
data = response.json()

print(f"Total reviews: {data['total_count']}")
for review in data["reviews"]:
    print(f"  ⭐ {review['rating']} - {review['title']} by {review['author']}")
```

---

## 📦 Response Format

```json
{
  "asin": "B0DY84N63N",
  "total_count": 10,
  "reviews": [
    {
      "rating": 5.0,
      "author": "kanika",
      "date": "1 November 2025",
      "verified_purchase": true,
      "variation": "Colour: Gold & Black | Size: Pack of 1",
      "title": "Good hold",
      "review": "Very nice, good quality and nice hold...",
      "images": [],
      "videos": []
    },
    {
      "rating": 1.0,
      "author": "Shubham Goyal",
      "date": "10 June 2025",
      "verified_purchase": true,
      "variation": null,
      "title": "Poor quality product",
      "review": "Center part is bended and quality and finish is too low.",
      "images": [
        "https://m.media-amazon.com/images/I/715L9FE5itL.jpg",
        "https://m.media-amazon.com/images/I/71+xnwrAG7L.jpg",
        "https://m.media-amazon.com/images/I/71pACCdC9EL.jpg",
        "https://m.media-amazon.com/images/I/719Td4I7QhL.jpg"
      ],
      "videos": []
    }
  ]
}
```

---

## 🔒 Security Features

| Feature | Description |
|---------|-------------|
| **API Key Auth** | All scraping endpoints require `X-API-Key` header |
| **Rate Limiting** | Default: 10 requests/minute per IP (configurable) |
| **ASIN Validation** | Rejects malformed ASINs before making any requests |
| **Credential Encryption** | Amazon credentials stored in `.env`, never exposed in API responses |

---

## 🛡️ Anti-Blocking Measures

| Technique | Description |
|-----------|-------------|
| **Headless Chromium** | Real browser via Playwright — renders JS, handles cookies |
| **Rotating User-Agents** | Pool of 15+ real browser UA strings per session |
| **Random Delays** | 2-5s random sleep between page interactions |
| **Viewport Randomization** | Random screen resolution per session |
| **WebDriver Flag Removal** | Overrides `navigator.webdriver` to avoid detection |
| **Human-like Typing** | Random keystroke delays during sign-in |
| **Stealth Scripts** | Chrome, plugins, and permissions API overrides |

---

## ⚙️ Configuration

All settings are in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | — | API key for authentication |
| `RATE_LIMIT` | `10/minute` | Rate limit per IP |
| `MIN_DELAY` | `2` | Minimum delay between pages (seconds) |
| `MAX_DELAY` | `5` | Maximum delay between pages (seconds) |
| `MAX_PAGES` | `10` | Hard cap on pages per request |
| `BASE_DOMAIN` | `https://www.amazon.in` | Amazon domain to scrape |
| `AMAZON_EMAIL` | — | Amazon account email for sign-in |
| `AMAZON_PASSWORD` | — | Amazon account password for sign-in |

---

## 📂 Project Structure

```
Amazon Review Scrapper/
├── .env                  # Environment config (credentials, API key)
├── .env.example          # Config template
├── config.py             # Settings loader (pydantic-settings)
├── models.py             # Pydantic data models
├── scraper.py            # Core scraping engine (Playwright + BeautifulSoup)
├── main.py               # FastAPI app & routes
├── requirements.txt      # Python dependencies
├── review_page.html      # HTML reference (for development)
└── README.md             # This file
```
