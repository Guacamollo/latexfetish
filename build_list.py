#!/usr/bin/env python3
"""Generate formatted link list for markdown text from a JSON file.

Usage:
    python build_list.py data/shops.json
        # print the markdown to stdout

    python build_list.py data/shops.json -o shoplist.md
        # write the markdown to shoplist.md instead of stdout

    python build_list.py data/shops.json --sort-json
        # rewrite the JSON file with shops and platforms sorted
        # and URLs normalized:
        #   - shops sorted alphabetically by name
        #   - links sorted website-first, then alphabetical
        #   - trailing slashes trimmed from URLs
        #   - twitter.com URLs rewritten to x.com

Icon and flag lookup prefers .svg and falls back to .png. Missing files
print a warning to stderr but don't stop the build.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# --- Configuration -----------------------------------------------------------

PLATFORMS = {
    "24vids":                    {"alt": "24vids",                  "title": "24vids"},
    "behance":                   {"alt": "behance",                 "title": "Behance"},
    "bluesky":                   {"alt": "bluesky",                 "title": "Bluesky"},
    "deviantart":                {"alt": "deviantart",              "title": "DeviantArt"},
    "ebay":                      {"alt": "ebay",                    "title": "eBay"},
    "etsy":                      {"alt": "etsy",                    "title": "Etsy"},
    "facebook":                  {"alt": "facebook",                "title": "Facebook"},
    "fetish-x":                  {"alt": "fetish-x",                "title": "fetish-x"},
    "fetlife":                   {"alt": "fetlife",                 "title": "FetLife"},
    "fler":                      {"alt": "fler",                    "title": "Fler"},
    "flickr":                    {"alt": "flickr",                  "title": "Flickr"},
    "instagram":                 {"alt": "instagram",               "title": "Instagram"},
    "joyclub":                   {"alt": "joyclub",                 "title": "JoyClub"},
    "kavyar":                    {"alt": "kavyar",                  "title": "Kavyar"},
    "latex247":                  {"alt": "latex247",                "title": "Latex 24/7"},
    "latexvideos":               {"alt": "latexvideos",             "title": "Latex Videos"},
    "latexzentrale":             {"alt": "latexzentrale",           "title": "LatexZentrale"},
    "linkedin":                  {"alt": "linkedin",                "title": "LinkedIn"},
    "model-kartei":              {"alt": "model-kartei",            "title": "Model-Kartei"},
    "modelmayhem":               {"alt": "modelmayhem",             "title": "Model Mayhem"},
    "peopleperhour":             {"alt": "peopleperhour",           "title": "People Per Hour"},
    "pinterest":                 {"alt": "pinterest",               "title": "Pinterest"},
    "purpleport":                {"alt": "purpleport",              "title": "PurplePort"},
    "shop":                      {"alt": "shop",                    "title": "Shop.app"},
    "thefetishistasdirectory":   {"alt": "thefetishistasdirectory", "title": "The Fetishistas Directory"},
    "threads":                   {"alt": "threads",                 "title": "Threads"},
    "tiktok":                    {"alt": "tiktok",                  "title": "TikTok"},
    "tumblr":                    {"alt": "tumblr",                  "title": "Tumblr"},
    "wearlatex":                 {"alt": "wearlatex",               "title": "WearLatex"},
    "website":                   {"alt": "website",                 "title": "Website"},
    "x":                         {"alt": "x (twitter)",             "title": "X (Twitter)"},
    "youtube":                   {"alt": "youtube",                 "title": "YouTube"},
}

COUNTRIES = {
    "at": "Austria",
    "au": "Australia",
    "be": "Belgium",
    "bg": "Bulgaria",
    "ca": "Canada",
    "ch": "Switzerland",
    "cl": "Chile",
    "cz": "Czechia",
    "de": "Germany",
    "es": "Spain",
    "fi": "Finland",
    "fr": "France",
    "gb": "United Kingdom",
    "hu": "Hungary",
    "it": "Italy",
    "nl": "Netherlands",
    "nz": "New Zealand",
    "pl": "Poland",
    "ru": "Russia",
    "se": "Sweden",
    "ua": "Ukraine",
    "us": "United States of America",
}

# Match twitter.com
TWITTER_HOST_RE = re.compile(
    r'^(https?://)(?:www\.|mobile\.)?twitter\.com(?=[/:?#]|$)',
    re.IGNORECASE,
)

# Disk paths
SCRIPT_DIR = Path(__file__).resolve().parent
ICONS_DIR = SCRIPT_DIR / "assets" / "icons"
FLAGS_DIR = SCRIPT_DIR / "assets" / "flags"

# URL paths
ICONS_URL = "../assets/icons"
FLAGS_URL = "../assets/flags"

# Asset extensions to try, in order of preference.
ASSET_EXTENSIONS = (".svg", ".png")

# --- Asset resolution --------------------------------------------------------

def resolve_asset(directory, stem):
    for ext in ASSET_EXTENSIONS:
        candidate = f"{stem}{ext}"
        if (directory / candidate).exists():
            return candidate, True
    return f"{stem}{ASSET_EXTENSIONS[0]}", False

# --- Sorting -----------------------------------------------------------------

def sort_shops(shops):
    # Shops with a country first (by country name, then shop name),
    # then shops without a country (by shop name).
    def key(s):
        country = s.get("country")
        if country:
            return (0, COUNTRIES[country], s["name"].lower())
        return (1, "", s["name"].lower())
    return sorted(shops, key=key)


def sort_links(links):
    # "website" always first, the rest alphabetical by platform.
    return sorted(links, key=lambda lk: (0 if lk["platform"] == "website" else 1, lk["platform"]))

# --- URL normalization -------------------------------------------------------

def normalize_url(url):
    """Rewrite twitter.com to x.com and trim trailing slashes."""
    new_url = TWITTER_HOST_RE.sub(r'\1x.com', url)
    new_url = new_url.rstrip("/")
    return new_url


def clean_urls(shops):
    """Apply normalize_url to every link in place. Returns the count of URLs changed."""
    changes = 0
    for shop in shops:
        for link in shop["links"]:
            original = link.get("url")
            if not original:
                continue
            cleaned = normalize_url(original)
            if cleaned != original:
                link["url"] = cleaned
                changes += 1
    return changes

# --- Rendering ---------------------------------------------------------------

def icon_stem(platform):
    meta = PLATFORMS[platform]
    return Path(meta.get("icon", platform)).stem


def icon_filename(platform):
    filename, _ = resolve_asset(ICONS_DIR, icon_stem(platform))
    return filename


def flag_filename(country):
    filename, _ = resolve_asset(FLAGS_DIR, country)
    return filename


def render_icon(platform):
    meta = PLATFORMS[platform]
    src = f'{ICONS_URL}/{icon_filename(platform)}'
    return (f'<img src="{src}" alt="{meta["alt"]}" 'f'title="{meta["title"]}" width="20">')


def render_link(link):
    inner = render_icon(link["platform"])
    if link.get("label"):
        inner = f'{inner} {link["label"]} '
    return f'[{inner}]({link["url"]})'


def render_flag(country):
    src = f'{FLAGS_URL}/{flag_filename(country)}'
    return (f'<img src="{src}" width="20" '
            f'alt="{country.upper()}" title="{COUNTRIES[country]}">')


def render_shop(shop):
    links = " ".join(render_link(lk) for lk in sort_links(shop["links"]))
    country = shop.get("country")
    if country:
        return f'- {render_flag(country)} **{shop["name"]}** {links}'
    return f'- **{shop["name"]}** {links}'


def render_all(shops):
    return "\n".join(render_shop(s) for s in sort_shops(shops))

# --- Validation --------------------------------------------------------------

def validate(shops):
    errors, warnings = [], []
    tried = " or ".join(ext.lstrip(".") for ext in ASSET_EXTENSIONS)
    for shop in shops:
        where = shop.get("name", "<unnamed shop>")
        country = shop.get("country")
        if country is not None:
            if country not in COUNTRIES:
                errors.append(f'{where}: unknown country "{country}"')
            else:
                _, found = resolve_asset(FLAGS_DIR, country)
                if not found:
                    warnings.append(f'{where}: missing flag file for "{country}" (tried {tried})')
        for link in shop["links"]:
            platform = link.get("platform")
            if platform not in PLATFORMS:
                errors.append(f'{where}: unknown platform "{platform}"')
                continue
            if "url" not in link:
                errors.append(f'{where} ({platform}): missing "url"')
            _, found = resolve_asset(ICONS_DIR, icon_stem(platform))
            if not found:
                warnings.append(f'{where}: missing icon file for "{platform}" (tried {tried})')
    return errors, warnings

# --- JSON loading ------------------------------------------------------------

def load_shops(json_path):
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"error: invalid JSON in {json_path}: {e}")

    if isinstance(data, list):
        return data, None, data

    if isinstance(data, dict):
        list_keys = [k for k, v in data.items() if isinstance(v, list)]
        if not list_keys:
            sys.exit(f"error: {json_path} has no top-level list of shops.")
        if len(list_keys) > 1:
            sys.exit(f'error: {json_path} has multiple top-level lists '
                     f'({", ".join(list_keys)}); not sure which holds '
                     f'the shops.')
        key = list_keys[0]
        return data[key], key, data

    sys.exit(f"error: {json_path} top-level JSON must be a list or object.")

# --- Main --------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate the shop link list for a README from a shops JSON file.")
    parser.add_argument("json_path", help="Path to the shops JSON file.")
    parser.add_argument("-o", "--output", help="Write rendered markdown to this file instead of stdout. Cannot be combined with --sort-json.")
    parser.add_argument("--sort-json", action="store_true", help="Rewrite the JSON file in place with shops sorted by name, links website-first, trailing slashes trimmed from URLs, and twitter.com URLs rewritten to x.com. No markdown is produced.")
    args = parser.parse_args(argv)

    if args.sort_json and args.output:
        parser.error("--output cannot be combined with --sort-json (--sort-json rewrites the input file and produces no markdown output).")
    return args


def main(argv=None):
    args = parse_args(argv)

    json_path = Path(args.json_path).resolve()
    if not json_path.is_file():
        sys.exit(f"error: JSON file not found: {json_path}")

    shops, wrapper_key, data = load_shops(json_path)

    errors, warnings = validate(shops)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.sort_json:
        url_changes = clean_urls(shops)
        # JSON file is sorted by shop name only
        sorted_shops = sorted(shops, key=lambda s: s["name"].lower())
        for shop in sorted_shops:
            shop["links"] = sort_links(shop["links"])
        if wrapper_key is None:
            payload = sorted_shops
        else:
            data[wrapper_key] = sorted_shops
            payload = data
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        extra = f", normalized {url_changes} URL(s)" if url_changes else ""
        print(f"{json_path.name} sorted (shops by name, links website-first){extra}.")
        return

    rendered = render_all(shops)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {output_path}", file=sys.stderr)
    else:
        print(rendered)


if __name__ == "__main__":
    main()