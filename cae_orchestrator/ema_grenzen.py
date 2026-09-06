"""Grenzen, die IMMER gelten -- und die Probe, dass CAD und Feld dieselbe Maschine meinen.

Warum dieses Modul entsteht
----------------------------

Zwei Groessen sind keine Auslegungsentscheidung, sondern Bauwirklichkeit, und
beide standen bisher nirgends als Tor:

1. **Der Luftspalt liegt zwischen 0,1 und 2,0 mm.** Er war an VIER Stellen
   verschieden gebunden -- ``ema_design_ai`` 0,5-3,0 · ``ema_optimize`` 0,1-3,0 ·
   ``ema_mobil`` 0,3-5,0 · ``ema_analysis`` mit einer stillen Klemme auf 0,3 --
   und an keiner davon so, wie eine gebaute Maschine aussieht. ``statorID`` und
   ``rotorOD`` sind ausserdem zwei UNABHAENGIGE Schemafelder: ``--set
   rotorOD=170`` neben ``statorID=190`` ergibt 10 mm Spalt, und nichts
   widersprach.
2. **Der Wickelkopf bleibt unter dem Statoraussendurchmesser.** Die Staebe
   koennen die Nut nicht verlassen, die Krone aber faechert radial auf --
   gemessen an einer 280/190-Maschine mit 6 Leitern und 4 Grad Spreizung liegt
   sie 0,5 mm unter dem Rand, bei 6 Grad daruber. Gezeichnet wurde das trotzdem.

Beide Grenzen sind **Tore, keine Warnungen**: eine Zahl ausserhalb ist kein
ungenauer Entwurf, sondern eine Maschine, die es nicht gibt. Wer sie ausdruecklich
will, setzt die Freigabe im Payload -- dann steht die Ueberschreitung im Klartext
im Ergebnis, statt unbemerkt durchzugehen.

Und die dritte Pruefung: passen CAD und Feld zusammen?
-------------------------------------------------------

Die Toolchain hat zwei Geometriewege, die aus DEMSELBEN ``geom`` verschiedene
Koerper bauen: ``ema_freecad`` zeichnet, ``ema_analysis._rasterise`` /
``ema_em3d.slot_rects`` rastern. Laufen sie auseinander, rechnet der Loeser eine
andere Maschine als die gezeichnete -- und beide Ergebnisse sehen fuer sich
plausibel aus. ``cad_gegen_feld`` stellt die Zahlen beider Seiten nebeneinander
und benennt die Unterschiede, statt sie zu vermuten.

Zwei sind dabei bekannt und BLEIBEN, weil sie gewollt sind; sie stehen als
``hinweis`` da, nicht als Fehler:

* Die **Nut** ist im CAD ein Rechteck fester Breite, im Feld ein Winkelsektor.
  Am Bohrungsrand stimmen beide (gemessen 8,290 gegen 8,288 mm), zum Nutgrund
  hin laeuft der Sektor auf (10,469 mm) -- der Zahn ist im Feld also schmaler
  als gezeichnet.
* Die **3-D-Stufe** fuehrt den Statorleiter gerade bis auf den Rand statt als
  Krone (Begruendung im Kopf von ``ema_em3d_harm``); sie zeichnet keinen
  Wickelkopf und will auch keinen.
"""

from __future__ import annotations

import math

# Der Luftspalt einer gebauten Maschine. Untergrenze: darunter traegt keine
# Lagerung und keine Fertigung. Obergrenze: darueber ist es keine E-Maschine
# mehr, sondern ein Versuchsaufbau -- die Hauptinduktivitaet faellt mit 1/g.
LUFTSPALT_MM = (0.1, 2.0)

# Payload-Schluessel, mit denen sich eine Grenze ausdruecklich oeffnen laesst.
# Absichtlich sprechend und nicht abkuerzbar: wer sie setzt, soll es gemeint haben.
FREIGABE = {
    "luftspalt": "luftspaltFreigabe",
    "hairpin": "hairpinFreigabe",
    "nuttiefe": "nuttiefeFreigabe",
}


class GrenzeVerletzt(ValueError):
    """Eine Grenze, die immer gilt, ist verletzt -- und nicht freigegeben."""


def _geom(quelle) -> dict:
    return dict((quelle or {}).get("geom") or quelle or {})


