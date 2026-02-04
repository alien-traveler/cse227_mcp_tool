# X (Twitter) User Posts Fetcher

Fetch posts from a specific X (Twitter) user by username. Two approaches available:

1. **API Approach** - Uses official X API v2 (requires API credentials)
2. **Browserbase Approach** - Scrapes via cloud browser (requires Browserbase account)

## Prerequisites

- Python 3.6+
- For API approach: X API Bearer Token (https://developer.x.com/)
- For Browserbase approach: Browserbase account (https://browserbase.com/)

## Setup

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit `.env` and add your credentials:

```bash
# For API approach
X_BEARER_TOKEN=your_bearer_token_here

# For Browserbase approach
BROWSERBASE_API_KEY=your_api_key_here
BROWSERBASE_PROJECT_ID=your_project_id_here
```

3. For Browserbase approach, install additional dependencies:

```bash
pip install browserbase playwright
playwright install chromium
```

---

## Approach 1: API (get_user_posts.py)

```bash
# Fetch all tweets from a user (up to 3200)
python get_user_posts.py elonmusk

# Fetch only the 10 most recent tweets
python get_user_posts.py elonmusk --max-results 10

# Save results to a JSON file
python get_user_posts.py elonmusk -o tweets.json

# Get raw API response (includes all fields)
python get_user_posts.py elonmusk --raw -o raw_tweets.json
```

### Options

| Option | Description |
|--------|-------------|
| `username` | X username to fetch posts from (without @) |
| `--max-results`, `-n` | Maximum number of tweets to fetch (default: all available) |
| `--output`, `-o` | Output file path (JSON format) |
| `--raw` | Output raw API response instead of formatted data |

## Output Format

```json
{
  "user": {
    "id": "123456789",
    "name": "Display Name",
    "username": "username"
  },
  "tweet_count": 100,
  "tweets": [
    {
      "id": "tweet_id",
      "text": "Tweet content...",
      "created_at": "2024-01-15T10:30:00.000Z",
      "likes": 42,
      "retweets": 5,
      "replies": 3
    }
  ]
}
```

### Limitations

- Maximum 3200 most recent tweets available per user (X API limitation)
- Requires valid X API credentials with appropriate access level

---

## Approach 2: Browserbase (get_user_posts_browserbase.py)

Scrapes posts directly from X.com using a cloud browser via Browserbase.

### Usage

```bash
# Scrape 10 posts from a user (default)
python get_user_posts_browserbase.py elonmusk

# Scrape 50 posts
python get_user_posts_browserbase.py elonmusk --max-posts 50

# Save results to a JSON file
python get_user_posts_browserbase.py elonmusk -o posts.json
```

### Options

| Option | Description |
|--------|-------------|
| `username` | X username to fetch posts from (without @) |
| `--max-posts`, `-n` | Maximum number of posts to scrape (default: 10) |
| `--output`, `-o` | Output file path (JSON format) |

### Output Format

```json
{
  "user": {
    "username": "elonmusk",
    "name": "Elon Musk",
    "bio": "...",
    "followers": "100M Followers",
    "following": "500 Following"
  },
  "post_count": 10,
  "posts": [
    {
      "id": "1234567890",
      "url": "https://x.com/elonmusk/status/1234567890",
      "text": "Post content...",
      "created_at": "2024-01-15T10:30:00.000Z",
      "metrics": {
        "likes": "1.2K",
        "retweets": "500",
        "replies": "200"
      },
      "is_retweet": false
    }
  ],
  "scraped_at": "2024-01-15T12:00:00.000Z"
}
```

### Limitations

- Slower than API approach (browser automation)
- May be affected by X.com UI changes
- Rate limited by Browserbase session limits
- No authentication support (can only see public posts)
