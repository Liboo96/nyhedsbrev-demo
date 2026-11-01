from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

from tools.common import NewsletterError, validate_email
from tools.create_newsletter import run
from tools.gmail_draft import send_draft
from tools.dry_run_fixture import fixture_research, write_fixture_image
from tools.local_infographic import generate_infographic
from tools.render_email import INFOGRAPHIC_CID, build_message, render_html, render_text
from tools.research import (
    contains_norwegian_markers,
    fetch_news_sources,
    is_danish_publisher_url,
    is_recent_publication,
    is_relevant_to_topic,
    parse_research,
)


def valid_payload() -> dict:
    urls = ["https://example.com/a", "https://example.org/b", "https://example.net/c"]
    return {
        "subject": "Et emne <test>", "preheader": "Kort overblik", "intro": "Introduktion",
        "points": [{"heading": f"Pointe {i + 1}", "body": "Brødtekst", "source_urls": [url]} for i, url in enumerate(urls)],
        "conclusion": "Konklusion", "infographic_brief": "Grafik", "infographic_alt": "Alt-tekst",
        "sources": [{"title": f"Kilde {i + 1}", "url": url, "published_at": "2026-01-01"} for i, url in enumerate(urls)],
    }


class ResearchTests(unittest.TestCase):
    def test_only_danish_publisher_domains_are_accepted(self):
        self.assertTrue(is_danish_publisher_url("https://www.dr.dk"))
        self.assertTrue(is_danish_publisher_url("https://nyheder.tv2.dk/"))
        for url in ["https://www.aftenposten.no", "https://example.com", "", "not-a-url"]:
            self.assertFalse(is_danish_publisher_url(url))

    def test_old_or_future_publications_are_rejected(self):
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.assertTrue(is_recent_publication("Sat, 01 Aug 2026 08:00:00 GMT", now=now))
        self.assertFalse(is_recent_publication("Thu, 24 Sep 2009 07:00:00 GMT", now=now))
        self.assertFalse(is_recent_publication("Mon, 01 Nov 2027 08:00:00 GMT", now=now))
        self.assertFalse(is_recent_publication("ukendt", now=now))

    def test_topic_relevance_accepts_ai_alias_and_rejects_unrelated_news(self):
        topic = "Kunstig intelligens i danske virksomheder"
        self.assertTrue(is_relevant_to_topic(topic, "Nyt AI-værktøj hjælper industrien"))
        self.assertTrue(is_relevant_to_topic(topic, "Kunstig intelligens ændrer arbejdsmarkedet"))
        self.assertFalse(is_relevant_to_topic(topic, "EU indfører gebyr på pakker"))
        self.assertFalse(is_relevant_to_topic(topic, "Sommeren i Københavns Lufthavn var travl"))

    def test_norwegian_language_markers_are_rejected_even_on_dk_domain(self):
        self.assertTrue(contains_norwegian_markers("AI-løsninger for mellomstore bedrifter"))
        self.assertTrue(contains_norwegian_markers("Prosessautomatisering med AI"))
        self.assertFalse(contains_norwegian_markers("AI-løsninger til små og mellemstore virksomheder"))

    def test_feed_filters_norwegian_and_old_sources(self):
        xml = """<rss><channel>
          <item><title>AI i danske virksomheder - DR</title><link>https://news.google.com/a</link><pubDate>Sat, 01 Aug 2026 08:00:00 GMT</pubDate><source url="https://www.dr.dk">DR</source><description>Kunstig intelligens i erhvervslivet</description></item>
          <item><title>AI i norske virksomheder - Aftenposten</title><link>https://news.google.com/b</link><pubDate>Sat, 01 Aug 2026 08:00:00 GMT</pubDate><source url="https://www.aftenposten.no">Aftenposten</source></item>
          <item><title>Gammel dansk AI-nyhed</title><link>https://news.google.com/c</link><pubDate>Thu, 24 Sep 2009 07:00:00 GMT</pubDate><source url="https://politiken.dk">Politiken</source><description>Kunstig intelligens</description></item>
          <item><title>Danske virksomheder investerer i AI</title><link>https://news.google.com/d</link><pubDate>Tue, 01 Sep 2026 08:00:00 GMT</pubDate><source url="https://borsen.dk">Børsen</source></item>
          <item><title>Kunstig intelligens breder sig i erhvervslivet</title><link>https://news.google.com/e</link><pubDate>Thu, 01 Oct 2026 08:00:00 GMT</pubDate><source url="https://www.berlingske.dk">Berlingske</source></item>
          <item><title>AI for mellomstore bedrifter</title><link>https://news.google.com/f</link><pubDate>Thu, 01 Oct 2026 08:00:00 GMT</pubDate><source url="https://radner.dk">Radner</source></item>
        </channel></rss>""".encode("utf-8")
        response = type("Response", (), {"body": xml})()
        with patch("tools.research.http_request", return_value=response):
            sources, notes = fetch_news_sources(
                "kunstig intelligens", now=datetime(2026, 11, 1, tzinfo=timezone.utc)
            )
        self.assertEqual(3, len(sources))
        self.assertNotIn("Aftenposten", notes)
        self.assertNotIn("2009", notes)
        self.assertNotIn("bedrifter", notes)

    def test_valid_schema(self):
        research = parse_research(valid_payload())
        self.assertEqual(3, len(research.points))
        self.assertEqual(3, len(research.sources))

    def test_too_few_sources(self):
        payload = valid_payload()
        payload["sources"] = payload["sources"][:2]
        with self.assertRaises(NewsletterError):
            parse_research(payload)

    def test_duplicate_source_rejected(self):
        payload = valid_payload()
        payload["sources"][2]["url"] = payload["sources"][0]["url"]
        with self.assertRaisesRegex(NewsletterError, "Dubleret"):
            parse_research(payload)

    def test_unknown_point_source_rejected(self):
        payload = valid_payload()
        payload["points"][0]["source_urls"] = ["https://unknown.example/x"]
        with self.assertRaises(NewsletterError):
            parse_research(payload)

    def test_source_must_be_in_news_feed(self):
        payload = valid_payload()
        allowed = {item["url"] for item in payload["sources"][:2]}
        with self.assertRaisesRegex(NewsletterError, "nyhedsfeed"):
            parse_research(payload, allowed)


