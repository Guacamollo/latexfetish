#!/usr/bin/env python3
"""Generate formatted markdown link page from data JSON file.

Usage:
    python build_list.py data/designers.json
        # print markdown page to stdout

    python build_list.py data/designers.json -o docs/designers.md
        # write markdown page to docs/designers.md

    python build_list.py data/designers.json --sort-json
        # rewrite JSON file with entries and links sorted
        # and URLs normalized:
        #   - entries sorted alphabetically by name
        #   - links sorted website-first, then by platform and label
        #   - trailing slashes trimmed from URLs
        #   - twitter.com URLs rewritten to x.com

Icon and flag lookup prefers .svg and falls back to .png.
Missing files print a warning to stderr but don't stop the build.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# --- Configuration -----------------------------------------------------------

# Page titles by top-level JSON key (fallback: key, title-cased).
TITLES = {
    "care": "Care & Maintenance",
    "communities": "Communities",
    "designers": "Designers",
    "events": "Events",
    "magazines": "Magazines & Media",
    "models": "Models",
    "photographers": "Photographers & Gallery Sites",
    "resources": "Resources",
    "shops": "Shops, Retailers & Resellers",
}

# platform id -> display title. Icon file is assets/icons/<id>.svg|.png and alt text is lowercased title.
PLATFORMS = {
    "24vids":                    "24vids",
    "behance":                   "Behance",
    "bluesky":                   "Bluesky",
    "deviantart":                "DeviantArt",
    "discord":                   "Discord",
    "diversia":                  "Diversia",
    "ebay":                      "eBay",
    "etsy":                      "Etsy",
    "facebook":                  "Facebook",
    "feeds2":                    "Feeds 2.0",
    "fetish-x":                  "fetish-x",
    "fetlife":                   "FetLife",
    "fler":                      "Fler",
    "flickr":                    "Flickr",
    "instagram":                 "Instagram",
    "joyclub":                   "JoyClub",
    "kavyar":                    "Kavyar",
    "latex247":                  "Latex 24/7",
    "latexvideos":               "Latex Videos",
    "latexzentrale":             "LatexZentrale",
    "linkedin":                  "LinkedIn",
    "model-kartei":              "Model-Kartei",
    "modelmayhem":               "Model Mayhem",
    "patreon":                   "Patreon",
    "peopleperhour":             "People Per Hour",
    "pinterest":                 "Pinterest",
    "purpleport":                "PurplePort",
    "reddit":                    "Reddit",
    "shop":                      "Shop.app",
    "sklavenzentrale":           "Sklavenzentrale",
    "spotify":                   "Spotify",
    "thefetishistasdirectory":   "The Fetishistas Directory",
    "threads":                   "Threads",
    "tiktok":                    "TikTok",
    "tumblr":                    "Tumblr",
    "twitch":                    "Twitch",
    "vimeo":                     "Vimeo",
    "wearlatex":                 "WearLatex",
    "website":                   "Website",
    "x":                         "X (Twitter)",
    "youtube":                   "YouTube",
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
    "dk": "Denmark",
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
    "uk": "United Kingdom",
    "us": "United States of America",
    "za": "South Africa",
}

GENDERS = ("female", "male", "Non-binary", "other")
ENTRY_KEYS = {"name", "country", "countries", "gender", "former_name", "type", "note", "links"}
LINK_KEYS = {"platform", "url", "label"}

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

# Asset extensions
ASSET_EXTENSIONS = (".svg", ".png")

# --- Asset resolution --------------------------------------------------------

def resolve_asset(directory, stem):
    for ext in ASSET_EXTENSIONS:
        candidate = f"{stem}{ext}"
        if (directory / candidate).exists():
            return candidate, True
    return f"{stem}{ASSET_EXTENSIONS[0]}", False

# --- Sorting -----------------------------------------------------------------

def entry_countries(entry):
    """Return the entry's country codes as a list ("country" or "countries")."""
    if entry.get("countries"):
        return entry["countries"]
    if entry.get("country"):
        return [entry["country"]]
    return []


