"""Safely fetch a web page and extract a readable preview (title, description, key text). No LLM.

WhatsApp users are untrusted, so this is an SSRF-hardened fetcher:
http(s) on default ports only, every hop's DNS result must be a public IP (we then connect to that exact
IP, so DNS rebinding can't swap it), redirects are followed manually and re-checked, size and time are capped.
"""
import asyncio
import ipaddress
import json
import re
import socket
import ssl
import time
from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 600_000
MAX_REDIRECTS = 4
UA = "Mozilla/5.0 (compatible; wa-bot/1.0; link preview)"
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
BARE_RE = re.compile(r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|ai|app|co|pk|edu|gov|info|me|tv|news|blog|xyz|tech|uk|us|in)(?:/\S*)?$", re.I)


async def _get_json(url: str):
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": UA}) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


class LinkError(Exception):
    """Message safe to show the user."""


def find_url(text: str) -> str | None:
    if m := URL_RE.search(text):
        url = m.group(0).rstrip(".,;:!?]}>'\"")
        while url.endswith(")") and url.count(")") > url.count("("):      # a bracket that closes the sentence, not the URL
            url = url[:-1].rstrip(".,;:!?]}>'\"")
        return url
    token = text.strip()
    if " " not in token and BARE_RE.match(token):
        return "https://" + token
    return None


async def _resolve(host: str, port: int) -> str:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise LinkError("🌐 I couldn't find that website (DNS lookup failed).")
    ips = {i[4][0] for i in infos}
    if not ips or not all(ipaddress.ip_address(ip).is_global for ip in ips):
        raise LinkError("🔒 I only open public websites.")
    return sorted(ips)[0]


@dataclass
class Page:
    url: str
    status: int
    content_type: str
    body: bytes
    length: int | None
    headers: dict = field(default_factory=dict)
    elapsed: float = 0.0
    redirects: list = field(default_factory=list)   # URLs we were redirected through


async def fetch(url: str, max_bytes: int = MAX_BYTES, accept: str = "") -> Page:
    started, chain = time.monotonic(), []
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=6), follow_redirects=False, headers={"User-Agent": UA, "Accept-Language": "en"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise LinkError("🔗 That doesn't look like a web link.")
            default = 443 if parts.scheme == "https" else 80
            if parts.port not in (None, default) or parts.username or parts.password:
                raise LinkError("🔒 Only standard web addresses are supported.")
            ip = await _resolve(parts.hostname, default)
            host_ip = f"[{ip}]" if ":" in ip else ip
            target = parts._replace(netloc=host_ip).geturl()
            try:
                async with client.stream(
                    "GET", target,
                    headers={"Host": parts.hostname, **({"Accept": accept} if accept else {})},
                    extensions={"sni_hostname": parts.hostname},
                ) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and (loc := r.headers.get("location")):
                        chain.append(url)
                        url = urljoin(url, loc)
                        continue
                    body = b""
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) >= max_bytes:
                            break
                    length = int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None
                    return Page(
                        url, r.status_code, r.headers.get("content-type", "").split(";")[0].strip().lower(),
                        body[:max_bytes], length, dict(r.headers), time.monotonic() - started, chain,
                    )
            except httpx.TimeoutException:
                raise LinkError("⏱️ That website took too long to respond.")
            except httpx.HTTPError:
                raise LinkError("🌐 I couldn't connect to that website.")
        raise LinkError("🔁 Too many redirects.")


# ---- HTML extraction -------------------------------------------------------------------------
SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "template", "button"}




