#!/usr/bin/env python3
"""
Search a target person with the Google SERP service API and save result pages as HTML.

Usage:
    python search_google_serp.py "Elon Musk" --max-results 10
    python search_google_serp.py "Sam Altman" -n 25 -o results/sam_search

Environment (via .env file or shell):
    GOOGLE_SERP_BASE_URL: API base URL
    GOOGLE_SERP_API_KEY: API key value (optional)
    GOOGLE_SERP_API_KEY_HEADER: API key header name (default: X-API-Key)
    GOOGLE_SERP_BEARER_TOKEN: Bearer token (optional)
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


def load_env_file():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value


load_env_file()


def build_auth_headers():
    """Build auth headers from environment variables."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "Python Google SERP Client",
    }

    api_key = os.environ.get("GOOGLE_SERP_API_KEY")
    if api_key:
        header_name = os.environ.get("GOOGLE_SERP_API_KEY_HEADER", "X-API-Key")
        headers[header_name] = api_key

    bearer_token = os.environ.get("GOOGLE_SERP_BEARER_TOKEN")
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    return headers


def request_json_get(base_url, endpoint, params, headers, timeout=20):
    """Perform GET request and parse JSON."""
    base = base_url.rstrip("/") + "/"
    path = endpoint.lstrip("/")
    query = urlencode(params)
    url = urljoin(base, path)
    if query:
        url = f"{url}?{query}"

    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
            return url, json.loads(text)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}: {body[:800]}")
    except URLError as e:
        raise RuntimeError(f"URL error for {url}: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON decode failed for {url}: {e}")


def request_json_post(base_url, endpoint, payload, headers, timeout=20):
    """Perform POST request with JSON body and parse JSON response."""
    base = base_url.rstrip("/") + "/"
    path = endpoint.lstrip("/")
    url = urljoin(base, path)

    body = json.dumps(payload).encode("utf-8")
    req_headers = dict(headers)
    req_headers["Content-Type"] = "application/json"

    req = Request(url, headers=req_headers, data=body, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            response_body = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            text = response_body.decode(charset, errors="replace")
            return url, json.loads(text)
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}: {error_body[:800]}")
    except URLError as e:
        raise RuntimeError(f"URL error for {url}: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON decode failed for {url}: {e}")


def find_results_list(payload):
    """Find result item list from API payload."""
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "organic_results", "search_results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    best = []

    def looks_like_result(item):
        if not isinstance(item, dict):
            return False
        keys = {k.lower() for k in item.keys()}
        return any(k in keys for k in ("url", "link", "href"))

    def walk(node):
        nonlocal best
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node):
                score = sum(1 for x in node if looks_like_result(x))
                if score > 0 and score >= len(best):
                    best = node
            for value in node:
                walk(value)

    walk(payload)
    return best


