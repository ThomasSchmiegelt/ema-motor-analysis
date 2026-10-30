"""Entscheiden zwischen gerechneten Entwürfen -- deterministisch, mit Begründung.

Warum es das Modul gibt
-----------------------

PI mit einem lokalen Modell bewertet nicht verlässlich: dieselbe Frage nach
zwei Entwürfen bekommt je nach Formulierung verschiedene Siegerinnen, und das
Modell begründet beide überzeugend. Hier steht die Regel, nach der es sich
stattdessen richtet. Das Urteil kommt aus drei Schritten, und an keinem ist
ein Sprachmodell beteiligt:

1. **Tore.** (Die Sättigung zählt ab ``SAETTIGUNG_ABWEISEN`` als Tor: darüber sind
   Moment und Leistung zu optimistisch, also der Kennwert selbst.) Jeder Entwurf geht durch ``ema_sicherheit.pruefen`` (Festigkeit,
   Magnetbruch, Steg, Drehzahl, Temperaturen, Sättigung, Entmagnetisierung,
   Rastmoment) und -- wenn möglich -- durch ``ema_magnetschluss.messen``. Ein
   verletztes Tor weist den Entwurf ab; ein ``hinweis`` tut es nicht, steht
   aber in der Zeile. Kein Tor wird hier erfunden oder verschoben: die
   Schwellen stehen in ihren eigenen Modulen.
2. **Ziel.** Unter den Bestandenen entscheidet EIN benanntes Ziel
   (``ZIELE``). Die Wahl des Ziels ist Sache des Menschen und gehört in
   ``AUFTRAG.md``; das Modul wählt sie nicht.
3. **Abstand.** Liegt der Beste weniger als ``KNAPP_PROZENT`` vor dem
   Zweiten, ist der Befund „kein klarer Sieger" -- die Kennzahlen kommen aus
   Rechnungen mit Modellunsicherheit, und eine Rangfolge unterhalb davon ist
   Zufall mit Begründung.

**Ein begründetes Nein ist ein Ergebnis**: besteht kein Entwurf, ist
``gewinner`` leer und ``bindend`` nennt das Tor, an dem die meisten scheitern.
Ein Entwurf ohne Rechnung (kein ``results.json``) wird nicht abgewiesen,
sondern als „nicht entscheidbar" geführt -- er hat das Tor nie gesehen.
"""
from __future__ import annotations

import collections
import json
import os

import ema_sicherheit

#: Abstand des Besten zum Zweiten, unter dem kein Sieger genannt wird.
KNAPP_PROZENT = 5.0

#: Sättigung: ``ema_sicherheit`` führt sie als Hinweis, weil sie nichts bricht -- sie macht
#: Kt, Moment und Leistung des Modells zu OPTIMISTISCH. Ab dieser Ausnutzung (B / B_sat) ist
#: der Kennwert, nach dem entschieden wird, nicht mehr belastbar; dann weist die Entscheidung
#: ab. Darunter bleibt es ein Hinweis (Flusserhaltung ist eine Abschätzung, kein Gitter).
SAETTIGUNG_ABWEISEN = 1.15

#: Ziele: (Schluessel in summary oder Rechnung, Richtung, Beschreibung).
ZIELE = {
    "leistungsdichte": ("P_je_kg", "max", "Spitzenleistung je kg Gesamtmasse (P_max_kW / mass_g)"),
    "moment":          ("T_peak_max_Nm", "max", "Spitzenmoment"),
    "leicht":          ("mass_g", "min", "geringste Gesamtmasse (Stellvertreter fuer Kosten: keine Preise im Lauf)"),
}


def _lesen(pfad: str) -> dict:
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _kennwert(ziel: str, s: dict):
    if ziel == "leistungsdichte":
        p, m = s.get("P_max_kW"), s.get("mass_g")
        return round(p / (m / 1000.0), 3) if isinstance(p, (int, float)) and isinstance(m, (int, float)) and m > 0 else None
    wert = s.get(ZIELE[ziel][0])
    return wert if isinstance(wert, (int, float)) else None


