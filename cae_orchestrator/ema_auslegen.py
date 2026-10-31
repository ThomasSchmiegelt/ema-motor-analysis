"""Phase 1 der Auslegung ohne Sprachmodell: Tore, Magnetschluss, ein Lauf, ein Urteil.

Anlass (31.10.2026, ``protokoll/ereignisprotokoll.md`` E-55 ff.): PI scheiterte in
den Rechenlaeufen nicht an der Entscheidungsguete, sondern am VORGEHEN -- 46
handgesetzte ``magnetschluss``-Aufrufe, Grundgeometrie verstellt statt der
Magnetparameter, kein einziger Lauf. Die Schritte dazwischen sind keine
Ermessensfragen; jeder hat ein Werkzeug, das ihn deterministisch beantwortet.
Dieses Modul fuehrt sie in fester Reihenfolge und haelt an, sobald eine Frage
kommt, die eine AUSLEGUNGSENTSCHEIDUNG ist:

  1. Tore vorab (Grenzen, Layout, Fliehkraft). Ein gerissenes Layout wird
     GEHEILT (``ema_magnetheilung``: kleinste Aenderung an Magnetparametern);
     ein gerissenes Fliehkrafttor nur dann selbst entlastet, wenn der Weg den
     Auftrag nicht aendert -- das ist allein das Rotorblech. Drehzahl,
     Aussen- und Wellendurchmesser sind Vorgaben des Menschen: sie werden
     genannt, nicht gewaehlt.
  2. Magnetschluss am Ist-Stand messen; nur wenn er nicht ``ok`` ist,
     ``magnetsuche`` -- und die fasst ausschliesslich Magnetparameter an.
  3. Ein Entwurfslauf (``run analyse --guete entwurf``) in ein eigenes Projekt.
  4. ``entscheide`` an diesem Projekt: besteht es die Tore, und welches bindet.

Was es NICHT tut, und das steht auch im Ergebnis: Kosten optimieren (der
schnelle Bewerter kennt keinen Kostenwert) und nach einem gerissenen Tor im
Lauf selbst nachbessern -- die Abbildung „Tor -> freier Parameter" ist noch
nicht belegt, und eine geratene waere genau das Handsuchen, das hier ersetzt
werden soll.

Der Lauf selbst wird als Funktion hereingereicht (``lauf``): er spricht HTTP mit
dem Server, alles andere hier ist oertlich und ohne Netz pruefbar.
"""

from __future__ import annotations

import copy
import os

# Ein Fliehkraftweg, der den Auftrag nicht aendert. Alles andere ist eine
# Vorgabe (Drehzahl, Bauraum, Welle) und wird nur genannt.
SELBST_WAEHLBAR = {"rotor_lam"}


def _schritt(protokoll: list, name: str, ok, text: str, **mehr) -> dict:
    s = {"schritt": name, "ok": ok, "text": text, **mehr}
    protokoll.append(s)
    return s


def _setze(payload: dict, schluessel: str, wert, ebene: str = "geom") -> None:
    if ebene == "geom":
        payload.setdefault("geom", {})[schluessel] = wert
    else:
        payload[schluessel] = wert


def tore(payload: dict) -> dict:
    """Die drei Stufe-0-Tore der Pipeline, dieselben Funktionen, keine Abschrift."""
    import ema_grenzen
    import ema_pipeline as PL
    from ema_rotorcheck import rotor_layout_check
    geom = payload.get("geom") or {}
    gr = ema_grenzen.pruefe(payload)
    lay = rotor_layout_check(geom)
    axial = lay.get("flussweg") == "axial"
    st = {"log": [], "progress": 0}
    flieh = {"ok": True, "wege": [], "grund": ""}
    try:
        PL._gate_rotor_stress(payload, st)
    except PL.AuslegungReisst as e:
        flieh = {"ok": False, "grund": str(e), "wege": getattr(e, "wege", []) or []}
    return {"grenzen": gr, "layout": lay, "layout_ok": axial or bool(lay.get("ok")),
            "axial": axial, "fliehkraft": flieh}


