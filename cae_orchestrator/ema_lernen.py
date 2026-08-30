"""Selbstlernfunktion: was die Toolchain aus ihren eigenen Laeufen gelernt hat.

Zwei Quellen, streng getrennt
-----------------------------

**1. Gemessene Regelmaessigkeiten** — aus der Rechnungsdatenbank hergeleitet, bei
jedem Aufruf neu. Niemand schreibt sie, niemand kann sie faelschen; sie aendern sich,
sobald sich der Bestand aendert. Beispiel aus dem echten Bestand: von den Laeufen mit
``struct_mesh_mm = 2`` hat **keiner** einen FEM-Wert geliefert, von denen mit 3 mm
sehr wohl. Diese Regel haette den stummen Fehlschlag vom 27.08. vorhergesagt.

**2. Erfahrungen** — Notizen, die ein Agent oder ein Mensch ablegt. Sie werden
**nur mit Beleg angenommen**: eine Lauf-Kennung, eine Zahl oder eine Befehlsausgabe.
Ohne Beleg wird die Notiz abgewiesen. Das ist die einzige Schranke, die dieses Modul
kennt, und sie hat einen Grund: ein Speicher, in den ein Sprachmodell ungepruefte
Eindruecke schreiben darf, fuellt sich mit Folklore, und die liest dann das naechste
Modell als Tatsache. Eine Regel ohne Beleg ist keine gelernte Regel, sondern ein
Geruecht mit Zeitstempel.

Was das Modul ausdruecklich NICHT tut
-------------------------------------

Es trainiert kein Modell und veraendert keine Gewichte. „Gelernt" heisst hier: aus
dem eigenen Bestand hergeleitet und beim naechsten Mal verfuegbar. Wer ein
Feintraining will, findet die Datengrundlage in ``ema_training.py`` — das ist ein
anderer Weg mit anderem Aufwand.

Veralten
--------

Jede Erfahrung merkt sich, wie viele Laeufe die Datenbank hatte, als sie geschrieben
wurde. ``pruefe`` meldet, welche seither weit hinter dem Bestand zurueckliegen — eine
Notiz von vor 20 Laeufen ist nicht falsch, aber sie ist ungeprueft alt.
"""

from __future__ import annotations

import json
import os
import statistics
import time

import ema_db as _db

ERFAHRUNGEN = os.path.expanduser("~/cae_projekte/_lernen/erfahrungen.jsonl")

# Ab so vielen neuen Laeufen gilt eine Erfahrung als nachpruefungsbeduerftig.
VERALTET_AB = 15


# ── 1. Gemessene Regeln aus der Datenbank ─────────────────────────────────────

def regel_fem_nach_netzweite(conn) -> dict:
    """Liefert die Struktur-FEM bei dieser Netzweite ueberhaupt Werte?

    Die Regel, an der drei Laeufe stillschweigend gescheitert sind.
    """
    zeilen = conn.execute("""
        SELECT p.wert_num AS netz,
               COUNT(*) AS laeufe,
               SUM(CASE WHEN k.wert_num IS NOT NULL THEN 1 ELSE 0 END) AS mit_wert
        FROM laeufe l
        JOIN parameter p ON p.lauf_id = l.lauf_id AND p.schluessel = 'struct_mesh_mm'
        LEFT JOIN kennwerte k ON k.lauf_id = l.lauf_id AND k.groesse = 'fem_sigma_vm_MPa'
        WHERE l.stufen <> ''
        GROUP BY p.wert_num ORDER BY p.wert_num""").fetchall()
    return {"netzweiten": [{"struct_mesh_mm": r["netz"], "laeufe": r["laeufe"],
                            "mit_fem_wert": r["mit_wert"]} for r in zeilen]}