def pick_url(item):
    """Get URL field from a result dict."""
    for key in ("url", "link", "href", "target_url", "result_url"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def normalize_result(item, rank):
    """Normalize raw result object to a stable structure."""
    url = pick_url(item)
    if not url:
        return None

    title = ""
    for key in ("title", "name", "headline"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            title = value.strip()
            break

    snippet = ""
    for key in ("snippet", "description", "summary", "body"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            snippet = value.strip()
            break

    return {
        "rank": rank,
        "title": title,
        "url": url,
        "snippet": snippet,
        "raw": item,
    }


def sanitize_name(text, max_len=60):
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_")
    if not cleaned:
        cleaned = "result"
    return cleaned[:max_len]


def html_wrapper_for_non_html(url, content_type, status_code):
    safe_url = html.escape(url)
    safe_type = html.escape(content_type or "unknown")
    safe_status = html.escape(str(status_code) if status_code is not None else "unknown")
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\">
    <title>Non-HTML result</title>
  </head>
  <body>
    <h1>Non-HTML content skipped</h1>
    <p>URL: <a href=\"{safe_url}\">{safe_url}</a></p>
    <p>Status: {safe_status}</p>
    <p>Content-Type: {safe_type}</p>
  </body>
</html>
"""


def fetch_and_save_html(url, output_path, timeout=20):
    """Download one result URL and save HTML locally."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PersonSearchBot/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = Request(url, headers=headers, method="GET")

    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None)
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()

            is_html = "text/html" in content_type.lower() or b"<html" in body[:2048].lower()
            if is_html:
                output_path.write_bytes(body)
            else:
                output_path.write_text(
                    html_wrapper_for_non_html(url, content_type, status),
                    encoding="utf-8",
                )

            return {
                "saved": True,
                "status_code": status,
                "content_type": content_type,
                "error": None,
            }
    except Exception as e:
        return {
            "saved": False,
            "status_code": None,
            "content_type": "",
            "error": str(e),
        }


def build_index_html(target_name, records):
    rows = []
    for record in records:
        url = html.escape(record["url"])
        title = html.escape(record.get("title") or "(no title)")
        local_file = html.escape(record.get("local_file") or "")
        status = html.escape(record.get("status", ""))
        snippet = html.escape(record.get("snippet", ""))
        rank = record.get("rank", "")
        local_link = f'<a href="{local_file}">{local_file}</a>' if local_file else "-"
        rows.append(
            f"<tr><td>{rank}</td><td>{title}</td><td><a href=\"{url}\">{url}</a></td>"
            f"<td>{local_link}</td><td>{status}</td><td>{snippet}</td></tr>"
        )

    safe_name = html.escape(target_name)
    body_rows = "\n".join(rows)
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\">
    <title>Search Results - {safe_name}</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 24px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: 8px; vertical-align: top; }}
      th {{ background: #f2f2f2; text-align: left; }}
      td {{ font-size: 13px; }}
    </style>
  </head>
  <body>
    <h1>Search Results: {safe_name}</h1>
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Title</th>
          <th>URL</th>
          <th>Local HTML</th>
          <th>Status</th>
          <th>Snippet</th>
        </tr>
      </thead>
      <tbody>
        {body_rows}
      </tbody>
    </table>
  </body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Search a target person with Google SERP API and save result pages as HTML."
    )
    parser.add_argument("target_name", help="Person name to search for")
    parser.add_argument(
        "--max-results",
        "-n",
        type=int,
        default=10,
        help="Maximum number of search results to save (default: 10)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Starting position for results (default: 1)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help="Output directory. Default: results/search_<name>_<timestamp>",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.environ.get("GOOGLE_SERP_BASE_URL"),
        help=f"SERP API base URL",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds (default: 20)",
    )

    args = parser.parse_args()

    if args.max_results <= 0:
        print("Error: --max-results must be positive.", file=sys.stderr)
        sys.exit(1)
    if args.start <= 0:
        print("Error: --start must be >= 1.", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = Path("results") / f"search_{sanitize_name(args.target_name)}_{timestamp}"
    output_dir = Path(args.output_dir) if args.output_dir else default_out
    output_dir.mkdir(parents=True, exist_ok=True)

    headers = build_auth_headers()

    payload = None
    used_url = None
    used_params = None
    used_method = None
    used_endpoint = None
    last_error = None

    print(f"Searching for: {args.target_name}")
    print(f"Base URL: {args.base_url}")

    if args.max_results <= 10:
        params = {"q": args.target_name, "num": args.max_results, "start": args.start}
        try:
            used_url, payload = request_json_get(
                base_url=args.base_url,
                endpoint="/search",
                params=params,
                headers=headers,
                timeout=args.timeout,
            )
            used_params = params
            used_method = "GET"
            used_endpoint = "/search"
            print(f"Search request succeeded: GET /search with params {params}")
        except RuntimeError as e:
            last_error = str(e)
    else:
        capped_total = min(args.max_results, 100)
        if args.max_results > 100:
            print("Warning: API max is 100 results. Capping --max-results to 100.")
        paged_body = {
            "q": args.target_name,
            "start": args.start,
            "num": 10,
            "per_request": 10,
            "total_results": capped_total,
        }
        try:
            used_url, payload = request_json_post(
                base_url=args.base_url,
                endpoint="/search/paged",
                payload=paged_body,
                headers=headers,
                timeout=args.timeout,
            )
            used_params = paged_body
            used_method = "POST"
            used_endpoint = "/search/paged"
            print("Search request succeeded: POST /search/paged")
        except RuntimeError as e:
            last_error = str(e)

    if payload is None:
        print("Error: search request failed for the OpenAPI-defined endpoint.", file=sys.stderr)
        if last_error:
            print(last_error, file=sys.stderr)
        sys.exit(1)

    raw_response_path = output_dir / "api_response.json"
    with open(raw_response_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved raw API response: {raw_response_path}")

    raw_results = find_results_list(payload)
    normalized = []
    seen_urls = set()

    for item in raw_results:
        if len(normalized) >= args.max_results:
            break
        if not isinstance(item, dict):
            continue
        record = normalize_result(item, rank=len(normalized) + 1)
        if not record:
            continue
        if record["url"] in seen_urls:
            continue
        seen_urls.add(record["url"])
        normalized.append(record)

    if not normalized:
        print("Warning: no URLs found in API response. Check api_response.json.")

    results_dir = output_dir / "html_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    for record in normalized:
        parsed = urlparse(record["url"])
        domain = sanitize_name(parsed.netloc or "unknown")
        name = f"{record['rank']:03d}_{domain}.html"
        output_path = results_dir / name

        status = fetch_and_save_html(record["url"], output_path, timeout=args.timeout)
        record["local_file"] = str(Path("html_results") / name)
        record["status"] = "saved" if status["saved"] else "failed"
        record["fetch_error"] = status["error"]
        record["status_code"] = status["status_code"]
        record["content_type"] = status["content_type"]

        if status["saved"]:
            saved_count += 1
            print(f"[{record['rank']:02d}] saved -> {output_path}")
        else:
            print(f"[{record['rank']:02d}] failed -> {record['url']} ({status['error']})")

    index_html_path = output_dir / "index.html"
    index_html_path.write_text(build_index_html(args.target_name, normalized), encoding="utf-8")

    summary_path = output_dir / "search_results.json"
    summary = {
        "target_name": args.target_name,
        "requested_max_results": args.max_results,
        "results_found": len(normalized),
        "results_saved": saved_count,
        "used_search_method": used_method,
        "used_search_endpoint": used_endpoint,
        "used_search_url": used_url,
        "used_search_params": used_params,
        "generated_at": datetime.now().isoformat(),
        "results": normalized,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\nDone.")
    print(f"Output directory: {output_dir}")
    print(f"Summary JSON: {summary_path}")
    print(f"Local index HTML: {index_html_path}")
    print(f"Saved pages: {saved_count}/{len(normalized)}")


if __name__ == "__main__":
    main()
