"""Erfahrungsdatenbank: Symptom -> Hebel, fuer die konkrete Geometrie NACHGERECHNET.

Anlass (31.10.2026): „wenn nicht genug Metall zwischen Hairpins und
Aussendurchmesser ist, geht er schnell in die Saettigung -- das sollte kein Tor
sein, sondern eine Erfahrung." Und: „wenn ich den Aussendurchmesser nicht erhoehen
kann, muss ich den Rotordurchmesser kleiner machen." Zwei Saetze, zwei Anforderungen:

* Eine Erfahrung ist **kein Tor**. Sie haelt nichts an und geht in keinen
  Exit-Code ein; sie sagt, was vermutlich hilft und was es kostet.
* Erfahrungen muessen **gegeneinander gewichtet** werden, und zwar an DIESER
  Maschine. Gemessen am frischen Payload mit 9 mm Restjoch: Rotor 188,6 -> 175 mm
  senkt B_joch von 2,31 auf 1,31 T, hebt aber den Zahn von 1,31 auf 1,41 T; der
  Lehrbuchhebel „mehr Pole, weniger Fluss je Pol" bringt das Joch nur auf 2,04 T und
  treibt den Zahn auf 1,93 T. Eine hingeschriebene Faustregel haette Letzteres als
  Abhilfe empfohlen. Deshalb wird jeder Hebel durchgerechnet (kleinste Aenderung,
  die das Symptom behebt), und seine Nebenwirkungen stehen daneben.

Was hier steht und was nicht
----------------------------

Die ERFAHRUNGEN selbst (Ausloeser, Hebel, Preis) sind Wissen ueber die Physik und
liegen versioniert in diesem Modul. BELEGE und ZAEHLER (wie oft ein Hebel an einer
konkreten Maschine geholfen hat, wie oft er ein anderes Symptom ausgeloest hat)
sind Laufzeitdaten und liegen unter ``~/cae_projekte/_lernen/`` -- geschrieben von
``pruefe(..., merken=True)`` und vom Lernprogramm (``ema_lernprogramm``).

Der Agent bekommt davon nichts in den Kontext gelegt. Er denkt zuerst frei und
fragt dann gezielt: ``cae_cli.py erfahrung pruefe --from-project X``.

Rechenweg: die Flusserhaltung aus ``ema_saettigung.eisenwege`` (analytisch, ms).
Der Preis eines Hebels steht in drei Groessen, die nicht gegeneinander verrechnet
werden -- vier eigentlich: das **Spitzenmoment** an Strom- und Spannungsgrenze
(``moment_erreichbar``, mit Reluktanzanteil, danach wird geordnet), ``Kt`` (geschlossene Formel wie ``compute_performance``, aber UNgerundet),
Nuttiefe (Kupferquerschnitt) und Aussendurchmesser (Bauraum). Bis zum 31.10.2026
stand hier ein Momentmass ``B_gap * D_r^2 * L`` (gleicher Strombelag); das
Lernprogramm hat es widerlegt: bei festen Magneten bleibt der Fluss je Pol
erhalten, ``B_gap * D_r`` ist konstant (gemessen 188,6/175/165 mm: B_gap
0,630/0,679/0,719 T, Kt 0,04100/0,04099/0,04098). Das Momentmass meldete -4,7 %,
Kt bewegt sich um -0,05 %. Der wirkliche Preis eines kleineren Laeufers ist das
hoehere Luftspalt- und Zahnfeld -- es steht als ``nachher`` mit da, und wo der
Zahn darueber saettigt, ist der Hebel ein Konflikt. S. ``BEFUNDE.md``.

**Kombinationen** (``kombinationen``): Hebel A zur Haelfte, dann Hebel B so weit
wie noetig. Ob ein Paar billiger ist als der beste Einzelhebel, wird NICHT mit
einer Gewichtung entschieden, sondern nach Pareto ueber die drei Preise: ein Paar
zaehlt, wenn kein helfender Einzelhebel in allen dreien mindestens so gut ist.
Nur PSM (``maschinenart == pmsm``) im ersten Schritt.
"""

from __future__ import annotations

import json
import os
import time

BELEGE = os.path.expanduser("~/cae_projekte/_lernen/erfahrung_belege.jsonl")