def regel_wertebereiche(conn, mindest_laeufe: int = 3) -> list:
    """Welche Werte sind in diesem Bestand ueblich — je Kennwert und je Verfahren.

    Damit laesst sich ein neues Ergebnis einordnen, ohne dass jemand aus dem Gedaechtnis
    eine Plausibilitaetsgrenze erfindet. Der Bestand ist klein; die Spanne ist eine
    Beobachtung, keine Norm.
    """
    aus = []
    for r in conn.execute("""SELECT groesse, methode, COUNT(*) n FROM kennwerte
                             WHERE wert_num IS NOT NULL AND einheit <> ''
                             GROUP BY groesse HAVING n >= ?""", (mindest_laeufe,)):
        werte = [x[0] for x in conn.execute(
            "SELECT wert_num FROM kennwerte WHERE groesse=? AND wert_num IS NOT NULL",
            (r["groesse"],))]
        if len(werte) < mindest_laeufe:
            continue
        aus.append({"groesse": r["groesse"], "methode": r["methode"], "n": len(werte),
                    "min": round(min(werte), 4), "median": round(statistics.median(werte), 4),
                    "max": round(max(werte), 4),
                    "einheit": conn.execute("SELECT einheit FROM kennwerte WHERE groesse=?",
                                            (r["groesse"],)).fetchone()["einheit"]})
    return sorted(aus, key=lambda x: x["groesse"])


def regel_ausbeute(conn) -> dict:
    """Wie viele Laeufe kommen ueberhaupt durch — und woran scheitern die anderen."""
    ges = conn.execute("SELECT COUNT(*) c FROM laeufe").fetchone()["c"]
    voll = conn.execute("SELECT COUNT(*) c FROM laeufe WHERE stufen <> ''").fetchone()["c"]
    stufen = {}
    for r in conn.execute("SELECT stufen FROM laeufe WHERE stufen <> ''"):
        for st in r["stufen"].split(","):
            stufen[st] = stufen.get(st, 0) + 1
    tore = [dict(r) for r in conn.execute(
        "SELECT tor, SUM(ok) gruen, COUNT(*) gesamt FROM tore GROUP BY tor")]
    return {"laeufe_gesamt": ges, "mit_ergebnis": voll,
            "abgebrochen": ges - voll,
            "stufen_haeufigkeit": dict(sorted(stufen.items(), key=lambda x: -x[1])),
            "tore": tore}


def gemessene_regeln(conn=None) -> dict:
    conn = conn or _db.oeffne()
    return {"stand": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ausbeute":        regel_ausbeute(conn),
            "fem_nach_netz":   regel_fem_nach_netzweite(conn),
            "wertebereiche":   regel_wertebereiche(conn)}


# ── 2. Erfahrungen — nur mit Beleg ────────────────────────────────────────────

class OhneBeleg(ValueError):
    pass


def merke(regel: str, beleg: str, quelle: str = "", conn=None) -> dict:
    """Eine Erfahrung ablegen. **Ohne Beleg wird sie abgewiesen.**

    ``beleg`` muss etwas Nachpruefbares enthalten: eine Lauf-Kennung, eine Zahl mit
    Einheit oder eine Befehlsausgabe. Die Pruefung ist bewusst grob — sie soll das
    freihaendige „ich glaube, feinere Netze sind besser" abfangen, nicht einen
    Sachverstaendigen gaengeln.
    """
    regel = (regel or "").strip()
    beleg = (beleg or "").strip()
    if len(regel) < 10:
        raise OhneBeleg("Die Regel ist zu kurz, um nachvollziehbar zu sein.")
    if len(beleg) < 15:
        raise OhneBeleg(
            "Kein Beleg. Eine Erfahrung ohne Beleg ist ein Geruecht mit Zeitstempel. "
            "Nenne eine Lauf-Kennung, eine gemessene Zahl oder eine Befehlsausgabe.")
    if not any(c.isdigit() for c in beleg):
        raise OhneBeleg(
            "Der Beleg enthaelt keine einzige Zahl und keine Kennung. "
            "Woran ist die Regel nachpruefbar?")

    conn = conn or _db.oeffne()
    n_laeufe = conn.execute("SELECT COUNT(*) c FROM laeufe").fetchone()["c"]
    satz = {"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "regel": regel,
            "beleg": beleg, "quelle": quelle, "laeufe_bei_aufnahme": n_laeufe}
    os.makedirs(os.path.dirname(ERFAHRUNGEN), exist_ok=True)
    with open(ERFAHRUNGEN, "a", encoding="utf-8") as f:
        f.write(json.dumps(satz, ensure_ascii=False) + "\n")
    return satz


