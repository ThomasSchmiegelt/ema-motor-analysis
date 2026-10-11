#!/usr/bin/env python3
"""Aus einem Fehlschlag einen BEFUND machen -- was, warum, und was hilft.

Gemeldet als: *„Oefter bekomme ich die Meldung 'Analyse fehlgeschlagen' und
mehr nicht. Das ist auch teilweise unlogisch, da ich beispielsweise einen Frame
rechnen kann. Ich brauche hier mehr Kontext oder einen konkreten Vorschlag."*

Beide Haelften der Beschwerde sind berechtigt, und die zweite ist die
interessantere.

**Warum „ich kann doch einen Frame rechnen" kein Widerspruch ist.**
``ema_analysis.render_preview_frame`` fuehrt **kein einziges Tor** -- es raster
die Geometrie und loest das Feld. ``run_pipeline`` fuehrt davor vier
(Maschinenart, Grenzen, Rotor-Layout, Fliehkraft). Eine Zeichnung, die sich
zeichnen UND als Frame rechnen laesst, kann an einem dieser Tore scheitern; das
ist kein Fehler, sondern der Zweck der Tore. Nur stand es nirgends, und aus dem
Sessel davor sieht es wie ein Widerspruch aus. Es steht jetzt in der Meldung.

**Warum es ueberhaupt nur EIN Tor mit Vorschlaegen gab.**
``AuslegungReisst`` traegt seit dem 12.09.2026 gerechnete Auswege, und die
Oberflaeche macht daraus Knoepfe. Geworfen wird sie aber nur vom
Fliehkraft-Tor. Jeder andere Fehlschlag -- eine verletzte Grenze, eine nicht
getragene Maschinenart, ein ungueltiges Layout, ein Abbruch in FreeCAD --
landete als nackter Traceback im Protokoll.

Dieses Modul macht aus JEDEM Fehlschlag dieselbe Form, die die Oberflaeche
schon zeichnen kann::

    {"tor", "titel", "befund", "wege": [{"text", "preis",
                                         "schluessel", "wert", "ebene"}],
     "hinweise": [...], "chat": "..."}

**Die Regel von ``ema_rotorcheck.entlastung`` gilt auch hier: jeder Weg wird
gegen DASSELBE Tor nachgeprueft, bevor er vorgeschlagen wird.** Einer, der es
erneut reissen laesst, ist keiner -- und ein Vorschlag, den das Werkzeug im
naechsten Anlauf selbst abweist, ist schlimmer als keiner, weil er Vertrauen
kostet.

**Vorgeschlagen ist nicht gewaehlt.** Jeder Weg nennt seinen Preis; uebernommen
wird auf Klick, und auch dann wird nur das Formular gesetzt. Was gebaut wird,
entscheidet der Mensch.
"""

import copy
import math

#: Wieviele Vorschlaege hoechstens angeboten werden. Mehr als eine Handvoll
#: ist keine Hilfe mehr, sondern eine zweite Entscheidung.
MAX_WEGE = 4

#: Der Satz, der die gemeldete Unstimmigkeit aufloest. Er steht nur dort, wo
#: wirklich ein Tor gerissen ist -- sonst waere er Beruhigung ohne Aussage.
VORSCHAU_SATZ = (
    "Dass die Live-Vorschau und ein einzelner Frame rechnen, widerspricht dem "
    "nicht: der Vorschaupfad rastert die Geometrie und loest das Feld, er "
    "fuehrt KEIN Tor. Die Analyse fuehrt davor vier (Maschinenart, Grenzen, "
    "Rotor-Layout, Fliehkraft) -- und genau eines davon hat hier gehalten.")


def _geom(payload):
    p = payload or {}
    return dict(p.get("geom") or {})


