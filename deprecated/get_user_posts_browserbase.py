#!/usr/bin/env python3
"""
Fetch posts from a specific X (Twitter) user by scraping via Browserbase.
Uses Browserbase cloud browser + Playwright for automation.

Usage:
    python get_user_posts_browserbase.py <username> [--max-posts N] [--output FILE]

Environment (via .env file or shell):
    BROWSERBASE_API_KEY: Your Browserbase API key (required)
    BROWSERBASE_PROJECT_ID: Your Browserbase project ID (required)

Requirements:
    pip install browserbase playwright
    playwright install chromium
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime


def load_env_file():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                if key not in os.environ:
                    os.environ[key] = value


load_env_file()


def get_browserbase_credentials():
    """Get Browserbase credentials from environment."""
    api_key = os.environ.get("BROWSERBASE_API_KEY")
    project_id = os.environ.get("BROWSERBASE_PROJECT_ID")

    if not api_key or not project_id:
        print("Error: BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID must be set.", file=sys.stderr)
        print("Add them to your .env file or set as environment variables.", file=sys.stderr)
        sys.exit(1)

    return api_key, project_id


def scrape_user_posts(username, max_posts=10):
    """
    Scrape posts from a user's X/Twitter profile using Browserbase.
    """
    try:
        from browserbase import Browserbase
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: Required packages not installed.", file=sys.stderr)
        print("Run: pip install browserbase playwright", file=sys.stderr)
        print("Then: playwright install chromium", file=sys.stderr)
        sys.exit(1)

    api_key, project_id = get_browserbase_credentials()

    # Initialize Browserbase
    bb = Browserbase(api_key=api_key)

    print(f"Creating Browserbase session...")
    session = bb.sessions.create(project_id=project_id)
    print(f"Session created: {session.id}")

    posts = []

    try:
        with sync_playwright() as pw:
            # Connect to Browserbase session
            browser = pw.chromium.connect_over_cdp(session.connect_url)
            context = browser.contexts[0]
            page = context.pages[0]

            # Navigate to user profile
            url = f"https://x.com/{username}"
            print(f"Navigating to {url}...")
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for posts to load
            print("Waiting for posts to load...")
            time.sleep(3)

            # Check if user exists
            if page.locator("text=This account doesn't exist").count() > 0:
                print(f"Error: User @{username} does not exist.", file=sys.stderr)
                return None

            if page.locator("text=Account suspended").count() > 0:
                print(f"Error: User @{username} is suspended.", file=sys.stderr)
                return None

            # Get user info from page
            user_info = extract_user_info(page, username)
            print(f"Found user: {user_info.get('name', username)}")

            # Scroll and collect posts
            print(f"Collecting posts (max: {max_posts})...")
            collected = 0
            scroll_attempts = 0
            max_scroll_attempts = 10
            seen_ids = set()

            while collected < max_posts and scroll_attempts < max_scroll_attempts:
                # Find all tweet articles on page
                tweet_elements = page.locator('article[data-testid="tweet"]').all()

                for tweet_el in tweet_elements:
                    if collected >= max_posts:
                        break

                    try:
                        post = extract_post_data(tweet_el, username)
                        if post and post.get("id") not in seen_ids:
                            seen_ids.add(post["id"])
                            posts.append(post)
                            collected += 1
                            print(f"  Collected {collected}/{max_posts} posts", end="\r")
                    except Exception:
                        continue

                # Scroll down to load more
                page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(1.5)
                scroll_attempts += 1

            print(f"\nCollected {len(posts)} posts total.")

            return {
                "user": user_info,
                "post_count": len(posts),
                "posts": posts,
                "scraped_at": datetime.utcnow().isoformat() + "Z"
            }

    finally:
        print("Closing Browserbase session...")
        bb.sessions.update(session.id, status="REQUEST_RELEASE", project_id=project_id)


def extract_user_info(page, username):
    """Extract user information from profile page."""
    info = {"username": username}

    try:
        # Try to get display name
        name_el = page.locator('[data-testid="UserName"]').first
        if name_el.count() > 0:
            name_text = name_el.inner_text()
            # First line is usually the display name
            lines = name_text.split("\n")
            if lines:
                info["name"] = lines[0].strip()

        # Try to get bio
        bio_el = page.locator('[data-testid="UserDescription"]').first
        if bio_el.count() > 0:
            info["bio"] = bio_el.inner_text().strip()

        # Try to get follower/following counts
        followers_el = page.locator(f'a[href="/{username}/verified_followers"]').first
        if followers_el.count() > 0:
            info["followers"] = followers_el.inner_text().strip()

        following_el = page.locator(f'a[href="/{username}/following"]').first
        if following_el.count() > 0:
            info["following"] = following_el.inner_text().strip()

    except Exception:
        pass

    return info


def extract_post_data(tweet_element, username):
    """Extract data from a single tweet element."""
    post = {}

    try:
        # Get tweet link which contains the ID
        link_el = tweet_element.locator(f'a[href*="/{username}/status/"]').first
        if link_el.count() > 0:
            href = link_el.get_attribute("href")
            # Extract ID from URL like /username/status/123456789
            if "/status/" in href:
                post["id"] = href.split("/status/")[-1].split("?")[0].split("/")[0]
                post["url"] = f"https://x.com{href}"

        # Get tweet text
        text_el = tweet_element.locator('[data-testid="tweetText"]').first
        if text_el.count() > 0:
            post["text"] = text_el.inner_text().strip()
        else:
            post["text"] = ""

        # Get timestamp
        time_el = tweet_element.locator("time").first
        if time_el.count() > 0:
            post["created_at"] = time_el.get_attribute("datetime")

        # Get metrics (likes, retweets, replies)
        post["metrics"] = {}

        reply_el = tweet_element.locator('[data-testid="reply"]').first
        if reply_el.count() > 0:
            reply_text = reply_el.inner_text().strip()
            post["metrics"]["replies"] = reply_text if reply_text else "0"

        retweet_el = tweet_element.locator('[data-testid="retweet"]').first
        if retweet_el.count() > 0:
            rt_text = retweet_el.inner_text().strip()
            post["metrics"]["retweets"] = rt_text if rt_text else "0"

        like_el = tweet_element.locator('[data-testid="like"]').first
        if like_el.count() > 0:
            like_text = like_el.inner_text().strip()
            post["metrics"]["likes"] = like_text if like_text else "0"

        # Check if it's a retweet
        retweet_indicator = tweet_element.locator('text="reposted"').first
        post["is_retweet"] = retweet_indicator.count() > 0

    except Exception as e:
        pass

    return post if post.get("id") else None


def main():
    parser = argparse.ArgumentParser(
        description="Scrape posts from X (Twitter) user via Browserbase"
    )
    parser.add_argument("username", help="X username (without @)")
    parser.add_argument(
        "--max-posts", "-n", type=int, default=10,
        help="Maximum number of posts to collect (default: 10)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="results/posts.json",
        help="Output file path (JSON format)"
    )

    args = parser.parse_args()
    username = args.username.lstrip("@")

    print(f"Scraping posts for @{username} via Browserbase...\n")

    result = scrape_user_posts(username, args.max_posts)

    if result is None:
        sys.exit(1)

    json_output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        # Ensure output directory exists
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"\nResults saved to: {args.output}")
    else:
        print("\n" + "=" * 50)
        print(json_output)


if __name__ == "__main__":
    main()