def _frei(geom: dict, name: str) -> bool:
    return bool(geom.get(FREIGABE[name], False))


# ── 1. Luftspalt ──────────────────────────────────────────────────────────────

def luftspalt(quelle) -> float:
    """Der Luftspalt in mm, ueber ``ema_radien`` -- also fuer BEIDE Bauformen."""
    import ema_radien
    return float(ema_radien.radien(_geom(quelle))["luftspalt_mm"])


def pruefe_luftspalt(quelle) -> dict:
    g = _geom(quelle)
    spalt = luftspalt(g)
    lo, hi = LUFTSPALT_MM
    ok = lo <= spalt <= hi
    return {
        "name": "luftspalt", "ok": ok, "wert_mm": round(spalt, 4),
        "band_mm": [lo, hi], "freigegeben": _frei(g, "luftspalt"),
        "text": (f"Luftspalt {spalt:.3f} mm"
                 + ("" if ok else
                    f" liegt ausserhalb {lo}–{hi} mm. Der Spalt folgt aus "
                    f"statorID und rotorOD und ist damit KEIN eigenes Feld — "
                    f"eines der beiden Masse gehoert geaendert. Ausdruecklich "
                    f"gewollt? Dann geom.{FREIGABE['luftspalt']} = true.")),
    }


# ── 2. Wickelkopf unter dem Statoraussendurchmesser ───────────────────────────

def pruefe_hairpin(quelle) -> dict:
    import ema_wicklung
    g = _geom(quelle)
    if ema_wicklung.art(g) != "hairpin":
        return {"name": "hairpin", "ok": True, "text": "keine Hairpins",
                "freigegeben": False, "entfaellt": True}
    r = ema_wicklung.hairpin_radien(g)
    ok = r["r_aussen_mm"] < r["r_stator_aussen_mm"]
    woher = max((("Krone", r["r_krone_aussen_mm"]),
                 ("Schweissseite", r["r_schweiss_aussen_mm"]),
                 ("Isolierhuelse", r["r_isolierung_aussen_mm"]),
                 ("aeusserste Lage", r["r_lage_aussen_mm"])), key=lambda t: t[1])[0]
    return {
        "name": "hairpin", "ok": ok, "freigegeben": _frei(g, "hairpin"),
        "d_hairpin_mm": round(r["d_aussen_mm"], 3),
        "d_stator_mm": round(2 * r["r_stator_aussen_mm"], 3),
        "ueberstand_mm": round(r["ueberstand_mm"], 4),
        "weiteste_stelle": woher, "radien": r,
        "text": (f"Wickelkopf aussen {r['d_aussen_mm']:.1f} mm gegen Stator "
                 f"{2 * r['r_stator_aussen_mm']:.1f} mm (weiteste Stelle: {woher})"
                 + ("" if ok else
                    f" — steht {r['ueberstand_mm']:+.2f} mm ueber. Kleinere "
                    f"windingHeadFlare/windingHeadSpread, weniger Leiter je Nut "
                    f"oder groesserer statorOD. Ausdruecklich gewollt? Dann "
                    f"geom.{FREIGABE['hairpin']} = true.")),
    }


# ── 3. Nuttiefe: CAD schneidet, das Feld klemmt ───────────────────────────────

def pruefe_nuttiefe(quelle) -> dict:
    """Die Nut darf das Rueckenjoch nicht auffressen.

    Gefunden beim Vergleich der beiden Geometriewege: ``ema_em3d.slot_rects``
    deckelt die Nuttiefe auf ``(r_so - r_si) - 1 mm`` und laesst 1 mm Joch
    stehen; ``ema_freecad`` deckelt NICHT und schneidet die Nut bei zu grosser
    ``slotDepth`` durch den Statorruecken. Das Feld rechnet dann ein Joch, das
    die Zeichnung nicht hat.
    """
    g = _geom(quelle)
    r_si = float(g.get("statorID", 0.0)) / 2.0
    r_so = float(g.get("statorOD", 0.0)) / 2.0
    tiefe = float(g.get("slotDepth", 0.0) or 0.0)
    wand = r_so - r_si
    deckel = max(1.0, wand - 1.0)
    ok = tiefe <= deckel
    return {
        "name": "nuttiefe", "ok": ok, "freigegeben": _frei(g, "nuttiefe"),
        "nuttiefe_mm": round(tiefe, 3), "statorwand_mm": round(wand, 3),
        "deckel_mm": round(deckel, 3),
        "text": (f"Nuttiefe {tiefe:.1f} mm in {wand:.1f} mm Statorwand"
                 + ("" if ok else
                    f" — das Feld deckelt auf {deckel:.1f} mm und laesst 1 mm "
                    f"Joch stehen, das CAD schneidet durch. Die beiden rechnen "
                    f"dann verschiedene Maschinen.")),
    }