def _weg(text, preis="", schluessel="", wert=None, ebene="geom",
         aenderungen=None):
    """Ein Weg. Er traegt EINEN Schluessel -- oder mehrere (`aenderungen`).

    Die mehrteiligen gab es ab dem 03.10.2026, und diese Funktion liess sie
    stillschweigend fallen: ohne `schluessel` kam ein Dict ohne jede Aenderung
    heraus, und der Knopf im Browser tat nichts. Gefunden beim Durchspielen,
    nicht beim Lesen.
    """
    w = {"text": text, "preis": preis}
    if schluessel:
        w.update({"schluessel": schluessel, "wert": wert, "ebene": ebene})
    if aenderungen:
        w.update({"aenderungen": dict(aenderungen), "ebene": ebene})
    return w


def _mit(payload, **aenderungen):
    """Eine KOPIE des Payloads mit geaenderten geom-Werten."""
    p = copy.deepcopy(payload or {})
    g = p.setdefault("geom", {})
    g.update(aenderungen)
    return p


# ── Suche: der beste Wert, der das Tor wirklich besteht ──────────────────────

def _anbieten(wege, payload, pruef, text, preis, schluessel, wert,
              ebene="geom"):
    """Einen Weg NUR anbieten, wenn er sein Tor wirklich besteht.

    Die Regel stand im Modulkopf und wurde in zwei von vier Zweigen nicht
    eingehalten -- der Nuttiefen- und der Statordurchmesser-Vorschlag gingen
    ungeprueft hinaus. An einer entarteten Geometrie (Statorbohrung groesser
    als der Aussendurchmesser) kam dabei „Nuttiefe auf 1,0 mm — -54,3 mm
    Statorwand lassen hoechstens 1,0 mm zu" heraus: eine negative Wand, ein
    sinnloser Wert, ein Knopf, der nichts heilt.

    Deshalb geht ab jetzt JEDER Weg durch diese eine Funktion. Die Regel ist
    damit strukturell und nicht mehr eine Frage der Sorgfalt an vier Stellen --
    dasselbe Argument, aus dem ``ema_rotorcheck.entlastung`` seine Wege gegen
    dasselbe Tor nachrechnet, bevor sie jemand zu sehen bekommt.
    """
    try:
        if not pruef(_mit(payload, **{schluessel: wert})):
            return False
    except Exception:                                        # noqa: BLE001
        return False
    wege.append(_weg(text, preis, schluessel, wert, ebene))
    return True


def _groesster_der_besteht(payload, schluessel, werte, pruef):
    """Aus einer absteigenden Werteliste den ersten, der ``pruef`` besteht.

    Absteigend, weil bei allen Hebeln hier der GROESSERE Wert der bessere ist
    (mehr Leiter, tiefere Nut) -- gesucht wird also die geringste Einbusse, die
    noch durchgeht. Geprueft wird mit der Funktion des Tors selbst; eine zweite
    Abstandsformel daneben waere genau die Stelle, an der ein Vorschlag
    entsteht, den der naechste Lauf abweist.
    """
    for w in werte:
        try:
            if pruef(_mit(payload, **{schluessel: w})):
                return w
        except Exception:                                    # noqa: BLE001
            continue
    return None


# ── Einzelne Tore ────────────────────────────────────────────────────────────