# Ziel nach einer Abhilfe: deutlich unter dem Knie, nicht genau darauf.
ZIEL_AUSNUTZUNG = 0.95


# ── Messung ──────────────────────────────────────────────────────────────────

def _messen(geom: dict, axial_mm: float, blech: str = "m270_35a") -> dict:
    """Eisenwege und Kt (ungerundet) einer Geometrie."""
    import ema_analysis as A
    import ema_saettigung as S
    bg = A._analytical_Bgap(geom)
    bg = float(bg[0] if isinstance(bg, (tuple, list)) else bg)
    e = S.eisenwege(geom, axial_mm, bg, blech)
    bsat = float(e["B_sat_T"])
    return {"B_gap": round(bg, 4), "B_joch": e["B_joch_T"], "B_zahn": e["B_zahn_T"],
            "B_rotorjoch": e["B_rotorjoch_T"], "B_sat": bsat,
            "joch_mm": e["joch_hoehe_mm"], "zahn_mm": e["zahn_breite_mm"],
            "kt": _kt(geom, axial_mm, bg), "T_spitze": _spitzenmoment(geom, axial_mm, bg)}


def _kt(geom: dict, axial_mm: float, bg: float) -> float:
    """``Kt`` wie ``ema_analysis.compute_performance``, ohne Rundung und durch ``p^2`` geteilt.

    Ungerundet, weil gerundet die Hebel nicht zu unterscheiden sind. Durch ``p^2``,
    weil die Hausformel ``1,5 p^2 (2/pi) B A`` auf eine Windung je Nut normiert ist
    und ueber die Polzahl NICHT vergleichbar: die Bruecke zur physikalischen
    Flussverkettung ist ``ema_asm.k_norm = pi k_w N_ph / p^2``. Ohne den Faktor meldete
    „mehr Pole" +309 % Kt -- bei gleichen Magneten. Fuer Hebel bei fester Polzahl
    aendert der Faktor nichts. Wicklungsfaktor und Nutzahl bleiben aussen vor."""
    import math
    import ema_fluss
    a = ema_fluss.flaechen(geom, axial_mm)["a_fluss_m2"]
    return 1.5 * (2 / math.pi) * bg * a


def _spitzenmoment(geom: dict, axial_mm: float, bg: float):
    """Spitzenmoment an der Strom- und Spannungsgrenze bei 1000 1/min (Konstantmomentbereich),
    ueber ``ema_analysis.moment_erreichbar`` -- dieselbe Kennfeldrechnung wie die Leistungskurve,
    also MIT Reluktanzanteil. ``Kt`` allein ist nur das Magnetmoment, und gerade das bleibt
    beim kleineren Laeufer stehen (gemessen 188,6 -> 175 mm: Kt -0,02 %, Spitze -6,5 %)."""
    import ema_analysis as A
    try:
        perf = A.compute_performance(geom, bg, 1000.0, axial_mm)
        r = A.moment_erreichbar(geom, perf, axial_mm, 1000.0, 0.0, 1000.0, 1000.0)
        return r.get("T_moeglich_Nm")
    except Exception:                                  # noqa: BLE001 -- dann fehlt der Preis, nicht die Pruefung
        return None


def _preise(geom: dict, g1: dict, m0: dict, m1: dict) -> dict:
    """Die drei Preise einer Aenderung, in Prozent vom Ausgangsstand."""
    def pct(a, b):
        return round(100.0 * (float(b) / float(a) - 1.0), 2)
    sp = (pct(m0["T_spitze"], m1["T_spitze"])
          if m0.get("T_spitze") and m1.get("T_spitze") is not None else None)
    return {"moment_pct": sp, "kt_pct": pct(m0["kt"], m1["kt"]),
            "nuttiefe_pct": pct(geom["slotDepth"], g1["slotDepth"]),
            "aussen_pct": pct(geom["statorOD"], g1["statorOD"])}


def _symptome(m: dict) -> list:
    """Welche Saettigungssymptome eine Messung zeigt (fuer Konflikte)."""
    s = []
    for name, key in (("statorjoch_saettigt", "B_joch"), ("zahn_saettigt", "B_zahn"),
                      ("rotorjoch_saettigt", "B_rotorjoch")):
        if m.get(key) is not None and m[key] / m["B_sat"] > 1.0:   # None: Weg nicht bestimmbar
            s.append(name)
    return s


