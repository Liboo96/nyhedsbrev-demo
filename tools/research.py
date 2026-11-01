from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus, urlparse

from tools.common import NewsletterError, http_request


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    published_at: str


@dataclass(frozen=True)
class Point:
    heading: str
    body: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class NewsletterResearch:
    subject: str
    preheader: str
    intro: str
    points: tuple[Point, ...]
    conclusion: str
    infographic_brief: str
    infographic_alt: str
    sources: tuple[Source, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NewsletterError(f"AI-output mangler feltet {field}")
    return value.strip()


def parse_research(data: dict[str, Any], allowed_source_urls: set[str] | None = None) -> NewsletterResearch:
    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list):
        raise NewsletterError("AI-output mangler en kildeliste")
    sources: list[Source] = []
    seen: set[str] = set()
    for item in raw_sources:
        if not isinstance(item, dict):
            raise NewsletterError("En kilde har et ugyldigt format")
        url = _text(item.get("url"), "sources.url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise NewsletterError(f"Ugyldig kilde-URL: {url}")
        normalized = url.rstrip("/")
        if normalized in seen:
            raise NewsletterError(f"Dubleret kilde-URL: {url}")
        if allowed_source_urls is not None and normalized not in {item.rstrip("/") for item in allowed_source_urls}:
            raise NewsletterError(f"Kilden findes ikke i det hentede nyhedsfeed: {url}")
        seen.add(normalized)
        sources.append(Source(_text(item.get("title"), "sources.title"), url, str(item.get("published_at") or "ukendt")))
    if len(sources) < 3:
        raise NewsletterError("Researchpakken skal indeholde mindst tre unikke kilder")

    raw_points = data.get("points")
    if not isinstance(raw_points, list) or len(raw_points) != 3:
        raise NewsletterError("Researchpakken skal indeholde præcis tre hovedpointer")
    source_urls = {source.url for source in sources}
    points: list[Point] = []
    for item in raw_points:
        if not isinstance(item, dict):
            raise NewsletterError("En hovedpointe har et ugyldigt format")
        refs = item.get("source_urls")
        if not isinstance(refs, list) or not refs or not all(isinstance(url, str) and url in source_urls for url in refs):
            raise NewsletterError("Hver hovedpointe skal referere til mindst én kendt kilde")
        points.append(Point(_text(item.get("heading"), "points.heading"), _text(item.get("body"), "points.body"), tuple(refs)))

    return NewsletterResearch(
        subject=_text(data.get("subject"), "subject"),
        preheader=_text(data.get("preheader"), "preheader"),
        intro=_text(data.get("intro"), "intro"),
        points=tuple(points),
        conclusion=_text(data.get("conclusion"), "conclusion"),
        infographic_brief=_text(data.get("infographic_brief"), "infographic_brief"),
        infographic_alt=_text(data.get("infographic_alt"), "infographic_alt"),
        sources=tuple(sources),
    )


def _gemini_text(payload: dict[str, Any]) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise NewsletterError("Gemini returnerede ikke et brugbart tekstsvar") from exc


def is_danish_publisher_url(value: str) -> bool:
    """Accept sources published on a Danish .dk domain, including subdomains."""
    try:
        host = (urlparse(value).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return host.endswith(".dk") and host != "dk"


def is_recent_publication(value: str, *, now: datetime | None = None, max_age_days: int = 365) -> bool:
    """Reject missing, future or stale feed dates for a current newsletter."""
    try:
        published = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return reference - timedelta(days=max_age_days) <= published <= reference + timedelta(days=1)


_TOPIC_STOPWORDS = {
    "danmark", "dansk", "danske", "den", "det", "der", "for", "fra", "hos", "med", "og", "som",
    "til", "virksomhed", "virksomheder", "professionelle", "samfund", "nyheder", "status", "udvikling",
}

_NORWEGIAN_MARKERS = {
    "bedrift", "bedrifter", "bruker", "brukere", "disse", "lærere", "mellom", "mellomstore",
    "nyheter", "oppgaver", "prosess", "prosessautomatisering", "skoleoppgaver", "søker", "utvider",
    "virksomhet", "virksomheter",
}


def contains_norwegian_markers(title: str, description: str = "") -> bool:
    words = set(re.findall(r"[a-zæøå]+", f"{title} {description}".casefold()))
    return bool(words & _NORWEGIAN_MARKERS)


def is_relevant_to_topic(topic: str, title: str, description: str = "") -> bool:
    """Require meaningful topic terms in the title/snippet before Gemini sees a source."""
    normalize = lambda value: re.findall(r"[a-zæøå0-9]+", value.casefold())
    topic_terms = [term for term in normalize(topic) if len(term) >= 3 and term not in _TOPIC_STOPWORDS]
    if not topic_terms:
        return False
    haystack = set(normalize(f"{title} {description}"))
    matches = sum(term in haystack for term in set(topic_terms))
    if {"kunstig", "intelligens"}.issubset(set(topic_terms)) and "ai" in haystack:
        matches = max(matches, 2)
    required = 1 if len(set(topic_terms)) == 1 else 2
    return matches >= required


def fetch_news_sources(
    topic: str,
    limit: int = 10,
    *,
    now: datetime | None = None,
    max_age_days: int = 365,
) -> tuple[list[Source], str]:
    sources: list[Source] = []
    notes: list[str] = []
    seen: set[str] = set()
    words = topic.split()
    # Feed locale controls the interface, not the publisher country.
    # The query and publisher URL check below keep actual sources Danish.
    queries = [f"{topic} site:.dk"]
    if len(words) > 2:
        queries.append(" ".join(words[:2]) + " Danmark site:.dk")
    for query in dict.fromkeys(queries):
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=da&gl=DK&ceid=DK:da"
        response = http_request(url, headers={"User-Agent": "NewsletterAutomation/1.0"}, timeout=30)
        try:
            root = ET.fromstring(response.body)
        except ET.ParseError as exc:
            raise NewsletterError("Det offentlige nyhedsfeed returnerede ugyldig XML") from exc
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            published = (item.findtext("pubDate") or "ukendt").strip()
            publisher = item.find("source")
            publisher_url = (publisher.get("url") or "").strip() if publisher is not None else ""
            description = html.unescape(item.findtext("description") or "")
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()
            normalized = link.rstrip("/")
            if not title or not link.startswith(("http://", "https://")) or normalized in seen:
                continue
            if not is_danish_publisher_url(publisher_url):
                continue
            if not is_recent_publication(published, now=now, max_age_days=max_age_days):
                continue
            if not is_relevant_to_topic(topic, title, description):
                continue
            if contains_norwegian_markers(title, description):
                continue
            seen.add(normalized)
            sources.append(Source(title, link, published))
            notes.append(
                f"Titel: {title}\nUdgiverdomæne: {publisher_url}\nDato: {published}"
                f"\nUddrag: {description or 'Intet uddrag'}\nURL: {link}"
            )
            if len(sources) >= limit:
                break
        if len(sources) >= limit:
            break
    if len(sources) < 3:
        raise NewsletterError(
            "Det offentlige nyhedsfeed fandt færre end tre aktuelle kilder fra danske .dk-udgivere"
        )
    return sources, "\n\n".join(notes)


def _gemini_call(api_key: str, model: str, body: dict[str, Any], timeout: float = 180) -> dict[str, Any]:
    response = http_request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        method="POST",
        headers={"x-goog-api-key": api_key},
        json_body=body,
        timeout=timeout,
    )
    payload = response.json()
    if not payload.get("candidates"):
        detail = payload.get("promptFeedback", {}).get("blockReason") or "intet svar"
        raise NewsletterError(f"Gemini kunne ikke generere indhold: {detail}")
    return payload


def research_newsletter(*, api_key: str, model: str, topic: str, angle: str, audience: str, tone: str) -> NewsletterResearch:
    schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string"}, "preheader": {"type": "string"}, "intro": {"type": "string"},
            "points": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"heading": {"type": "string"}, "body": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["heading", "body", "source_ids"]}},
            "conclusion": {"type": "string"}, "infographic_brief": {"type": "string"}, "infographic_alt": {"type": "string"},
        },
        "required": ["subject", "preheader", "intro", "points", "conclusion", "infographic_brief", "infographic_alt"],
    }
    feed_sources, feed_notes = fetch_news_sources(topic)
    source_by_id = {f"S{index}": source for index, source in enumerate(feed_sources, 1)}
    source_catalog = "\n".join(f"- {identifier}: {source.title}" for identifier, source in source_by_id.items())
    writing_prompt = f"""Skriv et kort dansk nyhedsbrev udelukkende ud fra nyhedsfeedet og kildekataloget nedenfor.
Emne: {topic}\nVinkel: {angle or 'vælg den mest relevante'}\nMålgruppe: {audience}\nTone: {tone}
Brug præcis tre hovedpointer. Hver source_ids-værdi skal indeholde mindst ét kilde-ID kopieret nøjagtigt fra kataloget.
Brug samlet mindst tre forskellige kilde-ID'er. Skriv aldrig URL'er i JSON-outputtet.
Hvis uddragene ikke dokumenterer en konkret detalje, skal den udelades eller formuleres som en usikker vurdering.
Alle kilder er forhåndsfiltreret til aktuelle udgivelser fra danske .dk-domæner. Skriv på naturligt dansk.
Infografikbriefen skal være landskabsformat og bruge minimal tekst.

NYHEDSFEED:\n{feed_notes}\n\nKILDEKATALOG:\n{source_catalog}"""
    payload = _gemini_call(api_key, model, {
        "contents": [{"role": "user", "parts": [{"text": writing_prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema},
    })
    try:
        content = _gemini_text(payload)
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise NewsletterError("Gemini returnerede ikke gyldigt struktureret output") from exc
    raw_points = data.get("points")
    if not isinstance(raw_points, list):
        raise NewsletterError("Gemini-output mangler hovedpointer")
    converted_points = []
    used_ids: set[str] = set()
    for point in raw_points:
        if not isinstance(point, dict) or not isinstance(point.get("source_ids"), list):
            raise NewsletterError("Hver hovedpointe skal have kilde-ID'er")
        identifiers = point.pop("source_ids")
        if not identifiers or any(identifier not in source_by_id for identifier in identifiers):
            raise NewsletterError("Gemini brugte et ukendt kilde-ID")
        used_ids.update(identifiers)
        point["source_urls"] = [source_by_id[identifier].url for identifier in identifiers]
        converted_points.append(point)
    if len(used_ids) < 3:
        raise NewsletterError("Nyhedsbrevet skal bruge mindst tre forskellige kilder")
    data["points"] = converted_points
    data["sources"] = [
        {"title": source.title, "url": source.url, "published_at": source.published_at}
        for source in feed_sources
    ]
    return parse_research(data, {source.url for source in feed_sources})