def _wege_grenzen(payload):
    """Konkrete Werte fuer die Grenzen, die immer gelten."""
    import ema_grenzen as G
    wege, hinweise = [], []
    try:
        erg = G.pruefe(payload)
    except Exception:                                        # noqa: BLE001
        return wege, hinweise
    g = _geom(payload)

    for b in erg.get("verletzt") or []:
        name = b.get("name")

        if name == "luftspalt":
            lo, hi = b.get("band_mm") or G.LUFTSPALT_MM
            ist = float(b.get("wert_mm") or 0.0)
            ziel = min(max(ist, lo), hi)
            # Der Spalt ist KEIN eigenes Feld -- geaendert wird die Bohrung.
            r_rot = float(g.get("rotorOD") or 0.0)
            if r_rot > 0:
                neu = round(r_rot + 2.0 * ziel, 2)
                _anbieten(
                    wege, payload,
                    lambda q: G.pruefe_luftspalt(q)["ok"],
                    f"Statorbohrung auf {neu:.2f} mm — dann liegt der "
                    f"Luftspalt bei {ziel:.2f} mm statt {ist:.2f} mm",
                    "Der Spalt folgt aus statorID und rotorOD; hier wird die "
                    "Bohrung bewegt, der Laeufer bleibt."
                    + (" Ein weiter Spalt kostet Luftspaltfeld und damit "
                       "Moment." if ziel > 1.0 else ""),
                    "statorID", neu)

        elif name == "hairpin":
            # Der einzige Hebel, der den Wickelkopf wirklich kleiner macht,
            # ohne die Maschine zu vergroessern: weniger LAGEN.
            n = int(g.get("conductorsPerSlot") or 0)
            if n > 2:
                kand = [k for k in range(n - 2, 1, -2)]
                best = _groesster_der_besteht(
                    payload, "conductorsPerSlot", kand,
                    lambda p: G.pruefe_hairpin(p)["ok"])
                if best:
                    _anbieten(
                        wege, payload,
                        lambda q: G.pruefe_hairpin(q)["ok"],
                        f"Leiter je Nut auf {best} statt {n}",
                        "Weniger Kupfer je Nut: hoehere Stromdichte bei "
                        "gleichem Strom, also mehr Wicklungsverlust.",
                        "conductorsPerSlot", best)
            ueber = float(b.get("ueberstand_mm") or 0.0)
            d_st = float(g.get("statorOD") or 0.0)
            if ueber > 0 and d_st > 0:
                neu = round(d_st + 2.0 * ueber + 2.0, 1)
                _anbieten(
                    wege, payload,
                    lambda q: G.pruefe_hairpin(q)["ok"],
                    f"Statoraussendurchmesser auf {neu:.1f} mm — dann passt "
                    f"der Wickelkopf ({b.get('weiteste_stelle', 'Krone')} "
                    f"steht {ueber:.1f} mm ueber)",
                    "Groessere Maschine: mehr Masse, mehr Bauraum.",
                    "statorOD", neu)

        elif name == "leiterquerschnitt":
            n = int(g.get("conductorsPerSlot") or 0)
            if n > 2:
                best = _groesster_der_besteht(
                    payload, "conductorsPerSlot",
                    [k for k in range(n - 2, 1, -2)],
                    lambda p: G.pruefe_leiterquerschnitt(p)["ok"])
                if best:
                    _anbieten(
                        wege, payload,
                        lambda q: G.pruefe_leiterquerschnitt(q)["ok"],
                        f"Leiter je Nut auf {best} statt {n} — dann passt die "
                        f"Wicklung in die Nut",
                        "Weniger Kupfer je Nut: mehr Wicklungsverlust bei "
                        "gleichem Strom.",
                        "conductorsPerSlot", best)
            tiefe = float(g.get("slotDepth") or 0.0)
            if tiefe > 0:
                kand = [round(tiefe + k, 1) for k in (4, 8, 12, 16)]
                best = _groesster_der_besteht(
                    payload, "slotDepth", kand,
                    lambda p: (G.pruefe_leiterquerschnitt(p)["ok"]
                               and G.pruefe_nuttiefe(p)["ok"]))
                if best:
                    _anbieten(
                        wege, payload,
                        lambda q: (G.pruefe_leiterquerschnitt(q)["ok"]
                                   and G.pruefe_nuttiefe(q)["ok"]),
                        f"Nut auf {best:.1f} mm vertiefen statt {tiefe:.1f} mm",
                        "Tiefere Nut heisst duenneres Rueckenjoch — das "
                        "Nuttiefen-Tor wurde dabei mitgeprueft.",
                        "slotDepth", best)

        elif name == "nuttiefe":
            tiefe = float(g.get("slotDepth") or 0.0)
            wand = float(b.get("statorwand_mm") or 0.0)
            deckel = float(b.get("deckel_mm") or 0.0)
            # Der Deckel muss selbst sinnvoll sein. An einer entarteten
            # Geometrie (Bohrung groesser als der Aussendurchmesser) wird die
            # Statorwand NEGATIV, und „Nuttiefe auf 1,0 mm" waere ein Knopf,
            # der nichts heilt -- dort ist nicht die Nut das Problem.
            if deckel > 0.5 and wand > 0.0:
                neu = round(min(deckel, max(tiefe - 1.0, 1.0)), 1)
                _anbieten(
                    wege, payload,
                    lambda q: G.pruefe_nuttiefe(q)["ok"],
                    f"Nuttiefe auf {neu:.1f} mm — {wand:.1f} mm Statorwand "
                    f"lassen hoechstens {deckel:.1f} mm zu",
                    "Flachere Nut: weniger Kupferquerschnitt, also mehr "
                    "Wicklungsverlust.",
                    "slotDepth", neu)

    if erg.get("verletzt"):
        hinweise.append(
            "Wer eine dieser Grenzen ausdruecklich will, setzt die zugehoerige "
            "Freigabe (z. B. geom.luftspaltFreigabe = true) — dann steht die "
            "Ueberschreitung als Warnung im Protokoll, statt unbemerkt "
            "durchzugehen.")
    return wege, hinweise


