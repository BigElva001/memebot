"""
Scans X for token mention velocity and rough narrative/sentiment.

Requires a real X API bearer token (X_BEARER_TOKEN in config/env).
As of the last time this was updated, X API v2 search access requires
a paid tier — there is no free search endpoint anymore. Get one at
https://developer.x.com/en/portal/products if you don't have one.

This module deliberately does NOT try to scrape X without an API key.
Scraping violates X's terms of service and breaks constantly — an API
key is the only reliable path.
"""

import time
import requests
from collections import defaultdict

import config


class XScanner:
    def __init__(self, bearer_token: str = None):
        self.token = bearer_token or config.X_BEARER_TOKEN
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _search_recent(self, query: str, max_results: int = 100):
        """Hit X API v2 recent search. Returns list of tweet dicts."""
        if not self.token:
            raise RuntimeError(
                "No X_BEARER_TOKEN set. Set it as an environment variable — "
                "see x_scanner.py docstring."
            )
        url = "https://api.x.com/2/tweets/search/recent"
        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "author_id,created_at,public_metrics",
        }
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def scan_token(self, symbol: str, cashtag: bool = True) -> dict:
        """
        Returns a signal dict for a given token symbol:
          {
            "mentions_per_hour": float,
            "unique_authors": int,
            "is_active": bool,
          }
        """
        query = f"${symbol}" if cashtag else symbol
        query += " -is:retweet"

        tweets = self._search_recent(query, max_results=100)
        if not tweets:
            return {"mentions_per_hour": 0, "unique_authors": 0, "is_active": False}

        authors = {t["author_id"] for t in tweets}

        # Estimate mentions/hour from the timestamp spread of what we got back
        times = sorted(t["created_at"] for t in tweets)
        # crude: assume results span from oldest to now
        span_hours = max(
            (time.time() - _parse_iso(times[0])) / 3600, 0.25
        )
        mentions_per_hour = len(tweets) / span_hours

        is_active = (
            mentions_per_hour >= config.MIN_MENTIONS_PER_HOUR
            and len(authors) >= config.MIN_UNIQUE_AUTHORS
        )

        return {
            "mentions_per_hour": round(mentions_per_hour, 1),
            "unique_authors": len(authors),
            "is_active": is_active,
        }

    def discover_trending_tokens(self, candidate_symbols: list) -> dict:
        """
        Scan a list of candidate token symbols (you supply the watchlist —
        e.g. from a token-launch feed or your own shortlist) and return
        only the ones showing active social signal.

        NOTE: This does NOT invent tokens to trade. "Scan all of X for
        good memes" isn't something an API can do unprompted — you still
        need a source of candidate symbols (a launch feed, a curated
        list, or DexScreener's new-pairs endpoint). Wire that in as the
        `candidate_symbols` input.
        """
        results = {}
        for sym in candidate_symbols:
            try:
                results[sym] = self.scan_token(sym)
            except Exception as e:
                results[sym] = {"error": str(e)}
            time.sleep(1)  # be polite to rate limits
        return {k: v for k, v in results.items() if v.get("is_active")}


def _parse_iso(ts: str) -> float:
    import datetime
    dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
