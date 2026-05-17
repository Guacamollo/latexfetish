#!/usr/bin/env python3
"""
Download a website's favicon.

Strategy:
  1. Fetch page and parse <link rel="icon" | "shortcut icon" | "apple-touch-icon" ...> tags
  2. Gets biggest images; Prefers SVGs
  3. Fall back to <scheme>://<host>/favicon.ico
  4. Save as PNG; SVGs pass through unchanged

Requires: curl_cffi, beautifulsoup4, Pillow, tldextract
    pip install curl_cffi beautifulsoup4 Pillow tldextract
"""

import argparse
import io
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import tldextract
from bs4 import BeautifulSoup
from curl_cffi import requests
from PIL import Image

IMPERSONATE = "chrome133"

ICON_RELS = {
    "icon",
    "shortcut icon",
    "apple-touch-icon",
    "apple-touch-icon-precomposed",
    "mask-icon",
}


def _parse_size(sizes_attr: str | None) -> int:
    """Return largest dimension declared in a `sizes` attribute, or 0."""
    if not sizes_attr:
        return 0
    best = 0
    for token in sizes_attr.split():
        if token.lower() == "any":  # SVG / scalable
            return 10_000
        try:
            w, h = token.lower().split("x")
            best = max(best, int(w), int(h))
        except ValueError:
            continue
    return best


def _clean_filename(netloc: str) -> str:
    host = netloc.lower().split(":")[0]  # drop :port
    extracted = tldextract.extract(host)
    return extracted.domain or host


def find_icon_candidates(page_url: str) -> list[str]:
    """Return absolute icon URLs found in page, best first."""
    try:
        resp = requests.get(
            page_url,
            timeout=10,
            allow_redirects=True,
            impersonate=IMPERSONATE,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"Warning: could not fetch page ({e}); falling back to /favicon.ico",
              file=sys.stderr)
        return []

    final_url = resp.url
    soup = BeautifulSoup(resp.text, "html.parser")

    scored = []
    for link in soup.find_all("link", rel=True):
        rels = {r.lower() for r in link.get("rel", [])}
        if rels.isdisjoint(ICON_RELS):
            continue
        href = link.get("href")
        if not href or href.startswith("data:"):
            continue
        absolute = urljoin(final_url, href)

        # Prefer SVGs
        link_type = (link.get("type") or "").lower()
        path = absolute.lower().split("?", 1)[0]
        is_svg = link_type == "image/svg+xml" or path.endswith(".svg")

        size = _parse_size(link.get("sizes"))
        if is_svg:
            size = max(size, 10_000)

        rel_bonus = 1 if rels & {"icon", "shortcut icon"} else 0
        scored.append((size, rel_bonus, absolute))

    scored.sort(reverse=True)
    return [url for _, _, url in scored]


def _is_svg(content: bytes) -> bool:
    """Detect SVG by content"""
    head = content.lstrip()[:2048].lower()
    return (head.startswith(b"<?xml") and b"<svg" in head) or head.startswith(b"<svg")


def _to_png(content: bytes) -> bytes:
    """Decode any raster image and re-encode as PNG"""
    img = Image.open(io.BytesIO(content))
    if img.format == "ICO" and hasattr(img, "ico"):
        sizes = img.ico.sizes()
        if sizes:
            largest = max(sizes, key=lambda s: s[0] * s[1])
            img = img.ico.getimage(largest)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def download_favicon(page_url: str, out_dir: str = ".") -> Path | None:
    if not page_url.startswith(("http://", "https://")):
        page_url = "https://" + page_url

    parsed = urlparse(page_url)
    root_fallback = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    candidates = find_icon_candidates(page_url)
    if root_fallback not in candidates:
        candidates.append(root_fallback)

    host = parsed.netloc
    candidates.append(f"https://www.google.com/s2/favicons?domain={host}&sz=128")
    candidates.append(f"https://icons.duckduckgo.com/ip3/{host}.ico")

    name = _clean_filename(parsed.netloc)

    for url in candidates:
        try:
            resp = requests.get(
                url,
                timeout=10,
                allow_redirects=True,
                impersonate=IMPERSONATE,
            )
        except Exception as e:
            print(f"  {url}: request failed ({e})", file=sys.stderr)
            continue
        if resp.status_code != 200:
            print(f"  {url}: HTTP {resp.status_code}", file=sys.stderr)
            continue
        if not resp.content:
            print(f"  {url}: empty response body", file=sys.stderr)
            continue
        ctype = resp.headers.get("Content-Type", "").lower()
        if "html" in ctype:
            print(f"  {url}: skipped (Content-Type {ctype!r} looks like an HTML error page)",
                  file=sys.stderr)
            continue

        content = resp.content
        try:
            if _is_svg(content):
                data, ext = content, ".svg"
            else:
                data, ext = _to_png(content), ".png"
        except Exception as e:
            print(f"  {url}: could not decode ({e})", file=sys.stderr)
            continue

        filename = Path(out_dir) / f"{name}{ext}"
        filename.write_bytes(data)
        print(f"Saved {url} -> {filename}")
        return filename

    print("No favicon could be downloaded.", file=sys.stderr)
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Download a website's favicon as PNG (or SVG).")
    p.add_argument("url", help="Site URL, e.g. https://stackoverflow.com")
    p.add_argument("-o", "--out-dir", default=".", help="Directory to save the icon in")
    args = p.parse_args()
    return 0 if download_favicon(args.url, args.out_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())