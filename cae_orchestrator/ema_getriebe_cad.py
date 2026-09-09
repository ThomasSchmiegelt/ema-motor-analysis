"""Das Getriebe zeichnen -- mit FCGear, sonst selbst.

Machbarkeit, gemessen statt geglaubt
------------------------------------

``freecad.gears`` (FCGear) ist ein Addon und war hier nicht installiert.
Nachgemessen am 09.09.2026 unter ``FreeCADCmd`` (FreeCAD 1.1.1, ohne GUI):

* ``InvoluteGear`` z = 20, m = 3, h = 40 -> 110.236 mm^3, 122 Flaechen, **0,12 s**
* ``InternalInvoluteGear`` z = 72, m = 1,25, h = 25 -> 35.748 mm^3, **0,17 s**

Es laeuft also kopflos, und schnell. Zwei Fallen dabei, beide gemessen:

1. **Das Addon gehoert nach ``~/.local/share/FreeCAD/v1-1/Mod``**, nicht nach
   ``~/.local/share/FreeCAD/Mod``. Dieser FreeCAD-Bau meldet als
   ``getUserAppDataDir()`` den Zweig ``v1-1/``; im Elternverzeichnis abgelegt
   wird das Addon schlicht nicht gefunden (``ModuleNotFoundError: No module
   named 'freecad.gears'``) -- ohne Hinweis darauf, dass es danebenliegt.
2. **Die Eigenschaften heissen anders, als die Beispiele im Netz sagen**:
   ``num_teeth`` (nicht ``teeth``), ``module``, ``height``, ``pressure_angle``,
   ``shift``, ``helix_angle``. Ein ``g.teeth = 20`` scheitert mit
   ``AttributeError`` an einem Objekt, das gerade eben noch erzeugt wurde.

Der Rueckfall
-------------

Ohne FCGear werden **Ersatzkoerper** gezeichnet -- Zylinder auf dem Teilkreis,
unverkennbar keine Verzahnung. Hier stand zuerst ein eigener
Evolventen-Erzeuger; er ist wieder heraus, und der Grund ist eine Messung, die
weiter unten am Code steht: an derselben Stufe lag er um den **Faktor 60**
daneben, und dem Bild sieht man das nicht an. Ein Rad, das wie ein Zahnrad
aussieht und die falsche Groesse hat, ist schlimmer als keines.

Der Rueckfall traegt **Stirnrad und Planetensatz**. Fuer Kegelrad und Schnecke
gibt es keinen -- dann steht das im Ergebnis, statt etwas Aehnliches zu zeichnen.

Was gezeichnet wird, steht im Ergebnis (``zeichner: "fcgear" | "ersatz"``, im
zweiten Fall mit ``vorbehalt``). Das ist keine Nebensache: die beiden Wege
erzeugen nicht dieselbe Flaeche, und wer spaeter eine Fertigungszeichnung daraus
zieht, muss wissen, welche er hat.
"""

from __future__ import annotations

import math
import os

FCGEAR_MOD = os.path.expanduser("~/.local/share/FreeCAD/v1-1/Mod/freecad.gears")


def fcgear_da() -> bool:
    """Liegt das Addon dort, wo dieser FreeCAD-Bau es sucht?"""
    return os.path.isdir(os.path.join(FCGEAR_MOD, "freecad", "gears"))


# ── Der eigene Erzeuger, als Text fuer den fremden Prozess ──────────────────

