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


def _arbeit_puls() -> None:
    """Der Arbeitsleiste im Agentenreiter sagen, dass gerade ins Netz gegriffen wird.

    Von hier und nicht aus dem Werkzeugtext des Agenten geraten: nur die Stelle,
    die tatsaechlich eine Verbindung aufmacht, weiss, dass sie es tut. Weich
    fehlschlagend -- eine Anzeige darf eine Recherche nie abbrechen.
    """
    try:
        import ema_arbeit
        ema_arbeit.puls()
    except Exception:                                        # noqa: BLE001
        pass


def suche(frage: str, treffer: int = 5, region: str = "de-de") -> list:
    """Websuche. Gibt ``[{titel, adresse, anriss}]`` zurueck."""
    _arbeit_puls()
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
    _arbeit_puls()
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


# ── Unter dem Projekt ablegen ─────────────────────────────────────────────────

import re as _re
import urllib.parse as _up
import urllib.request as _ur

# Bildabruf: bewusst eng. Nur was der Agent AUSDRUECKLICH nennt, nur diese Formate,
# und ein Deckel — ein Recherchelauf soll kein Bilderarchiv anlegen.
BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
BILD_MAX_BYTE = 4 * 1024 * 1024
BILD_MAX_ZAHL = 6
KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cae-orchestrator/recherche"}


def _ordner(projekt_pfad: str) -> str:
    d = os.path.join(projekt_pfad, "recherche")
    os.makedirs(os.path.join(d, "bilder"), exist_ok=True)
    return d


def bilder_im_text(html_oder_url: str, basis: str = "") -> list:
    """Bildadressen aus einer HTML-Seite sammeln (nur zum Vorschlagen, lädt nichts)."""
    treffer = []
    for m in _re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html_oder_url, _re.I):
        u = _up.urljoin(basis, m.group(1))
        if u.lower().split("?")[0].endswith(BILD_ENDUNGEN):
            treffer.append(u)
    # Reihenfolge erhalten, Doppelte raus
    gesehen, aus = set(), []
    for u in treffer:
        if u not in gesehen:
            gesehen.add(u); aus.append(u)
    return aus[:20]


def hole_bild(adresse: str, ziel_ordner: str) -> dict:
    """Ein Bild herunterladen. Gibt ``{datei, adresse, bytes}`` oder ``{fehler}``.

    Urheberrecht: heruntergeladene Bilder bleiben fremdes Werk. Sie liegen hier zur
    eigenen Anschauung; wer sie in einen Bericht nimmt, der weitergegeben wird, muss
    die Rechtelage selbst klaeren. Die Quelladresse wird darum immer mitgespeichert.
    """
    _arbeit_puls()
    try:
        req = _ur.Request(adresse, headers=KOPF)
        with _ur.urlopen(req, timeout=25) as r:
            roh = r.read(BILD_MAX_BYTE + 1)
    except Exception as e:                                   # noqa: BLE001
        return {"adresse": adresse, "fehler": f"{type(e).__name__}: {e}"}
    if len(roh) > BILD_MAX_BYTE:
        return {"adresse": adresse, "fehler": f"groesser als {BILD_MAX_BYTE//1024//1024} MB"}
    name = os.path.basename(_up.urlparse(adresse).path) or "bild"
    name = _re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]
    if not name.lower().endswith(BILD_ENDUNGEN):
        name += ".png"
    ziel = os.path.join(ziel_ordner, name)
    n = 1
    while os.path.exists(ziel):
        stamm, endung = os.path.splitext(name)
        ziel = os.path.join(ziel_ordner, f"{stamm}_{n}{endung}"); n += 1
    with open(ziel, "wb") as f:
        f.write(roh)
    return {"datei": ziel, "adresse": adresse, "bytes": len(roh)}