def sort_entries(entries):
    # Entries with country first (by first country name, then entry name),
    # then without country (by entry name).
    def key(entry):
        countries = entry_countries(entry)
        if countries:
            return (0, COUNTRIES[countries[0]], entry["name"].lower())
        return (1, "", entry["name"].lower())
    return sorted(entries, key=key)


def sort_links(links):
    # "website" always first, rest by platform, then label.
    return sorted(links, key=lambda lk: (0 if lk["platform"] == "website" else 1, lk["platform"], lk.get("label") or ""))

# --- URL normalization -------------------------------------------------------

def normalize_url(url):
    """Rewrite twitter.com to x.com and trim trailing slashes."""
    new_url = TWITTER_HOST_RE.sub(r'\1x.com', url)
    new_url = new_url.rstrip("/")
    return new_url


def clean_urls(entries):
    """Apply normalize_url to every link in place. Returns count of URLs changed."""
    changes = 0
    for entry in entries:
        for link in entry["links"]:
            original = link.get("url")
            if not original:
                continue
            cleaned = normalize_url(original)
            if cleaned != original:
                link["url"] = cleaned
                changes += 1
    return changes

# --- Rendering ---------------------------------------------------------------

def icon_filename(platform):
    filename, _ = resolve_asset(ICONS_DIR, platform)
    return filename


def flag_filename(country):
    filename, _ = resolve_asset(FLAGS_DIR, country)
    return filename


def render_icon(platform):
    title = PLATFORMS[platform]
    src = f'{ICONS_URL}/{icon_filename(platform)}'
    return (f'<img src="{src}" alt="{title.lower()}" '
            f'title="{title}" width="20">')


def render_link(link):
    inner = render_icon(link["platform"])
    if link.get("label"):
        inner = f'{inner} {link["label"]}'
    return f'[{inner}]({link["url"]})'


def render_flag(country):
    src = f'{FLAGS_URL}/{flag_filename(country)}'
    return (f'<img src="{src}" width="20" '
            f'alt="{country.upper()}" title="{COUNTRIES[country]}">')


def render_entry(entry):
    name = f'**{entry["name"]}**'
    if entry.get("former_name"):
        name += f' *(formerly {entry["former_name"]})*'
    if entry.get("type"):
        name += f' *({entry["type"]})*'
    flags = " ".join(render_flag(c) for c in entry_countries(entry))
    links = " ".join(render_link(lk) for lk in sort_links(entry["links"]))
    line = "- " + " ".join(part for part in (flags, name, links) if part)
    if entry.get("note"):
        line += f' - *{entry["note"]}*'
    return line


def render_list(entries):
    return "\n".join(render_entry(e) for e in sort_entries(entries))


def render_page(entries, title):
    """Render the full page: heading, then the list (grouped by gender if used)."""
    parts = [f"# {title}"]
    if any(e.get("gender") for e in entries):
        for gender in GENDERS:
            group = [e for e in entries if e.get("gender", "other") == gender]
            if group:
                parts += ["", f"## {gender.title()}", "", render_list(group)]
    else:
        parts += ["", render_list(entries)]
    return "\n".join(parts)

# --- Validation --------------------------------------------------------------

def _validate_countries(entry, where, errors, warnings, tried):
    if entry.get("country") and entry.get("countries"):
        errors.append(f'{where}: has both "country" and "countries"')
    for country in entry_countries(entry):
        if country not in COUNTRIES:
            errors.append(f'{where}: unknown country "{country}"')
        else:
            _, found = resolve_asset(FLAGS_DIR, country)
            if not found:
                warnings.append(f'{where}: missing flag file for "{country}" (tried {tried})')


def _validate_link(link, where, errors, warnings, tried):
    for key in link:
        if key not in LINK_KEYS:
            warnings.append(f'{where}: unknown link key "{key}" (ignored)')
    platform = link.get("platform")
    if platform not in PLATFORMS:
        errors.append(f'{where}: unknown platform "{platform}"')
        return
    if "url" not in link:
        errors.append(f'{where} ({platform}): missing "url"')
    _, found = resolve_asset(ICONS_DIR, platform)
    if not found:
        warnings.append(f'{where}: missing icon file for "{platform}" (tried {tried})')