@dataclass
class Extracted:
    title: str = ""
    meta: dict = field(default_factory=dict)
    h1: str = ""
    paras: list = field(default_factory=list)         # readable paragraphs (>= 40 chars), in page order
    links: dict = field(default_factory=dict)         # rel -> href (canonical, icon, feed)
    lang: str = ""
    words: int = 0                                    # words in <p> text, for reading time
    ld: dict = field(default_factory=dict)            # useful bits of JSON-LD (author, dates, headline)
    headings: list = field(default_factory=list)      # (level, text)
    images: int = 0
    forms: int = 0
    scripts: list = field(default_factory=list)       # <script src>
    anchors: list = field(default_factory=list)       # <a href>


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out = Extracted()
        self._skip = 0
        self._tag = ""
        self._buf: list[str] = []
        self._ld: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        o = self.out
        if tag == "html" and a.get("lang"):
            o.lang = a["lang"]
        elif tag == "link":
            rel, href = (a.get("rel") or "").lower(), a.get("href")
            if href:
                if "canonical" in rel:
                    o.links.setdefault("canonical", href)
                elif "icon" in rel:
                    o.links.setdefault("icon", href)
                elif "alternate" in rel and ("rss" in (a.get("type") or "") or "atom" in (a.get("type") or "")):
                    o.links.setdefault("feed", href)
        elif tag == "a" and a.get("href") and len(o.anchors) < 800:
            o.anchors.append(a["href"].strip())
        elif tag == "img" and (a.get("src") or a.get("data-src")):
            o.images += 1
        elif tag == "form":
            o.forms += 1
        elif tag == "script" and a.get("src") and len(o.scripts) < 120:
            o.scripts.append(a["src"])
        if tag == "script" and "ld+json" in (a.get("type") or "").lower():
            self._ld = []
            self._skip += 1
        elif tag in SKIP:
            self._skip += 1
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                o.meta.setdefault(key, a["content"].strip())
        elif tag in ("title", "h1", "h2", "h3", "p"):
            self._tag, self._buf = tag, []

    def handle_endtag(self, tag):
        o = self.out
        if tag == "script" and self._ld is not None:
            self._skip = max(0, self._skip - 1)
            _read_jsonld("".join(self._ld), o.ld)
            self._ld = None
        elif tag in SKIP and self._skip:
            self._skip -= 1
        elif tag == self._tag:
            text = " ".join("".join(self._buf).split())
            if tag == "title" and not o.title:
                o.title = text
            elif tag in ("h1", "h2", "h3") and 2 <= len(text) <= 140:
                if tag == "h1" and not o.h1:
                    o.h1 = text
                if len(o.headings) < 30 and text not in [h for _, h in o.headings]:
                    o.headings.append((int(tag[1]), text))
            elif tag == "p":
                o.words += len(text.split())
                if len(text) >= 40 and len(o.paras) < 30:
                    o.paras.append(text)
            self._tag = ""

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        elif self._tag and (not self._skip or self._tag == "title"):
            self._buf.append(data)


def _read_jsonld(raw: str, into: dict) -> None:
    """Pull author / dates / headline / publisher / type out of schema.org JSON-LD (first useful value wins)."""
    try:
        data = json.loads(raw)
    except ValueError:
        return
    stack = data if isinstance(data, list) else [data]
    while stack:
        d = stack.pop(0)
        if not isinstance(d, dict):
            continue
        stack.extend(d["@graph"] if isinstance(d.get("@graph"), list) else [])
        for key in ("author", "publisher"):
            v = d.get(key)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, dict):
                v = v.get("name")
            if isinstance(v, str) and v:
                into.setdefault(key, v)
        for src, dst in (("datePublished", "published"), ("dateModified", "modified"), ("headline", "headline")):
            if isinstance(d.get(src), str):
                into.setdefault(dst, d[src])
        t = d.get("@type")
        if isinstance(t, list):
            t = t[0] if t else None
        if isinstance(t, str):
            into.setdefault("types", [])
            if t not in into["types"] and len(into["types"]) < 4:
                into["types"].append(t)


def _decode(page: "Page") -> str:
    head = page.body[:3000].decode("ascii", "ignore")
    m = re.search(r"charset=[\"']?([\w-]+)", head, re.I)
    for enc in filter(None, [m.group(1) if m else None, "utf-8"]):
        try:
            return page.body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return page.body.decode("utf-8", "replace")


