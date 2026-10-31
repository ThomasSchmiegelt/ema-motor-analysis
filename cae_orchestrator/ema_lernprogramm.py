"""Lernprogramm fuer die Erfahrungsdatenbank -- erst nur PSM.

Die Frage war: „er mal einen Tag lang alles machen und vergleichen, oder es wird
ein Lernprogramm erstellt". Beides, in zwei Stufen, und die Reihenfolge ist
bewusst:

**Stufe 1 (dieses Modul): planvoll statt beliebig, analytisch, Minuten.** Es zieht
Entwuerfe aus den Schemabereichen (Aussendurchmesser, Rotor/Stator-Verhaeltnis,
Nuttiefe, Polzahl, Magnetbauform), verwirft, was das Layouttor nicht besteht, und
prueft jede Erfahrung aus ``ema_erfahrung`` daran -- mit allen Hebeln. Jeder
Hebel hinterlaesst einen Beleg: geholfen, Konflikt (loest ein anderes Symptom
aus), reicht nicht. Daraus entsteht die Gewichtung UEBER viele Maschinen, die
``erfahrung liste`` und ``erfahrung pruefe`` mitfuehren. Kein Sprachmodell, kein
Server; eine Pruefung kostet Millisekunden bis wenige Sekunden.

**Stufe 2 (noch nicht gebaut): ein Tag echter Laeufe.** Ein voller Entwurfslauf
kostet gut 10 Minuten, ein Tag also rund 140 Laeufe. Die sind zu wertvoll, um
beliebig gezogen zu werden: sie gehoeren an die Stellen, an denen Stufe 1 einen
Hebel als knapp oder strittig ausweist, und pruefen dort die analytische Aussage
gegen den gerechneten Lauf. Eine FDM-Gegenprobe des Statorjochs taugt dafuer nicht
-- |B| im Statoreisen konvergiert bei den bezahlbaren Aufloesungen nicht
(``ema_saettigung``, s. BEFUNDE.md).

Was die Zahlen bedeuten: ein Anteil „hilft" sagt, wie oft ein Hebel das Symptom an
einer zufaelligen gueltigen Maschine behebt, ohne ein neues auszuloesen. Das ist
eine Eigenschaft des MODELLS ueber dem gezogenen Raum, kein Naturgesetz -- und die
Ziehung bestimmt mit, was herauskommt; sie steht deshalb im Ergebnis.
"""

from __future__ import annotations

import random
import time

import ema_erfahrung as E

BAUFORMEN = ("v", "vv", "u", "delta", "spoke", "bar")


def entwurf(basis: dict, rng: random.Random) -> dict:
    """Ein gezogener PSM-Entwurf auf Grundlage eines vollstaendigen Payloads."""
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
             p=rng.choice((2, 3, 4, 5, 6)), magShape=rng.choice(BAUFORMEN))
    wand = (od - sid) / 2.0
    g["slotDepth"] = round(wand * rng.uniform(0.45, 0.92), 1)
    return p


def lauf(n: int = 300, seed: int = 1, basis: dict | None = None, minuten: float | None = None,
         log=print) -> dict:
    """``n`` gueltige Entwuerfe pruefen (oder bis ``minuten`` um sind)."""
    import ema_maschinenart as MA
    from ema_rotorcheck import rotor_layout_check
    if basis is None:
        from cae_cli import frischer_payload
        basis = frischer_payload("radial")
    rng = random.Random(seed)
    marke = f"lernprogramm {time.strftime('%Y%m%d_%H%M%S')} seed={seed}"
    t0 = time.time()
    gezogen = gueltig = mit_symptom = 0
    ausloeser: dict = {}
    while gueltig < n:
        if minuten and time.time() - t0 > 60 * minuten:
            break
        gezogen += 1
        if gezogen > 50 * n:                           # Raum fast leer: ehrlich abbrechen
            break
        p = entwurf(basis, rng)
        if MA.art_code(p["geom"]) != "pmsm" or not rotor_layout_check(p["geom"]).get("ok"):
            continue
        gueltig += 1
        try:
            r = E.pruefe(p, merken=True, quelle=marke)
        except Exception as ex:                        # noqa: BLE001 -- ein Entwurf, kein Abbruch
            log(f"  Entwurf {gueltig}: nicht pruefbar ({ex})")
            continue
        if r["treffer"]:
            mit_symptom += 1
        for t in r["treffer"]:
            ausloeser[t["id"]] = ausloeser.get(t["id"], 0) + 1
        if gueltig % 50 == 0:
            log(f"  {gueltig}/{n} gueltig ({gezogen} gezogen), {mit_symptom} mit Symptom, "
                f"{time.time() - t0:.0f} s")
    return {"marke": marke, "gezogen": gezogen, "gueltig": gueltig, "mit_symptom": mit_symptom,
            "ausloeser": ausloeser, "sekunden": round(time.time() - t0, 1),
            "zaehler": {eid: E.zaehler(eid) for eid in E.ERFAHRUNGEN},
            "ziehung": "Stator 120–400 mm, Bohrung/Aussen 0,55–0,72, Spalt 0,5–1,5 mm, "
                       "Nuttiefe 45–92 % der Statorwand, p 2–6, Bauformen " + "/".join(BAUFORMEN)}


def als_text(r: dict) -> str:
    z = [f"LERNPROGRAMM (PSM, Stufe 1 analytisch) — {r['marke']}",
         f"  {r['gueltig']} gueltige Entwuerfe aus {r['gezogen']} gezogenen in {r['sekunden']} s; "
         f"{r['mit_symptom']} zeigten ein Symptom.",
         f"  Ziehung: {r['ziehung']}"]
    for eid, n in r["ausloeser"].items():
        z.append(f"  {eid}: {n}× ausgeloest")
    z.append("  Gewichtung je Hebel (alle bisherigen Belege, nicht nur dieser Lauf):")
    for eid, hebel in r["zaehler"].items():
        for h, c in sorted(hebel.items(), key=lambda kv: -kv[1]["hilft"]):
            ges = sum(c.values()) or 1
            z.append(f"    {eid}/{h:<16} hilft {100 * c['hilft'] / ges:5.1f} %  Konflikt {100 * c['konflikt'] / ges:5.1f} %  "
                     f"reicht nicht {100 * c['reicht_nicht'] / ges:5.1f} %  (n={ges})")
    z.append("  Eigenschaft des Modells ueber diesem Raum, kein Naturgesetz. Stufe 2 (echte Laeufe an den strittigen Stellen) ist noch nicht gebaut.")
    return "\n".join(z)