def speichere(projekt_pfad: str, adresse: str, notiz: str = "",
              auszug: str = "", bilder: list | None = None,
              werte: list | None = None) -> dict:
    """Eine Quelle unter dem Projekt ablegen — Text, Bilder, und die genannten Werte.

    ``werte`` ist eine Liste ``[{groesse, wert, einheit, zitat}]``. Sie wandert
    **zusaetzlich** in die Rechnungsdatenbank, aber in die Tabelle ``referenzwerte``
    und nicht zu den gerechneten Kennwerten (siehe ``ema_db``).

    **Zahlen werden NICHT automatisch aus dem Text gefischt.** Wer einen Wert
    uebernimmt, nennt ihn und die Textstelle, aus der er stammt. Ein Regelausdruck,
    der Zahlen aus Fliesstext klaubt, verwechselt frueher oder spaeter eine
    Seitenzahl mit einer Stegbreite — und niemand merkt es, weil das Ergebnis
    plausibel aussieht.
    """
    if not os.path.isdir(projekt_pfad):
        raise FileNotFoundError(f"Projekt nicht gefunden: {projekt_pfad}")
    d = _ordner(projekt_pfad)
    seite = hole(adresse) if not auszug else {"adresse": adresse, "titel": "",
                                              "datum": "", "text": auszug,
                                              "zeichen": len(auszug), "gekuerzt": False}
    if seite.get("fehler"):
        return seite

    geladen = []
    for u in (bilder or [])[:BILD_MAX_ZAHL]:
        geladen.append(hole_bild(u, os.path.join(d, "bilder")))

    satz = {"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "adresse": adresse, "titel": seite.get("titel", ""),
            "datum": seite.get("datum", ""), "notiz": notiz,
            "auszug": (seite.get("text") or "")[:MAX_ZEICHEN],
            "zeichen_gesamt": seite.get("zeichen", 0),
            "bilder": geladen, "werte": werte or []}
    with open(os.path.join(d, "quellen.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(satz, ensure_ascii=False) + "\n")

    # Werte in die Datenbank — in referenzwerte, NICHT zu den gerechneten Kennwerten.
    uebernommen, abgewiesen = 0, []
    if werte:
        try:
            import ema_db
            conn = ema_db.oeffne()
            pid = os.path.basename(projekt_pfad.rstrip("/"))
            for w in werte:
                try:
                    ema_db.referenz_hinzufuegen(
                        conn, w["groesse"], w.get("wert"), w.get("einheit", ""),
                        w.get("zitat", ""), adresse, seite.get("titel", ""),
                        projekt_id=pid, notiz=notiz)
                    uebernommen += 1
                except (ema_db.OhneQuelle, KeyError) as e:
                    abgewiesen.append(f"{w.get('groesse', '?')}: {e}")
            conn.close()
        except Exception as e:                               # noqa: BLE001
            abgewiesen.append(f"Datenbank: {e}")

    _notiere("speichere", adresse, f"{len(geladen)} Bilder, {uebernommen} Werte")
    return {"abgelegt": os.path.join(d, "quellen.jsonl"),
            "titel": satz["titel"], "bilder": geladen,
            "werte_uebernommen": uebernommen, "werte_abgewiesen": abgewiesen}


def quellen(projekt_pfad: str) -> list:
    """Die unter einem Projekt abgelegten Quellen."""
    f = os.path.join(projekt_pfad, "recherche", "quellen.jsonl")
    if not os.path.isfile(f):
        return []
    aus = []
    with open(f, encoding="utf-8") as fh:
        for z in fh:
            z = z.strip()
            if z:
                try:
                    aus.append(json.loads(z))
                except ValueError:
                    pass
    return aus


def quellen_markdown(projekt_pfad: str) -> str:
    """Der Quellenabschnitt fuer den Bericht — mit Bildern und Herkunftsvermerk."""
    q = quellen(projekt_pfad)
    if not q:
        return ""
    z = ["### Herangezogene Fremdquellen", "",
         "Die folgenden Veroeffentlichungen wurden zur Einordnung herangezogen. Sie "
         "sind **nicht Teil der Rechnung** und wurden nicht nachgerechnet.", ""]
    for i, s in enumerate(q, 1):
        z.append(f"{i}. **{s['titel'] or s['adresse']}** — {s['adresse']}"
                 + (f" (Stand {s['datum']})" if s.get("datum") else ""))
        if s.get("notiz"):
            z.append(f"   * Wofuer herangezogen: {s['notiz']}")
        for w in s.get("werte", []):
            z.append(f"   * Entnommen: {w.get('groesse')} = {w.get('wert')} "
                     f"{w.get('einheit', '')} — „{(w.get('zitat') or '')[:160]}“")
        for b in s.get("bilder", []):
            if b.get("datei"):
                z.append(f"\n![Abbildung aus {s['titel'] or s['adresse']}]"
                         f"({b['datei']})\n")
                z.append(f"   *Quelle der Abbildung: {b['adresse']} — fremdes Werk, "
                         f"Rechtelage vor einer Weitergabe klaeren.*")
    return "\n".join(z) + "\n"