# ── Hebel: kleinste Aenderung, die das Symptom behebt ─────────────────────────

def _halbierung(geom, axial, schluessel, lo, hi, ok, mitziehen=None, schritte=24):
    """Kleinster Abstand vom Istwert, bei dem ``ok(messung)`` gilt (lo/hi in Suchrichtung)."""
    def bau(w):
        g = dict(geom)
        g[schluessel] = round(w, 2)
        if mitziehen:
            mitziehen(g, geom)
        return g
    if not ok(_messen(bau(hi), axial)):
        return None
    a, b = lo, hi                         # a: nicht ok (Istwert), b: ok
    for _ in range(schritte):
        mid = (a + b) / 2.0
        if ok(_messen(bau(mid), axial)):
            b = mid
        else:
            a = mid
    return bau(b)


def _hebel_rotor_kleiner(geom, axial, ok):
    """Rotor kleiner bei gleichem Luftspalt und gleich tiefer Nut: die Statorwand waechst."""
    import ema_text2ema as T2E
    spalt = (float(geom["statorID"]) - float(geom["rotorOD"])) / 2.0

    def zieh(g, _alt):
        g["statorID"] = round(float(g["rotorOD"]) + 2 * spalt, 2)
    lo = max(T2E.SCHEMA["rotorOD"]["lo"], float(geom["shaftD"]) + 30.0)
    return _halbierung(geom, axial, "rotorOD", float(geom["rotorOD"]), lo, ok, zieh)


def _hebel_nut_flacher(geom, axial, ok):
    return _halbierung(geom, axial, "slotDepth", float(geom["slotDepth"]), 5.0, ok)


def _hebel_stator_groesser(geom, axial, ok):
    import ema_text2ema as T2E
    return _halbierung(geom, axial, "statorOD", float(geom["statorOD"]),
                       float(T2E.SCHEMA["statorOD"]["hi"]), ok)


def _hebel_mehr_pole(geom, axial, ok):
    """Ganzzahlig: die naechsten zwei Polpaarzahlen. Kein Treffer ist auch eine Auskunft."""
    for dp in (1, 2):
        g = dict(geom)
        g["p"] = int(geom["p"]) + dp
        if ok(_messen(g, axial)):
            return g
    g = dict(geom)
    g["p"] = int(geom["p"]) + 2
    return {"_kein_treffer": True, "geom": g}


ERFAHRUNGEN = {
    "statorjoch_saettigt": {
        "symptom": "Zu wenig Eisen zwischen Nutgrund (Hairpins) und Aussendurchmesser: das Statorjoch saettigt.",
        "warum": "Der Polfluss teilt sich im Joch auf zwei Wege; B_joch ~ Phi_Pol / (2 * h_joch * L * k_Fe). "
                 "Halbes Restjoch, doppelte Induktion -- unter dem Mindestjoch geht es steil nach oben.",
        "gilt_fuer": ("pmsm",),
        "ausloeser": lambda m: m["B_joch"] is not None and m["B_joch"] / m["B_sat"] > 1.0,
        "behoben": lambda m: m["B_joch"] is not None and m["B_joch"] / m["B_sat"] <= ZIEL_AUSNUTZUNG,
        "kennwert": "B_joch",
        "hebel": [
            {"id": "stator_groesser", "param": "statorOD", "fn": _hebel_stator_groesser,
             "preis": "Bauraum und Masse; oft durch den Auftrag festgelegt"},
            {"id": "rotor_kleiner", "param": "rotorOD", "fn": _hebel_rotor_kleiner,
             "preis": "Statorbohrung zieht mit; bei festen Magneten bleibt Kt fast stehen, B_gap und Zahnfeld steigen"},
            {"id": "nut_flacher", "param": "slotDepth", "fn": _hebel_nut_flacher,
             "preis": "weniger Kupferquerschnitt: hoehere Stromdichte und Kupferverluste"},
            {"id": "mehr_pole", "param": "p", "fn": _hebel_mehr_pole,
             "preis": "hoehere Frequenz und Eisenverluste; in diesem Modell steigt B_gap mit, der Zahn kann saettigen"},
        ],
        "beleg_start": "Messreihe 31.10.2026, frischer Payload (Stator 280/190): Restjoch 22,5/13,5/9,0/4,5 mm -> "
                       "B_joch 0,92/1,54/2,31/4,62 T; Projekt 20261030_212617: Joch 473 % der 1,70-T-Grenze.",
    },
}