def _tore_heilen(payload: dict, protokoll: list, log) -> bool:
    """Tore vorab, mit Heilung des Layouts und dem einen selbst waehlbaren
    Fliehkraftweg. ``False`` = angehalten, der Grund steht im Protokoll."""
    import ema_magnetheilung
    t = tore(payload)
    if not t["grenzen"]["ok"]:
        verletzt = [b.get("text", b.get("name")) for b in t["grenzen"].get("befunde", [])
                    if not b.get("ok")]
        _schritt(protokoll, "grenzen", False,
                 "Grenze verletzt: " + "; ".join(verletzt)
                 + " -- das sind Hauptmasse, die der Auftrag vorgibt; nicht selbst geaendert.")
        return False
    _schritt(protokoll, "grenzen", True, "Luftspalt, Wickelkopf, Nuttiefe, Leiter innerhalb der Grenzen")
    if not t["layout_ok"]:
        h = ema_magnetheilung.heile(payload["geom"])
        if not h.get("set"):
            _schritt(protokoll, "layout", False,
                     "Layout ungueltig, keine Heilung ueber Magnetparameter: "
                     + "; ".join(t["layout"].get("fatal") or []) + f" ({h.get('hinweis', '')})")
            return False
        for k, (alt, neu) in h["aenderung"].items():
            payload["geom"][k] = neu
        _schritt(protokoll, "layout", True, "Layout geheilt: " + " ".join(f"--set {s}" for s in h["set"]),
                 set=list(h["set"]))
        log("  Layout geheilt: " + " ".join(h["set"]))
        t = tore(payload)
        if not t["layout_ok"]:
            _schritt(protokoll, "layout", False, "Nach der Heilung weiter ungueltig: "
                     + "; ".join(t["layout"].get("fatal") or []))
            return False
    else:
        _schritt(protokoll, "layout", True, "Layout gueltig" + (" (Axialfluss: nicht zustaendig)" if t["axial"] else ""))

    if not t["fliehkraft"]["ok"]:
        wege = t["fliehkraft"]["wege"]
        eigen = [w for w in wege if w.get("schluessel") in SELBST_WAEHLBAR]
        if eigen:
            w = eigen[0]
            _setze(payload, w["schluessel"], w["wert"], w.get("ebene") or "payload")
            t = tore(payload)
            if t["fliehkraft"]["ok"]:
                _schritt(protokoll, "fliehkraft", True,
                         f"Fliehkraft entlastet: --set {w['schluessel']}={w['wert']} ({w.get('preis', '')})",
                         set=[f"{w['schluessel']}={w['wert']}"])
                log(f"  Fliehkraft entlastet: {w['schluessel']}={w['wert']}")
                return True
        andere = [f"{w['schluessel']}={w['wert']} ({w.get('preis', '')})"
                  for w in wege if w.get("schluessel") and w.get("schluessel") not in SELBST_WAEHLBAR]
        _schritt(protokoll, "fliehkraft", False,
                 t["fliehkraft"]["grund"].split("\n")[0]
                 + (" -- moegliche Wege, die den Auftrag aendern (Entscheidung des Menschen): "
                    + "; ".join(andere) if andere else ""), wege=wege)
        return False
    _schritt(protokoll, "fliehkraft", True, "Fliehkraft an der Bohrung besteht")
    return True


def _magnetschluss(payload: dict, protokoll: list, log, *, suche_kw: dict) -> bool:
    """Ist-Stand messen; nur bei Bedarf suchen. ``False`` = angehalten."""
    import ema_maschinenart as MA
    import ema_magnetschluss as MS
    geom = payload["geom"]
    if MA.art_code(geom) != "pmsm" or geom.get("magShape") in ("custom", "spm", "halbach"):
        _schritt(protokoll, "magnetschluss", None,
                 f"nicht zustaendig fuer {MA.art_code(geom)}/{geom.get('magShape')} -- uebersprungen")
        return True
    log("  Magnetschluss am Ist-Stand messen …")
    m = MS.urteil(geom, mit_bild=False)
    if not m.get("ok"):
        _schritt(protokoll, "magnetschluss", None, f"nicht messbar: {m.get('grund')} -- uebersprungen")
        return True
    if m["stufe"] == "ok":
        _schritt(protokoll, "magnetschluss", True,
                 f"Ist-Stand ok (Streuanteil {m['streuanteil']:.0%}) -- keine Suche noetig")
        return True
    log(f"  Ist-Stand {m['stufe']} ({m['streuanteil']:.0%}) -- Magnetsuche …")
    import ema_magnetsuche as MSU
    r = MSU.suche(geom, None, log=lambda t: log("    " + t), **suche_kw)
    b = r.get("beste")
    if not r.get("ok") or not b or b.get("stufe") != "ok":
        _schritt(protokoll, "magnetsuche", False,
                 f"Ist-Stand {m['stufe']} ({m['streuanteil']:.0%}), und die Suche fand keine Anordnung "
                 f"mit Stufe ok" + (f" (beste: {b['stufe']}, {(b.get('streu') or 0):.0%})" if b else "")
                 + " -- Bauform oder Polzahl sind eine Auslegungsentscheidung.")
        return False
    for k, v in b["set"].items():
        geom[k] = v
    sets = [f"{k}={v}" for k, v in b["set"].items()]
    _schritt(protokoll, "magnetsuche", True,
             f"Ist-Stand {m['stufe']} ({m['streuanteil']:.0%}) -> Stufe ok, B_gap {b.get('B_gap_T')} T: "
             + " ".join(f"--set {s}" for s in sets), set=sets)
    # Die Suche filtert am Layouttor, nicht an der Fliehkraft: nachpruefen.
    t = tore(payload)
    if not (t["layout_ok"] and t["fliehkraft"]["ok"]):
        _schritt(protokoll, "tore_nach_suche", False,
                 "Die gefundene Anordnung reisst ein Tor: "
                 + (t["fliehkraft"]["grund"].split("\n")[0] if not t["fliehkraft"]["ok"]
                    else "; ".join(t["layout"].get("fatal") or [])))
        return False
    return True


