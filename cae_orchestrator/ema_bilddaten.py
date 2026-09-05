"""Bilddatensatz: Rotorquerschnitte zeichnen, von Hand bewerten, eine Regel daraus ziehen.

Woher der Wunsch kam
--------------------

Aus einem Plan fuer **10.000 Zufallsmaschinen mit optischer Bewertung**, aus dem ein
Bildmodell lernen sollte, ob ein Querschnitt „gut aussieht". Die Idee ist richtig --
das Auge sieht Missverhaeltnisse, fuer die es keine Kennzahl gibt. Die Zahl 10.000
war es nicht, und zwar aus drei **gemessenen** Gruenden:

* Von zufaellig gezogenen Geometrien besteht rund **ein Viertel** das Layouttor
  (``ema_rotorcheck.rotor_layout_check``). Die uebrigen drei Viertel sind Taschen, die
  sich schneiden oder aus dem Rotor ragen -- geometrisch unmoegliche Maschinen. Die
  muss niemand ansehen: das Tor entscheidet sie in Millisekunden und exakt.
* Von den Ueberlebenden nennt die vorhandene Heuristik (``ema_training.auto_label``)
  bereits **79,3 %** „schlecht". Ein menschliches Urteil traegt dort nichts bei, wo
  eine Regel schon entscheidet.
* Was uebrig bleibt -- die Faelle, in denen das Auge wirklich gebraucht wird -- sind
  rund **5 %** der Ziehungen. Bei 10.000 waeren das 500 lohnende Bilder und 9.500,
  die Zeit kosten. Also werden gleich die 500 gezogen.

Was hier NICHT gebaut wird
--------------------------

**Kein neuronales Netz.** Die Geometrie liegt exakt vor; sie aus Pixeln
zurueckzuschaetzen waere ein Rueckschritt. Am Ende steht eine **Schranke ueber
gemessenen Groessen des Querschnitts** -- lesbar, nachrechenbar, bestreitbar -- die
als belegte Erfahrung nach ``ema_lernen`` geht. ``regel_suchen`` sucht sie, prueft
sie auf einem **zurueckgehaltenen Drittel** und weigert sich, sie abzulegen, wenn sie
dort nicht besser ist als schlichtes Raten der Mehrheit.

**Keine Vorbelegung durch die Heuristik.** Die Bewertungsseite zeigt das Bild und
sonst nichts: keine Masse, keine Kennzahlen, keinen Vorschlag. Wer eine Heuristik
vorschlaegt, bekommt sie bestaetigt zurueck -- und genau das unabhaengige Urteil,
dessentwegen der Mensch gefragt wird, ist dann weg.

Ablauf
------

    cae_cli.py bilddaten erzeugen --anzahl 500     # ziehen, Tor, zeichnen
    cae_cli.py bilddaten seite                     # bewerten.html schreiben
    #   -> im Browser oeffnen, 1=gut 2=mittel 3=schlecht, am Ende "Speichern"
    cae_cli.py bilddaten einlesen --datei ~/Downloads/urteile.json
    cae_cli.py bilddaten regel [--merken]

Ablage: ``~/cae_projekte/_bilddaten/`` -- Laufzeitdaten, nicht versioniert.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time

import ema_text2ema as _T2E
from ema_rotorcheck import rotor_layout_check
from ema_topology import TOPOLOGY_LABELS, leg_center, magnet_legs

STORE   = os.path.expanduser("~/cae_projekte/_bilddaten")
SATZ    = os.path.join(STORE, "datensatz.jsonl")
BILDER  = os.path.join(STORE, "bilder")
SEITE   = os.path.join(STORE, "bewerten.html")

URTEILE = ("gut", "mittel", "schlecht")

# Bildkante in Pixeln. 384 statt der 1300 des Berichtsbildes: bewertet wird die
# GESTALT, und die ist bei 384 px vollstaendig zu sehen. Gemessen an derselben
# Geometrie: 0,138 s und 33 kB je Bild gegen 0,245 s und 172 kB in Berichtsgroesse.
PX = 384

# Bauformen, die gezogen werden. ``custom`` bleibt draussen: die gezeichnete
# Geometrie kommt aus der Oberflaeche und laesst sich nicht sinnvoll wuerfeln.
BAUFORMEN = ("v", "vasym", "bar", "u", "vv", "delta", "spoke", "pmasynrm")


# ── 1. Ziehen ─────────────────────────────────────────────────────────────────

def _vorgaben() -> dict:
    """Alle geom-Schluessel mit ihrem Schema-Vorgabewert.

    Quelle ist ``ema_text2ema.SCHEMA`` -- dieselbe, aus der ``/param_schema`` die
    Oberflaeche speist. Eine eigene Tabelle hier waere die zweite Wahrheit.
    """
    return {k: s.get("def") for k, s in _T2E.SCHEMA.items() if s.get("geom")}


def _klemme(key: str, wert: float) -> float:
    """Einen Zahlenwert in die Schema-Grenzen zwingen und wie das Schema runden."""
    spec = _T2E.SCHEMA.get(key)
    if not spec or spec.get("kind") != "num":
        return wert
    wert = max(spec["lo"], min(spec["hi"], float(wert)))
    return int(round(wert)) if spec.get("int") else round(wert, 3)


def ziehe(rng: random.Random, basis: dict | None = None) -> dict:
    """Eine Zufallsgeometrie.

    Gezogen werden **Verhaeltnisse**, nicht Absolutmasse: der Wellendurchmesser als
    Anteil des Rotors, die Magnetlaenge als Anteil der Rotorwandstaerke. Damit ist
    die radiale Ordnung (statorOD > statorID > rotorOD > shaftD) durch die Konstruktion
    erfuellt und muss nicht hinterher repariert werden -- ``ema_text2ema._validate``
    macht genau diese Reparatur, kann hier aber nicht helfen, weil es die
    Feinparameter (``adv``) absichtlich gar nicht fuellt.
    """
    g = _vorgaben()
    if basis:
        g.update({k: v for k, v in basis.items() if k in g})

    u = rng.uniform
    stator_od = u(140.0, 400.0)
    stator_id = stator_od * u(0.55, 0.78)
    rotor_od  = stator_id - 2 * u(0.4, 0.9)                 # Luftspalt je Seite
    shaft_d   = rotor_od * u(0.20, 0.45)
    wand      = (rotor_od - shaft_d) / 2.0                  # Rotorwandstaerke [mm]

    g.update({
        "statorOD":       _klemme("statorOD", stator_od),
        "statorID":       _klemme("statorID", stator_id),
        "rotorOD":        _klemme("rotorOD",  rotor_od),
        "shaftD":         _klemme("shaftD",   shaft_d),
        "shaftBoreD":     0,
        "slotDepth":      _klemme("slotDepth", (stator_od - stator_id) / 2 * u(0.45, 0.80)),
        "slots":          3 * rng.randint(4, 24),
        "p":              rng.randint(2, 8),
        "magShape":       rng.choice(BAUFORMEN),
        "magDepthRel":    _klemme("magDepthRel", u(0.45, 0.90)),
        "magWidth":       _klemme("magWidth",  wand * u(0.30, 1.30)),
        "magThick":       _klemme("magThick",  u(2.0, 12.0)),
        "magDist":        _klemme("magDist",   u(0.0, 0.35 * wand)),
        "magLayerGap":    _klemme("magLayerGap", u(1.0, 0.5 * wand)),
        "magTangLen":     _klemme("magTangLen", 0.0 if rng.random() < 0.5
                                                else wand * u(0.3, 1.2)),
        "magGapMm":       _klemme("magGapMm", u(0.05, 0.3)),
        "slotWidthRatio": _klemme("slotWidthRatio", u(0.30, 0.70)),
        "magAngle":       _klemme("magAngle", u(60.0, 160.0)),
    })
    return g


# ── 2. Merkmale — worueber eine Regel spaeter ueberhaupt reden kann ───────────

def merkmale(geom: dict, tor: dict | None = None) -> dict:
    """Messbare Groessen des Querschnitts.

    Das ist die Wortliste der spaeteren Regel: ``regel_suchen`` kann nur Schranken
    ueber diesen Groessen finden. Aufgenommen ist deshalb nur, was sich am fertigen
    Blechschnitt **nachmessen** laesst -- kein Gewicht, keine Kennzahl aus einem
    Verfahren, nichts, das eine spaetere Rechnung umstossen koennte.
    """
    tor = tor if tor is not None else rotor_layout_check(geom)
    lay = tor.get("layout", {})

    r_rot   = float(geom["rotorOD"]) / 2.0
    r_shaft = float(geom["shaftD"]) / 2.0
    r_si    = float(geom["statorID"]) / 2.0
    r_so    = float(geom["statorOD"]) / 2.0
    polzahl = max(2, int(geom["p"]) * 2)
    nuten   = int(geom["slots"])
    wand    = max(1e-6, r_rot - r_shaft)

    legs, _meta = magnet_legs(geom)
    innen = [l for l in legs if l.placement == "interior"]
    flaeche_pol = sum(l.length * l.thickness for l in legs)
    ring        = math.pi * (r_rot ** 2 - r_shaft ** 2)

    # Radiale Lage der Taschen: wie viel Blech bleibt aussen zum Luftspalt und
    # innen zur Welle. Beides sind die Stellen, an denen ein Rotor reisst.
    r_aussen, r_innen = [], []
    gap = max(0.05, min(0.3, float(geom.get("magGapMm", 0.1))))
    for l in legs:
        cx, cy = leg_center(l)
        rad = math.hypot(cx, cy)
        halb = math.hypot(l.length / 2 + gap, l.thickness / 2 + gap)
        r_aussen.append(rad + halb)
        r_innen.append(rad - halb)

    dtheta_s = 2 * math.pi / max(1, nuten)
    import ema_wicklung
    _ng = ema_wicklung.nutgeometrie(geom)
    nutbreite = _ng["nut_breite_mm"]
    zahnbreite = _ng["zahn_breite_m"] * 1000.0
    polteilung = math.pi * 2 * r_rot / polzahl

    import ema_screen as _SC
    return {
        "polzahl":            float(polzahl),
        "nuten":              float(nuten),
        "nuten_je_pol":       nuten / polzahl,
        "q_pol_strang":       nuten / (polzahl * 3.0),
        "wicklung_symm":      1.0 if _SC.wicklung_moeglich(nuten, polzahl) else 0.0,
        "steg_min_mm":        float(lay.get("min_web_found_mm") or 0.0),
        "steg_rel":           float(lay.get("min_web_found_mm") or 0.0) / wand,
        "randsteg_mm":        r_rot - max(r_aussen) if r_aussen else 0.0,
        "jochsteg_mm":        min(r_innen) - r_shaft if r_innen else 0.0,
        "magnetflaeche_rel":  flaeche_pol * polzahl / ring if ring > 0 else 0.0,
        "polbedeckung":       min(1.5, len(innen) * float(geom["magWidth"]) / polteilung),
        "schlankheit":        float(geom["magWidth"]) / max(1e-6, float(geom["magThick"])),
        "nabenanteil":        float(geom["shaftD"]) / max(1e-6, float(geom["rotorOD"])),
        "magnettiefe":        float(geom.get("magDepthRel", 0.7)),
        "rotorwand_mm":       wand,
        "luftspalt_mm":       (r_si - r_rot),
        "zahn_zu_nut":        zahnbreite / max(1e-6, nutbreite),
        "statorjoch_mm":      max(0.0, r_so - r_si - float(geom["slotDepth"])),
        "lagen_je_pol":       float(len(legs)),
    }


# ── 3. Erzeugen: ziehen, Tor, zeichnen, ablegen ───────────────────────────────

def _kennung(geom: dict) -> str:
    roh = json.dumps(geom, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:12]


def zeichne(geom: dict, pfad: str, px: int = PX) -> str:
    """Den Querschnitt ohne Beschriftung ablegen.

    Gezeichnet wird mit ``ema_pipeline.render_cross_section`` -- **demselben** Code,
    aus dem das Bild im Projektbericht kommt. Ein eigener Zeichner haette hier ein
    Bild ergeben, das eine Maschine zeigt, die so nie gerechnet wurde.
    """
    import matplotlib.pyplot as plt
    from ema_pipeline import render_cross_section

    dpi = 100
    fig, ax = plt.subplots(figsize=(px / dpi, px / dpi), dpi=dpi)
    try:
        render_cross_section(geom, ax, beschriftung=False)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        fig.savefig(pfad, dpi=dpi, facecolor="#0d1117", pad_inches=0)
    finally:
        plt.close(fig)
    return pfad


def _lies() -> list:
    if not os.path.isfile(SATZ):
        return []
    aus = []
    with open(SATZ, encoding="utf-8") as f:
        for z in f:
            z = z.strip()
            if z:
                try:
                    aus.append(json.loads(z))
                except json.JSONDecodeError:
                    pass
    return aus


def _schreibe(saetze: list) -> None:
    os.makedirs(STORE, exist_ok=True)
    tmp = SATZ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for s in saetze:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    os.replace(tmp, SATZ)


def erzeuge(anzahl: int = 500, seed: int | None = None, basis: dict | None = None,
            px: int = PX, hoechstversuche: int | None = None,
            min_web: float | None = None) -> dict:
    """``anzahl`` Varianten erzeugen, die das Layouttor bestehen.

    Gezaehlt werden die BESTANDENEN, nicht die Ziehungen -- sonst haengt die Groesse
    des Datensatzes an einer Ausbeute, die niemand vorher kennt. ``hoechstversuche``
    deckelt den Aufwand, falls die Ausbeute in einem Basisentwurf zusammenbricht.
    """
    rng = random.Random(seed)
    hoechstversuche = hoechstversuche or anzahl * 12
    vorhanden = _lies()
    bekannt = {s["id"] for s in vorhanden}

    t0 = time.time()
    neu, versuche, durchgefallen, doppelt = [], 0, 0, 0
    while len(neu) < anzahl and versuche < hoechstversuche:
        versuche += 1
        g = ziehe(rng, basis)
        tor = rotor_layout_check(g) if min_web is None else rotor_layout_check(g, min_web)
        if not tor["ok"]:
            durchgefallen += 1
            continue
        kid = _kennung(g)
        if kid in bekannt:
            doppelt += 1
            continue
        bekannt.add(kid)
        bild = os.path.join(BILDER, kid + ".png")
        zeichne(g, bild, px)
        neu.append({
            "id": kid,
            "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "geom": g,
            "bild": os.path.relpath(bild, STORE),
            "tor": {"ok": True,
                    "topologie": tor["layout"]["topology"],
                    "steg_min_mm": tor["layout"]["min_web_found_mm"],
                    "warnungen": tor["warnings"]},
            "merkmale": merkmale(g, tor),
            "urteil": None, "urteil_zeit": None, "notiz": "",
        })

    _schreibe(vorhanden + neu)
    dauer = time.time() - t0
    return {"neu": len(neu), "ziehungen": versuche,
            "durchgefallen": durchgefallen, "doppelt": doppelt,
            "ausbeute": round(len(neu) / versuche, 4) if versuche else 0.0,
            "sekunden": round(dauer, 1),
            "sekunden_je_bild": round(dauer / len(neu), 3) if neu else None,
            "gesamt": len(vorhanden) + len(neu), "ablage": STORE}


def stand() -> dict:
    saetze = _lies()
    bewertet = [s for s in saetze if s.get("urteil")]
    je_urteil, je_form = {}, {}
    for s in saetze:
        f = s["geom"]["magShape"]
        je_form[f] = je_form.get(f, 0) + 1
        if s.get("urteil"):
            je_urteil[s["urteil"]] = je_urteil.get(s["urteil"], 0) + 1
    return {"varianten": len(saetze), "bewertet": len(bewertet),
            "offen": len(saetze) - len(bewertet),
            "je_urteil": je_urteil, "je_bauform": je_form, "ablage": STORE}


# ── 4. Bewertungsseite ────────────────────────────────────────────────────────

_SEITE_VORLAGE = """<!doctype html>
<meta charset="utf-8"><title>Rotorquerschnitte bewerten</title>
<style>
 body{background:#0d1117;color:#c9d1d9;font:14px system-ui,sans-serif;margin:0;
      display:flex;flex-direction:column;align-items:center;gap:12px;padding:18px}
 img{width:%(px)dpx;height:%(px)dpx;border:1px solid #30363d;border-radius:6px;
     image-rendering:auto;background:#0d1117}
 .k{display:flex;gap:8px} button{font:inherit;padding:8px 18px;border-radius:6px;
     border:1px solid #30363d;background:#161b22;color:#c9d1d9;cursor:pointer}
 button:hover{border-color:#58a6ff} .z{color:#8b949e;font-size:13px}
 .f{color:#8b949e;max-width:%(px)dpx;text-align:center;font-size:12px;line-height:1.5}
 b{color:#e6edf3}
</style>
<h2 style="margin:0">Rotorquerschnitt bewerten</h2>
<div class=f>Nur das Bild. Keine Masse, keine Kennzahlen, kein Vorschlag &mdash;
 das Urteil soll unabh&auml;ngig von dem sein, was die Werkzeugkette ohnehin schon
 rechnet. Tasten: <b>1</b> gut &middot; <b>2</b> mittel &middot; <b>3</b> schlecht
 &middot; <b>u</b> zur&uuml;ck &middot; <b>s</b> speichern.</div>
<div class=z id=z></div>
<img id=b alt="">
<div class=k>
 <button onclick="w('gut')">1 &mdash; gut</button>
 <button onclick="w('mittel')">2 &mdash; mittel</button>
 <button onclick="w('schlecht')">3 &mdash; schlecht</button>
 <button onclick="zurueck()">u &mdash; zur&uuml;ck</button>
 <button onclick="sichern()">s &mdash; speichern</button>
</div>
<script>
const D = %(daten)s;
const K = "bilddaten-urteile";
let U = {}; try { U = JSON.parse(localStorage.getItem(K) || "{}"); } catch(e) {}
let i = D.findIndex(d => !(d.id in U)); if (i < 0) i = D.length ? D.length - 1 : 0;
function zeige(){
  const n = Object.keys(U).length;
  document.getElementById('z').textContent =
     (i+1) + " / " + D.length + "   \\u00b7   " + n + " bewertet"
     + (D[i] && U[D[i].id] ? "   \\u00b7   bisher: " + U[D[i].id] : "");
  if (D[i]) document.getElementById('b').src = D[i].bild;
}
function w(u){ if(!D[i]) return; U[D[i].id] = u;
  localStorage.setItem(K, JSON.stringify(U));
  if (i < D.length - 1) i++; zeige(); }
function zurueck(){ if (i > 0) i--; zeige(); }
function sichern(){
  const b = new Blob([JSON.stringify(U, null, 1)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = "urteile.json"; a.click();
}
addEventListener('keydown', e => {
  if (e.key === '1') w('gut'); else if (e.key === '2') w('mittel');
  else if (e.key === '3') w('schlecht'); else if (e.key === 'u') zurueck();
  else if (e.key === 's') sichern();
});
zeige();
</script>
"""


def bewertungsseite(nur_offene: bool = True, px: int = PX) -> str:
    """Eine eigenstaendige HTML-Seite zum Durchklicken schreiben.

    Bewusst ohne Server: die Seite laeuft ueber ``file://``, haelt den Zwischenstand
    im ``localStorage`` des Browsers und gibt die Urteile als Datei heraus, die
    ``einlesen`` zurueck in den Datensatz legt. Damit haengt das Bewerten an keinem
    laufenden Dienst -- und der Datensatz bleibt die eine Wahrheit, nicht der Browser.
    """
    saetze = _lies()
    if nur_offene:
        saetze = [s for s in saetze if not s.get("urteil")]
    daten = [{"id": s["id"], "bild": s["bild"].replace(os.sep, "/")} for s in saetze]
    os.makedirs(STORE, exist_ok=True)
    with open(SEITE, "w", encoding="utf-8") as f:
        f.write(_SEITE_VORLAGE % {"px": px,
                                  "daten": json.dumps(daten, ensure_ascii=False)})
    return SEITE


def einlesen(pfad: str) -> dict:
    """Urteile aus der von der Seite gespeicherten JSON-Datei uebernehmen."""
    with open(pfad, encoding="utf-8") as f:
        urteile = json.load(f)
    if not isinstance(urteile, dict):
        raise ValueError("Erwartet wird ein Objekt {\"<id>\": \"gut|mittel|schlecht\"}.")

    saetze = _lies()
    nach_id = {s["id"]: s for s in saetze}
    gesetzt, unbekannt, ungueltig, unveraendert = 0, [], [], 0
    jetzt = time.strftime("%Y-%m-%dT%H:%M:%S")
    for kid, u in urteile.items():
        if u not in URTEILE:
            ungueltig.append(kid)
            continue
        s = nach_id.get(kid)
        if s is None:
            unbekannt.append(kid)
            continue
        if s.get("urteil") == u:
            unveraendert += 1
            continue
        s["urteil"] = u
        s["urteil_zeit"] = jetzt
        gesetzt += 1
    _schreibe(saetze)
    return {"gesetzt": gesetzt, "unveraendert": unveraendert,
            "unbekannt": len(unbekannt), "ungueltig": len(ungueltig),
            "bewertet_gesamt": sum(1 for s in saetze if s.get("urteil"))}


# ── 5. Regelsuche ─────────────────────────────────────────────────────────────
#
# Gesucht wird eine Schranke, keine Gewichtsmatrix. Zwei Gruende, und beide sind
# praktisch: eine Schranke laesst sich am Blech nachmessen und bestreiten, und sie
# braucht keine 10.000 Beispiele, um nicht bloss den Datensatz auswendig zu lernen.

MERKMALSNAMEN = ("steg_min_mm", "steg_rel", "randsteg_mm", "jochsteg_mm",
                 "magnetflaeche_rel", "polbedeckung", "schlankheit", "nabenanteil",
                 "magnettiefe", "rotorwand_mm", "luftspalt_mm", "zahn_zu_nut",
                 "statorjoch_mm", "nuten_je_pol", "q_pol_strang", "polzahl",
                 "lagen_je_pol", "wicklung_symm")


def _teile(kid: str) -> str:
    """Fest zugeteilt statt zufaellig: dieselbe Variante liegt in jedem Lauf in
    derselben Haelfte. Sonst waere die Pruefzahl bei jedem Aufruf eine andere."""
    return "test" if int(hashlib.sha1(kid.encode()).hexdigest(), 16) % 10 >= 7 else "train"


def _bilanz(y, vorhersage) -> float:
    """Ausgewogene Trefferquote. Nicht die schlichte: bei 80 % ``schlecht`` bekaeme
    „immer schlecht" sonst 80 % und saehe nach einer Erkenntnis aus."""
    tp = sum(1 for a, b in zip(y, vorhersage) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y, vorhersage) if a == 0 and b == 0)
    np_, nn = sum(1 for a in y if a == 1), sum(1 for a in y if a == 0)
    if not np_ or not nn:
        return 0.0
    return 0.5 * (tp / np_ + tn / nn)


def _schwellen(werte: list, n: int = 20) -> list:
    w = sorted(set(werte))
    if len(w) < 2:
        return []
    if len(w) <= n + 1:
        return [(a + b) / 2 for a, b in zip(w, w[1:])]
    return [ (w[int(len(w) * i / (n + 1))] + w[int(len(w) * i / (n + 1)) + 1]) / 2
             for i in range(1, n + 1) ]


def _regel_text(teile: list) -> str:
    return " und ".join(f"{m} {'>=' if r == 'ge' else '<='} {s:.4g}"
                        for m, r, s in teile)


def _trifft(x: dict, teile: list) -> bool:
    for m, r, s in teile:
        v = x.get(m)
        if v is None:
            return False
        if (r == "ge" and v < s) or (r == "le" and v > s):
            return False
    return True


def regel_suchen(mittel_als: str = "aus", hoechstens_paare: int = 6) -> dict:
    """Aus den Urteilen eine Schranke ziehen -- und sie auf zurueckgehaltenen Daten pruefen.

    ``mittel_als``: ``aus`` laesst die mittleren Urteile weg (Vorgabe -- sie sind
    genau die strittigen), ``gut`` oder ``schlecht`` schlaegt sie der jeweiligen
    Seite zu.

    Zurueck kommt immer auch die **Grundquote**: was blosses Raten der Mehrheit auf
    demselben Pruefteil erreicht. Eine Regel, die die nicht schlaegt, ist keine.
    """
    saetze = [s for s in _lies() if s.get("urteil")]
    def ziel(s):
        u = s["urteil"]
        if u == "mittel":
            return {"gut": 1, "schlecht": 0}.get(mittel_als)
        return 1 if u == "gut" else 0

    daten = [(s["id"], s["merkmale"], ziel(s)) for s in saetze]
    daten = [d for d in daten if d[2] is not None]
    train = [d for d in daten if _teile(d[0]) == "train"]
    test  = [d for d in daten if _teile(d[0]) == "test"]

    grund = {"bewertet": len(saetze), "verwendet": len(daten),
             "train": len(train), "test": len(test),
             "gut_anteil": round(sum(d[2] for d in daten) / len(daten), 3) if daten else None,
             "mittel_als": mittel_als}
    if len(train) < 20 or len(test) < 10:
        return {**grund, "genug": False, "regeln": [],
                "hinweis": "Zu wenige Urteile fuer eine belastbare Suche — mindestens "
                           "30 bewertete Varianten, davon 10 im Pruefteil."}

    y_tr = [d[2] for d in train]
    y_te = [d[2] for d in test]
    # Grundquote: die ausgewogene Trefferquote der Mehrheitsantwort ist per
    # Konstruktion 0,5. Daneben die schlichte Quote, weil die Zahl gefragt wird.
    mehrheit = 1 if sum(y_te) * 2 >= len(y_te) else 0
    grund["grundquote_schlicht"] = round(
        sum(1 for a in y_te if a == mehrheit) / len(y_te), 3)
    grund["grundquote_ausgewogen"] = 0.5

    # (a) einzelne Schranken
    einzeln = []
    for m in MERKMALSNAMEN:
        werte = [d[1].get(m) for d in train if d[1].get(m) is not None]
        if len(werte) < len(train):
            continue
        for s in _schwellen(werte):
            for r in ("ge", "le"):
                teile = [(m, r, s)]
                g = _bilanz(y_tr, [1 if _trifft(d[1], teile) else 0 for d in train])
                einzeln.append((g, teile))
    einzeln.sort(key=lambda t: -t[0])

    # (b) Paare — nur aus den Merkmalen, die einzeln schon etwas taugen. Alles
    #     gegen alles waere hier nicht teuer, aber es wuerde die Zahl der
    #     ausprobierten Regeln so aufblaehen, dass die beste per Zufall gut aussieht.
    beste_merkmale, gesehen = [], set()
    for g, teile in einzeln:
        m = teile[0][0]
        if m not in gesehen:
            gesehen.add(m)
            beste_merkmale.append(m)
        if len(beste_merkmale) >= hoechstens_paare:
            break

    paare = []
    for i, m1 in enumerate(beste_merkmale):
        w1 = _schwellen([d[1][m1] for d in train], 12)
        for m2 in beste_merkmale[i + 1:]:
            w2 = _schwellen([d[1][m2] for d in train], 12)
            for s1 in w1:
                for r1 in ("ge", "le"):
                    for s2 in w2:
                        for r2 in ("ge", "le"):
                            teile = [(m1, r1, s1), (m2, r2, s2)]
                            g = _bilanz(y_tr, [1 if _trifft(d[1], teile) else 0
                                               for d in train])
                            paare.append((g, teile))
    paare.sort(key=lambda t: -t[0])

    ausgabe = []
    for g_tr, teile in (einzeln[:1] + paare[:1]):
        v_te = [1 if _trifft(d[1], teile) else 0 for d in test]
        g_te = _bilanz(y_te, v_te)
        ausgabe.append({
            "regel": _regel_text(teile),
            "teile": [{"merkmal": m, "richtung": r, "schwelle": round(s, 4)}
                      for m, r, s in teile],
            "train_ausgewogen": round(g_tr, 3),
            "test_ausgewogen":  round(g_te, 3),
            "test_schlicht":    round(sum(1 for a, b in zip(y_te, v_te) if a == b)
                                      / len(y_te), 3),
            "haelt": g_te > 0.5 + 1e-9,
        })
    ausgabe.sort(key=lambda r: -r["test_ausgewogen"])
    # Die Bauform ist keine Schranke, sondern eine Liste — sie gehoert trotzdem in
    # den Befund, weil sie oft das ist, was das Auge eigentlich beurteilt hat.
    je_form = {}
    for s in saetze:
        f = s["geom"]["magShape"]
        e = je_form.setdefault(f, {"n": 0, "gut": 0})
        e["n"] += 1
        e["gut"] += 1 if s["urteil"] == "gut" else 0
    for f, e in je_form.items():
        e["gut_anteil"] = round(e["gut"] / e["n"], 3)

    return {**grund, "genug": True, "regeln": ausgabe,
            "je_bauform": {TOPOLOGY_LABELS.get(f, f): e for f, e in sorted(je_form.items())}}


def merke_regel(befund: dict, quelle: str = "bilddaten", conn=None) -> dict:
    """Die beste Regel als belegte Erfahrung ablegen -- wenn sie den Pruefteil haelt.

    Die Weigerung ist der eigentliche Wert dieser Funktion: eine Schranke, die auf
    zurueckgehaltenen Urteilen nicht besser ist als Raten, ist eine Eigenschaft des
    Datensatzes und keine des Rotors. Sie darf nicht in den Erfahrungsspeicher, sonst
    steht sie dort spaeter als „gemessen".
    """
    import ema_lernen

    if not befund.get("genug"):
        return {"abgelegt": False, "grund": befund.get("hinweis", "zu wenige Urteile")}
    kandidaten = [r for r in befund["regeln"] if r["haelt"]]
    if not kandidaten:
        return {"abgelegt": False,
                "grund": "Keine der gefundenen Schranken schlaegt auf dem Pruefteil "
                         "das blosse Raten (ausgewogene Trefferquote <= 0,5). "
                         "Das ist ein Befund, kein Fehler: das Urteil haengt dann an "
                         "etwas, das in den Merkmalen nicht vorkommt."}
    r = kandidaten[0]
    regel = (f"Ein Rotorquerschnitt wird optisch als gut beurteilt, wenn "
             f"{r['regel']} (gemessen am Blechschnitt).")
    beleg = (f"{befund['verwendet']} von Hand bewertete Querschnitte "
             f"({befund['train']} Lern-, {befund['test']} Pruefteil, feste Zuteilung "
             f"ueber die Variantenkennung). Ausgewogene Trefferquote "
             f"{r['train_ausgewogen']} im Lern-, {r['test_ausgewogen']} im Pruefteil; "
             f"blosses Raten der Mehrheit erreicht dort ausgewogen 0,5 "
             f"(schlicht {befund['grundquote_schlicht']}). Anteil 'gut' insgesamt "
             f"{befund['gut_anteil']}.")
    satz = ema_lernen.merke(regel, beleg, quelle=quelle, conn=conn)
    return {"abgelegt": True, "regel": regel, "beleg": beleg, "satz": satz}


# ── 6. Textausgabe ────────────────────────────────────────────────────────────

def stand_text(s: dict) -> str:
    z = [f"Bilddatensatz  {s['ablage']}",
         f"  Varianten {s['varianten']}   bewertet {s['bewertet']}   offen {s['offen']}"]
    if s["je_urteil"]:
        z.append("  Urteile:  " + "  ".join(f"{k} {v}" for k, v in sorted(s["je_urteil"].items())))
    if s["je_bauform"]:
        z.append("  Bauformen: " + "  ".join(f"{k} {v}" for k, v in sorted(s["je_bauform"].items())))
    return "\n".join(z)


def regel_text(b: dict) -> str:
    z = [f"Urteile: {b['verwendet']} verwendet von {b['bewertet']} bewertet "
         f"(mittel: {b['mittel_als']})   Lernteil {b['train']}   Pruefteil {b['test']}"]
    if b.get("gut_anteil") is not None:
        z.append(f"Anteil 'gut': {b['gut_anteil']}")
    if not b.get("genug"):
        z.append("")
        z.append(b.get("hinweis", "zu wenige Urteile"))
        return "\n".join(z)
    z.append(f"Raten der Mehrheit im Pruefteil: ausgewogen 0.5 "
             f"(schlicht {b['grundquote_schlicht']})")
    z.append("")
    for r in b["regeln"]:
        marke = "haelt" if r["haelt"] else "HAELT NICHT"
        z.append(f"  {r['regel']}")
        z.append(f"      Lernteil {r['train_ausgewogen']}   Pruefteil "
                 f"{r['test_ausgewogen']} ({marke}), schlicht {r['test_schlicht']}")
    if b.get("je_bauform"):
        z.append("")
        z.append("  Anteil 'gut' je Bauform:")
        for f, e in b["je_bauform"].items():
            z.append(f"      {f:<28} {e['gut_anteil']:.2f}  (n={e['n']})")
    return "\n".join(z)