def aus_versuch(befund: dict, quelle: str = "versuch", conn=None) -> list:
    """Aus einem geplanten Versuch (``ema_screen.durchprobieren``) Regeln ableiten.

    Der Unterschied zu ``merke`` von Hand: hier schreibt kein Sprachmodell auf, was es
    zu wissen glaubt -- die Saetze werden aus dem Versuchsergebnis **erzeugt**, und der
    Beleg ist der Versuch selbst, mit Zahlen. Das ist die einzige Art, wie dieser
    Speicher automatisch wachsen darf, ohne sich mit Folklore zu fuellen.

    Aufgenommen wird nur, was **Geometrie oder Arithmetik** ist -- ob eine Tasche in
    den Pol passt, ob sich eine Wicklung symmetrisch legen laesst, welche Achse eine
    Kennzahl auf der analytischen Stufe ueberhaupt bewegt. Diese Aussagen kann ein
    spaeterer Feldlauf nicht umstossen. Rangfolgen und Guetezahlen werden **nicht**
    gemerkt: die haengen am Verfahren, und das ist auf dieser Stufe analytisch.
    """
    n = befund.get("geprueft", 0)
    saetze = []

    # 1. Baubarkeit je Bauform — die haltbarste Aussage des ganzen Versuchs.
    for form in sorted(befund.get("karte", {})):
        k = befund["karte"][form]
        voll, klein, nix = k["volle_groesse"], k["nur_verkleinert"], k["gar_nicht"]
        if not (voll or klein or nix):
            continue
        teile = []
        if voll:
            teile.append("in voller Magnetgroesse bei p=" + ",".join(map(str, voll)))
        if klein:
            teile.append("nur verkleinert bei " +
                         ", ".join(f"p={p} (Massstab {m:.2f})" for p, m in klein))
        if nix:
            teile.append("gar nicht bei p=" + ",".join(map(str, nix)))
        saetze.append((
            f"Bauform '{form}' ist mit dieser Rotorgroesse {'; '.join(teile)} baubar.",
            f"Geplanter Versuch ueber {n} Kombinationen, 2-D-Layouttor "
            f"(Mindeststeg {2.0} mm) auf jeder einzelnen. Karte: {json.dumps(k)}"))

    # 2. Welche Achse eine Kennzahl auf dieser Stufe NICHT bewegt.
    for kennzahl, achsen in (befund.get("unbewegt") or {}).items():
        fest = sorted(a for a, konstant in achsen.items() if konstant)
        if fest:
            saetze.append((
                f"Auf der analytischen Stufe haengt {kennzahl} NICHT von "
                f"{' und '.join(fest)} ab. Wer danach unterscheiden will, braucht den "
                f"Feldlauf.",
                f"Geplanter Versuch, {n} Kombinationen: bei fester Polpaarzahl und "
                f"Bauform ist {kennzahl} ueber alle Werte von {', '.join(fest)} "
                f"identisch (0 abweichende Gruppen)."))

    # 3. Bauformen, die auf dieser Stufe ununterscheidbar sind.
    for gruppe in befund.get("ununterscheidbar") or []:
        saetze.append((
            f"Die Bauformen {', '.join(gruppe)} liefern auf der analytischen Stufe "
            f"dieselbe Kt und dieselbe B_gap -- sie sind dort nicht zu trennen.",
            f"Geplanter Versuch ueber {n} Kombinationen: bei gleicher Polpaarzahl "
            f"stimmen Kt und B_gap auf 6 Nachkommastellen ueberein."))

    aufgenommen = []
    for regel, beleg in saetze:
        try:
            aufgenommen.append(merke(regel, beleg, quelle=quelle, conn=conn))
        except OhneBeleg as e:                                # noqa: PERF203
            aufgenommen.append({"abgewiesen": str(e), "regel": regel})
    return aufgenommen


def erfahrungen() -> list:
    if not os.path.isfile(ERFAHRUNGEN):
        return []
    aus = []
    with open(ERFAHRUNGEN, encoding="utf-8") as f:
        for z in f:
            z = z.strip()
            if z:
                try:
                    aus.append(json.loads(z))
                except ValueError:
                    pass
    return aus