def auslegen(payload: dict, *, ziel: str = "leistungsdichte", guete: str = "entwurf",
             lauf=None, suche_kw: dict | None = None, log=print) -> dict:
    """Phase 1. ``lauf(payload) -> (projekt_ordner | None, fehlertext)``; ``None``
    heisst: nur die oertlichen Schritte, kein Rechenlauf.

    Liefert ``{"ok", "angehalten_bei", "schritte", "payload", "projekt",
    "entscheidung", "nicht_getan"}``. ``ok`` heisst: der Entwurf hat gerechnet und
    besteht die Tore von ``entscheide``."""
    import ema_entscheidung as EE
    import ema_text2ema as T2E
    if ziel not in EE.ZIELE:
        raise ValueError(f"Ziel '{ziel}' unbekannt; moeglich: {', '.join(EE.ZIELE)}")
    p = copy.deepcopy(payload)
    if not p.get("geom"):
        raise ValueError("Keine Geometrie im Payload.")
    prot: list = []
    out = {"ok": False, "angehalten_bei": None, "schritte": prot, "payload": p,
           "projekt": None, "entscheidung": None, "ziel": ziel,
           "nicht_getan": ["Kostenoptimierung (der schnelle Bewerter kennt keinen Kostenwert)",
                           "Nachbessern nach einem im Lauf gerissenen Tor (Abbildung Tor -> Parameter nicht belegt)"]}

    def _halt():
        out["angehalten_bei"] = prot[-1]["schritt"] if prot else None
        return out

    log("1/4 Tore vorab")
    if not _tore_heilen(p, prot, log):
        return _halt()
    log("2/4 Magnetschluss")
    if not _magnetschluss(p, prot, log, suche_kw=suche_kw or {}):
        return _halt()
    if lauf is None:
        _schritt(prot, "lauf", None, "kein Rechenlauf verlangt (--ohne-lauf) -- Tore und Magnetschluss bestanden")
        out["ok"] = None
        return out
    log(f"3/4 Entwurfslauf (Guete {guete})")
    T2E.guete_anwenden(p, guete)
    ordner, fehler = lauf(p)
    if not ordner:
        _schritt(prot, "lauf", False, f"Lauf gescheitert: {fehler}")
        return _halt()
    out["projekt"] = os.path.basename(os.path.normpath(ordner))
    _schritt(prot, "lauf", True, f"gerechnet in {out['projekt']}")
    log("4/4 Entscheiden")
    e = EE.entscheide([ordner], ziel)
    out["entscheidung"] = e
    if e["gewinner"] is None:
        _schritt(prot, "entscheide", False, "besteht die Tore nicht: " + (e.get("urteil") or ""),
                 bindend=e.get("bindend"))
        return _halt()
    _schritt(prot, "entscheide", True, e.get("urteil") or "besteht die Tore")
    out["ok"] = True
    return out


def als_text(e: dict) -> str:
    zeichen = {True: "✓", False: "✗", None: "·"}
    z = [f"AUSLEGEN (Phase 1, ohne Sprachmodell) — Ziel {e['ziel']}"]
    for s in e["schritte"]:
        z.append(f"  {zeichen[s['ok']]} {s['schritt']:<15} {s['text']}")
    if e["ok"] is True:
        z.append(f"  Ergebnis: {e['projekt']} besteht die Tore.")
    elif e["ok"] is None:
        z.append("  Ergebnis: vorbereitet, nicht gerechnet.")
    else:
        z.append(f"  Ergebnis: angehalten bei '{e['angehalten_bei']}'. Ein begruendetes Nein ist ein Ergebnis.")
    gesetzt = [x for s in e["schritte"] for x in s.get("set", [])]
    if gesetzt:
        z.append("  Geaendert: " + " ".join(f"--set {x}" for x in gesetzt))
    z.append("  Nicht getan: " + "; ".join(e["nicht_getan"]))
    return "\n".join(z)