class RenderingTests(unittest.TestCase):
    def test_html_escapes_content_and_has_cid(self):
        research = parse_research(valid_payload())
        rendered = render_html(research)
        self.assertIn("Et emne &lt;test&gt;", rendered)
        self.assertIn(f"cid:{INFOGRAPHIC_CID}", rendered)
        self.assertNotIn("Et emne <test>", rendered)

    def test_html_snapshot(self):
        rendered = render_html(fixture_research("Test"))
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        self.assertEqual("660ff80eddb77cf15438de36474239177bfbce599575b929d1f25f69166ecd2a", digest)

    def test_mime_contains_fallback_html_and_inline_image(self):
        research = fixture_research("Test")
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "image.png"
            write_fixture_image(image_path)
            message = build_message(recipient="test@example.com", research=research, html_body=render_html(research), text_body=render_text(research), image_path=image_path)
            parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
            types = [part.get_content_type() for part in parsed.walk()]
            self.assertIn("text/plain", types)
            self.assertIn("text/html", types)
            self.assertIn("image/png", types)
            image_part = next(part for part in parsed.walk() if part.get_content_type() == "image/png")
            self.assertEqual(f"<{INFOGRAPHIC_CID}>", image_part["Content-ID"])


class InfographicTests(unittest.TestCase):
    def test_local_infographic_is_real_png(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "infographic.png"
            generate_infographic(fixture_research("Test"), path)
            with Image.open(path) as image:
                self.assertEqual("PNG", image.format)
                self.assertEqual((1200, 675), image.size)


class ValidationTests(unittest.TestCase):
    def test_one_email_only(self):
        self.assertEqual("person@example.com", validate_email("person@example.com"))
        for value in ["a@example.com,b@example.com", "not-an-email", "a@example.com\nBcc:x@example.com"]:
            with self.assertRaises(NewsletterError):
                validate_email(value)

    def test_dry_run_never_calls_external_services(self):
        args = argparse.Namespace(topic="Testemne", angle="", audience="bred", tone="neutral", recipient="test@example.com", dry_run=True)
        with tempfile.TemporaryDirectory() as directory, \
             patch("tools.create_newsletter.ROOT", Path(directory)), \
             patch("tools.create_newsletter.research_newsletter") as research_call, \
             patch("tools.create_newsletter.create_draft") as gmail_call:
            result = run(args)
            research_call.assert_not_called()
            gmail_call.assert_not_called()
            output = Path(result["output_dir"])
            self.assertTrue((output / "newsletter.html").exists())
            manifest = json.loads((output / "run-manifest.json").read_text())
            self.assertEqual("complete", manifest["status"])
            self.assertIsNone(manifest["draft_id"])

    def test_dry_run_rejects_send(self):
        args = argparse.Namespace(topic="Testemne", angle="", audience="bred", tone="neutral", recipient="test@example.com", dry_run=True, send=True)
        with self.assertRaisesRegex(NewsletterError, "--send"):
            run(args)

    def test_send_draft_preserves_stored_mime(self):
        request = unittest.mock.Mock()
        request.execute.return_value = {"id": "sent-message-id"}
        drafts = unittest.mock.Mock()
        drafts.send.return_value = request
        users = unittest.mock.Mock()
        users.drafts.return_value = drafts
        service = unittest.mock.Mock()
        service.users.return_value = users
        with patch("tools.gmail_draft.get_gmail_service", return_value=service):
            message_id = send_draft("draft-id", Path("credentials.json"), Path("token.json"))
        self.assertEqual("sent-message-id", message_id)
        drafts.send.assert_called_once_with(userId="me", body={"id": "draft-id"})


if __name__ == "__main__":
    unittest.main()