def _wege_maschinenart(payload, text):
    """Eine Art, die die Stufe nicht traegt -- was statt dessen geht."""
    import ema_maschinenart as MA
    hinweise = []
    try:
        art = MA.hole(MA.art_code(_geom(payload)))
    except Exception:                                        # noqa: BLE001
        return [], hinweise
    hinweise.append(
        f"{art.label} traegt heute: {', '.join(art.stufen)}.")
    # Die Reihenfolge ist nicht beliebig: "keiner" ist auch "nicht fdm", und
    # umgekehrt gepruefte Bedingungen machten den zweiten Zweig unerreichbar --
    # herausgekommen ist der Satz „die Feldstufe laeuft ueber keiner".
    if art.feldweg == "keiner":
        hinweise.append(
            "Fuer diese Art gibt es ueberhaupt keine Feldstufe: ihre "
            "Durchflutung ist zeitabhaengig (Kaefig, kommutierter Anker) und "
            "in einem magnetostatischen Loeser nicht darstellbar. Ein "
            "begruendetes Nein ist hier das Ergebnis, kein fehlendes Stueck.")
    elif art.feldweg and art.feldweg != "fdm":
        hinweise.append(
            "Die Feldstufe dieser Art laeuft ueber "
            + MA.FELDWEG_WERKZEUG.get(art.feldweg, art.feldweg)
            + " — nicht ueber die Pipeline. Das ist kein Mangel, sondern ein "
              "anderer Loeser: derselbe Knopf wuerde die falsche Physik "
              "rechnen.")
    return [], hinweise


def _wege_layout(payload):
    """Ein ungueltiges Rotor-Layout -- ueber die vorhandene Entlastung."""
    try:
        import ema_rotorcheck as RC
        ent = RC.entlastung(_geom(payload))
    except Exception:                                        # noqa: BLE001
        return [], []
    wege = []
    for w in (ent or {}).get("wege", []) if isinstance(ent, dict) else (ent or []):
        if isinstance(w, dict) and w.get("text"):
            wege.append(_weg(w["text"], w.get("preis", ""),
                             w.get("schluessel", ""), w.get("wert"),
                             w.get("ebene", "geom"),
                             w.get("aenderungen")))
    return wege, []




