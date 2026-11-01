# Bidrag til projektet

Tak for interessen. Projektet er en lille, sikker prototype. Ændringer bør bevare den tydelige adskillelse mellem research, AI, validering, rendering og levering.

## Kom i gang

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -v
.venv/bin/python -m tools.create_newsletter \
  --topic "Kunstig intelligens i danske virksomheder" \
  --dry-run
```

Dry-run er den anbefalede udviklingsvej. Den bruger fixtures og ændrer ikke Gmail.

## Før et bidrag

1. Beskriv det problem, ændringen løser.
2. Hold ændringen afgrænset til ét ansvar.
3. Tilføj eller opdater tests ved ændret adfærd.
4. Kør hele testsuiten.
5. Kontroller en ny dry-run og dens manifest.
6. Del aldrig `.env`, `credentials.json`, `token.json` eller filer fra `.tmp/`.

## Kodestil

- Brug små funktioner med tydelige navne.
- Brug type hints på offentlige funktioner og centrale datastrukturer.
- Lad validering fejle tydeligt med `NewsletterError`.
- Log kun sikre metadata, aldrig indhold eller legitimationsoplysninger.
- Bevar dansk brugerkommunikation og korte engelske docstrings, hvor de hjælper udviklere.
- Undgå skjulte netværkskald i hjælpefunktioner.

## Ændringer med eksterne konsekvenser

En pull request må ikke gøre automatisk afsendelse til standard. Betalte API-kald, nye datakilder og eksterne mutationer skal være tydelige, dokumenterede og kunne testes uden at blive udført.

## Pull request

Beskriv kort:

- problemet
- løsningen
- hvordan den er testet
- eventuelle nye risici eller begrænsninger

Se [ARCHITECTURE.md](ARCHITECTURE.md) for dataflow og modulansvar.
