import datetime
import email.utils
import http.client
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

FIRST_RUN_ENTRIES = 5


def normalize(url):
    parts = urllib.parse.urlsplit(url.strip())
    path = parts.path.rstrip("/") or ""
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def host(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def fetch(url, command=None):
    if command:
        proc = subprocess.run(shlex.split(command) + [url], capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write("fetch failed for %s (exit %d): %s\n" % (url, proc.returncode, proc.stderr.strip()[-200:]))
            return None
        return proc.stdout
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "flynns-workflows-kb-scout"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (OSError, ValueError, http.client.HTTPException) as exc:
        sys.stderr.write("fetch failed for %s: %s\n" % (url, exc))
        return None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(node, *names):
    for child in node.iter():
        if _local(child.tag) in names and child is not node and (child.text or "").strip():
            return child.text.strip()
    return ""


def _iso(raw):
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        when = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_feed(body):
    root = ET.fromstring(body)
    entries = []
    for node in root.iter():
        kind = _local(node.tag)
        if kind not in ("entry", "item"):
            continue
        link = ""
        for child in node:
            if _local(child.tag) == "link":
                href = child.get("href")
                if href and child.get("rel", "alternate") == "alternate":
                    link = href
                    break
                if (child.text or "").strip():
                    link = child.text.strip()
        if not link:
            continue
        author = ""
        for child in node:
            if _local(child.tag) in ("author", "creator"):
                author = _text(child, "name") or (child.text or "").strip()
                break
        entries.append(
            {
                "url": link,
                "title": _text(node, "title"),
                "published": _iso(_text(node, "published", "updated", "pubDate", "date")),
                "author": author,
            }
        )
    return entries


def new_entries(entries, mark, known):
    if not mark:
        dated = sorted((e for e in entries if e["published"]), key=lambda e: e["published"], reverse=True)
        undated = [e for e in entries if not e["published"] and normalize(e["url"]) not in known]
        return (dated + undated)[:FIRST_RUN_ENTRIES]
    return [
        e
        for e in entries
        if (e["published"] and e["published"] > mark) or (not e["published"] and normalize(e["url"]) not in known)
    ]


BODY_CLASSES = ({"paperBody"}, {"appendix"}, {"body", "markup"})
ASSET_HOSTS = ("substackcdn.com",)
ASSET_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".heic", ".ico", ".css", ".js", ".woff", ".woff2")
AMAZON_HOST = re.compile(r"^(www\.)?amazon\.[a-z.]+$")


def _is_body(attrs):
    tokens = set((dict(attrs).get("class") or "").split())
    return any(needed <= tokens for needed in BODY_CLASSES)


BLOCK_TAGS = ("p", "li", "blockquote", "td", "dd", "h1", "h2", "h3", "h4", "h5", "h6")
IMPLIED_END = ("p", "li", "td", "dd")
NON_ARTICLE_HOSTS = ("youtube.com", "youtu.be", "wikipedia.org", "linkedin.com", "x.com", "twitter.com")
ANCHOR_LIMIT = 120
CONTEXT_LIMIT = 300
CONTEXT_LEAD = 150


def _collapse(text):
    return " ".join(text.split())


class _Block:
    def __init__(self, tag):
        self.tag = tag
        self.parts = []


class _Link:
    def __init__(self, href, block, offset, in_body):
        self.href = href
        self.block = block
        self.offset = offset
        self.in_body = in_body
        self.parts = []


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []
        self.has_body = False
        self.skip = 0
        self.body = 0
        self.ignore = 0
        self.blocks = []
        self.anchor = None

    def _close_block(self, tag):
        names = [b.tag for b in self.blocks]
        if tag in names:
            while self.blocks:
                if self.blocks.pop().tag == tag:
                    break

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            if self.body:
                self.body += 1
            elif _is_body(attrs):
                self.body = 1
                self.has_body = True
        elif tag in ("nav", "footer", "header"):
            self.skip += 1
        elif tag in ("script", "style"):
            self.ignore += 1
        elif tag in BLOCK_TAGS:
            if self.blocks and self.blocks[-1].tag in IMPLIED_END and tag in IMPLIED_END:
                self.blocks.pop()
            self.blocks.append(_Block(tag))
        elif tag == "a" and not self.skip:
            href = dict(attrs).get("href")
            if href:
                block = self.blocks[-1] if self.blocks else None
                offset = len("".join(block.parts)) if block else 0
                self.anchor = _Link(href, block, offset, bool(self.body))
                self.found.append(self.anchor)

    def handle_endtag(self, tag):
        if tag == "div" and self.body:
            self.body -= 1
        elif tag in ("nav", "footer", "header") and self.skip:
            self.skip -= 1
        elif tag in ("script", "style") and self.ignore:
            self.ignore -= 1
        elif tag in BLOCK_TAGS:
            self._close_block(tag)
        elif tag == "a":
            self.anchor = None

    def handle_data(self, data):
        if self.ignore:
            return
        if self.blocks:
            self.blocks[-1].parts.append(data)
        if self.anchor is not None:
            self.anchor.parts.append(data)


def _excluded(absolute):
    parts = urllib.parse.urlsplit(absolute)
    name = parts.netloc.lower()
    if name in ASSET_HOSTS or name.endswith(".substackcdn.com"):
        return True
    if parts.path.lower().endswith(ASSET_EXTENSIONS):
        return True
    if AMAZON_HOST.match(name) or name == "amzn.to":
        return True
    if is_noise(absolute):
        return True
    return name in ("kentbeck.com", "www.kentbeck.com") and parts.path.startswith("/kent-beck-sponsorship")


def is_noise(url):
    parts = urllib.parse.urlsplit(normalize(url))
    name = (parts.hostname or "").lower()
    if any(name == h or name.endswith("." + h) for h in NON_ARTICLE_HOSTS):
        return True
    return not parts.path


def _context(link, anchor):
    if link.block is None:
        return anchor
    raw = "".join(link.block.parts)
    text = _collapse(raw)
    if not text:
        return anchor
    prefix = raw[: link.offset]
    pos = len(_collapse(prefix)) + (1 if prefix.strip() and prefix[-1].isspace() else 0)
    if len(text) <= CONTEXT_LIMIT:
        return text
    start = max(0, pos - CONTEXT_LEAD)
    return text[start : start + CONTEXT_LIMIT]


def extract_link_context(body, base):
    parser = _Links()
    parser.feed(body or "")
    parser.close()
    chosen = [link for link in parser.found if (link.in_body if parser.has_body else True)]
    results = []
    seen = set()
    for link in chosen:
        absolute = urllib.parse.urljoin(base, link.href)
        if urllib.parse.urlsplit(absolute).scheme not in ("http", "https"):
            continue
        absolute = normalize(absolute)
        if host(absolute) == host(base) or _excluded(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        anchor = _collapse("".join(link.parts))[:ANCHOR_LIMIT]
        results.append({"url": absolute, "anchor": anchor, "context": _context(link, anchor)})
    return results


def extract_links(body, base):
    return [r["url"] for r in extract_link_context(body, base)]


def kb_resources(root):
    found = set()
    refs = os.path.join(root, "references")
    if not os.path.isdir(refs):
        return None
    for dirpath, _, names in os.walk(refs):
        for name in names:
            if not name.endswith(".md"):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = re.match(r"^resource:\s*['\"]?(\S+?)['\"]?\s*$", line)
                    if match:
                        found.add(normalize(match.group(1)))
                        break
    return found