def bewerten(ordner: str, ziel: str, mit_magnetschluss: bool = True) -> dict:
    """Ein Entwurf: Tore, Kennwert. Liefert immer eine Zeile, auch bei Fehlern."""
    name = os.path.basename(os.path.normpath(ordner))
    r, m = _lesen(os.path.join(ordner, "results.json")), _lesen(os.path.join(ordner, "meta.json"))
    if not r:
        return {"projekt": name, "status": "nicht_entscheidbar",
                "grund": "keine results.json -- der Entwurf wurde nie gerechnet"}
    befund = ema_sicherheit.pruefen(r, m)
    def _ueber_saettigung(k):
        w, g = k.get("wert"), k.get("grenze")
        return (k.get("name") == "saettigung" and isinstance(w, (int, float))
                and isinstance(g, (int, float)) and g > 0 and w / g > SAETTIGUNG_ABWEISEN)

    offen = [k for k in befund["kriterien"] if not k.get("ok")]
    harte = [k for k in offen if k.get("schwere") != "hinweis" or _ueber_saettigung(k)]
    hinweise = [k for k in offen if k not in harte]
    abweisung = [{"tor": k["name"], "text": str(k.get("text", ""))[:160]} for k in harte]
    notiz: list[str] = [f"{k['name']}: {str(k.get('text', ''))[:90]}" for k in hinweise]

    if mit_magnetschluss:
        geom = (m.get("payload") or {}).get("geom") or {}
        if geom:
            try:
                import ema_magnetschluss as MS
                ms = MS.messen_stabil(geom)
                if ms.get("ok"):
                    if ms["stufe"] == "kurzschluss":
                        abweisung.append({"tor": "magnetschluss", "text": ms["grund"]})
                    elif ms["stufe"] in ("auffaellig", "unsicher"):
                        notiz.append(f"magnetschluss ({ms['stufe']}): {ms['grund']}")
                else:
                    # Layout ungueltig oder keine Magnete: kein Messwert. Ein ungueltiges
                    # Layout weist das Sicherheitstor ohnehin ab; hier nur vermerken.
                    notiz.append(f"magnetschluss nicht gemessen: {ms.get('grund', '')[:120]}")
            except Exception as e:                                # noqa: BLE001
                notiz.append(f"magnetschluss nicht gemessen: {type(e).__name__}")

    s = r.get("summary") or {}
    wert = _kennwert(ziel, s)
    zeile = {"projekt": name, "status": "abgewiesen" if abweisung else "bestanden",
             "abweisungen": abweisung, "hinweise": notiz, "kennwert": wert}
    if not abweisung and wert is None:
        zeile["status"] = "nicht_entscheidbar"
        zeile["grund"] = f"Zielgroesse '{ZIELE[ziel][0]}' fehlt im Ergebnis"
    return zeile


def entscheide(ordner: list[str], ziel: str = "leistungsdichte",
               mit_magnetschluss: bool = True) -> dict:
    if ziel not in ZIELE:
        raise ValueError(f"Ziel '{ziel}' unbekannt; moeglich: {', '.join(ZIELE)}")
    zeilen = [bewerten(o, ziel, mit_magnetschluss) for o in ordner]
    gut = [z for z in zeilen if z["status"] == "bestanden"]
    richtung = ZIELE[ziel][1]
    gut.sort(key=lambda z: z["kennwert"], reverse=(richtung == "max"))
    for i, z in enumerate(gut, 1):
        z["rang"] = i

    out = {"ziel": ziel, "ziel_text": ZIELE[ziel][2], "zeilen": zeilen,
           "gewinner": None, "klar": False, "bindend": None}
    if not gut:
        zaehler = collections.Counter(a["tor"] for z in zeilen for a in z.get("abweisungen", []))
        if zaehler:
            tor, n = zaehler.most_common(1)[0]
            out["bindend"] = tor
            out["urteil"] = (f"Kein Entwurf besteht. Am haeufigsten bindet '{tor}' "
                             f"({n} von {len(zeilen)}). Das ist das Ergebnis: dort ansetzen, "
                             "nicht den am wenigsten schlechten waehlen.")
        else:
            out["urteil"] = "Nichts entscheidbar: keiner der Entwuerfe ist gerechnet."
        return out

    erster = gut[0]
    out["gewinner"] = erster["projekt"]
    if len(gut) == 1:
        out["klar"] = True
        out["urteil"] = (f"{erster['projekt']} besteht als einziger alle Tore "
                         f"({ZIELE[ziel][0]} = {erster['kennwert']}).")
        return out
    zweiter = gut[1]
    ref = abs(erster["kennwert"]) or 1.0
    abstand = abs(erster["kennwert"] - zweiter["kennwert"]) / ref * 100.0
    out["abstand_prozent"] = round(abstand, 2)
    if abstand < KNAPP_PROZENT:
        out["klar"] = False
        out["urteil"] = (f"Kein klarer Sieger: {erster['projekt']} liegt nur {abstand:.1f} % vor "
                         f"{zweiter['projekt']} (Schwelle {KNAPP_PROZENT:.0f} %) -- unterhalb der "
                         "Modellunsicherheit. Entscheiden nach einem zweiten Ziel oder genauer rechnen.")
    else:
        out["klar"] = True
        out["urteil"] = (f"{erster['projekt']} gewinnt nach '{ziel}' mit {abstand:.1f} % Vorsprung "
                         f"vor {zweiter['projekt']}; {len(zeilen) - len(gut)} abgewiesen oder offen.")
    return out


def als_text(e: dict) -> str:
    z = [f"Entscheidung nach „{e['ziel']}“ — {e['ziel_text']}", f"  {e['urteil']}"]
    for r in e["zeilen"]:
        kopf = f"  {r.get('rang', '–')}. {r['projekt']}  [{r['status']}]"
        if r.get("kennwert") is not None:
            kopf += f"  {r['kennwert']}"
        z.append(kopf)
        for a in r.get("abweisungen", []):
            z.append(f"       ✗ {a['tor']}: {a['text']}")
        if r.get("grund"):
            z.append(f"       ? {r['grund']}")
        for h in r.get("hinweise", [])[:3]:
            z.append(f"       · {h}")
    return "\n".join(z)