# ── Abfrage ──────────────────────────────────────────────────────────────────

def pruefe(payload: dict, fest=(), merken: bool = False, quelle: str = "pruefe") -> dict:
    """Alle zustaendigen Erfahrungen gegen diese Geometrie pruefen.

    ``fest``: Parameter, die der Auftrag festlegt -- deren Hebel werden genannt,
    aber nicht gerechnet. Liefert ``{"art", "messung", "treffer": [...]}``; jeder
    Treffer traegt seine Hebel, je Hebel die kleinste wirksame Aenderung, die
    Nebenwirkungen (neue Symptome = Konflikt) und die Aenderung von Kt."""
    import ema_maschinenart as MA
    geom = dict(payload.get("geom") or {})
    if not geom:
        raise ValueError("Keine Geometrie im Payload.")
    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    art = MA.art_code(geom)
    m0 = _messen(geom, axial)
    fest = {f.strip() for f in fest if f and f.strip()}
    out = {"art": art, "messung": m0, "treffer": [], "nicht_zustaendig": []}
    for eid, e in ERFAHRUNGEN.items():
        if art not in e["gilt_fuer"]:
            out["nicht_zustaendig"].append(eid)
            continue
        if not e["ausloeser"](m0):
            continue
        tr = {"id": eid, "symptom": e["symptom"], "warum": e["warum"], "kennwert": e["kennwert"],
              "ist": m0[e["kennwert"]], "grenze": m0["B_sat"], "hebel": [],
              "mindestjoch_mm": round(m0["joch_mm"] * m0["B_joch"] / (ZIEL_AUSNUTZUNG * m0["B_sat"]), 1),
              "erfahrung": zaehler(eid)}
        for h in e["hebel"]:
            z = {"id": h["id"], "param": h["param"], "preis": h["preis"]}
            if h["param"] in fest:
                z.update(status="fest", text=f"{h['param']} ist durch den Auftrag festgelegt")
                tr["hebel"].append(z)
                continue
            r = h["fn"](geom, axial, e["behoben"])
            kein = isinstance(r, dict) and r.get("_kein_treffer")
            g1 = r["geom"] if kein else r
            if g1 is None:
                z.update(status="reicht_nicht", text=f"auch am Rand des Bereichs von {h['param']} nicht behoben")
            else:
                m1 = _messen(g1, axial)
                neu = [s for s in _symptome(m1) if s not in _symptome(m0)]
                aend = {k: (geom.get(k), g1.get(k)) for k in ("statorOD", "statorID", "rotorOD", "slotDepth", "p")
                        if g1.get(k) != geom.get(k)}
                z.update(status="reicht_nicht" if kein else ("konflikt" if neu else "hilft"),
                         aenderung=aend, nachher=m1, neue_symptome=neu,
                         **_preise(geom, g1, m0, m1),
                         _geom=g1)          # intern (Lernprogramm); fuer Ausgaben: ohne_intern()
            tr["hebel"].append(z)
        # Gewichtung AN DIESER MASCHINE: hilft vor Konflikt vor reicht nicht vor fest;
        # innerhalb „hilft" der kleinste Verlust an Spitzenmoment, dann an Kt, dann an
        # Nuttiefe (Kupferquerschnitt).
        rang = {"hilft": 0, "konflikt": 1, "reicht_nicht": 2, "fest": 3}
        def _verlust(z, k):
            v = z.get(k)
            return -v if v is not None else 0.0
        tr["hebel"].sort(key=lambda z: (rang[z["status"]], _verlust(z, "moment_pct"), _verlust(z, "kt_pct"),
                                        _verlust(z, "nuttiefe_pct")))
        out["treffer"].append(tr)
        if merken:
            for z in tr["hebel"]:
                if z["status"] in ("hilft", "konflikt", "reicht_nicht"):
                    beleg(eid, z["id"], z["status"], quelle=quelle,
                          daten={"vorher": m0[e["kennwert"]], "nachher": (z.get("nachher") or {}).get(e["kennwert"]),
                                 "neue_symptome": z.get("neue_symptome", []),
                                 "kt_pct": z.get("kt_pct"), "moment_pct": z.get("moment_pct"), "aenderung": z.get("aenderung")})
    return out


