from __future__ import annotations

import base64
from pathlib import Path

from tools.research import NewsletterResearch, Point, Source


_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+X8WZ5QAAAABJRU5ErkJggg==")


def fixture_research(topic: str) -> NewsletterResearch:
    sources = (
        Source("Eksempelkilde A", "https://example.com/source-a", "2026-01-01"),
        Source("Eksempelkilde B", "https://example.org/source-b", "2026-01-02"),
        Source("Eksempelkilde C", "https://example.net/source-c", "2026-01-03"),
    )
    return NewsletterResearch(
        subject=f"Kort briefing: {topic}",
        preheader="Tre kildebaserede hovedpointer i et hurtigt overblik.",
        intro="Dette er fixtureindhold til en lokal dry-run. Ingen eksterne tjenester er blevet kaldt.",
        points=(
            Point("Det første perspektiv", "En kort eksempeltekst, der demonstrerer nyhedsbrevets opbygning.", (sources[0].url,)),
            Point("Det andet perspektiv", "Endnu en eksempeltekst med en tydelig forbindelse til en kilde.", (sources[1].url,)),
            Point("Det tredje perspektiv", "Den sidste eksempeltekst afrunder den redaktionelle struktur.", (sources[2].url,)),
        ),
        conclusion="Dry-run-resultatet kan bruges til at kontrollere HTML, MIME og lokale artefakter.",
        infographic_brief="En neutral liggende oversigtsgrafik med tre visuelle elementer og ingen tal.",
        infographic_alt="Eksempelgrafik med tre hovedpointer.",
        sources=sources,
    )


def write_fixture_image(path: Path) -> None:
    path.write_bytes(_PNG)
