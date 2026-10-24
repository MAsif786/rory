"""GitHub: search repositories and show a repository's details."""
import asyncio
import os
from datetime import datetime

import httpx

from app.core.schemas import Input, UserError
from app.core.tool import Tool

tool = Tool("github", title="GitHub", emoji="🐙", description="Search repos and show repo details")

REPO = r"[\w.-]+/[\w.-]+"
API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if tok := os.getenv("GITHUB_TOKEN", "").strip():
        h["Authorization"] = f"Bearer {tok}"
    return h


def _k(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


async def _get(http, path: str, **params):
    r = await http.get(f"{API}{path}", params=params or None, headers=_headers())
    r.raise_for_status()
    return r.json()


@tool.feature(
    "search", repeat="reuse", description="Search GitHub repositories by name or topic",
    phrases=["github {query}", "search github for {query}", "github repos for {query}", "github repos about {query}",
             "find repos for {query}", "gh {query}"],
    examples=["github fastapi", "search github for telegram bot"],
    inputs={"query": Input(required=True, ask="🐙 What should I search GitHub for?")})
async def search(ctx, query):
    items = (await _get(ctx.services.http, "/search/repositories", q=query, sort="stars", per_page=5)).get("items", [])
    if not items:
        raise UserError(f"🐙 No repositories found for *{query}*.")
    lines = [f"🐙 *Top repos for “{query}”*", ""]
    for i, r in enumerate(items, 1):
        lines.append(f"{i}. *{r['full_name']}* ⭐ {_k(r['stargazers_count'])} · {r.get('language') or '—'}")
        if desc := (r.get("description") or "").strip():
            lines.append(f"   {desc[:90]}")
    lines.append("\nDetails: *repo owner/name*")
    return "\n".join(lines)


@tool.feature(
    "repo", repeat="reuse", description="Details of a GitHub repository (stats, languages, topics, latest release)",
    phrases=["repo {repo}", "the repo {repo}", "github {repo}", "repository {repo}", "gh repo {repo}"],
    keywords=["repo", "repository"],
    examples=["repo tiangolo/fastapi", "github psf/requests"],
    inputs={"repo": Input(required=True, pattern=REPO, ask="🐙 Which repo? (e.g. *tiangolo/fastapi*)")})
async def repo(ctx, repo):
    http = ctx.services.http
    try:
        r = await _get(http, f"/repos/{repo}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise UserError(f"🐙 Repo *{repo}* not found.") from None
        raise
    # extras: a failure here (rate limit, no releases) must never break the main card
    langs, release = await asyncio.gather(_get(http, f"/repos/{r['full_name']}/languages"),
                                          _get(http, f"/repos/{r['full_name']}/releases/latest"), return_exceptions=True)
    d = lambda iso: datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")
    lines = [f"🐙 *{r['full_name']}*" + (" · 🍴 fork" if r.get("fork") else "") + (" · 📦 archived" if r.get("archived") else ""),
             (r.get("description") or "")[:250], ""]
    lines.append(f"⭐ {r['stargazers_count']:,} stars · 🍴 {r['forks_count']:,} forks · 👀 {r.get('subscribers_count', 0):,} watching · 🐞 {r['open_issues_count']:,} open issues")
    if isinstance(langs, dict) and langs:
        total = sum(langs.values())
        top = [(k, v / total) for k, v in sorted(langs.items(), key=lambda kv: -kv[1]) if v / total >= 0.01][:4]
        lines.append("💻 " + " · ".join(f"{k} {share:.0%}" for k, share in top))
    elif r.get("language"):
        lines.append(f"💻 {r['language']}")
    lines.append(f"📜 {(r.get('license') or {}).get('spdx_id') or 'no license'} · 📦 {r.get('size', 0) / 1024:,.1f} MB · 🌿 {r.get('default_branch', 'main')}")
    if r.get("topics"):
        lines.append(f"🏷️ {', '.join(r['topics'][:8])}")
    if isinstance(release, dict) and release.get("tag_name"):
        lines.append(f"🚀 Latest release: {release['tag_name']} ({d(release['published_at'])})")
    lines.append(f"📅 Created {d(r['created_at'])} · last push {d(r['pushed_at'])}")
    if r.get("homepage"):
        lines.append(f"🏠 {r['homepage']}")
    lines.append(f"🔗 {r['html_url']}")
    return "\n".join(lines)