def _teilweise(geom: dict, g1: dict, anteil: float) -> dict:
    """``geom`` um ``anteil`` des Weges zu ``g1`` geschoben (Polpaare ganzzahlig, mindestens +1)."""
    g = dict(geom)
    for k in ("statorOD", "statorID", "rotorOD", "slotDepth"):
        if g1.get(k) != geom.get(k):
            g[k] = round(float(geom[k]) + anteil * (float(g1[k]) - float(geom[k])), 2)
    if g1.get("p") != geom.get("p"):
        dp = int(g1["p"]) - int(geom["p"])
        g["p"] = int(geom["p"]) + max(1, round(anteil * dp))
    return g


def _dominiert(a: dict, b: dict) -> bool:
    """``b`` ist in allen drei Preisen mindestens so gut wie ``a`` (und damit ``a`` nicht noetig)."""
    ma, mb = a.get("moment_pct"), b.get("moment_pct")
    if ma is not None and mb is not None and mb < ma - 1e-9:
        return False
    return (b["kt_pct"] >= a["kt_pct"] - 1e-9 and b["nuttiefe_pct"] >= a["nuttiefe_pct"] - 1e-9
            and b["aussen_pct"] <= a["aussen_pct"] + 1e-9)


def kombinationen(payload: dict, treffer: dict, fest=(), anteil: float = 0.5) -> list:
    """Jedes geordnete Hebelpaar (A, B): A zu ``anteil`` seines Einzelweges, dann B so weit wie noetig.

    ``treffer`` ist ein Eintrag aus ``pruefe(...)["treffer"]``. A braucht einen Einzelweg
    (Status hilft oder Konflikt); B wird an der vorgeschobenen Geometrie neu gesucht.
    Jedes Paar traegt ``pareto``: kein helfender Einzelhebel ist in Kt, Nuttiefe UND
    Aussendurchmesser mindestens so gut."""
    geom = dict(payload["geom"])
    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    e = ERFAHRUNGEN[treffer["id"]]
    fest = {f.strip() for f in fest if f and f.strip()}
    m0 = _messen(geom, axial)
    einzeln = {z["id"]: z for z in treffer["hebel"]}
    helfer = [z for z in treffer["hebel"] if z["status"] == "hilft"]
    out = []
    for ha in e["hebel"]:
        za = einzeln.get(ha["id"]) or {}
        if ha["param"] in fest or za.get("status") not in ("hilft", "konflikt") or "_geom" not in za:
            continue
        ga = _teilweise(geom, za["_geom"], anteil)
        for hb in e["hebel"]:
            if hb["id"] == ha["id"] or hb["param"] in fest:
                continue
            k = {"id": f"{ha['id']}+{hb['id']}", "a": ha["id"], "b": hb["id"], "anteil_a": anteil}
            r = hb["fn"](ga, axial, e["behoben"])
            kein = isinstance(r, dict) and r.get("_kein_treffer")
            g1 = None if kein else r
            if g1 is None:
                k["status"] = "reicht_nicht"
            else:
                m1 = _messen(g1, axial)
                neu = [s for s in _symptome(m1) if s not in _symptome(m0)]
                k.update(status="konflikt" if neu else "hilft", neue_symptome=neu, nachher=m1,
                         aenderung={x: (geom.get(x), g1.get(x)) for x in ("statorOD", "statorID", "rotorOD", "slotDepth", "p")
                                    if g1.get(x) != geom.get(x)},
                         **_preise(geom, g1, m0, m1), _geom=g1)
                if k["status"] == "hilft":
                    k["pareto"] = not any(_dominiert(k, h) for h in helfer)
                    # Wie viel von B noch noetig ist, gemessen an B allein: 0,5 heisst
                    # „die Haelfte A ersetzt die Haelfte B" (linear), darunter ergaenzen
                    # sich die beiden, darueber stehen sie sich im Weg.
                    zb = einzeln.get(hb["id"]) or {}
                    if zb.get("status") in ("hilft", "konflikt") and hb["param"] != "p":
                        d1 = float(zb["_geom"][hb["param"]]) - float(geom[hb["param"]])
                        d2 = float(g1[hb["param"]]) - float(ga[hb["param"]])
                        if abs(d1) > 1e-6:
                            k["bedarf_b"] = round(d2 / d1, 3)
            out.append(k)
    return out