# ---- small helpers -------------------------------------------------------------------------------------
def _cut(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def _date(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return raw.strip()[:10]


def _abs(page_url: str, href: str | None) -> str:
    return urljoin(page_url, href) if href else ""


def _size(n: int) -> str:
    return f"{n / 1024:,.0f} KB" if n >= 1024 else f"{n} B"


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def technical_line(page: "Page") -> str:
    bits = [f"HTTP {page.status}", page.content_type or "unknown type"]
    if size := page.length or len(page.body):
        bits.append(_size(size) + ("+" if len(page.body) >= MAX_BYTES and not page.length else ""))
    bits.append(f"{page.elapsed:.1f}s")
    if page.headers.get("server"):
        bits.append(page.headers["server"][:30])
    return "⚙️ " + " · ".join(bits)


# ---- technology / security detection ----------------------------------------------------------------------
_TECH = [  # (category, name, substring that must appear in the lower-cased HTML)
    ("platform", "WordPress", "wp-content"), ("platform", "WordPress", "wp-includes"),
    ("platform", "Shopify", "cdn.shopify.com"), ("platform", "Wix", "static.wixstatic.com"),
    ("platform", "Squarespace", "squarespace.com"), ("platform", "Webflow", "data-wf-page"),
    ("platform", "Drupal", "drupal-settings-json"), ("platform", "Joomla", "/media/jui/"),
    ("platform", "Ghost", 'content="ghost'), ("platform", "Medium", "cdn-client.medium.com"),
    ("framework", "Next.js", "/_next/"), ("framework", "Next.js", "__next_data__"), ("framework", "Nuxt", "/_nuxt/"),
    ("framework", "Gatsby", "___gatsby"), ("framework", "Astro", "astro-island"), ("framework", "Angular", "ng-version"),
    ("framework", "React", "data-reactroot"), ("framework", "React", "react-dom"), ("framework", "Vue", "__vue"),
    ("framework", "Vue", "vue.min.js"), ("framework", "Svelte", "svelte-"), ("framework", "Docusaurus", "docusaurus"),
    ("framework", "jQuery", "jquery"), ("framework", "Bootstrap", "bootstrap"), ("framework", "Tailwind CSS", "tailwind"),
    ("framework", "Font Awesome", "font-awesome"), ("framework", "Font Awesome", "fontawesome"),
    ("analytics", "Google Tag Manager", "googletagmanager.com"), ("analytics", "Google Analytics", "google-analytics.com"),
    ("analytics", "Google Analytics", "gtag/js"), ("analytics", "Meta Pixel", "connect.facebook.net"),
    ("analytics", "Hotjar", "hotjar"), ("analytics", "Plausible", "plausible.io"), ("analytics", "Microsoft Clarity", "clarity.ms"),
    ("analytics", "Cloudflare Analytics", "cloudflareinsights.com"), ("analytics", "Segment", "cdn.segment.com"),
    ("analytics", "Stripe", "js.stripe.com"), ("analytics", "reCAPTCHA", "recaptcha"), ("analytics", "hCaptcha", "hcaptcha.com"),
]
_HOST_HEADERS = [  # (header, substring-or-None, name)
    ("cf-ray", None, "Cloudflare"), ("x-vercel-id", None, "Vercel"), ("x-nf-request-id", None, "Netlify"),
    ("x-github-request-id", None, "GitHub Pages"), ("x-amz-cf-id", None, "Amazon CloudFront"),
    ("x-azure-ref", None, "Azure Front Door"), ("fly-request-id", None, "Fly.io"), ("x-render-origin-server", None, "Render"),
    ("x-served-by", "cache-", "Fastly"), ("via", "varnish", "Varnish"), ("server", "cloudflare", "Cloudflare"),
    ("server", "akamai", "Akamai"), ("server", "github.com", "GitHub Pages"),
]
SECURITY_HEADERS = [  # (header, short label)
    ("strict-transport-security", "HSTS"), ("content-security-policy", "CSP"), ("x-frame-options", "X-Frame-Options"),
    ("x-content-type-options", "X-Content-Type-Options"), ("referrer-policy", "Referrer-Policy"),
    ("permissions-policy", "Permissions-Policy"),
]


def detect_tech(html: str, ex: Extracted, headers: dict) -> dict[str, list[str]]:
    h = html.lower()
    h_src = " ".join(ex.scripts).lower()
    found: dict[str, list[str]] = {"platform": [], "framework": [], "analytics": [], "hosting": [], "server": []}

    def add(cat, name):
        if name not in found[cat]:
            found[cat].append(name)

    for cat, name, needle in _TECH:
        if needle in h or needle in h_src:
            add(cat, name)
    if gen := ex.meta.get("generator"):
        add("platform", _cut(gen, 40))
    hl = {k.lower(): v for k, v in headers.items()}
    for header, needle, name in _HOST_HEADERS:
        if header in hl and (needle is None or needle in hl[header].lower()):
            add("hosting", name)
    if hl.get("server") and hl["server"].lower() not in ("cloudflare",):
        add("server", _cut(hl["server"], 30))
    if hl.get("x-powered-by"):
        add("server", _cut(hl["x-powered-by"], 30))
    return found


def security_snapshot(page: "Page") -> tuple[list[str], list[str]]:
    hl = {k.lower() for k in page.headers}
    return [lab for hd, lab in SECURITY_HEADERS if hd in hl], [lab for hd, lab in SECURITY_HEADERS if hd not in hl]


_SOCIAL = [  # (domain suffix, emoji, label)
    ("twitter.com", "🐦", "X/Twitter"), ("x.com", "🐦", "X/Twitter"), ("facebook.com", "📘", "Facebook"),
    ("instagram.com", "📸", "Instagram"), ("linkedin.com", "💼", "LinkedIn"), ("youtube.com", "▶️", "YouTube"),
    ("github.com", "🐙", "GitHub"), ("tiktok.com", "🎵", "TikTok"), ("t.me", "✈️", "Telegram"),
    ("wa.me", "💬", "WhatsApp"), ("discord.gg", "🎮", "Discord"), ("reddit.com", "👽", "Reddit"),
    ("pinterest.com", "📌", "Pinterest"), ("medium.com", "📝", "Medium"),
]
_SOCIAL_SKIP = ("/share", "/intent/", "/sharer", "/hashtag", "/login", "/signup", "/watch", "/tr?")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css", ".ico")


def classify_links(page_url: str, ex: Extracted, html: str) -> dict:
    base = _host(page_url)
    internal, external, social, emails, phones = [], Counter(), {}, [], []
    for href in ex.anchors:
        if not href or href.startswith(("#", "javascript:")):
            continue
        if href.lower().startswith("mailto:"):
            e = href[7:].split("?")[0].strip().lower()
            if e and e not in emails:
                emails.append(e)
            continue
        if href.lower().startswith("tel:"):
            t = href[4:].strip()
            if t and t not in phones:
                phones.append(t)
            continue
        full = urljoin(page_url, href)
        parts = urlsplit(full)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        host = parts.hostname.lower().removeprefix("www.")
        if host == base or host.endswith("." + base):
            internal.append(parts.path or "/")
            continue
        external[host] += 1
        segs = [x for x in parts.path.strip("/").split("/") if x]
        for dom, emoji, label in _SOCIAL:
            if (host == dom or host.endswith("." + dom)) and segs and not any(x in full for x in _SOCIAL_SKIP):
                # github/medium/reddit links are usually *content* ("see this repo"); only a bare profile/org counts
                if dom in ("github.com", "medium.com") and len(segs) != 1:
                    continue
                if dom == "reddit.com" and not (segs[0] in ("r", "user") and len(segs) == 2):
                    continue
                social.setdefault(label, (emoji, f"{host}{parts.path.rstrip('/')}"))
    for e in _EMAIL.findall(html):
        e = e.lower()
        if not e.endswith(_IMG_EXT) and e not in emails and len(emails) < 12:
            emails.append(e)
    return {"internal": internal, "external": external, "social": social, "emails": emails, "phones": phones}


# ---- report (parsed page) + short-lived cache so follow-ups like "tech" don't refetch ---------------------
@dataclass
class Report:
    page: "Page"
    ex: Extracted
    html: str

    @property
    def is_html(self) -> bool:
        return self.page.content_type in ("text/html", "application/xhtml+xml", "")


def build_report(page: "Page") -> Report:
    report = Report(page, Extracted(), "")
    if report.is_html:
        report.html = _decode(page)
        p = _Parser()
        try:
            p.feed(report.html)
        except Exception:        # malformed markup: keep whatever was parsed so far
            pass
        report.ex = p.out
    return report


_cache: dict[str, tuple[float, Report]] = {}
CACHE_TTL, CACHE_MAX = 600, 24


async def get_report(url: str, *, fresh: bool = False) -> Report:
    now = time.monotonic()
    if not fresh and (hit := _cache.get(url)) and now - hit[0] < CACHE_TTL:
        return hit[1]
    page = await fetch(url)
    if page.status >= 400:
        raise LinkError(f"🚫 That page returned an error (HTTP {page.status}).")
    report = build_report(page)
    for k in [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL]:
        _cache.pop(k, None)
    if len(_cache) >= CACHE_MAX:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
    _cache[url] = (now, report)
    return report


# ---- formatting: default summary -----------------------------------------------------------------------------
LINK_SECTIONS = "*links* · *contacts* · *tech* · *security* · *text*"


def summary(r: Report) -> tuple[str, str]:
    """The default `!link` answer. Returns (text, absolute image URL or '')."""
    page, e = r.page, r.ex
    host = urlsplit(page.url).hostname or ""
    if not r.is_html:
        lines = [f"📎 *{host}*", f"This link is a file ({page.content_type or 'unknown type'}), not a web page.", ""]
        if page.headers.get("last-modified"):
            lines.append(f"📅 Modified: {page.headers['last-modified']}")
        return "\n".join(lines + [technical_line(page), f"🔗 {page.url}"]), ""

    m, ld = e.meta, e.ld
    title = m.get("og:title") or e.title or ld.get("headline") or e.h1 or host
    site = m.get("og:site_name") or host
    long_paras = [p for p in e.paras if len(p) >= 60]
    desc = m.get("og:description") or m.get("description") or m.get("twitter:description") or " ".join(long_paras[:2])

    lines = [f"🌐 *{_cut(title, 120)}*", f"_{site}_", ""]
    lines.append(_cut(desc, 500) if desc else "(No readable text found — the page may load its content with JavaScript.)")

    # excerpt: the first real paragraph, if it adds something the description doesn't already say
    d_low = (desc or "").lower()
    for para in long_paras:
        prose = len(para.split()) >= 12 and para.rstrip().endswith((".", "!", "?", ":", "”", '"', ")"))
        if prose and para.lower()[:60] not in d_low and para.lower()[:40] not in d_low:
            lines += ["", "📝 *Excerpt*", _cut(para, 380)]
            break

    # outline: h1/h2/h3 in order, h1 first
    heads = [(lvl, t) for lvl, t in e.headings if t.lower() != title.lower()]
    if len(heads) >= 2:
        lines += ["", "📑 *Outline*"] + [f"{'•' if lvl == 1 else '  –'} {_cut(t, 70)}" for lvl, t in heads[:7]]
        if len(heads) > 7:
            lines.append(f"  … and {len(heads) - 7} more sections")

    # ---- metadata ----
    meta = []
    author = m.get("author") or m.get("article:author") or ld.get("author") or m.get("twitter:creator")
    if author and not author.startswith("http"):
        meta.append(f"👤 Author: {_cut(author, 60)}")
    if ld.get("publisher") and ld["publisher"] != site:
        meta.append(f"🏢 Publisher: {_cut(ld['publisher'], 60)}")
    published = m.get("article:published_time") or m.get("og:published_time") or m.get("date") or ld.get("published")
    modified = m.get("article:modified_time") or m.get("og:updated_time") or ld.get("modified")
    if published:
        meta.append(f"📅 Published: {_date(published)}" + (f" · updated {_date(modified)}" if modified and _date(modified) != _date(published) else ""))
    elif modified:
        meta.append(f"📅 Updated: {_date(modified)}")
    elif page.headers.get("last-modified"):
        meta.append(f"📅 Modified: {page.headers['last-modified'][:25]}")
    kind = m.get("og:type")
    types = ld.get("types")
    if kind or types:
        meta.append("🏷️ Type: " + " · ".join(x for x in [kind, ", ".join(types) if types else ""] if x)
                    + (f" · section: {m['article:section']}" if m.get("article:section") else ""))
    if m.get("keywords"):
        kws = [k.strip() for k in m["keywords"].split(",") if k.strip()][:6]
        if kws:
            meta.append(f"🔖 Keywords: {', '.join(kws)}")
    lang = m.get("og:locale") or e.lang
    if lang:
        meta.append(f"🌍 Language: {lang}")
    if e.words >= 200:
        meta.append(f"⏱️ ~{max(1, round(e.words / 200))} min read ({e.words:,} words)")
    image = _abs(page.url, m.get("og:image") or m.get("twitter:image"))
    if image:
        meta.append(f"🖼️ Image: {_cut(image, 110)}")
    canonical = _abs(page.url, e.links.get("canonical") or m.get("og:url"))
    if canonical and canonical.rstrip("/") != page.url.rstrip("/"):
        meta.append(f"📌 Canonical: {_cut(canonical, 110)}")
    if e.links.get("feed"):
        meta.append(f"📡 Feed: {_cut(_abs(page.url, e.links['feed']), 110)}")
    if page.redirects:
        meta.append(f"↪️ Redirected ({len(page.redirects)}x) from {_cut(page.redirects[0], 80)}")
    if meta:
        lines += ["", "ℹ️ *Metadata*", *meta]

    # ---- stats, tech, security snapshot ----
    c = classify_links(page.url, e, r.html)
    ext = sum(c["external"].values())
    stats = [f"{e.words:,} words" if e.words else "", f"{e.images} images" if e.images else "",
             f"{len(c['internal']) + ext} links ({ext} external)" if (c["internal"] or ext) else "",
             f"{len(e.headings)} headings" if e.headings else "", f"{e.forms} forms" if e.forms else "",
             f"{len(e.scripts)} scripts" if e.scripts else ""]
    stats = [x for x in stats if x]
    if stats:
        lines += ["", f"📊 *Page stats* — {' · '.join(stats)}"]

    tech = detect_tech(r.html, e, page.headers)
    flat = [t for cat in ("platform", "framework", "hosting", "analytics") for t in tech[cat]]
    if flat:
        lines.append(f"🧩 *Tech* — {', '.join(flat[:7])}{' …' if len(flat) > 7 else ''}")
    present, missing = security_snapshot(page)
    https = page.url.startswith("https://")
    lines.append(f"🔒 *Security* — {'HTTPS ✅' if https else 'HTTP only ⚠️'} · HSTS {'✅' if 'HSTS' in present else '❌'} · "
                 f"CSP {'✅' if 'CSP' in present else '❌'} · {len(present)}/{len(SECURITY_HEADERS)} security headers")
    if c["emails"] or c["phones"] or c["social"]:
        bits = ([f"✉️ {len(c['emails'])} email" + ("s" if len(c["emails"]) != 1 else "")] if c["emails"] else []) + \
               ([f"📞 {len(c['phones'])} phone" + ("s" if len(c["phones"]) != 1 else "")] if c["phones"] else []) + \
               ([f"{len(c['social'])} social profile" + ("s" if len(c["social"]) != 1 else "")] if c["social"] else [])
        lines.append(f"📇 *Contact info found* — {' · '.join(bits)}")

    lines += [technical_line(page), "", f"🔗 {page.url}"]
    return "\n".join(lines), image


# ---- formatting: deeper sections (reply "links", "contacts", "tech", "security", "text") -------------------
def section_links(r: Report) -> str:
    c = classify_links(r.page.url, r.ex, r.html)
    host = _host(r.page.url)
    ext = c["external"]
    lines = [f"🔗 *Links on {host}*", "", f"📊 {len(c['internal']) + sum(ext.values())} total · {len(c['internal'])} internal · "
             f"{sum(ext.values())} external across {len(ext)} sites"]
    if ext:
        lines += ["", "🌐 *Most-linked external sites*"] + [f"• {d} ({n})" for d, n in ext.most_common(8)]
    paths = list(dict.fromkeys(p for p in c["internal"] if p != "/" and len(p) > 1))[:8]
    if paths:
        lines += ["", "📄 *Pages on this site*"] + [f"• {_cut(p, 60)}" for p in paths]
    if c["social"]:
        lines += ["", "📣 *Social*"] + [f"{emoji} {label}: {_cut(url, 60)}" for label, (emoji, url) in list(c["social"].items())[:6]]
    if r.ex.links.get("feed"):
        lines += ["", f"📡 Feed: {_abs(r.page.url, r.ex.links['feed'])}"]
    if len(lines) <= 3 and not ext and not paths:
        lines.append("No links found — the page may build its content with JavaScript.")
    return "\n".join(lines)


def section_contacts(r: Report) -> str:
    c = classify_links(r.page.url, r.ex, r.html)
    parts = urlsplit(r.page.url)
    lines = [f"📇 *Contact info — {_host(r.page.url)}*", ""]
    if c["emails"]:
        lines += ["✉️ *Emails*"] + [f"• {e}" for e in c["emails"][:6]] + [""]
    if c["phones"]:
        lines += ["📞 *Phones*"] + [f"• {p}" for p in c["phones"][:4]] + [""]
    if c["social"]:
        lines += ["📣 *Social profiles*"] + [f"{emoji} {label}: {_cut(url, 60)}" for label, (emoji, url) in list(c["social"].items())[:8]] + [""]
    if not (c["emails"] or c["phones"] or c["social"]):
        lines += ["No emails, phone numbers or social profiles found on this page.", "",
                  f"💡 Try its contact page: {parts.scheme}://{parts.hostname}/contact"]
    return "\n".join(lines).rstrip()


def section_tech(r: Report) -> str:
    t = detect_tech(r.html, r.ex, r.page.headers)
    names = {"platform": "🏗️ Platform / CMS", "framework": "⚛️ Frameworks & libraries", "hosting": "☁️ Hosting / CDN",
             "analytics": "📈 Analytics & services", "server": "🖥️ Server"}
    lines = [f"🧩 *Tech stack — {_host(r.page.url)}*", ""]
    for cat, label in names.items():
        if t[cat]:
            lines.append(f"{label}: {', '.join(t[cat])}")
    if len(lines) == 2:
        lines.append("I couldn't identify any technology from the page's HTML or headers.")
    lines += ["", f"📜 {len(r.ex.scripts)} external scripts · {r.ex.images} images · {len(r.html) // 1024:,} KB of HTML"]
    return "\n".join(lines)


def section_text(r: Report, limit: int = 1800) -> str:
    e = r.ex
    if not e.paras:
        return "📄 No readable article text found — the page may load its content with JavaScript."
    out, total = [], 0
    for p in e.paras:
        if total + len(p) > limit:
            room = limit - total
            if room > 120:
                out.append(_cut(p, room))
            break
        out.append(p)
        total += len(p)
    title = e.meta.get("og:title") or e.title or _host(r.page.url)
    return f"📄 *{_cut(title, 100)}*\n\n" + "\n\n".join(out) + f"\n\n— ~{e.words:,} words total · 🔗 {r.page.url}"


# ---- security & network (extra lookups, run only when asked) ---------------------------------------------------
_MULTI_TLD = {"co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "co.in", "com.pk", "net.pk", "org.pk", "edu.pk", "gov.pk",
              "co.jp", "com.br", "co.za", "com.sa", "com.eg", "com.tr", "co.nz"}
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def registrable(host: str) -> str:
    labels = host.split(".")
    return ".".join(labels[-3:] if ".".join(labels[-2:]) in _MULTI_TLD and len(labels) >= 3 else labels[-2:])


async def tls_info(host: str) -> dict | None:
    try:
        ip = await _resolve(host, 443)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 443, ssl=ssl.create_default_context(), server_hostname=host), 6)
        try:
            obj = writer.get_extra_info("ssl_object")
            cert, version = obj.getpeercert(), obj.version()
        finally:
            writer.close()
        issuer = dict(x[0] for x in cert.get("issuer", ()))
        exp = ssl.cert_time_to_seconds(cert["notAfter"])
        return {"issuer": issuer.get("organizationName") or issuer.get("commonName") or "unknown", "version": version,
                "expires": datetime.fromtimestamp(exp, timezone.utc), "days": int((exp - time.time()) // 86400),
                "names": len(cert.get("subjectAltName", ()))}
    except Exception:
        return None


async def rdap_info(domain: str) -> dict | None:
    if not _HOSTNAME.match(domain):
        return None
    try:
        d = await asyncio.wait_for(_get_json(f"https://rdap.org/domain/{domain}"), 9)
        ev = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
        registrar = ""
        for ent in d.get("entities", []):
            if "registrar" in ent.get("roles", []):
                for item in (ent.get("vcardArray") or [None, []])[1]:
                    if item and item[0] == "fn":
                        registrar = item[3]
        return {"created": ev.get("registration"), "expires": ev.get("expiration"), "changed": ev.get("last changed"), "registrar": registrar}
    except Exception:
        return None


async def host_info(host: str) -> dict | None:
    try:
        ip = await _resolve(host, 443)
        d = await asyncio.wait_for(_get_json(f"https://ipinfo.io/{ip}/json"), 8)
        return {"ip": ip, "org": d.get("org", ""), "city": d.get("city", ""), "country": d.get("country", "")}
    except Exception:
        return None


async def section_security(r: Report) -> str:
    host = urlsplit(r.page.url).hostname or ""
    https = r.page.url.startswith("https://")
    tls, rdap, where = await asyncio.gather(
        tls_info(host) if https else _none(), rdap_info(registrable(host)), host_info(host))
    present, missing = security_snapshot(r.page)
    lines = [f"🔒 *Security & network — {host}*", ""]
    if not https:
        lines.append("⚠️ This page is served over plain HTTP (not encrypted).")
    elif tls:
        warn = " ⚠️ expiring soon" if tls["days"] < 15 else ""
        lines.append(f"🔐 HTTPS ✅ · {tls['version']} · issued by {tls['issuer']}\n   valid until {tls['expires']:%d %b %Y} ({tls['days']} days left){warn} · {tls['names']} names")
    else:
        lines.append("🔐 HTTPS ✅ (certificate details unavailable)")
    lines.append("🛡️ Headers: " + " · ".join([f"{x} ✅" for x in present] + [f"{x} ❌" for x in missing]))
    if where:
        lines.append(f"🌍 Hosted at {where['ip']} — {where['org'] or 'unknown network'}"
                     + (f" · {', '.join(x for x in (where['city'], where['country']) if x)}" if where["city"] or where["country"] else ""))
    if rdap and rdap.get("created"):
        created = datetime.fromisoformat(rdap["created"].replace("Z", "+00:00"))
        years = (datetime.now(timezone.utc) - created).days / 365.25
        line = f"🗓️ Domain {registrable(host)}: registered {created:%d %b %Y} ({years:.1f} years old)"
        if rdap.get("expires"):
            line += f" · expires {_date(rdap['expires'])}"
        if rdap.get("registrar"):
            line += f"\n   registrar: {_cut(rdap['registrar'], 60)}"
        lines.append(line)
        if years < 1:
            lines.append("⚠️ Very new domain — be careful with unfamiliar sites.")
    else:
        lines.append("🗓️ Domain age: unavailable for this domain")
    if r.page.redirects:
        lines.append(f"↪️ Redirect chain: {' → '.join(_host(u) for u in [*r.page.redirects, r.page.url])}")
    return "\n".join(lines)


async def _none():
    return None


# ---- images ------------------------------------------------------------------------------------
MAX_IMAGE = 4_000_000
_MAGIC = [(b"\xff\xd8\xff", "image/jpeg", "jpg"), (b"\x89PNG\r\n\x1a\n", "image/png", "png"), (b"GIF8", "image/gif", "gif")]


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """Identify by content, not by the server's claim (so SVG/HTML never slip through as 'images')."""
    for magic, mime, ext in _MAGIC:
        if data.startswith(magic):
            return mime, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


async def fetch_image(url: str) -> tuple[bytes, str, str] | None:
    """Download a page image through the same SSRF-hardened fetcher. Returns (bytes, mimetype, ext) or None."""
    try:
        page = await asyncio.wait_for(fetch(url, max_bytes=MAX_IMAGE + 1, accept="image/jpeg,image/png,image/webp,image/gif,*/*;q=0.5"), 15)
    except (LinkError, asyncio.TimeoutError):
        return None
    if page.status != 200 or not page.body or len(page.body) > MAX_IMAGE:
        return None
    kind = sniff_image(page.body)
    return (page.body, *kind) if kind else None