PRUEFUNGEN = (pruefe_luftspalt, pruefe_hairpin, pruefe_nuttiefe)


def pruefe(quelle) -> dict:
    """Alle Grenzen auf einmal. Sammelt ALLE Befunde, bricht nicht beim ersten ab."""
    befunde = [f(quelle) for f in PRUEFUNGEN]
    verletzt = [b for b in befunde if not b["ok"] and not b.get("freigegeben")]
    frei = [b for b in befunde if not b["ok"] and b.get("freigegeben")]
    return {"ok": not verletzt, "befunde": befunde,
            "verletzt": verletzt, "freigegeben": frei}


def pruefe_hart(quelle) -> dict:
    """Wie ``pruefe``, wirft aber bei einer nicht freigegebenen Verletzung."""
    erg = pruefe(quelle)
    if erg["verletzt"]:
        raise GrenzeVerletzt(" · ".join(b["text"] for b in erg["verletzt"]))
    return erg


def als_text(erg: dict) -> str:
    z = []
    for b in erg["befunde"]:
        if b.get("entfaellt"):
            marke = "–"
        elif b["ok"]:
            marke = "✓"
        elif b.get("freigegeben"):
            marke = "⚠"
        else:
            marke = "✗"
        zusatz = "  [ausdruecklich freigegeben]" if (not b["ok"] and b.get("freigegeben")) else ""
        z.append(f"  {marke} {b['text']}{zusatz}")
    return "\n".join(z)


# ── 4. Zeichnet das CAD dieselbe Maschine, die das Feld rechnet? ──────────────

