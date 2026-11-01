# Opret et automatisk nyhedsbrev

## Formål

Find kilder gennem et offentligt Google News RSS-feed, skriv et kort dansk nyhedsbrev med den aktuelle gratis Gemini Flash-model, generér én lokal infografik, og opret resultatet som en Gmail-kladde. Standardkørslen må aldrig sende mailen. Afsendelse kræver både flaget `--send` og brugerens udtrykkelige godkendelse til den konkrete modtager.

## Input

- Påkrævet: `--topic`.
- Valgfrit: `--angle`, `--audience`, `--tone`, `--recipient`.
- Standardmålgruppe: bred professionel målgruppe.
- Standardtone: neutral og professionel.
- Standardmodtager: `NEWSLETTER_RECIPIENT` fra `.env`.
- Kun én modtager accepteres.

## Forudsætninger

1. Python 3.11 eller nyere.
2. Installer `requirements.txt`.
3. Udfyld `.env` med en Gemini API-nøgle og en testmodtager.
4. Læg en Google OAuth Desktop App-fil i `credentials.json`. Første livekørsel åbner OAuth-flowet og gemmer `token.json` med scope `gmail.compose`.
5. Bekræft altid med brugeren, før en livekørsel foretager betalte API-kald. Efter et fejlet betalt kald skal en ny livekørsel bekræftes igen.

## Sikker prøve

Kør uden netværk, credits eller Gmail-ændringer:

```bash
python -m tools.create_newsletter --topic "Kunstig intelligens i danske virksomheder" --dry-run
```

Resultatet ligger i `.tmp/<run-id>/` og indeholder researchfixture, PNG, HTML, tekst, EML og manifest.

## Livekørsel

Når brugeren udtrykkeligt har godkendt ét Gemini-kald og én Gmail-kladde:

```bash
python -m tools.create_newsletter \
  --topic "Emnet" \
  --angle "Valgfri vinkel" \
  --audience "bred professionel målgruppe" \
  --tone "neutral og professionel"
```

Til en udtrykkeligt godkendt testafsendelse til den validerede modtager tilføjes `--send`. Gmail sender da den allerede gemte rå MIME-kladde gennem samme API-session, så inline-billedets Content-ID bevares.

## Rækkefølge og kvalitetskrav

1. Validér én modtager og nødvendig konfiguration.
2. Søg med `site:.dk` og hent mindst tre unikke HTTP(S)-kilder fra Google News RSS.
   - Kildens udgiver-URL skal ligge på et dansk `.dk`-domæne. Feedets danske sprogindstilling er ikke i sig selv tilstrækkelig.
   - Kilden skal have en gyldig udgivelsesdato og som standard være højst 365 dage gammel.
   - Norske, svenske, internationale og udaterede kilder afvises, selv hvis de omtaler Danmark.
   - Titel eller uddrag skal matche emnets centrale søgeord; almindelige fagforkortelser som `AI` accepteres.
   - Et dansk domæne er ikke nok i sig selv: emnemæssigt irrelevante danske artikler afvises også.
   - Tydelige norske sprogformer afvises også på `.dk`-domæner.
   - Stop uden Gemini- eller Gmail-kald, hvis der ikke findes mindst tre aktuelle danske kilder.
3. Brug Gemini uden betalt søgeværktøj til at forme feedets titler, datoer, uddrag og URL'er som præcis tre hovedpointer i det validerede JSON-skema.
4. Stop ved ugyldig JSON, tomme felter, dublerede/ugyldige URL'er, færre end tre kilder eller en URL, der ikke kommer fra feedet.
5. Gem den validerede researchpakke.
6. Generér en lokal 1200 × 675 PNG med de tre validerede overskrifter og korte tekster. Der foretages intet billed-API-kald.
7. Render tabelbaseret HTML, tekstfallback og en MIME-meddelelse med infografikken som inline Content-ID.
8. Opret én Gmail-kladde gennem `users.drafts.create`.
9. Send kun kladden gennem `users.drafts.send`, når `--send` er angivet, og brugeren har godkendt den konkrete afsendelse. Rekonstruér ikke mailen via en anden forbindelse, da inline-billedet ellers kan gå tabt.
10. Log kun run-ID, trin, model, kladde-ID, mail-ID, varighed og sikre fejlbeskeder. Log aldrig nøgler, tokens eller hele mailindholdet.

## Output

- Gmail-kladde-id ved livekørsel.
- `.tmp/<run-id>/research.json`
- `.tmp/<run-id>/infographic.png`
- `.tmp/<run-id>/newsletter.html`
- `.tmp/<run-id>/newsletter.txt`
- `.tmp/<run-id>/newsletter.eml`
- `.tmp/<run-id>/run-manifest.json`

## Fejlhåndtering

- Manglende nøgler/OAuth: stop før den relevante eksterne handling og vis konfigurationsnavnet.
- Rate limit eller ekstern HTTP-fejl: stop. Foretag ikke automatisk et nyt betalt job.
- Feed- eller Gemini-fejl: gem manifestet og stop før Gmail.
- Gmail-fejl: behold alle lokale artefakter, registrér fejlen i manifestet og send intet.
- Uklar ekstern mutation: inspicér leverandørens status før en ny livekørsel for at undgå dubletter eller ekstra credits.
