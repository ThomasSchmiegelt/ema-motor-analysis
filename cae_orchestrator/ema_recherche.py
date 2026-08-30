"""Internetrecherche fuer die Agenten (PI und Hermes).

Bewusste Abkehr von einer bisherigen Regel
------------------------------------------

Bis hierher galt in der Wurzel-``AGENTS.md``: „Nichts hier redet ueber das Heimnetz
hinaus. Keine externe Gegenstelle einbauen." Diese Regel ist auf ausdrueckliche
Entscheidung aufgehoben — die Agenten duerfen recherchieren. ``AGENTS.md`` wurde
entsprechend umgeschrieben, statt die Regel stehen zu lassen und zu unterlaufen.

Was daraus folgt, und zwar sachlich und nicht als Mahnung: **was aus dem Netz kommt,
ist Text, den jemand anderes geschrieben hat.** Er kann falsch sein, veraltet, oder
Anweisungen an ein Sprachmodell enthalten. In einer Dokumentation, die Rechenergebnisse
belegen soll, darf er darum nicht neben den gerechneten Zahlen stehen, als waere er
gleichwertig. Dieses Modul markiert deshalb jedes Ergebnis als **Fremdtext mit
Quellenangabe** — dieselbe Trennung, die das Werkzeug zwischen analytischer Formel und
Feldrechnung schon macht.

Zwei Verben, beide ohne Schluessel und ohne Konto:

``suche``   DuckDuckGo ueber ``ddgs`` — Titel, Adresse, Anriss
``hole``    eine Seite als Text ueber ``trafilatura`` (Artikelextraktion, kein Roh-HTML)

Beide Agenten benutzen sie ueber ``bash``; es gibt keinen zweiten Weg und keine
Sonderbehandlung fuer einen der beiden.
"""

from __future__ import annotations

import json
import os
import time

# Wie viel Text eine geholte Seite hoechstens beisteuert. Ein 46.000-Zeichen-Artikel
# (gemessen an de.wikipedia/Synchronmaschine) fuellt sonst allein schon zwei Drittel
# des 65k-Kontextfensters und draengt die Rechenergebnisse heraus.
MAX_ZEICHEN = 6000
MAX_TREFFER = 10

PROTOKOLL = os.path.expanduser("~/cae_projekte/_recherche/protokoll.jsonl")


def _notiere(art: str, was: str, ergebnis: str) -> None:
    """Mitschrift, damit spaeter nachvollziehbar ist, woher eine Aussage kam.

    Kein Tor und keine Sperre — es wird nichts verhindert. Aber wenn in einem Bericht
    eine Behauptung steht, soll man nachsehen koennen, welche Seite sie geliefert hat.
    """
    try:
        os.makedirs(os.path.dirname(PROTOKOLL), exist_ok=True)
        with open(PROTOKOLL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "art": art, "was": was, "ergebnis": ergebnis[:200]},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def suche(frage: str, treffer: int = 5, region: str = "de-de") -> list:
    """Websuche. Gibt ``[{titel, adresse, anriss}]`` zurueck."""
    from ddgs import DDGS

    treffer = max(1, min(MAX_TREFFER, int(treffer)))
    aus = []
    for r in DDGS().text(frage, region=region, max_results=treffer):
        aus.append({"titel": r.get("title", ""), "adresse": r.get("href", ""),
                    "anriss": (r.get("body", "") or "")[:300]})
    _notiere("suche", frage, f"{len(aus)} Treffer")
    return aus


def hole(adresse: str, max_zeichen: int = MAX_ZEICHEN) -> dict:
    """Eine Seite als Fliesstext. Gibt ``{adresse, titel, text, zeichen, gekuerzt}``."""
    import trafilatura

    roh = trafilatura.fetch_url(adresse)
    if not roh:
        _notiere("hole", adresse, "nicht erreichbar")
        return {"adresse": adresse, "fehler": "nicht erreichbar oder nicht vorhanden"}
    text = trafilatura.extract(roh, include_comments=False, include_tables=True) or ""
    meta = trafilatura.extract_metadata(roh)
    voll = len(text)
    gekuerzt = voll > max_zeichen
    _notiere("hole", adresse, f"{voll} Zeichen")
    return {"adresse": adresse,
            "titel": getattr(meta, "title", None) or "",
            "datum": getattr(meta, "date", None) or "",
            "text": text[:max_zeichen],
            "zeichen": voll,
            "gekuerzt": gekuerzt}


def als_text(daten, art: str) -> str:
    """Agentenfreundliche Ausgabe — mit der Herkunftsmarke davor."""
    kopf = ("FREMDTEXT AUS DEM INTERNET — nicht gerechnet, nicht geprueft. "
            "In einem Bericht nur MIT Quellenangabe verwenden und niemals als "
            "Ersatz fuer eine Zahl aus der Rechnungsdatenbank.\n")
    if art == "suche":
        zeilen = [kopf]
        for i, t in enumerate(daten, 1):
            zeilen.append(f"{i}. {t['titel']}\n   {t['adresse']}\n   {t['anriss']}")
        return "\n".join(zeilen)
    if daten.get("fehler"):
        return f"Fehler: {daten['fehler']} ({daten['adresse']})"
    kuerz = (f"\n\n[gekuerzt auf {MAX_ZEICHEN} von {daten['zeichen']} Zeichen]"
             if daten["gekuerzt"] else "")
    return (kopf + f"\nQuelle: {daten['adresse']}\n"
            f"Titel : {daten['titel']}\n"
            + (f"Datum : {daten['datum']}\n" if daten["datum"] else "")
            + "\n" + daten["text"] + kuerz)
