#!/usr/bin/env python3
"""
AkkisHost External Uptime Checker
- Reads targets from sites.yml
- Supports sub-pages via pages:
- Async HTTP checks with retries/timeouts
- Fails (exit code 2) if any site fails
- Optional Slack webhook via SLACK_WEBHOOK_URL
- Optional JSON report with --json
"""
import asyncio
import os
import sys
import json
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    import yaml
except ImportError:
    print("Please install: pip install aiohttp pyyaml", file=sys.stderr)
    sys.exit(1)


OK_STATUS_RANGES = [(200, 299), (300, 399)]


def parse_status_ranges(ranges: List[str]):
    out = []

    for r in ranges:
        try:
            a, b = map(int, r.split("-"))
            out.append((min(a, b), max(a, b)))
        except Exception:
            pass

    return out or OK_STATUS_RANGES


def is_status_ok(status: int, expected: Optional[int], ranges) -> bool:
    if expected is not None:
        return status == expected

    return any(lo <= status <= hi for lo, hi in ranges)


def expand_sites(raw_sites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sites = []

    for site in raw_sites:
        parent = dict(site)
        parent.pop("pages", None)
        sites.append(parent)

        base_url = site.get("url", "").rstrip("/")

        for page in site.get("pages", []):
            path = page.get("path", "/")
            full_url = base_url + path if path.startswith("/") else base_url + "/" + path

            child = {
                **site,
                **page,
                "url": full_url,
                "parent": site.get("name") or site.get("url"),
            }

            child.pop("pages", None)

            # Parent keyword alt sayfalara otomatik geçmesin.
            # Alt sayfada keyword istenirse page altında ayrıca yazılabilir.
            if "keyword" not in page:
                child.pop("keyword", None)

            sites.append(child)

    return sites


async def fetch_once(session: aiohttp.ClientSession, url: str, timeout: int):
    headers = {"User-Agent": "akkishost-uptime/1.0"}
    return await session.get(
        url,
        timeout=timeout,
        headers=headers,
        allow_redirects=True,
    )


async def check_site(
    session: aiohttp.ClientSession,
    site: Dict[str, Any],
    defaults: Dict[str, Any],
    ranges,
):
    if site.get("disabled"):
        return {
            "url": site.get("url"),
            "status": "skipped",
            "reason": "disabled",
        }

    url = site["url"]
    expected = site.get("expected_status")
    keyword = site.get("keyword")
    timeout = int(site.get("timeout", defaults.get("timeout", 10)))
    retries = int(site.get("retries", defaults.get("retries", 1)))

    last_exc = None

    for _ in range(retries + 1):
        try:
            resp = await fetch_once(session, url, timeout)
            status = resp.status
            body = await resp.content.read(4096)
            text = body.decode("utf-8", errors="ignore")

            ok = is_status_ok(status, expected, ranges)

            if ok and keyword:
                ok = keyword.lower() in text.lower()

                if not ok:
                    last_exc = Exception(
                        f"Keyword not found: {keyword} (HTTP {status})"
                    )
                    await asyncio.sleep(0.5)
                    continue

            if ok:
                return {
                    "url": url,
                    "status": "ok",
                    "http_status": status,
                }

            last_exc = Exception(
                f"Unexpected status {status}"
                + (f" (expected {expected})" if expected else "")
            )

        except Exception as e:
            last_exc = e

        await asyncio.sleep(0.5)

    return {
        "url": url,
        "status": "fail",
        "error": str(last_exc),
    }


async def send_slack(webhook: str, text: str):
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(webhook, json={"text": text}, timeout=10) as r:
                await r.text()
        except Exception:
            pass


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", default="monitor/sites.yml")
    parser.add_argument("--concurrency", "-j", type=int, default=10)
    parser.add_argument("--json")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_sites = data.get("sites", [])
    sites = expand_sites(raw_sites)

    defaults = data.get("defaults", {})
    ranges = parse_status_ranges(
        defaults.get("allow_status_ranges", ["200-299", "300-399"])
    )

    timeout = aiohttp.ClientTimeout(
        total=None,
        sock_connect=10,
        sock_read=15,
    )

    async with aiohttp.ClientSession(timeout=timeout) as session:
        sem = asyncio.Semaphore(max(1, args.concurrency))

        async def run(site):
            async with sem:
                return await check_site(session, site, defaults, ranges)

        results = await asyncio.gather(*(run(site) for site in sites))

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "fail")
    skip = sum(1 for r in results if r["status"] == "skipped")

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    lines = [f"🔍 AkkisHost Uptime — {now}"]

    for r in results:
        if r["status"] == "ok":
            lines.append(f"✅ {r['url']} - OK (HTTP {r.get('http_status')})")
        elif r["status"] == "skipped":
            lines.append(f"⏭️  {r['url']} (skipped)")
        else:
            lines.append(f"❌ {r['url']} — {r.get('error', 'unknown error')}")

    summary = f"OK:{ok} | FAIL:{fail} | SKIP:{skip} | Total:{len(results)}"
    lines.append(summary)

    out = "\n".join(lines)
    print(out)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as jf:
            json.dump(
                {
                    "timestamp": now,
                    "summary": {
                        "ok": ok,
                        "fail": fail,
                        "skip": skip,
                        "total": len(results),
                    },
                    "results": results,
                },
                jf,
                ensure_ascii=False,
                indent=2,
            )

    webhook = os.getenv("SLACK_WEBHOOK_URL")

    if webhook:
        await send_slack(webhook, ("✅" if fail == 0 else "❌") + " " + out)

    sys.exit(0 if fail == 0 else 2)


if __name__ == "__main__":
    asyncio.run(main())
