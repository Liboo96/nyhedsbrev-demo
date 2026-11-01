from __future__ import annotations

import html
from email.message import EmailMessage
from pathlib import Path

from tools.research import NewsletterResearch


INFOGRAPHIC_CID = "newsletter-infographic"


def render_html(research: NewsletterResearch) -> str:
    point_rows = []
    for index, point in enumerate(research.points, 1):
        links = " · ".join(
            f'<a href="{html.escape(url, quote=True)}" style="color:#2458a6">kilde</a>' for url in point.source_urls
        )
        point_rows.append(f"""
          <tr><td style="padding:0 32px 24px">
            <div style="font:700 12px Arial,sans-serif;color:#2458a6;text-transform:uppercase;letter-spacing:1px">Pointe {index}</div>
            <h2 style="margin:7px 0 8px;font:700 22px Georgia,serif;color:#172033">{html.escape(point.heading)}</h2>
            <p style="margin:0;font:16px/1.6 Arial,sans-serif;color:#39445a">{html.escape(point.body)}</p>
            <p style="margin:8px 0 0;font:12px Arial,sans-serif">{links}</p>
          </td></tr>""")
    sources = "".join(
        f'<li style="margin:0 0 8px"><a href="{html.escape(source.url, quote=True)}" style="color:#2458a6">{html.escape(source.title)}</a> <span style="color:#758096">({html.escape(source.published_at)})</span></li>'
        for source in research.sources
    )
    return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#eef1f6">
<div style="display:none;max-height:0;overflow:hidden;color:transparent">{html.escape(research.preheader)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef1f6"><tr><td align="center" style="padding:24px 12px">
  <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;background:#fff;border-radius:12px;overflow:hidden">
    <tr><td style="padding:36px 32px 28px;background:#172033">
      <div style="font:700 12px Arial,sans-serif;color:#9cbcff;text-transform:uppercase;letter-spacing:1.4px">Aktuel briefing</div>
      <h1 style="margin:10px 0 0;font:700 34px/1.15 Georgia,serif;color:#fff">{html.escape(research.subject)}</h1>
    </td></tr>
    <tr><td style="padding:28px 32px 24px"><p style="margin:0;font:17px/1.65 Arial,sans-serif;color:#39445a">{html.escape(research.intro)}</p></td></tr>
    {''.join(point_rows)}
    <tr><td style="padding:4px 24px 28px"><img src="cid:{INFOGRAPHIC_CID}" width="552" alt="{html.escape(research.infographic_alt, quote=True)}" style="display:block;width:100%;max-width:552px;height:auto;border:0;border-radius:8px"></td></tr>
    <tr><td style="padding:26px 32px;background:#f5f7fa"><h2 style="margin:0 0 8px;font:700 21px Georgia,serif;color:#172033">Kort fortalt</h2><p style="margin:0;font:16px/1.6 Arial,sans-serif;color:#39445a">{html.escape(research.conclusion)}</p></td></tr>
    <tr><td style="padding:28px 32px"><h2 style="margin:0 0 12px;font:700 18px Georgia,serif;color:#172033">Kilder</h2><ol style="margin:0;padding-left:20px;font:13px/1.5 Arial,sans-serif;color:#39445a">{sources}</ol></td></tr>
    <tr><td style="padding:18px 32px;border-top:1px solid #e5e8ee;font:12px Arial,sans-serif;color:#758096">Udarbejdet som en kildebaseret briefing.</td></tr>
  </table>
</td></tr></table></body></html>"""


def render_text(research: NewsletterResearch) -> str:
    lines = [research.subject, "", research.intro, ""]
    for index, point in enumerate(research.points, 1):
        lines.extend([f"{index}. {point.heading}", point.body, "Kilder: " + ", ".join(point.source_urls), ""])
    lines.extend(["KORT FORTALT", research.conclusion, "", "KILDER"])
    lines.extend(f"- {source.title}: {source.url} ({source.published_at})" for source in research.sources)
    return "\n".join(lines) + "\n"


def build_message(*, recipient: str, research: NewsletterResearch, html_body: str, text_body: str, image_path: Path) -> EmailMessage:
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = research.subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    image = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    subtype = {".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}.get(suffix, "png")
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    html_part.add_related(image, maintype="image", subtype=subtype, cid=f"<{INFOGRAPHIC_CID}>", filename=image_path.name, disposition="inline")
    return message