def _wege_laeufer(payload, text):
    """Die Tore der Laeufer-BAUART: Schenkelpol, Polbefestigung, Daempferkaefig.

    Sie fehlten hier bis zum 03.10.2026 vollstaendig -- „Schenkelpol", „Spule"
    und „Erreger" kamen in diesem Modul null mal vor --, und weil
    ``_gate_laeufer`` ausserdem ein nacktes ``RuntimeError`` warf, landete eine
    abgewiesene fremderregte Maschine im ``else``-Zweig: Titel „Der Lauf ist
    abgebrochen", kein Weg, ein Traceback.

    Gerechnet wird hier nichts. Jedes Tor bringt seine eigene Entlastung mit
    (``ema_eesm_cad.entlastung``, ``ema_schenkelpol.entlastung``) -- dieselbe
    Aufteilung wie bei ``ema_rotorcheck.entlastung``, damit die Wege dort
    entstehen, wo auch die Grenze gerechnet wird, und nicht ein zweites Mal
    daneben.
    """
    g   = _geom(payload)
    ax  = float((payload or {}).get("axial_len") or 80.0)
    rpm = float((payload or {}).get("rpm_to")
                or (payload or {}).get("rpm_from") or 0.0)

    # BEIDE Quellen, immer. Vorher entschied der Text, welche gefragt wird --
    # und dann sah man beim Daempfer-Tor nicht, dass der Laeufer daneben in
    # Einzelarme zerfaellt. Ein Tor haelt den Lauf an; was sonst noch offen
    # ist, bleibt trotzdem offen und gehoert in dieselbe Liste.
    quellen = []
    will_pol = will_bef = True
    if will_pol:
        try:
            import ema_eesm_cad as _EC
            quellen.append(_EC.entlastung(g, ax))
        except Exception:                                    # noqa: BLE001
            pass
    if will_bef:
        try:
            import ema_schenkelpol as _SP
            quellen.append(_SP.entlastung(g, ax, rpm))
        except Exception:                                    # noqa: BLE001
            pass

    wege, hinweise = [], []
    for q in quellen:
        for w in (q.get("wege") or []):
            if w.get("text"):
                wege.append(_weg(w["text"], w.get("preis", ""),
                                 w.get("schluessel", ""), w.get("wert"),
                                 w.get("ebene", "geom"),
                                 w.get("aenderungen")))
        hinweise += [h for h in (q.get("hinweise") or []) if h]
        kombi = q.get("kombi") or {}
        if kombi:
            hinweise.append(
                "Gemeinsam heilt es: "
                + ", ".join(f"{a} = {b:g}" for a, b in sorted(kombi.items()))
                + ". Einzeln wirkt keine dieser Aenderungen, deshalb steht "
                  "dafuer kein Knopf da.")
    return wege, hinweise

# ── Die eine Stelle ──────────────────────────────────────────────────────────