# ── Der Rueckfall: Ersatzkoerper, KEINE Verzahnung ──────────────────────────
#
# Hier stand zuerst ein eigener Evolventen-Erzeuger. Er ist wieder heraus, und
# der Grund ist eine Messung: an derselben Stufe (z 18/63, m = 1,5, b = 30) gab
# FCGear 16.677 + 209.396 mm^3, der eigene Erzeuger 12.092.260 mm^3 -- um den
# Faktor 60 daneben, und dem Bild sieht man das nicht an. Ein Zahnrad, das wie
# ein Zahnrad aussieht und die falsche Groesse hat, ist schlimmer als keines:
# wer eine Fertigungszeichnung daraus zieht, merkt es zu spaet.
#
# Statt dessen zeichnet der Rueckfall ZYLINDER auf dem Teilkreis -- unverkennbar
# keine Verzahnung, und genau das, was man fuer die Frage braucht, um die es
# beim Einbau in der Welle geht: passt das Ding hinein und wo sitzt es. Jedes
# Ergebnis traegt ``zeichner: "ersatz"``, und die Ausgabe sagt, dass die Zaehne
# fehlen.
_ERSATZ_HILFE = '''
import math
import FreeCAD as App
import Part
from FreeCAD import Vector

def zahnrad(z, m, b, alpha_grad=20.0, x=0.0, innen=False, punkte=12):
    """ERSATZKOERPER auf dem Teilkreis -- ohne Zaehne. S. Modulkopf."""
    d = m * z
    if innen:
        aussen = Part.makeCylinder(d / 2.0 + 3.0 * m, b)
        return aussen.cut(Part.makeCylinder(d / 2.0, b + 2.0, Vector(0, 0, -1)))
    return Part.makeCylinder(d / 2.0, b)
'''


def _kopf(projekt_dir: str, name: str) -> str:
    return f'''
import os, math, traceback
import FreeCAD as App
import Part
from FreeCAD import Vector

ZIEL = {projekt_dir!r}
NAME = {name!r}
doc = App.newDocument("getriebe")
_koerper = []
'''


def _fuss() -> str:
    return '''
try:
    if not _koerper:
        raise RuntimeError("kein Koerper erzeugt")
    # VERBUND, nicht Vereinigung. ``fuse`` ueber zwei Zahnraeder, deren
    # Kopfkreise sich beruehren, gab gemessen ein Volumen von 0,00 mm^3 zurueck
    # -- die Einzelkoerper hatten 16.677 und 209.396 mm^3, der Verschnitt
    # scheiterte still. Ein Getriebe ist ohnehin eine Baugruppe und kein
    # verschweisster Klumpen: die Raeder bleiben getrennte Solids.
    verbund = Part.makeCompound(_koerper)
    obj = doc.addObject("Part::Feature", "Getriebe")
    obj.Shape = verbund
    doc.recompute()
    print("CAD_VOLUME:%.2f" % sum(k.Volume for k in _koerper))
    print("CAD_KOERPER:%d" % len(_koerper))
    fcstd = os.path.join(ZIEL, NAME + ".FCStd")
    doc.saveAs(fcstd)
    print("SAVED:" + fcstd)
    try:
        step = os.path.join(ZIEL, NAME + ".step")
        Part.export([obj], step)
        print("STEP_SAVED:" + step)
    except Exception as e:
        print("STEP_FAIL:" + str(e)[:200])
    print("CAD_SUCCESS")
except Exception as e:
    print("CAD_FEHLER:" + type(e).__name__ + ": " + str(e)[:300])
    traceback.print_exc()
'''


def _fcgear_rad(var: str, z: int, m: float, b: float, innen: bool,
                beta: float = 0.0, x: float = 0.0,
                lage: tuple = (0.0, 0.0, 0.0)) -> str:
    """Ein Rad ueber FCGear. Eigenschaftsnamen s. Modulkopf -- ``num_teeth``,
    nicht ``teeth``."""
    klasse = "InternalInvoluteGear" if innen else "InvoluteGear"
    return f'''
{var} = doc.addObject("Part::FeaturePython", "{var}")
{klasse}({var})
{var}.num_teeth = {int(z)}
{var}.module = "{m} mm"
{var}.height = "{b} mm"
{var}.pressure_angle = "20 deg"
{var}.shift = {x}
{var}.helix_angle = "{beta} deg"
doc.recompute()
_s = {var}.Shape.copy()
_s.Placement = App.Placement(Vector({lage[0]}, {lage[1]}, {lage[2]}),
                             App.Rotation(0, 0, 0))
_koerper.append(_s)
'''


def _ersatz_rad(var: str, z: int, m: float, b: float, innen: bool,
               x: float = 0.0, lage: tuple = (0.0, 0.0, 0.0)) -> str:
    return f'''
_s = zahnrad({int(z)}, {m}, {b}, x={x}, innen={bool(innen)})
_s.Placement = App.Placement(Vector({lage[0]}, {lage[1]}, {lage[2]}),
                             App.Rotation(0, 0, 0))
_koerper.append(_s)
'''


