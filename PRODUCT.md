# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

FastAPI with Jinja2 templates, plain CSS and a small vanilla JS file (no build step). Confirmed by the user.

## Users

Public visitors who open a web page instead of WhatsApp. They type short everyday requests (weather, conversions, facts, jokes, games) and expect an answer in a line or two. Mostly on phones.

## Product Purpose

Rory is a rule-based chat companion with pluggable tools, no LLM. The web chat is a second front door to the same bot: same tools, same follow-ups and games, anonymous cookie session per browser.

## Positioning

Fast, deterministic answers from real tools, not a general-purpose AI. The interface should never imply open-ended AI capability; it should show what Rory can do and hand over examples.

## Constraints

- Replies are WhatsApp-style text (*bold*, _italic_, emoji, line breaks); the web renders that markup, backend unchanged.
- Messages max 1000 characters; per-sender rate limit applies.
- No accounts. State lives server-side for about an hour of idle time.
