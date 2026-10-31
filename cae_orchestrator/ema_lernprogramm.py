"""Lernprogramm fuer die Erfahrungsdatenbank -- erst nur PSM.

Die Frage war: „er mal einen Tag lang alles machen und vergleichen, oder es wird
ein Lernprogramm erstellt" -- und dann: „wenn ich ihm sage ‚mach mal eine Stunde',
kann er 15 Minuten fuers Auswerten einplanen". Beides steckt hier drin:

**Zeitplan.** ``lauf(minuten=60, auswertung_anteil=0.25)`` lernt hoechstens 45
Minuten und haelt den Rest fuer die Auswertung frei. Die eigene Auswertung (der
Bericht) braucht Sekunden; was vom Viertel uebrig bleibt, steht im Bericht als Zeit
fuer die Deutung -- durch den Menschen oder durch den Agenten, der den Lauf
angestossen hat. Das Programm wartet NICHT, bis die Stunde um ist: sind die
Gewichte stabil, hoert es auf und sagt es. Ein Lauf, der eine Stunde rechnet, weil
eine Stunde bestellt war, obwohl nach drei Minuten nichts Neues mehr kam, waere
verschwendete Maschinenzeit.

**Lernen, in Runden zu je ``RUNDE`` gueltigen Entwuerfen:**

* *Stufe 1, analytisch (ms):* Entwuerfe aus den Schemabereichen ziehen, am
  Layouttor filtern, jede Erfahrung mit allen Hebeln pruefen (``ema_erfahrung``),
  je Hebel einen Beleg schreiben: hilft, Konflikt, reicht nicht.
* *Trainingsplan:* nicht bloss zufaellig ziehen, sondern ALLES probieren. Der Plan
  ist das Raster Bauform x Polpaarzahl (6 x 5 = 30 Zellen); gezogen wird reihum,
  Zelle fuer Zelle, sodass jede gleich oft drankommt und der Bericht je Zelle
  sagen kann, was dort hilft. Innerhalb einer Zelle sind die Masse zufaellig.
* *Kombinationen:* an jedem Entwurf mit Symptom zusaetzlich jedes geordnete
  Hebelpaar (``ema_erfahrung.kombinationen``: A zur Haelfte, dann B so weit wie
  noetig). Gezaehlt wird wie bei Einzelhebeln (Beleg-Id ``A+B``), dazu, ob das Paar
  nach Pareto gegen alle helfenden Einzelhebel besteht und wie viel von B noch
  noetig war (``bedarf_b``; 0,5 = linear, darunter ergaenzen sich die beiden).
* *Preisprobe:* waehlen ``Kt`` (Magnetmoment) und Spitzenmoment (mit Reluktanz)
  denselben besten Hebel? Die erste Fassung verglich hier ein Momentmass
  ``B_gap·D_r²·L`` mit Kt und fand 0 % gegen -4,7 % -- daraus wurde der Befund,
  dass der Fluss je Pol bei festen Magneten erhalten bleibt (``BEFUNDE.md``).

**Stabil** heisst: nach mindestens ``MIN_ENTWUERFE`` aendert sich keine Hilft-Quote
zwischen zwei Runden um mehr als ``STABIL_PP`` Prozentpunkte.

**Stufe 2 (noch nicht gebaut): echte Laeufe.** Ein Entwurfslauf kostet gut 10
Minuten; die gehoeren an die Stellen, die dieser Bericht als strittig ausweist.

**Mitschrift.** Jeder Lauf legt ``~/cae_projekte/_lernen/lernlaeufe/<marke>/``
an: ``bericht.md`` (Ergebnisse und Erkenntnisse, ohne Sprachmodell aus den Zahlen
abgeleitet), ``daten.json``, ``protokoll.log`` (von Beginn an mitgeschrieben, samt qwens
Rundenkommentaren), ``deutung_qwen.md`` und eine Zeile in ``index.jsonl``. Die Erkenntnisse
sind Regeln ueber Zahlen („Hebel X hilft in a %"), keine Prosa -- was sie
bedeuten, ist der Teil, fuer den die Auswertungszeit reserviert ist.

Was die Zahlen bedeuten: eine Eigenschaft des MODELLS ueber dem gezogenen Raum,
kein Naturgesetz; die Ziehung steht deshalb im Bericht.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import time

import ema_erfahrung as E

BAUFORMEN = ("v", "vv", "u", "delta", "spoke", "bar")
RUNDE = 200
MIN_ENTWUERFE = 1000
STABIL_PP = 0.5
ABLAGE = os.path.expanduser("~/cae_projekte/_lernen/lernlaeufe")


def entwurf(basis: dict, rng: random.Random, zelle: dict | tuple | None = None) -> dict:
    """Ein gezogener PSM-Entwurf auf Grundlage eines vollstaendigen Payloads.

    ``zelle`` legt fest, was der Trainingsplan an dieser Stelle vorgibt: ``magShape``,
    ``p`` und/oder ``stator_lam`` (Tupel ``(Bauform, p)`` wie bisher)."""
    if isinstance(zelle, tuple):
        zelle = {"magShape": zelle[0], "p": zelle[1]}
    zelle = zelle or {}
    import ema_text2ema as T2E
    S = T2E.SCHEMA
    p = {**basis, "geom": dict(basis["geom"])}
    g = p["geom"]
    od = rng.uniform(max(S["statorOD"]["lo"], 120.0), min(S["statorOD"]["hi"], 400.0))
    ratio = rng.uniform(0.55, 0.72)                    # Bohrung / Aussendurchmesser
    spalt = rng.uniform(0.5, 1.5)
    sid = od * ratio
    g.update(statorOD=round(od, 1), statorID=round(sid, 1), rotorOD=round(sid - 2 * spalt, 1),
             shaftD=round(max(S["shaftD"]["lo"], (sid - 2 * spalt) * rng.uniform(0.25, 0.4)), 1),
             p=zelle.get("p") or rng.choice(POLPAARE),
             magShape=zelle.get("magShape") or rng.choice(BAUFORMEN))
    if zelle.get("stator_lam"):
        p["stator_lam"] = zelle["stator_lam"]
    # Die Magnetmasze folgen dem Laeufer: Laenge als Anteil der Polteilung, Dicke und
    # Abstaende mit dem Durchmesser. Fest aus dem Grundentwurf (42 mm Magnet an jeder
    # Maschine) blieben 11 von 30 Zellen ohne einen einzigen gueltigen Entwurf --
    # Doppel-V bei JEDER Polzahl -- und der Plan haette sie still nie probiert.
    rod = float(g["rotorOD"])
    s_ = rod / 190.0
    teilung = 3.14159 * rod / (2 * int(g["p"]))
    def klemm(k, w):
        return round(max(S[k]["lo"], min(S[k]["hi"], w)), 2)
    g.update(magWidth=klemm("magWidth", teilung * rng.uniform(0.2, 0.55)),
             magThick=klemm("magThick", rng.uniform(3.0, 8.0) * s_),
             magDist=klemm("magDist", rng.uniform(2.0, 10.0) * s_),
             magDepthRel=klemm("magDepthRel", rng.uniform(0.5, 0.85)),
             magLayerGap=klemm("magLayerGap", rng.uniform(4.0, 12.0) * s_),
             magAngle=klemm("magAngle", rng.uniform(90.0, 150.0)), magTangLen=0)
    wand = (od - sid) / 2.0
    g["slotDepth"] = round(wand * rng.uniform(0.45, 0.92), 1)
    return p


POLPAARE = (2, 3, 4, 5, 6)
VERSUCHE_JE_ZELLE = 300


class _QwenWaechter:
    """Qwen schaut nach jeder Runde auf die Quoten -- im Hintergrund, ohne das Lernen aufzuhalten.

    Ist der vorige Kommentar noch nicht fertig, wird die Runde uebersprungen statt
    gestaut. Der Kommentar ist eine Zeile im Protokoll und entscheidet NICHTS: Ende,
    Quoten und Bericht kommen aus den Zahlen."""

    def __init__(self, log):
        self.log = log
        self.faden = None
        self.kommentare: list = []

    def runde(self, nr, quoten, mit_symptom, gueltig, leer):
        import threading
        if self.faden and self.faden.is_alive():
            return
        tab = "; ".join(f"{k} {v:.1f} %" for k, v in sorted(quoten.items()))
        prompt = (f"Lernlauf, Runde {nr}: {gueltig} gueltige PSM-Entwuerfe, {mit_symptom} mit Symptom. "
                  f"Hilft-Quoten je Hebel: {tab}. Leere Zellen im Trainingsplan: {', '.join(leer) or 'keine'}. "
                  "Antworte in EINEM deutschen Satz: ist etwas auffaellig, das der Mensch wissen sollte? "
                  "Keine neuen Zahlen.")

        def los():
            try:
                import ema_report as R
                t = R.call_ollama(prompt, timeout=120).strip().splitlines()[0][:300]
                self.kommentare.append({"runde": nr, "text": t})
                self.log(f"  qwen (Runde {nr}): {t}")
            except Exception as e:                                   # noqa: BLE001
                self.log(f"  qwen (Runde {nr}) nicht erreichbar: {type(e).__name__}")
        self.faden = threading.Thread(target=los, daemon=True)
        self.faden.start()

    def warten(self, s):
        if self.faden:
            self.faden.join(s)


# Die Elektrobleche aus ``ema_pipeline.LAMINATES``; Vollmaterial (S235, 42CrMo4) ist
# kein Statorblech und bleibt draussen.
BLECHE = ("m250_35a", "m270_35a", "m400_50a", "m800_65a")

# Was „heute lernen" heissen kann. ``bericht`` lernt nichts: es fasst alle bisherigen
# Belege und Laeufe zusammen, und qwen schreibt die Deutung dazu.
BEREICHE = {
    "bauformen": "jede Magnetbauform mit jeder Polpaarzahl (6 x 5 Zellen)",
    "materialien": "jedes Elektroblech (M250 … M800, Knie 1,65 … 1,85 T) mit jeder Polpaarzahl (4 x 5 Zellen)",
    "bericht": "nichts lernen, sondern einen Gesamtbericht ueber alle bisherigen Laeufe schreiben",
}
VORSCHLAG = os.path.expanduser("~/cae_projekte/_lernen/naechster_vorschlag.json")


def trainingsplan(bereich: str = "bauformen") -> list:
    """Die Zellen, die reihum drankommen -- je Bereich ein anderes Raster."""
    if bereich == "materialien":
        return [{"stator_lam": b, "p": p} for b in BLECHE for p in POLPAARE]
    return [{"magShape": b, "p": p} for b in BAUFORMEN for p in POLPAARE]


def zellname(z: dict) -> str:
    return "/".join(str(z[k]) for k in ("magShape", "stator_lam", "p") if k in z)


def _quoten(zaehler: dict) -> dict:
    q = {}
    for eid, hebel in zaehler.items():
        for h, c in hebel.items():
            ges = sum(c.values())
            if ges:
                q[f"{eid}/{h}"] = 100.0 * c["hilft"] / ges
    return q


def lauf(minuten: float | None = None, auswertung_anteil: float = 0.25, n: int | None = None,
         seed: int | None = None, basis: dict | None = None, preisprobe: bool = True,
         ablage: str | None = None, log=print, abbrechen=lambda: False,
         kombinieren: bool = True, fortschritt=None, deuten_mit_qwen: bool = False,
         bereich: str = "bauformen") -> dict:
    """Ein Lernlauf nach Zeitplan (``minuten``) oder Anzahl (``n``); mit beidem gilt, was zuerst eintritt."""
    import ema_maschinenart as MA
    from ema_rotorcheck import rotor_layout_check
    if basis is None:
        from cae_cli import frischer_payload
        basis = frischer_payload("radial")
    if minuten is None and n is None:
        n = MIN_ENTWUERFE
    seed = int(time.time()) % 100000 if seed is None else seed
    rng = random.Random(seed)
    marke = time.strftime("%Y%m%d_%H%M%S")
    t0 = time.time()
    lern_s = None if minuten is None else 60.0 * minuten * (1.0 - auswertung_anteil)
    # Mitschrift von Anfang an: jede Zeile (auch qwens Rundenkommentare) geht sofort
    # nach ``<marke>/protokoll.log`` -- lesbar, waehrend der Lauf noch laeuft, und
    # danach fuer jeden, der wissen will, wie es zum Bericht kam.
    _ordner = os.path.join(ablage or ABLAGE, marke)
    os.makedirs(_ordner, exist_ok=True)
    _log_pfad = os.path.join(_ordner, "protokoll.log")
    _log_aussen = log

    def log(t):
        try:
            with open(_log_pfad, "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%H:%M:%S ") + str(t) + "\n")
        except OSError:
            pass
        _log_aussen(t)
    log(f"Lernlauf {marke}: seed {seed}, "
        + (f"Zeitplan {minuten:g} min ({int(100 * auswertung_anteil)} % Auswertung)" if minuten is not None else f"n={n}")
        + f", Kombinationen {'an' if kombinieren else 'aus'}, qwen {'an' if deuten_mit_qwen else 'aus'}")
    _waechter = _QwenWaechter(log) if deuten_mit_qwen else None
    if bereich not in BEREICHE:
        raise ValueError(f"unbekannter Bereich {bereich!r} -- {', '.join(BEREICHE)}")
    if bereich == "bericht":
        return gesamtbericht(ablage=ablage, log=log, deuten_mit_qwen=deuten_mit_qwen)
    plan = trainingsplan(bereich)
    zeiger = 0
    leer: set = set()
    zellen: dict = {}                 # "bauform/p" -> {gueltig, symptom, hilft: {hebel: n}}
    kombi: dict = {}                  # "A+B" -> {hilft, konflikt, reicht_nicht, pareto, bedarf: [...]}
    quelle = f"lernprogramm {marke} seed={seed}"
    zaehler_vorher = {eid: E.zaehler(eid) for eid in E.ERFAHRUNGEN}

    gezogen = gueltig = mit_symptom = 0
    lauf_zaehler: dict = {}
    preise: list = []                 # je Hebel, der hilft: Spitzenmoment- und Kt-Aenderung
    rangfolge = {"gleich": 0, "anders": 0, "gleichstand": 0}
    konflikte: list = []
    runden: list = []
    ende = "anzahl"
    q_alt = None
    stabil_in_folge = 0

    def zeit_um():
        return lern_s is not None and time.time() - t0 > lern_s

    while True:
        if abbrechen():
            ende = "abgebrochen"
            break
        if n is not None and gueltig >= n:
            ende = "anzahl"
            break
        if zeit_um():
            ende = "zeit"
            break
        if len(leer) == len(plan):
            ende = "raum_leer"
            break
        zelle = plan[zeiger % len(plan)]
        zeiger += 1
        zname = zellname(zelle)
        if zname in leer:
            continue
        zk = zellen.setdefault(zname, {"gueltig": 0, "symptom": 0, "hilft": {}, "versuche": 0})
        # Je Zelle hoechstens VERSUCHE_JE_ZELLE Ziehungen fuer EINEN gueltigen Entwurf;
        # bleibt eine Zelle beim ersten Mal ganz leer, faellt sie aus dem Plan und
        # steht als leer im Bericht (eine Bauform, die bei dieser Polzahl im
        # Ziehungsraum nie passt, ist auch eine Auskunft).
        p = None
        for _ in range(VERSUCHE_JE_ZELLE):
            gezogen += 1
            zk["versuche"] += 1
            q = entwurf(basis, rng, zelle)
            if MA.art_code(q["geom"]) == "pmsm" and rotor_layout_check(q["geom"]).get("ok"):
                p = q
                break
        if p is None:
            if zk["gueltig"] == 0:
                leer.add(zname)
            continue
        g0 = p["geom"]
        gueltig += 1
        zk["gueltig"] += 1
        try:
            r = E.pruefe(p, merken=True, quelle=quelle)
        except Exception as ex:                        # noqa: BLE001
            log(f"  Entwurf {gueltig}: nicht pruefbar ({ex})")
            continue
        if r["treffer"]:
            mit_symptom += 1
            zk["symptom"] += 1
        for t in r["treffer"]:
            lz = lauf_zaehler.setdefault(t["id"], {})
            versuch = []
            for h in t["hebel"]:
                if h["status"] == "fest":
                    continue
                c = lz.setdefault(h["id"], {"hilft": 0, "konflikt": 0, "reicht_nicht": 0})
                c[h["status"]] += 1
                if h["status"] == "konflikt" and len(konflikte) < 15:
                    konflikte.append({"hebel": h["id"], "neu": h["neue_symptome"],
                                      "geom": {k: g0.get(k) for k in ("statorOD", "statorID", "rotorOD", "slotDepth", "p", "magShape")},
                                      "aenderung": h.get("aenderung")})
                if h["status"] == "hilft":
                    zk["hilft"][h["id"]] = zk["hilft"].get(h["id"], 0) + 1
                    if preisprobe and h.get("moment_pct") is not None:
                        preise.append({"erfahrung": t["id"], "hebel": h["id"],
                                       "moment_pct": h["moment_pct"], "kt_pct": h["kt_pct"]})
                        versuch.append((h["id"], h["moment_pct"], h["kt_pct"]))
            if len(versuch) >= 2:
                # Gleichstand ausweisen: liegen die beiden Besten naeher als 0,1 %
                # beieinander, waehlt das Mass keinen -- das ist die Auskunft.
                def bester(i):
                    v = sorted(versuch, key=lambda x: -x[i])
                    return None if v[0][i] - v[1][i] < 0.1 else v[0][0]
                a, b = bester(1), bester(2)
                rangfolge["gleichstand" if a is None or b is None else ("gleich" if a == b else "anders")] += 1
            if kombinieren:
                for k in E.kombinationen(p, t):
                    c = kombi.setdefault(k["id"], {"hilft": 0, "konflikt": 0, "reicht_nicht": 0,
                                                   "pareto": 0, "bedarf": [], "moment": []})
                    c[k["status"]] += 1
                    E.beleg(t["id"], k["id"], k["status"], quelle=quelle,
                            daten={"kt_pct": k.get("kt_pct"), "moment_pct": k.get("moment_pct"),
                                   "bedarf_b": k.get("bedarf_b"), "aenderung": k.get("aenderung")})
                    if k["status"] == "hilft":
                        c["pareto"] += bool(k.get("pareto"))
                        if k.get("bedarf_b") is not None:
                            c["bedarf"].append(k["bedarf_b"])
                        if k.get("moment_pct") is not None:
                            c["moment"].append(k["moment_pct"])
        if fortschritt:
            fortschritt({"gueltig": gueltig, "gezogen": gezogen, "mit_symptom": mit_symptom,
                         "sekunden": round(time.time() - t0, 1), "lern_s": lern_s, "n": n})

        if gueltig % RUNDE == 0:
            q = _quoten({eid: lauf_zaehler.get(eid, {}) for eid in E.ERFAHRUNGEN})
            delta = max((abs(q[k] - q_alt.get(k, q[k])) for k in q), default=0.0) if q_alt else None
            runden.append({"gueltig": gueltig, "sekunden": round(time.time() - t0, 1),
                           "max_aenderung_pp": None if delta is None else round(delta, 2)})
            log(f"  Runde {len(runden)}: {gueltig} gueltig ({gezogen} gezogen), {mit_symptom} mit Symptom, "
                f"{time.time() - t0:.0f} s" + ("" if delta is None else f", Quoten-Aenderung max {delta:.2f} pp"))
            if delta is not None and delta < STABIL_PP:
                stabil_in_folge += 1
            else:
                stabil_in_folge = 0
            q_alt = q
            if deuten_mit_qwen:
                _waechter.runde(len(runden), q, mit_symptom, gueltig, sorted(leer))
            if minuten is not None and n is None and gueltig >= MIN_ENTWUERFE and stabil_in_folge >= 2:
                ende = "stabil"
                break

    if _waechter:
        _waechter.warten(30.0)
    lern_ende = time.time()
    ergebnis = {"marke": marke, "seed": seed, "quelle": quelle, "ende": ende,
                "zeitplan": None if minuten is None else {"minuten": minuten, "auswertung_anteil": auswertung_anteil,
                                                          "lernen_hoechstens_s": round(lern_s, 1)},
                "gezogen": gezogen, "gueltig": gueltig, "mit_symptom": mit_symptom,
                "lern_sekunden": round(lern_ende - t0, 1), "runden": runden,
                "dieser_lauf": lauf_zaehler,
                "gesamt": {eid: E.zaehler(eid) for eid in E.ERFAHRUNGEN},
                "vorher": zaehler_vorher, "preise": preise, "rangfolge": rangfolge,
                "konflikte": konflikte, "zellen": zellen,
                "qwen_runden": _waechter.kommentare if _waechter else [], "kombinationen": kombi,
                "plan": [zellname(z) for z in plan], "bereich": bereich,
                "ziehung": "Stator 120–400 mm, Bohrung/Aussen 0,55–0,72, Spalt 0,5–1,5 mm, "
                           "Nuttiefe 45–92 % der Statorwand; Trainingsplan " + bereich + ": " + BEREICHE[bereich]}
    ergebnis["erkenntnisse"] = erkenntnisse(ergebnis)
    ergebnis["auswertung_sekunden"] = round(time.time() - lern_ende, 2)
    if minuten is not None:
        rest = 60.0 * minuten - (time.time() - t0)
        ergebnis["deutungszeit_min"] = round(max(0.0, rest) / 60.0, 1)
    ablegen(ergebnis, ablage or ABLAGE)
    if deuten_mit_qwen:
        frist = None if minuten is None else max(60.0, 60.0 * minuten - (time.time() - t0))
        ergebnis["deutung"] = deuten(ergebnis, log=log, frist_s=frist)
    ergebnis["vorschlag"] = vorschlag(ergebnis, ablage or ABLAGE)
    log(f"  Vorschlag fuer das naechste Training: {ergebnis['vorschlag']['bereich']}, "
        f"{ergebnis['vorschlag']['minuten']:g} min -- {ergebnis['vorschlag']['gruende'][0]}")
    return ergebnis


def erkenntnisse(r: dict) -> list:
    """Regeln ueber Zahlen -- ohne Sprachmodell, jede mit ihrer Grundlage."""
    z = []
    for eid, hebel in r["dieser_lauf"].items():
        for h, c in sorted(hebel.items(), key=lambda kv: -kv[1]["hilft"]):
            ges = sum(c.values())
            if not ges:
                continue
            hq, kq, rq = (100.0 * c[k] / ges for k in ("hilft", "konflikt", "reicht_nicht"))
            satz = f"{eid}: Hebel {h} hilft in {hq:.1f} % von {ges} Faellen"
            if kq >= 1.0:
                satz += f", loest in {kq:.1f} % ein anderes Symptom aus"
            if rq >= 1.0:
                satz += f", reicht in {rq:.1f} % nicht"
            alt = r["vorher"].get(eid, {}).get(h)
            if alt and sum(alt.values()):
                aq = 100.0 * alt["hilft"] / sum(alt.values())
                satz += f" (vorher {aq:.1f} % aus {sum(alt.values())} Belegen)"
            z.append(satz + ".")
    je = {}
    for p in r["preise"]:
        je.setdefault(f"{p['erfahrung']}/{p['hebel']}", []).append(p)
    for k, ps in je.items():
        mm = statistics.median(x["moment_pct"] for x in ps)
        kt = statistics.median(x["kt_pct"] for x in ps)
        z.append(f"Preis {k}: Spitzenmoment median {mm:+.1f} %, Kt median {kt:+.2f} % (n={len(ps)}).")
    rf = r["rangfolge"]
    if sum(rf.values()):
        ges = sum(rf.values())
        z.append(f"Rangfolge der helfenden Hebel: Spitzenmoment und Kt waehlen in {100.0 * rf['gleich'] / ges:.0f} % "
                 f"denselben besten, in {100.0 * rf['anders'] / ges:.0f} % verschiedene; in "
                 f"{100.0 * rf['gleichstand'] / ges:.0f} % liegen die beiden Besten unter 0,1 % beieinander "
                 f"und eines der Masse waehlt keinen (n={ges}).")
    for kid, c in sorted((r.get("kombinationen") or {}).items(), key=lambda kv: -kv[1]["hilft"]):
        ges = c["hilft"] + c["konflikt"] + c["reicht_nicht"]
        if not ges or not c["hilft"]:
            continue
        satz = f"Kombination {kid}: hilft in {100.0 * c['hilft'] / ges:.1f} % von {ges}"
        satz += f", davon {100.0 * c['pareto'] / c['hilft']:.0f} % von keinem Einzelhebel geschlagen"
        if c["bedarf"]:
            bq = statistics.median(c["bedarf"])
            art = "linear" if abs(bq - 0.5) < 0.03 else ("ergaenzen sich" if bq < 0.5 else "stehen sich im Weg")
            satz += f"; von B noch noetig median {bq:.2f} des Einzelweges ({art})"
        if c["moment"]:
            satz += f"; Spitzenmoment median {statistics.median(c['moment']):+.1f} %"
        z.append(satz + ".")
    leer = [k for k, v in (r.get("zellen") or {}).items() if v["gueltig"] == 0]
    if leer:
        z.append(f"Trainingsplan: in {len(leer)} Zellen kein gueltiger Entwurf ({', '.join(leer[:6])}).")
    grund = {"stabil": "die Quoten waren stabil (zweimal hintereinander unter "
                       f"{STABIL_PP} Prozentpunkten Aenderung)",
             "zeit": "die Lernzeit war um", "anzahl": "die verlangte Anzahl war erreicht",
             "raum_leer": "kaum noch gueltige Entwuerfe im Ziehungsraum", "abgebrochen": "abgebrochen"}
    z.append(f"Ende des Lernens nach {r['lern_sekunden']} s, weil {grund.get(r['ende'], r['ende'])}.")
    return z


def als_text(r: dict) -> str:
    z = [f"# Lernlauf {r['marke']} (PSM, Stufe 1, Trainingsplan + Kombinationen)", ""]
    if r.get("zeitplan"):
        zp = r["zeitplan"]
        z.append(f"Zeitplan: {zp['minuten']:g} min, davon {int(100 * zp['auswertung_anteil'])} % fuer die Auswertung "
                 f"(Lernen hoechstens {zp['lernen_hoechstens_s'] / 60:.1f} min).")
    z.append(f"Gelernt: {r['lern_sekunden']} s, {r['gueltig']} gueltige Entwuerfe aus {r['gezogen']} gezogenen, "
             f"{r['mit_symptom']} mit Symptom. Auswertung: {r.get('auswertung_sekunden', 0)} s.")
    if "deutungszeit_min" in r:
        z.append(f"**Fuer die Deutung bleiben {r['deutungszeit_min']} min.**")
    z.append(f"Ziehung: {r['ziehung']} (seed {r['seed']}).")
    z += ["", "## Erkenntnisse (aus den Zahlen, ohne Sprachmodell)", ""]
    z += [f"- {s}" for s in r["erkenntnisse"]]
    z += ["", "## Gewichtung je Hebel, alle Belege", ""]
    for eid, hebel in r["gesamt"].items():
        for h, c in sorted(hebel.items(), key=lambda kv: -kv[1]["hilft"]):
            ges = sum(c.values()) or 1
            z.append(f"- {eid}/{h}: hilft {100 * c['hilft'] / ges:.1f} %, Konflikt {100 * c['konflikt'] / ges:.1f} %, "
                     f"reicht nicht {100 * c['reicht_nicht'] / ges:.1f} % (n={ges})")
    if r.get("zellen"):
        z += ["", "## Trainingsplan: was je Zelle hilft (gueltig, mit Symptom, helfende Hebel)", ""]
        for k in r["plan"]:
            v = r["zellen"].get(k) or {"gueltig": 0, "symptom": 0, "hilft": {}}
            h = ", ".join(f"{a} {n}" for a, n in sorted(v["hilft"].items(), key=lambda kv: -kv[1])) or "—"
            z.append(f"- {k}: {v['gueltig']} gueltig, {v['symptom']} mit Symptom; hilft: {h}")
    if r.get("qwen_runden"):
        z += ["", "## Was qwen waehrend des Laufs anmerkte (entscheidet nichts)", ""]
        z += [f"- Runde {k['runde']}: {k['text']}" for k in r["qwen_runden"]]
    if r["konflikte"]:
        z += ["", "## Beispiele fuer Konflikte (Kandidaten fuer Stufe 2)", ""]
        for k in r["konflikte"][:8]:
            g = k["geom"]
            z.append(f"- {k['hebel']} -> neu {', '.join(k['neu'])}: Stator {g['statorOD']}/{g['statorID']}, "
                     f"Rotor {g['rotorOD']}, Nut {g['slotDepth']}, p {g['p']}, {g['magShape']}")
    if r["runden"]:
        z += ["", "## Runden", ""]
        z += [f"- {x['gueltig']} Entwuerfe nach {x['sekunden']} s"
              + ("" if x["max_aenderung_pp"] is None else f", Quoten-Aenderung max {x['max_aenderung_pp']} pp")
              for x in r["runden"]]
    z += ["", "Eigenschaft des Modells ueber diesem Raum, kein Naturgesetz. Stufe 2 (echte Laeufe an den "
              "strittigen Stellen) ist noch nicht gebaut."]
    return "\n".join(z)


def ablegen(r: dict, wurzel: str) -> str:
    ordner = os.path.join(wurzel, r["marke"])
    os.makedirs(ordner, exist_ok=True)
    with open(os.path.join(ordner, "bericht.md"), "w", encoding="utf-8") as f:
        f.write(als_text(r) + "\n")
    with open(os.path.join(ordner, "daten.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(wurzel, "index.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"marke": r["marke"], "ende": r["ende"], "gueltig": r["gueltig"],
                            "bereich": r.get("bereich", "bauformen"),
                            "mit_symptom": r["mit_symptom"], "lern_sekunden": r["lern_sekunden"]},
                           ensure_ascii=False) + "\n")
    r["ordner"] = ordner
    return ordner


def deuten(r: dict, modell: str | None = None, log=print, frist_s: float | None = None,
           bericht: str | None = None) -> dict | None:
    """Die Deutung durch das LOKALE Sprachmodell (qwen), in der reservierten Auswertungszeit.

    Der Bericht bleibt die Quelle: er entsteht ohne Sprachmodell aus den Zahlen. Qwen
    bekommt ihn, schreibt ``deutung_qwen.md`` daneben, und jede Zahl seiner Antwort wird
    gegen den Bericht geprueft (``ema_chat.deckung_pruefen``) -- eine erfundene steht als
    ungedeckt unter der Deutung, statt still mitzulaufen. Ohne Ollama: ``None`` und ein
    Satz im Protokoll, der Lauf ist trotzdem fertig."""
    import ema_chat
    import ema_report as R
    bericht = bericht or als_text(r)
    prompt = ("Du wertest einen Lernlauf einer Erfahrungsdatenbank fuer E-Maschinen (PSM) aus. "
              "Der Bericht unten ist ohne Sprachmodell aus Zahlen entstanden und ist massgebend. "
              "Schreibe auf Deutsch, knapp, in drei Abschnitten: 1. Was der Lauf zeigt (nur Zahlen "
              "aus dem Bericht, keine neuen). 2. Was auffaellt oder widerspruechlich ist (z. B. leere "
              "Zellen, Gleichstaende, Konflikte, Kombinationen, die sich im Weg stehen). 3. Was als "
              "Naechstes gerechnet werden sollte (Stufe 2, echte Laeufe) und warum. Erfinde keine "
              "Zahlen und keine Physik, die nicht im Bericht steht.\n\n" + bericht)
    t0 = time.time()
    try:
        text = R.call_ollama(prompt, model=modell or R.DEFAULT_MODEL,
                             timeout=int(max(60, frist_s or 600)))
    except Exception as e:                                           # noqa: BLE001
        log(f"  Deutung durch qwen nicht moeglich ({type(e).__name__}: {e}); der Bericht steht.")
        return None
    ungedeckt = ema_chat.deckung_pruefen(text, bericht)
    out = {"modell": modell or R.DEFAULT_MODEL, "sekunden": round(time.time() - t0, 1),
           "text": text, "ungedeckt": ungedeckt}
    with open(os.path.join(r["ordner"], "deutung_qwen.md"), "w", encoding="utf-8") as f:
        f.write(f"# Deutung {r['marke']} durch {out['modell']} ({out['sekunden']} s)\n\n"
                "Massgebend ist `bericht.md`; das hier ist die Lesart des lokalen Modells.\n\n"
                + text.strip() + "\n")
        if ungedeckt:
            f.write("\n---\n**Ungedeckte Zahlen** (stehen nicht im Bericht): " + ", ".join(map(str, ungedeckt)) + "\n")
    log(f"  Deutung durch {out['modell']} in {out['sekunden']} s, {len(ungedeckt)} ungedeckte Zahl(en).")
    return out


def vorschlag(r: dict, wurzel: str) -> dict:
    """Was als Naechstes gelernt werden sollte -- aus den Zahlen, ohne Sprachmodell.

    Abgelegt im Laufordner (``vorschlag.json``) und als ``naechster_vorschlag.json``
    unter ``_lernen/``; dort liest ihn der Knopf als Vorauswahl und ``--bereich``
    ohne Angabe als Vorgabe. Qwens Vorschlaege (Abschnitt 3 seiner Deutung) stehen
    daneben, entscheiden aber nicht."""
    bisher = {x.get("bereich", "bauformen") for x in laeufe(wurzel)}
    gruende, bereich, minuten = [], r.get("bereich", "bauformen"), 60.0
    nie = [b for b in BEREICHE if b != "bericht" and b not in bisher]
    if nie:
        bereich = nie[0]
        gruende.append(f"Bereich {bereich} wurde noch nie gelernt ({BEREICHE[bereich]}).")
    duenn = [k for k, v in (r.get("zellen") or {}).items() if 0 < v["symptom"] < 10]
    if duenn and not nie:
        minuten = max(30.0, 2 * float((r.get("zeitplan") or {}).get("minuten") or 30))
        gruende.append(f"{len(duenn)} Zellen mit weniger als 10 Symptomfaellen ({', '.join(duenn[:5])}) -- "
                       f"laenger lernen, {minuten:g} min.")
    leer = [k for k, v in (r.get("zellen") or {}).items() if v["gueltig"] == 0]
    if leer:
        gruende.append(f"{len(leer)} Zellen ohne gueltigen Entwurf ({', '.join(leer[:5])}): "
                       "die Ziehung trifft dort nie das Layouttor -- erst die Ziehung ansehen.")
    strittig = []
    for eid, hebel in (r.get("dieser_lauf") or {}).items():
        for h, c in hebel.items():
            ges = sum(c.values())
            if ges >= 10 and c["konflikt"] / ges > 0.05:
                strittig.append(f"{eid}/{h} ({100 * c['konflikt'] / ges:.0f} % Konflikt)")
    if strittig:
        gruende.append("Stufe 2 (echte Laeufe, noch nicht gebaut) gehoert an: " + ", ".join(strittig[:4]) + ".")
    if not gruende:
        gruende.append("Quoten stabil, keine duennen oder leeren Zellen -- naechster Bereich oder ein Gesamtbericht.")
        if bereich == r.get("bereich"):
            bereich = "bericht"
    qwen = None
    d = r.get("deutung") or {}
    if d.get("text"):
        t = d["text"]
        i = max(t.find("3."), 0)
        qwen = t[i:i + 1200].strip()
    v = {"von": r["marke"], "bereich": bereich, "minuten": minuten, "gruende": gruende,
         "qwen": qwen, "zeit": time.strftime("%Y-%m-%d %H:%M")}
    try:
        with open(os.path.join(r["ordner"], "bericht.md"), "a", encoding="utf-8") as f:
            f.write("\n## Vorschlag fuer das naechste Training\n\n"
                    f"Bereich **{bereich}**, {minuten:g} min.\n\n" + "".join(f"- {g}\n" for g in gruende)
                    + (f"\nqwen schlaegt vor (entscheidet nicht):\n\n> " + qwen.replace("\n", "\n> ") + "\n" if qwen else ""))
    except (OSError, KeyError):
        pass
    for pfad in (os.path.join(r.get("ordner") or wurzel, "vorschlag.json"),
                 os.path.join(os.path.dirname(wurzel.rstrip("/")), "naechster_vorschlag.json")):
        try:
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump(v, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
    return v


def naechster_vorschlag(wurzel: str | None = None) -> dict | None:
    pfad = os.path.join(os.path.dirname((wurzel or ABLAGE).rstrip("/")), "naechster_vorschlag.json")
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gesamtbericht(ablage: str | None = None, log=print, deuten_mit_qwen: bool = True) -> dict:
    """Bereich ``bericht``: nichts lernen, sondern alle bisherigen Laeufe zusammenfassen."""
    wurzel = ablage or ABLAGE
    marke = time.strftime("%Y%m%d_%H%M%S") + "_bericht"
    ordner = os.path.join(wurzel, marke)
    os.makedirs(ordner, exist_ok=True)
    alle = laeufe(wurzel)
    z = [f"# Gesamtbericht {marke}", "", f"{len(alle)} Lernlaeufe bisher.", "", "## Laeufe", ""]
    for x in alle[:30]:
        z.append(f"- {x['marke']}: Bereich {x.get('bereich', 'bauformen')}, {x['gueltig']} Entwuerfe, "
                 f"{x['mit_symptom']} mit Symptom, Ende {x['ende']}")
    z += ["", "## Gewichtung je Hebel, alle Belege", ""]
    for eid in E.ERFAHRUNGEN:
        for h, c in sorted(E.zaehler(eid).items(), key=lambda kv: -kv[1]["hilft"]):
            ges = sum(c.values()) or 1
            z.append(f"- {eid}/{h}: hilft {100 * c['hilft'] / ges:.1f} %, Konflikt {100 * c['konflikt'] / ges:.1f} %, "
                     f"reicht nicht {100 * c['reicht_nicht'] / ges:.1f} % (n={ges})")
    z += ["", "## Erkenntnisse der letzten Laeufe", ""]
    for x in alle[:5]:
        try:
            with open(os.path.join(wurzel, x["marke"], "daten.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        z.append(f"### {x['marke']} ({d.get('bereich', 'bauformen')})")
        z += [f"- {e}" for e in d.get("erkenntnisse", [])[:12]]
        z.append("")
    text = "\n".join(z)
    with open(os.path.join(ordner, "bericht.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    r = {"marke": marke, "ordner": ordner, "bereich": "bericht", "ende": "bericht", "gueltig": 0,
         "mit_symptom": 0, "lern_sekunden": 0.0, "erkenntnisse": [f"{len(alle)} Laeufe zusammengefasst."],
         "text": text}
    with open(os.path.join(wurzel, "index.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"marke": marke, "ende": "bericht", "gueltig": 0, "bereich": "bericht",
                            "mit_symptom": 0, "lern_sekunden": 0.0}, ensure_ascii=False) + "\n")
    log(f"Gesamtbericht ueber {len(alle)} Laeufe: {ordner}/bericht.md")
    if deuten_mit_qwen:
        r["deutung"] = deuten(r, log=log, bericht=text)
    return r


def laeufe(wurzel: str | None = None) -> list:
    """Bisherige Lernlaeufe, juengster zuerst."""
    try:
        with open(os.path.join(wurzel or ABLAGE, "index.jsonl"), encoding="utf-8") as f:
            return [json.loads(z) for z in f if z.strip()][::-1]
    except OSError:
        return []