def bauen(erg: dict, projekt_dir: str, *, name: str = "getriebe",
          mit_welle: bool = True, timeout: int = 300) -> dict:
    """Die Auslegung zeichnen. Rueckgabe sagt, WER gezeichnet hat.

    ``mit_welle`` legt beim Einbau ``in_welle`` zusaetzlich die Hohlwelle als
    durchsichtigen Zylinder darum -- ohne sie sieht man dem Bild nicht an, worum
    es bei diesem Einbau geht.
    """
    if not erg.get("ok"):
        return {"ok": False, "grund": "keine gueltige Auslegung"}
    art = erg.get("art")
    zeichner = "fcgear" if fcgear_da() else "ersatz"
    if art in ("kegelrad", "schnecke") and zeichner != "fcgear":
        return {"ok": False, "zeichner": None,
                "grund": (f"Fuer '{art}' gibt es keinen Ersatzkoerper, und FCGear "
                          f"liegt nicht unter {FCGEAR_MOD}. Es wird nichts "
                          f"gezeichnet — ein aehnlicher Koerper waere hier "
                          f"schlimmer als keiner.")}

    code = [_kopf(projekt_dir, name)]
    if zeichner == "fcgear":
        code.append("from freecad.gears.features import InvoluteGear, "
                    "InternalInvoluteGear\n")
    else:
        code.append(_ERSATZ_HILFE)

    rad = _fcgear_rad if zeichner == "fcgear" else (
        lambda var, z, m, b, innen, beta=0.0, x=0.0, lage=(0, 0, 0):
        _ersatz_rad(var, z, m, b, innen, x, lage))

    if art == "planeten":
        st = erg["stufen"][0]
        m, b = st["m_mm"], st["b_mm"]
        a_sp = st["a_sonne_planet_mm"]
        code.append(rad("Sonne", st["z_sonne"], m, b, False))
        for k in range(st["n_planeten"]):
            w = 2.0 * math.pi * k / st["n_planeten"]
            code.append(rad(f"Planet{k}", st["z_planet"], m, b, False,
                            lage=(a_sp * math.cos(w), a_sp * math.sin(w), 0.0)))
        code.append(rad("Hohlrad", st["z_hohlrad"], m, b, True))
        if mit_welle and erg.get("einbau") == "in_welle":
            iw = erg.get("in_welle") or {}
            d_i = float(iw.get("d_noetig_mm", st["d_aussen_mm"]))
            d_a = d_i + 2.0 * 8.0
            code.append(f'''
_w = Part.makeCylinder({d_a / 2.0}, {b + 24.0}, Vector(0, 0, {-12.0}))
_w = _w.cut(Part.makeCylinder({d_i / 2.0}, {b + 26.0}, Vector(0, 0, {-13.0})))
_wo = doc.addObject("Part::Feature", "Hohlwelle")
_wo.Shape = _w
doc.recompute()
''')
    elif art == "stirnrad":
        z_off = 0.0
        for k, st in enumerate(erg["stufen"]):
            m, b, a = st["m_mm"], st["b_mm"], st["a_mm"]
            code.append(rad(f"Ritzel{k}", st["z1"], m, b, False,
                            beta=st.get("beta_grad", 0.0), lage=(0, 0, z_off)))
            code.append(rad(f"Rad{k}", st["z2"], m, b, False,
                            beta=-st.get("beta_grad", 0.0), lage=(a, 0, z_off)))
            z_off += b + 10.0
    elif art == "kegelrad":
        # FCGear zeichnet das Kegelrad selbst; die Auslegung liefert nur die
        # Zaehnezahlen und den Modul.
        code.append("from freecad.gears.features import BevelGear\n")
        for var, z, lage in (("Ritzel", erg["z1"], (0, 0, 0)),
                             ("Tellerrad", erg["z2"], (0, 0, 0))):
            code.append(f'''
{var} = doc.addObject("Part::FeaturePython", "{var}")
BevelGear({var})
{var}.num_teeth = {int(z)}
{var}.module = "{erg['m_mm']} mm"
{var}.height = "{erg['b_mm']} mm"
doc.recompute()
_s = {var}.Shape.copy()
_koerper.append(_s)
''')
    else:                                          # schnecke
        code.append("from freecad.gears.features import WormGear\n")
        code.append(f'''
Schnecke = doc.addObject("Part::FeaturePython", "Schnecke")
WormGear(Schnecke)
Schnecke.num_teeth = {int(erg.get("z_schnecke", 2))}
Schnecke.module = "{erg.get('m_mm', 2.0)} mm"
Schnecke.height = "{max(30.0, 3.0 * erg.get('m_mm', 2.0) * 6)} mm"
doc.recompute()
_koerper.append(Schnecke.Shape.copy())
''')

    code.append(_fuss())
    quelle = "\n".join(code)

    import freecad_runner
    a = freecad_runner.run_freecad_script(quelle, timeout=timeout)
    out = (a.get("stdout") or "")
    erfolg = "CAD_SUCCESS" in out
    step = fcstd = ""
    for zeile in out.splitlines():
        if zeile.startswith("STEP_SAVED:"):
            step = zeile.split(":", 1)[1].strip()
        elif zeile.startswith("SAVED:"):
            fcstd = zeile.split(":", 1)[1].strip()
    fehler = next((z for z in out.splitlines() if z.startswith("CAD_FEHLER:")), "")
    n_koerper = next((int(z.split(":", 1)[1]) for z in out.splitlines()
                      if z.startswith("CAD_KOERPER:")), 0)
    return {"ok": bool(erfolg), "zeichner": zeichner, "koerper": n_koerper,
            "vorbehalt": ("" if zeichner == "fcgear" else
                          "ERSATZKOERPER ohne Verzahnung — nur fuer die Frage, "
                          "ob und wo es passt. Fuer eine Zahnform muss FCGear "
                          f"unter {FCGEAR_MOD} liegen."),
            "step": step, "fcstd": fcstd,
            "grund": fehler[11:] if fehler else ("" if erfolg else
                                                 "FreeCAD meldete keinen Erfolg"),
            "volumen_mm3": next((float(z.split(":", 1)[1])
                                 for z in out.splitlines()
                                 if z.startswith("CAD_VOLUME:")), None)}