def cad_gegen_feld(quelle, axial_mm: float = 0.0) -> dict:
    """Die Zahlen BEIDER Geometriewege nebeneinander, aus demselben ``geom``.

    Verglichen wird nur, was beide Seiten wirklich selbst ausrechnen -- nicht,
    was sie aus derselben Funktion holen. Wo eine Groesse aus einer geteilten
    Quelle kommt (``ema_topology.magnet_legs``, ``ema_asm.kaefig``), steht das
    als solches da: dort KANN nichts auseinanderlaufen, und eine Zeile
    „stimmt ueberein" waere Beruhigung ohne Aussage.
    """
    import ema_analysis
    import ema_em3d
    import ema_radien
    import ema_topology
    import ema_wicklung

    g = _geom(quelle)
    axial = float(axial_mm or g.get("axialLen") or 0.0)
    r_si = float(g["statorID"]) / 2.0
    r_so = float(g["statorOD"]) / 2.0
    n_slots = max(int(g.get("slots", 1) or 1), 1)
    tiefe = float(g.get("slotDepth", 0.0) or 0.0)

    zeilen, hinweise = [], []

    # Radien
    r_feld = ema_radien.radien(g)
    zeilen.append({"groesse": "Statorbohrung r_si [mm]",
                   "cad": round(r_si, 4), "feld": round(r_feld["r_stator_innen_mm"], 4)})
    zeilen.append({"groesse": "Stator aussen r_so [mm]",
                   "cad": round(r_so, 4), "feld": round(r_feld["r_stator_aussen_mm"], 4)})
    zeilen.append({"groesse": "Luftspalt [mm]",
                   "cad": round((float(g["statorID"]) - float(g["rotorOD"])) / 2.0, 4),
                   "feld": round(r_feld["luftspalt_mm"], 4)})

    # Nut -- die eine Stelle, an der die beiden Wege verschieden BAUEN
    ng = ema_wicklung.nutgeometrie(g)
    dth = 2.0 * math.pi / n_slots
    sw = dth * 0.5 / 2.0
    zeilen.append({"groesse": "Nutbreite am Bohrungsrand [mm]",
                   "cad": round(ng["nut_breite_mm"], 4),
                   "feld": round(2.0 * r_si * math.sin(sw), 4)})
    zeilen.append({"groesse": "Nutbreite am Nutgrund [mm]",
                   "cad": round(ng["nut_breite_mm"], 4),
                   "feld": round(2.0 * (r_si + tiefe) * math.sin(sw), 4)})
    hinweise.append("Die Nut ist im CAD ein Rechteck fester Breite, im Feld ein "
                    "Winkelsektor. Am Bohrungsrand stimmen beide, zum Nutgrund hin "
                    "laeuft der Sektor auf — der Zahn ist im Feld schmaler als "
                    "gezeichnet. Gewollt und alt, aber es steht sonst nirgends.")

    # Nuttiefe: das Feld deckelt, das CAD nicht
    rechtecke = ema_em3d.slot_rects(g)
    tiefe_feld = float(rechtecke[0]["length"]) if rechtecke else 0.0
    zeilen.append({"groesse": "Nuttiefe [mm]", "cad": round(tiefe, 4),
                   "feld": round(tiefe_feld, 4)})

    # Magnete und Kaefig kommen aus EINER Quelle -- das ist die Aussage
    geteilt = []
    try:
        legs, _meta = ema_topology.magnet_legs(g)
        geteilt.append(f"Magnete: {len(legs)} Schenkel je Pol aus "
                       f"ema_topology.magnet_legs — beide Wege lesen dieselbe Funktion")
    except Exception as e:
        # Ein duenner Payload ist kein Grund, die uebrige Gegenueberstellung
        # wegzuwerfen -- sie ist ein Diagnosewerkzeug, kein Tor.
        geteilt.append(f"Magnete: nicht ausgewertet ({type(e).__name__}: {e})")
    if str(g.get("machineType", "pmsm")).lower() == "asm" and axial > 0:
        import ema_asm
        kf = ema_asm.kaefig(g, axial)
        geteilt.append(f"Kaefig: {kf['n_stab']} Staebe, Steg {ema_asm.KAEFIG_STEG_MM} mm "
                       f"aus ema_asm.kaefig — ebenfalls eine Quelle")

    # Wickelkopf: das CAD zeichnet ihn, die 3-D-Feldstufe bewusst nicht
    if ema_wicklung.art(g) == "hairpin":
        hr = ema_wicklung.hairpin_radien(g)
        zeilen.append({"groesse": "Wicklung aussen r [mm]",
                       "cad": round(hr["r_aussen_mm"], 4),
                       "feld": round(r_si + tiefe_feld, 4)})
        hinweise.append("Die 3-D-Feldstufe fuehrt den Statorleiter gerade bis auf den "
                        "Aussenrand statt als Krone (Begruendung im Kopf von "
                        "ema_em3d_harm) — sie zeichnet keinen Wickelkopf und will "
                        "auch keinen. Der Unterschied ist gewollt.")

    for z in zeilen:
        d = abs(float(z["cad"]) - float(z["feld"]))
        bez = max(abs(float(z["cad"])), 1e-9)
        z["abweichung_mm"] = round(d, 4)
        z["abweichung_pct"] = round(100.0 * d / bez, 3)
        z["gleich"] = d <= 1e-3

    return {"zeilen": zeilen, "geteilt": geteilt, "hinweise": hinweise,
            "alle_gleich": all(z["gleich"] for z in zeilen)}


def cad_gegen_feld_text(erg: dict) -> str:
    z = ["  Groesse                              CAD        Feld    Abweichung",
         "  " + "-" * 66]
    for r in erg["zeilen"]:
        marke = " " if r["gleich"] else "≠"
        z.append(f"  {marke} {r['groesse']:<34s} {r['cad']:>9.3f} {r['feld']:>11.3f}"
                 f" {r['abweichung_mm']:>8.3f} mm")
    if erg["geteilt"]:
        z.append("")
        z.append("  Aus EINER Quelle — dort kann nichts auseinanderlaufen:")
        for s in erg["geteilt"]:
            z.append(f"    · {s}")
    if erg["hinweise"]:
        z.append("")
        z.append("  Gewollte Unterschiede:")
        for h in erg["hinweise"]:
            z.append(f"    ⓘ {h}")
    return "\n".join(z)