def diagnose(exc, payload=None, log=None) -> dict:
    """Was ist schiefgegangen, warum, und was hilft.

    ``exc``     die Ausnahme (oder ihr Text).
    ``payload`` der Payload des Laufs -- er traegt die Zahlen, aus denen sich
                ein Vorschlag rechnen laesst.
    ``log``     das Protokoll; seine letzte Stufe sagt, WO es passiert ist.
    """
    text = str(exc)
    typ = type(exc).__name__ if isinstance(exc, BaseException) else "Fehler"
    erg = {"tor": "", "titel": "", "befund": text, "wege": [],
           "befunde": list(getattr(exc, "befunde", []) or []),
           "hinweise": list(getattr(exc, "hinweise", []) or []),
           "chat": "", "typ": typ}

    # 1. Ein Tor, das seine Auswege schon mitbringt (Fliehkraft).
    wege = list(getattr(exc, "wege", []) or [])
    _ist_laeufer = (getattr(exc, "tor", "") == "laeufer"
                    or "Laeufertor" in text or "Polbefestigung" in text
                    or "Daempferkaefig" in text)
    if wege and not _ist_laeufer:
        erg.update(tor=getattr(exc, "tor", "") or "fliehkraft",
                   titel="Ein Auslegungstor hat gehalten",
                   befund=getattr(exc, "befund", "") or text, wege=wege)
        erg["hinweise"].append(VORSCHAU_SATZ)

    elif typ == "GrenzeVerletzt":
        w, h = _wege_grenzen(payload)
        erg.update(tor="grenzen",
                   titel="Eine Grenze, die immer gilt, ist verletzt",
                   wege=w)
        erg["hinweise"] = h + [VORSCHAU_SATZ]

    elif typ == "ArtNichtUnterstuetzt":
        w, h = _wege_maschinenart(payload, text)
        erg.update(tor="maschinenart",
                   titel="Diese Maschinenart traegt diese Stufe nicht",
                   wege=w)
        erg["hinweise"] = h

    elif _ist_laeufer:
        w, h = _wege_laeufer(payload, text)
        erg.update(tor="laeufer",
                   titel="Das Tor der Laeufer-Bauart hat gehalten",
                   befund=getattr(exc, "befund", "") or text, wege=w)
        # Die Ausnahme bringt ihre Hinweise mit, und `_wege_laeufer` rechnet
        # dieselben noch einmal aus -- ohne diese Entdopplung steht jeder
        # Satz zweimal im Kasten (gemeldet am 04.10.2026).
        _h, _gesehen = [], set()
        for x in list(erg["hinweise"]) + list(h) + [VORSCHAU_SATZ]:
            if x and x not in _gesehen:
                _gesehen.add(x); _h.append(x)
        erg["hinweise"] = _h

    elif typ in ("LayoutUngueltig", "AuslegungReisst"):
        w, _h = _wege_layout(payload)
        erg.update(tor="layout", titel="Die Zeichnung des Laeufers ist ungueltig",
                   wege=w)
        erg["hinweise"].append(VORSCHAU_SATZ)

    elif typ == "_DegenerateMeshError" or "entartete" in text.lower():
        erg.update(tor="netz", titel="Das 3-D-Netz entartet")
        erg["hinweise"].append(
            "Die Zellgroessen sind an der Geometrie gedeckelt (s. `_cl_decke`), "
            "aber das Knoten-Ziel kann trotzdem unerreichbar sein. Ein "
            "HOEHERES Knoten-Ziel hilft hier haeufiger als ein niedrigeres: "
            "das Netz scheitert an zu GROSSEN Zellen, nicht an zu kleinen.")

    elif "freecad" in text.lower() or "CAD_" in text:
        erg.update(tor="cad", titel="Der Geometriebau in FreeCAD ist gescheitert")
        erg["hinweise"].append(
            "Das Protokoll unter dieser Meldung traegt die Ausgabe des "
            "FreeCAD-Unterprozesses — dort steht die eigentliche Ursache.")

    else:
        erg.update(titel=f"Der Lauf ist abgebrochen ({typ})")
        stufe = _letzte_stufe(log)
        if stufe:
            erg["hinweise"].append(f"Zuletzt lief: {stufe}")

    erg["chat"] = _chat_frage(erg, payload)
    erg["wege"] = erg["wege"][:MAX_WEGE]
    return erg


def _letzte_stufe(log) -> str:
    """Die letzte Protokollzeile, die eine STUFE benennt (nicht den Traceback)."""
    for z in reversed(list(log or [])):
        t = str(z).strip()
        if not t or t.startswith("FATAL") or t.startswith("  "):
            continue
        return t[:160]
    return ""


def _chat_frage(erg, payload) -> str:
    """Eine fertige Frage fuer den Chat -- mit dem Kontext, den er braucht.

    Der Chat erdet auf dem Steckbrief des gebundenen Projekts und kann
    nachschlagen; was ihm fehlt, ist der FEHLSCHLAG. Ohne ihn fragt der Mensch
    „warum geht das nicht" und der Chat raet.
    """
    g = _geom(payload)
    masse = ", ".join(
        f"{k}={g[k]}" for k in ("machineType", "p", "slots", "statorOD",
                                "statorID", "rotorOD", "shaftD",
                                "conductorsPerSlot", "slotDepth")
        if k in g)
    return (f"Der Lauf ist abgebrochen: {erg['titel']}.\n"
            f"Befund: {erg['befund']}\n"
            f"Geometrie: {masse}\n\n"
            f"Erklaere mir, was diese Grenze bedeutet und welcher der Wege sie "
            f"am wenigsten teuer aufloest. Nenne die Herkunft jeder Zahl und "
            f"erfinde keine.")
