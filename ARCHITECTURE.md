# Arkitektur

Projektet følger WAT-princippet: workflowet beskriver opgaven, AI håndterer den sproglige bearbejdning, og Python-værktøjerne udfører de gentagelige og kontrollerbare trin.

## Dataflow

```text
CLI-input
  → Google News RSS
  → kildefiltrering
  → Gemini med struktureret JSON-skema
  → valideret NewsletterResearch
  → PNG, HTML, tekst og MIME-mail
  → Gmail-kladde
  → valgfri, eksplicit afsendelse
```

## Moduler

| Modul | Ansvar |
| --- | --- |
| `tools/create_newsletter.py` | Orkestrerer én kørsel, artefakter, manifest og levering. |
| `tools/research.py` | Henter feed, filtrerer kilder, kalder Gemini og validerer researchpakken. |
| `tools/local_infographic.py` | Genererer en lokal PNG ud fra de tre validerede pointer. |
| `tools/render_email.py` | Renderer HTML, tekstfallback og MIME-struktur med inline-billede. |
| `tools/gmail_draft.py` | Håndterer OAuth, Gmail-kladde og eksplicit afsendelse. |
| `tools/common.py` | Fælles konfiguration, HTTP og sikre brugerfejl. |
| `tools/render_preview.py` | Laver en browserpreview uden at ændre den rigtige MIME-mail. |

## Vigtige grænser

- Gemini modtager kun kilder, som feedfiltret har godkendt.
- Gemini returnerer kilde-ID'er, ikke frie URL'er.
- Python oversætter ID'erne til de oprindelige feed-URL'er og afviser ukendte værdier.
- `--dry-run` må ikke kalde netværk eller Gmail.
- Standardkørslen opretter kun en kladde.
- `--send` er et særskilt valg og kan ikke kombineres med dry-run.
- Gmail sender den gemte MIME-kladde i stedet for at rekonstruere HTML’en.

## Artefakter fra en kørsel

Hver kørsel får sin egen mappe under `.tmp/<run-id>/`:

- `research.json`
- `infographic.png`
- `newsletter.html`
- `newsletter.txt`
- `newsletter.eml`
- `run-manifest.json`

Manifestet er en kort driftslog. Det må ikke indeholde nøgler, tokens eller hele mailindholdet.

## Udvidelse

Nye kilder bør implementeres før AI-trinnet og returnere samme `Source`-model. Nye leveringskanaler bør placeres efter rendering og kræve deres egen eksplicitte godkendelse. Undgå at blande kildehentning, tekstgenerering og levering i samme funktion.