def ohne_intern(x):
    """Interne Schluessel (``_geom``) fuer Ausgabe und Ablage entfernen."""
    if isinstance(x, dict):
        return {k: ohne_intern(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, list):
        return [ohne_intern(v) for v in x]
    return x


# ── Belege und Zaehler (Laufzeitdaten) ───────────────────────────────────────

def beleg(erfahrung: str, hebel: str, ergebnis: str, quelle: str, daten=None, pfad: str | None = None) -> None:
    pfad = pfad or BELEGE
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "a", encoding="utf-8") as f:
        f.write(json.dumps({"zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "erfahrung": erfahrung,
                            "hebel": hebel, "ergebnis": ergebnis, "quelle": quelle,
                            "daten": daten or {}}, ensure_ascii=False, default=str) + "\n")


def zaehler(erfahrung: str, pfad: str | None = None) -> dict:
    """Je Hebel: wie oft hat er geholfen, einen Konflikt ausgeloest, nicht gereicht."""
    pfad = pfad or BELEGE
    z: dict = {}
    try:
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                try:
                    b = json.loads(zeile)
                except ValueError:
                    continue
                if b.get("erfahrung") != erfahrung:
                    continue
                h = z.setdefault(b["hebel"], {"hilft": 0, "konflikt": 0, "reicht_nicht": 0})
                if b.get("ergebnis") in h:
                    h[b["ergebnis"]] += 1
    except OSError:
        pass
    return z


def als_text(r: dict) -> str:
    m = r["messung"]
    z = [f"ERFAHRUNG ({r['art']}) — Messung: B_joch {m['B_joch']} T, B_zahn {m['B_zahn']} T, "
         f"B_rotorjoch {m['B_rotorjoch']} T gegen {m['B_sat']} T; Restjoch {m['joch_mm']} mm"]
    if r["nicht_zustaendig"] and not r["treffer"]:
        z.append(f"  Fuer {r['art']} gibt es noch keine Erfahrungen (erst PSM).")
    elif not r["treffer"]:
        z.append("  Keine Erfahrung schlaegt an.")
    zeichen = {"hilft": "✓", "konflikt": "⚠", "reicht_nicht": "✗", "fest": "·"}
    for t in r["treffer"]:
        z.append(f"  ℹ {t['symptom']}")
        z.append(f"    {t['kennwert']} {t['ist']} T > {t['grenze']} T; Mindestjoch hier ≈ {t['mindestjoch_mm']} mm "
                 f"(Ziel {int(ZIEL_AUSNUTZUNG * 100)} % des Knies). {t['warum']}")
        z.append("    Hebel, an dieser Maschine gerechnet (kleinste wirksame Aenderung):")
        for h in t["hebel"]:
            zeile = f"    {zeichen[h['status']]} {h['id']:<16}"
            if h["status"] == "fest":
                zeile += h["text"]
            elif h.get("aenderung") is not None:
                zeile += " ".join(f"{k} {a}→{b}" for k, (a, b) in h["aenderung"].items())
                n = h["nachher"]
                zeile += f"  | B_joch {n['B_joch']} T, B_zahn {n['B_zahn']} T, Spitzenmoment {h['moment_pct']:+.1f} %, Kt {h['kt_pct']:+.2f} %, Nuttiefe {h['nuttiefe_pct']:+.1f} %, Aussen {h['aussen_pct']:+.1f} %"
                if h["neue_symptome"]:
                    zeile += "  | NEU: " + ", ".join(h["neue_symptome"])
                if h["status"] == "reicht_nicht":
                    zeile += "  | reicht nicht"
            else:
                zeile += h.get("text", "")
            z.append(zeile)
            z.append(f"        Preis: {h['preis']}")
            erf = t["erfahrung"].get(h["id"])
            if erf:
                z.append(f"        bisher: hilft {erf['hilft']}× · Konflikt {erf['konflikt']}× · reicht nicht {erf['reicht_nicht']}×")
    z.append("  Kein Tor: das sind Hinweise. Spitzenmoment an Strom-/Spannungsgrenze bei 1000 1/min (mit Reluktanz), Kt = Magnetanteil (1 Wdg/Nut, /p²).")
    return "\n".join(z)
