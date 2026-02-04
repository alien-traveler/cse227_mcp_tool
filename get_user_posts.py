#!/usr/bin/env python3
"""
Fetch all posts from a specific X (Twitter) user by username.
Uses X API v2 endpoints.

Usage:
    python get_user_posts.py <username> [--max-results N] [--output FILE]

Environment (via .env file or shell):
    X_BEARER_TOKEN: Your X API Bearer Token (required)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


def load_env_file():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


# Load .env file before accessing environment variables
load_env_file()

BASE_URL = "https://api.x.com/2"


def get_bearer_token():
    """Get bearer token from environment variable."""
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        print("Error: X_BEARER_TOKEN environment variable is not set.", file=sys.stderr)
        print("Get your token from https://developer.x.com/", file=sys.stderr)
        sys.exit(1)
    return token


def make_request(url, bearer_token):
    """Make an authenticated GET request to the X API."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "Python X API Client",
    }
    request = Request(url, headers=headers)

    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        print(f"Response: {error_body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def get_user_by_username(username, bearer_token):
    """
    Step 1: Get user ID from username.
    Endpoint: GET /2/users/by/username/:username
    """
    url = f"{BASE_URL}/users/by/username/{username}"
    print(f"Fetching user info for @{username}...")

    data = make_request(url, bearer_token)

    if "errors" in data and not data.get("data"):
        print(f"Error: User @{username} not found.", file=sys.stderr)
        sys.exit(1)

    user = data["data"]
    print(f"Found user: {user['name']} (@{user['username']}) - ID: {user['id']}")
    return user


def get_user_tweets(user_id, bearer_token, max_results=None):
    """
    Step 2: Get all tweets from user by ID.
    Endpoint: GET /2/users/:id/tweets

    Note: Maximum 3200 most recent tweets are available.
    """
    all_tweets = []
    pagination_token = None
    page = 1

    # Tweet fields to include
    tweet_fields = [
        "id", "text", "created_at", "author_id",
        "public_metrics", "entities", "referenced_tweets"
    ]

    while True:
        # Build query parameters
        params = {
            "max_results": 100,  # Max per request
            "tweet.fields": ",".join(tweet_fields),
        }

        if pagination_token:
            params["pagination_token"] = pagination_token

        url = f"{BASE_URL}/users/{user_id}/tweets?{urlencode(params)}"

        print(f"Fetching page {page}...", end=" ", flush=True)
        data = make_request(url, bearer_token)

        tweets = data.get("data", [])
        print(f"got {len(tweets)} tweets")

        if not tweets:
            break

        all_tweets.extend(tweets)

        # Check if we've reached the requested max
        if max_results and len(all_tweets) >= max_results:
            all_tweets = all_tweets[:max_results]
            break

        # Check for next page
        meta = data.get("meta", {})
        pagination_token = meta.get("next_token")

        if not pagination_token:
            break

        page += 1
        # Rate limit: be nice to the API
        time.sleep(0.5)

    return all_tweets


def format_tweet(tweet):
    """Format a tweet for display."""
    metrics = tweet.get("public_metrics", {})
    return {
        "id": tweet["id"],
        "text": tweet["text"],
        "created_at": tweet.get("created_at", "N/A"),
        "likes": metrics.get("like_count", 0),
        "retweets": metrics.get("retweet_count", 0),
        "replies": metrics.get("reply_count", 0),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fetch all posts from a X (Twitter) user by username"
    )
    parser.add_argument("username", help="X username (without @)")
    parser.add_argument(
        "--max-results", "-n", type=int, default=None,
        help="Maximum number of tweets to fetch (default: all available, up to 3200)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file path (JSON format). If not specified, prints to stdout."
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Output raw API response instead of formatted data"
    )

    args = parser.parse_args()

    # Remove @ if user included it
    username = args.username.lstrip("@")

    bearer_token = get_bearer_token()

    # Step 1: Get user ID
    user = get_user_by_username(username, bearer_token)

    # Step 2: Get tweets
    print(f"\nFetching tweets for user ID {user['id']}...")
    tweets = get_user_tweets(user["id"], bearer_token, args.max_results)

    print(f"\nTotal tweets fetched: {len(tweets)}")

    # Prepare output
    if args.raw:
        output_data = {"user": user, "tweets": tweets}
    else:
        output_data = {
            "user": {
                "id": user["id"],
                "name": user["name"],
                "username": user["username"],
            },
            "tweet_count": len(tweets),
            "tweets": [format_tweet(t) for t in tweets],
        }

    # Output results
    json_output = json.dumps(output_data, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"\nResults saved to: {args.output}")
    else:
        print("\n" + "=" * 50)
        print(json_output)


if __name__ == "__main__":
    main()