# ── Das Bild: der Querschnitt, gezeichnet aus den Zahlen ────────────────────
#
# Kein Abbild der CAD-Datei, sondern dasselbe Verfahren, mit dem die Kette auch
# ihren Motorquerschnitt zeichnet (``ema_pipeline.render_cross_section``): aus
# den Groessen, nicht aus dem Koerper. Das kostet keine FreeCAD-Sitzung und
# beantwortet die Frage, um die es hier geht -- sitzt der Satz da, wo er soll,
# und passt er in die Bohrung.

def bild(erg: dict, pfad: str) -> str:
    """Querschnitt als PNG. Rueckgabe ist der Pfad oder ""."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
    except Exception:                                        # noqa: BLE001
        return ""
    if not erg.get("ok"):
        return ""

    fig, ax = plt.subplots(figsize=(7.2, 7.2), facecolor="#0e1116")
    ax.set_facecolor("#0e1116")
    art = erg.get("art")

    def kreis(x, y, d, farbe, breite=1.6, strich="-", fuellung=None, z=2):
        ax.add_patch(Circle((x, y), d / 2.0, fill=fuellung is not None,
                            facecolor=fuellung or "none", edgecolor=farbe,
                            lw=breite, ls=strich, zorder=z))

    if art == "planeten":
        st = erg["stufen"][0]
        m = st["m_mm"]
        a_sp = st["a_sonne_planet_mm"]
        # Die Bohrung zuerst -- sie ist der Rahmen, in den es passen muss.
        iw = erg.get("in_welle") or {}
        if iw:
            d_v = iw.get("d_verfuegbar_mm") or 0
            if d_v:
                kreis(0, 0, d_v, "#ffb454", 2.2, "--", z=1)
                ax.text(0, d_v / 2.0 + 3, f"verfuegbar {d_v:.1f} mm "
                        f"({iw.get('bindend', '')})", color="#ffb454",
                        ha="center", fontsize=9)
        kreis(0, 0, st["d_aussen_mm"], "#93a1b1", 1.4, ":", z=1)
        # Unter den AUSSERSTEN Kreis, nicht unter den eigenen -- sonst liegt die
        # Beschriftung im Bild.
        _unten = max(st["d_aussen_mm"], (iw.get("d_verfuegbar_mm") or 0)) / 2.0
        ax.text(0, -_unten - 9, f"Hohlrad aussen {st['d_aussen_mm']:.1f} mm",
                color="#93a1b1", ha="center", fontsize=9)
        kreis(0, 0, st["d_hohlrad_mm"], "#4ea1ff", 2.0, fuellung=None)
        kreis(0, 0, st["d_sonne_mm"], "#4ec98f", 2.0)
        kreis(0, 0, st["d_sonne_mm"] + 2 * m, "#4ec98f", 0.8, ":")
        for k in range(st["n_planeten"]):
            w = 2.0 * math.pi * k / st["n_planeten"]
            px, py = a_sp * math.cos(w), a_sp * math.sin(w)
            kreis(px, py, st["d_planet_mm"], "#ff6b6b", 1.8)
            kreis(px, py, st["d_planet_mm"] + 2 * m, "#ff6b6b", 0.8, ":")
        r_max = max(st["d_aussen_mm"], iw.get("d_verfuegbar_mm") or 0) / 2.0 * 1.18
        titel = (f"Planetensatz  i = {erg['i_ist']}  ·  "
                 f"z {st['z_sonne']}/{st['z_planet']}/{st['z_hohlrad']}  ·  "
                 f"m = {m} mm")
    else:
        x = 0.0
        r_max = 1.0
        farben = ("#4ec98f", "#4ea1ff")
        for k, st in enumerate(erg.get("stufen", [])):
            f = farben[k % 2]
            kreis(x, 0, st["d1_mm"], f, 2.0)
            kreis(x, 0, st["da1_mm"], f, 0.8, ":")
            kreis(x + st["a_mm"], 0, st["d2_mm"], f, 2.0)
            kreis(x + st["a_mm"], 0, st["da2_mm"], f, 0.8, ":")
            ax.plot([x, x + st["a_mm"]], [0, 0], color=f, lw=0.8, ls="--", zorder=1)
            ax.text(x + st["a_mm"] / 2.0, st["da2_mm"] / 2.0 + 6,
                    f"{st.get('name', '')}  z {st['z1']}/{st['z2']}  m {st['m_mm']}",
                    color=f, ha="center", fontsize=9)
            r_max = max(r_max, abs(x) + st["da1_mm"] / 2.0,
                        abs(x + st["a_mm"]) + st["da2_mm"] / 2.0)
            x += st["a_mm"]
        r_max *= 1.12
        titel = (f"{art}  i = {erg.get('i_ist')}  ·  "
                 f"{erg.get('n_stufen', 1)} Stufe(n)")

    ax.set_xlim(-r_max, r_max)
    ax.set_ylim(-r_max, r_max)
    ax.set_aspect("equal")
    ax.set_title(titel, color="#dfe6ee", fontsize=11)
    ax.tick_params(colors="#4a5560", labelsize=8)
    for sp in ax.spines.values():
        sp.set_color("#2a333f")
    fuss = (f"Werkstoff {erg.get('werkstoff', '?')} [{erg.get('werkstoff_beleg', '?')}]"
            f"   ·   Wirkungsgrad {(erg.get('wirkungsgrad') or {}).get('eta_nenn', '?')}"
            f"   ·   Masse {erg.get('masse_kg', '?')} kg")
    fig.text(0.5, 0.025, fuss, color="#93a1b1", ha="center", fontsize=8.5)
    try:
        os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
        fig.savefig(pfad, dpi=130, facecolor=fig.get_facecolor(),
                    bbox_inches="tight")
    except OSError:
        return ""
    finally:
        plt.close(fig)
    return pfad