def _validate_entry(entry, errors, warnings, tried):
    where = entry.get("name", "<unnamed entry>")
    for key in entry:
        if key not in ENTRY_KEYS:
            warnings.append(f'{where}: unknown key "{key}" (ignored)')
    gender = entry.get("gender")
    if gender is not None and gender not in GENDERS:
        errors.append(f'{where}: unknown gender "{gender}" '
                      f'(expected one of {", ".join(GENDERS)})')
    _validate_countries(entry, where, errors, warnings, tried)
    links = entry.get("links")
    if not isinstance(links, list):
        errors.append(f'{where}: missing "links" list')
        return
    for link in links:
        _validate_link(link, where, errors, warnings, tried)


def validate(entries):
    errors, warnings = [], []
    tried = " or ".join(ext.lstrip(".") for ext in ASSET_EXTENSIONS)
    for entry in entries:
        _validate_entry(entry, errors, warnings, tried)
    return errors, warnings

# --- JSON loading ------------------------------------------------------------

def load_entries(json_path):
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"error: invalid JSON in {json_path}: {e}")

    if isinstance(data, list):
        return data, None, data

    if isinstance(data, dict):
        list_keys = [k for k, v in data.items() if isinstance(v, list)]
        if not list_keys:
            sys.exit(f"error: {json_path} has no top-level list of entries.")
        if len(list_keys) > 1:
            sys.exit(f'error: {json_path} has multiple top-level lists '
                     f'({", ".join(list_keys)}); not sure which holds '
                     f'the entries.')
        key = list_keys[0]
        return data[key], key, data

    sys.exit(f"error: {json_path} top-level JSON must be a list or object.")

# --- Main --------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate markdown link page from data JSON file.")
    parser.add_argument("json_path", help="Path to data JSON file.")
    parser.add_argument("-o", "--output", help="Write rendered markdown page to this file. Cannot be combined with --sort-json.")
    parser.add_argument("--title", help="Override page heading (default: derived from JSON file's top-level key).")
    parser.add_argument("--sort-json", action="store_true", help="Rewrite JSON file in place with entries sorted by name, links website-first, trailing slashes trimmed from URLs, and twitter.com URLs rewritten to x.com. No markdown is produced.")
    args = parser.parse_args(argv)

    if args.sort_json and args.output:
        parser.error("--output cannot be combined with --sort-json (--sort-json rewrites the input file and produces no markdown output).")
    return args


def report_problems(entries):
    errors, warnings = validate(entries)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def sort_json_file(json_path, entries, wrapper_key, data):
    url_changes = clean_urls(entries)
    # JSON file is sorted by entry name only
    sorted_entries = sorted(entries, key=lambda e: e["name"].lower())
    for entry in sorted_entries:
        entry["links"] = sort_links(entry["links"])
    if wrapper_key is None:
        payload = sorted_entries
    else:
        data[wrapper_key] = sorted_entries
        payload = data
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    extra = f", normalized {url_changes} URL(s)" if url_changes else ""
    print(f"{json_path.name} sorted (entries by name, links website-first){extra}.")


def main(argv=None):
    args = parse_args(argv)

    # Redirected stdout on Windows defaults to legacy code page.
    # Force UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    json_path = Path(args.json_path).resolve()
    if not json_path.is_file():
        sys.exit(f"error: JSON file not found: {json_path}")

    entries, wrapper_key, data = load_entries(json_path)
    report_problems(entries)

    if args.sort_json:
        sort_json_file(json_path, entries, wrapper_key, data)
        return

    key = wrapper_key or json_path.stem
    title = args.title or TITLES.get(key, key.replace("_", " ").title())
    rendered = render_page(entries, title)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {output_path}", file=sys.stderr)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