def pruefe(conn=None) -> dict:
    """Welche Erfahrungen sind seit ihrer Aufnahme weit hinter den Bestand gefallen."""
    conn = conn or _db.oeffne()
    jetzt = conn.execute("SELECT COUNT(*) c FROM laeufe").fetchone()["c"]
    alt, frisch = [], []
    for e in erfahrungen():
        (alt if jetzt - e.get("laeufe_bei_aufnahme", 0) >= VERALTET_AB else frisch).append(
            dict(e, neue_laeufe_seither=jetzt - e.get("laeufe_bei_aufnahme", 0)))
    return {"laeufe_jetzt": jetzt, "frisch": frisch, "nachzupruefen": alt}


# ── Ausgabe fuer die Agenten ──────────────────────────────────────────────────

def als_text(conn=None) -> str:
    """Alles, was gelernt wurde — als Text, den beide Agenten am Sitzungsanfang lesen."""
    conn = conn or _db.oeffne()
    r = gemessene_regeln(conn)
    a = r["ausbeute"]
    z = ["# Was diese Toolchain aus ihren eigenen Laeufen weiss", "",
         "## Gemessen (aus der Rechnungsdatenbank, bei jedem Aufruf neu hergeleitet)", "",
         f"* Bestand: **{a['laeufe_gesamt']} Laeufe**, davon {a['mit_ergebnis']} mit "
         f"Ergebnis und {a['abgebrochen']} abgebrochen."]

    netz = r["fem_nach_netz"]["netzweiten"]
    if netz:
        z += ["", "* Struktur-FEM nach Netzweite — **liefert sie ueberhaupt Werte?**", ""]
        z += ["  | struct_mesh_mm | Laeufe | mit FEM-Wert |", "  |---|---|---|"]
        for n in netz:
            z.append(f"  | {n['struct_mesh_mm']} | {n['laeufe']} | {n['mit_fem_wert']} |")
        # Nicht erst bei null warnen: eine Ausbeute von 1 aus 11 ist genauso eine
        # Regel, und der Bestand ist zu klein, als dass "genau null" ein sinnvoller
        # Schwellwert waere.
        schwach = [n for n in netz
                   if n["laeufe"] >= 2 and n["mit_fem_wert"] / n["laeufe"] < 0.5]
        if schwach:
            z += ["", "  **Beobachtung:** " + "; ".join(
                f"bei {n['struct_mesh_mm']} mm lieferten nur {n['mit_fem_wert']} von "
                f"{n['laeufe']} Laeufen einen FEM-Wert" for n in schwach) +
                ". Ueblicher Grund ist die Zeitueberschreitung — feinere Netze kosten "
                "ueberproportional Zeit (gemessen: 3 mm ≈ 7 min, 2 mm deutlich mehr "
                "als der 20-Minuten-Deckel). Groeberes Netz waehlen, oder "
                "`struct_solver='ccx'`: der eigene Rechensatz rechnet denselben Fall "
                "in Sekunden."]

    if a["tore"]:
        z += ["", "* Tore:"]
        for t in a["tore"]:
            z.append(f"  * `{t['tor']}`: {t['gruen'] or 0} von {t['gesamt']} gruen")

    wb = r["wertebereiche"]
    if wb:
        z += ["", "* Uebliche Wertebereiche in diesem Bestand "
              "(Beobachtung, keine Norm — der Bestand ist klein):", "",
              "  | Kennwert | Verfahren | min | Median | max | n |", "  |---|---|---|---|---|---|"]
        for w in wb[:18]:
            z.append(f"  | {w['groesse']} {w['einheit']} | {w['methode']} | "
                     f"{w['min']} | {w['median']} | {w['max']} | {w['n']} |")

    e = erfahrungen()
    z += ["", "## Erfahrungen (abgelegt, jede mit Beleg)", ""]
    if not e:
        z.append("*(noch keine)*")
    else:
        for x in e:
            z += [f"* **{x['regel']}**",
                  f"  * Beleg: {x['beleg']}",
                  f"  * abgelegt {x['zeit'][:10]}"
                  + (f", Quelle: {x['quelle']}" if x.get("quelle") else "")]
    p = pruefe(conn)
    if p["nachzupruefen"]:
        z += ["", f"**Nachzupruefen** ({VERALTET_AB}+ neue Laeufe seit Aufnahme):"]
        for x in p["nachzupruefen"]:
            z.append(f"* {x['regel']} — {x['neue_laeufe_seither']} Laeufe seither")
    return "\n".join(z) + "\n"
