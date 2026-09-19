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
    # JEDES Teil bekommt sein eigenes Objekt, und dann zusaetzlich den Verbund.
    # Ohne die Einzelobjekte heisst im Baum alles "Getriebe", und ein Befund
    # "Getriebe_3 x Rotor" sagt niemandem, welches Rad gemeint ist.
    for _n, _k in _koerper:
        _o = doc.addObject("Part::Feature", _n)
        _o.Shape = _k
    verbund = Part.makeCompound([k for _n, k in _koerper])
    obj = doc.addObject("Part::Feature", "Getriebe")
    obj.Shape = verbund
    doc.recompute()
    print("CAD_VOLUME:%.2f" % sum(k.Volume for _n, k in _koerper))
    print("CAD_KOERPER:%d" % len(_koerper))

    # ── Nachmessen am GEBAUTEN Koerper, nicht am Parameter ───────────────
    #
    # Dasselbe Verfahren wie in `bau_eesm.py`: jedes Paar ueber
    # `common().Volume`. Bei einem Getriebe ist das nicht Kosmetik, sondern die
    # einzige Probe darauf, dass die Raeder wirklich INEINANDER greifen statt
    # ineinander zu stecken -- ein Planetenrad, dessen Zaehne nicht in Phase
    # stehen, sieht im Bild richtig aus und frisst sich im Modell durch die
    # Sonne. Gemessen wurden so 336…358 mm3 (1,4 %) an einem Satz, bei dem
    # `z_sonne/n_planeten` nicht aufgeht.
    #
    # Eine Zahnpaarung beruehrt einander per Konstruktion; unterhalb von
    # SCHWELLE gilt das als Beruehrung und nicht als Durchdringung.
    SCHWELLE = 0.02                                  # Prozent des kleineren Koerpers

    def _zufall(saat):
        # Ein eigener, winziger Zufallsgenerator statt `random`: die Probe soll
        # bei jedem Lauf DIESELBEN Punkte nehmen, sonst schwankt der Befund.
        z = [int(saat)]
        def _next():
            z[0] = (1103515245 * z[0] + 12345) % 2147483648
            return z[0] / 2147483648.0
        return _next
    schlimm, funde = 0.0, []
    for _i in range(len(_koerper)):
        for _j in range(_i + 1, len(_koerper)):
            _a, _b = _koerper[_i][1], _koerper[_j][1]
            # Erst die Huellquader: zwei Koerper, deren Kaesten sich nicht
            # beruehren, koennen sich nicht durchdringen -- das spart den
            # teuren Schnitt und, wichtiger, die Gelegenheit zu scheitern.
            if not _a.BoundBox.intersect(_b.BoundBox):
                continue
            try:
                _v = _a.common(_b).Volume
            except Exception:
                print("CAD_DURCHDRINGUNG_UNKLAR:%s x %s: Schnitt gescheitert"
                      % (_koerper[_i][0], _koerper[_j][0]))
                continue
            _klein = min(_a.Volume, _b.Volume)
            # OCCs `common` gibt bei einem gescheiterten Schnitt gemessen das
            # Volumen EINES Operanden zurueck -- bitgleich. Zweimal gesehen an
            # einem Planetenrad, das damit vollstaendig im Hohlrad gesteckt
            # haette, waehrend die beiden baugleichen Nachbarn 1,4 % zeigten.
            # Eine 100-%-Meldung, die in Wirklichkeit ein Fehlschlag ist, waere
            # schlimmer als keine: sie schickt die Suche ans falsche Ende.
            if abs(_v - _klein) < 1e-6 * max(_klein, 1.0):
                # Der Schnitt liefert BITGLEICH das Volumen des kleineren
                # Koerpers. Das heisst entweder „er steckt ganz darin" oder
                # „die Boolesche ist gescheitert" -- und beides sieht gleich
                # aus. Der Huellquader entscheidet es NICHT: der eines
                # Planeten liegt sehr wohl in dem des Hohlrads, er steckt ja in
                # dessen Loch. Also die Gegenprobe mit dem Schnitt: wer wirklich
                # drinsteckt, hat nichts ausserhalb.
                # Der Schiedsrichter ist KEINE zweite Boolesche -- `cut`
                # scheitert an derselben Stelle wie `common` und bestaetigt den
                # Fehler nur (beide meldeten uebereinstimmend, ein Planetenrad
                # stecke ganz im Hohlrad, waehrend es in dessen LOCH sass).
                # Statt dessen Punktproben: liegt der kleinere Koerper wirklich
                # im groesseren, sind auch seine Punkte darin.
                _k, _g = ((_a, _b) if _a.Volume <= _b.Volume else (_b, _a))
                _bb, _rnd = _k.BoundBox, _zufall(12345)
                _drin = _beide = 0
                for _n2 in range(600):
                    _pt = App.Vector(
                        _bb.XMin + _rnd() * (_bb.XMax - _bb.XMin),
                        _bb.YMin + _rnd() * (_bb.YMax - _bb.YMin),
                        _bb.ZMin + _rnd() * (_bb.ZMax - _bb.ZMin))
                    if not _k.isInside(_pt, 1e-6, True):
                        continue
                    _drin += 1
                    if _g.isInside(_pt, 1e-6, True):
                        _beide += 1
                _anteil = (100.0 * _beide / _drin) if _drin >= 20 else None
                if _anteil is not None and _anteil < 90.0:
                    print("CAD_DURCHDRINGUNG_UNKLAR:%s x %s: die Boolesche "
                          "meldet 100 %% (%.1f mm3), die Punktprobe dagegen "
                          "%.1f %% aus %d Proben -- Beruehrung oder "
                          "gescheiterter Schnitt, nicht nachweisbar"
                          % (_koerper[_i][0], _koerper[_j][0], _v,
                             _anteil, _drin))
                    continue
            _rel = 100.0 * _v / max(_klein, 1e-9)
            if _rel > SCHWELLE:
                schlimm = max(schlimm, _rel)
                funde.append("%s x %s: %.1f mm3 (%.2f %%)"
                             % (_koerper[_i][0], _koerper[_j][0], _v, _rel))
    print("CAD_DURCHDRINGUNG:%.4f" % schlimm)
    for _f in funde[:12]:
        print("CAD_DURCHDRINGUNG_PAAR:" + _f)
    fcstd = os.path.join(ZIEL, NAME + ".FCStd")
    # KEINE .FCBak-Sicherung. FreeCAD legt beim Ueberschreiben eine an, und weil
    # die Auslegung mehrmals hintereinander laeuft, sammeln sich im Projekt
    # ``getriebe.<zeit>.FCBak``-Dateien, die niemand liest -- die vorige Fassung
    # steht ohnehin in ``rechnungen/`` als Zahlen. Der Schalter ist eine
    # Nutzereinstellung dieses FreeCAD-Laufs und wirkt nur in diesem Prozess.
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool(
        "CreateBackupFiles", False)
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


def _zylinder(var: str, r: float, h: float, lage: tuple) -> str:
    """Ein Zylinder als benannter Koerper -- Bolzen, Welle, Nabe."""
    return (f'\n_s = Part.makeCylinder({r!r}, {h!r}, '
            f'Vector({lage[0]!r}, {lage[1]!r}, {lage[2]!r}))\n'
            f'_koerper.append(({var!r}, _s))\n')


def _scheibe_mit_loechern(var: str, r: float, h: float, z: float,
                          loecher) -> str:
    """Eine Scheibe mit Bohrungen -- die Stegwange des Planetentraegers.

    Die Bohrungen sind der Punkt: ohne sie steckt jeder Planetenbolzen im
    Vollmaterial, und der Steg ist kein Planetentraeger, sondern eine Scheibe,
    durch die drei Bolzen hindurchgehen.
    """
    z = float(z)
    stueck = [f'\n_s = Part.makeCylinder({r!r}, {h!r}, Vector(0, 0, {z!r}))\n']
    for cx, cy, rl in loecher:
        stueck.append(
            f'_s = _s.cut(Part.makeCylinder({float(rl)!r}, {h + 2.0!r}, '
            f'Vector({float(cx)!r}, {float(cy)!r}, {z - 1.0!r})))\n')
    stueck.append(f'_koerper.append(({var!r}, _s))\n')
    return "".join(stueck)


def _fcgear_rad(var: str, z: int, m: float, b: float, innen: bool,
                beta: float = 0.0, x: float = 0.0,
                lage: tuple = (0.0, 0.0, 0.0), dreh: float = 0.0,
                wand: float = 0.0, pfeil: bool = False,
                bohrung: float = 0.0) -> str:
    """Ein Rad ueber FCGear. Eigenschaftsnamen s. Modulkopf -- ``num_teeth``,
    nicht ``teeth``.

    ``dreh`` ist die Verdrehung um die eigene Achse in Grad, BEVOR das Rad an
    seinen Platz geschoben wird. Fuer ein einzelnes Rad ist sie bedeutungslos,
    fuer ein Planetenrad ist sie die halbe Miete: es muss an seiner Stelle in
    die Sonne greifen, und dafuer betraegt die noetige Verdrehung gerade
    ``Stellwinkel * z_Sonne/z_Planet``.

    ``wand`` ist die Wandstaerke ueber dem Zahngrund des INNENverzahnten Rades.
    Ohne sie nimmt FCGear seinen Vorgabewert, und der Ring hat eine Wand, die
    zur Auslegung nicht passt.

    ``bohrung`` ist der Durchmesser der Wellen- bzw. Bolzenbohrung. FCGear
    zeichnet eine volle Scheibe; ohne die Bohrung steckt die Welle im
    Vollmaterial des Rades -- gemessen 27 % der Sonnenwelle und 59 % jedes
    Planetenbolzens.

    Das FCGear-Objekt wird nach dem Kopieren **entfernt**. Es blieb sonst neben
    dem Verbund im Dokument stehen -- an seinem Ursprung, also mitten in der
    Baugruppe: ein gespeicherter Planetensatz enthielt gemessen jedes Rad
    zweimal, einmal richtig und einmal in der Mitte.
    """
    klasse = "InternalInvoluteGear" if innen else "InvoluteGear"
    wandzeile = f'{var}.thickness = "{wand} mm"\n' if (innen and wand > 0) else ""
    bohrzeile = ("" if bohrung <= 0 else
                 f"_s = _s.cut(Part.makeCylinder({bohrung / 2.0!r}, {b + 2.0!r}, "
                 f"Vector(0, 0, -1.0)))\n")
    pfeilzeile = f"{var}.double_helix = True\n" if pfeil else ""
    return f'''
{var} = doc.addObject("Part::FeaturePython", "{var}")
{klasse}({var})
{var}.num_teeth = {int(z)}
{var}.module = "{m} mm"
{var}.height = "{b} mm"
{var}.pressure_angle = "20 deg"
{var}.shift = {x}
{var}.helix_angle = "{beta} deg"
{wandzeile}{pfeilzeile}doc.recompute()
_s = {var}.Shape.copy()
doc.removeObject({var!r})
_s.rotate(Vector(0, 0, 0), Vector(0, 0, 1), {float(dreh)!r})
{bohrzeile}_s.translate(Vector({lage[0]}, {lage[1]}, {lage[2]}))
_koerper.append(("{var}", _s))
'''


def _ersatz_rad(var: str, z: int, m: float, b: float, innen: bool,
               x: float = 0.0, lage: tuple = (0.0, 0.0, 0.0),
               dreh: float = 0.0, bohrung: float = 0.0) -> str:
    # `dreh` bleibt hier wirkungslos und wird trotzdem entgegengenommen: der
    # Ersatzkoerper ist ein ZYLINDER und hat keine Zaehne, die in Phase stehen
    # koennten. Zwei verschiedene Signaturen waeren die naechste Stelle, an der
    # ein Aufrufer den falschen Zeichner erwischt.
    bohrzeile = ("" if bohrung <= 0 else
                 f"_s = _s.cut(Part.makeCylinder({bohrung / 2.0!r}, {b + 2.0!r}, "
                 f"Vector(0, 0, -1.0)))\n")
    return f'''
_s = zahnrad({int(z)}, {m}, {b}, x={x}, innen={bool(innen)})
{bohrzeile}_s.translate(Vector({lage[0]}, {lage[1]}, {lage[2]}))
_koerper.append(("{var}", _s))
'''


# Das Skript, das den fertigen Motor OEFFNET und den Satz hineinlegt.
# Kein f-String: es wird mit ``.format`` gefuellt, und der Text ist voller
# geschweifter Klammern (dict-Literale, Formatangaben) -- doppelt zu escapen
# waere die naechste Stelle, an der jemand eine Klammer vergisst.
_MOTOR_SKRIPT = '''
import os, math, traceback
import FreeCAD as App
import Part
from FreeCAD import Vector

try:
    mot = App.openDocument({motor!r})
    satz = App.openDocument({satz!r})

    # --- Die Bohrung wird GEMESSEN, nicht aus dem Payload geglaubt ---------
    #
    # Gesucht ist der kleinste Zylinder um die Drehachse, der im Laeufer
    # wirklich steht. Eine Zahl aus der Eingabe sagt, was gewollt war; diese
    # sagt, was gezeichnet wurde -- und nur die zweite entscheidet, ob der Satz
    # hineingeht.
    r_bohrung = None
    for o in mot.Objects:
        sh = getattr(o, "Shape", None)
        if sh is None or sh.isNull():
            continue
        for f in sh.Faces:
            s = f.Surface
            if not hasattr(s, "Radius") or not hasattr(s, "Axis"):
                continue
            ax = s.Axis
            if abs(abs(ax.z) - 1.0) > 1e-6:
                continue
            p = s.Center if hasattr(s, "Center") else s.Position
            if math.hypot(p.x, p.y) > 0.01:
                continue
            r = float(s.Radius)
            if r > 0.5 and (r_bohrung is None or r < r_bohrung):
                r_bohrung = r
    if r_bohrung is None:
        print("BOHRUNG_GEMESSEN:0.0")
        print("HINWEIS:keine Bohrung gefunden -- die Welle ist voll")
    else:
        print("BOHRUNG_GEMESSEN:%.4f" % (2.0 * r_bohrung))

    # --- Den Satz mittig in den Laeufer legen -----------------------------
    mot_teile = [(o.Label, o.Shape) for o in mot.Objects
                 if getattr(o, "Shape", None) is not None and not o.Shape.isNull()]
    # Mittig heisst mittig im BLECHPAKET, nicht in allem, was das Dokument
    # enthaelt: die Hairpin-Wickelkoepfe ragen ueber beide Stirnseiten hinaus
    # und verschoben den Satz gemessen um 2,9 mm aus der Mitte.
    _bezug = [s for n, s in mot_teile if n.startswith(("Rotor", "Stator"))]
    if _bezug:
        zmin = min(s.BoundBox.ZMin for s in _bezug)
        zmax = max(s.BoundBox.ZMax for s in _bezug)
    else:
        zmin = min(s.BoundBox.ZMin for _n, s in mot_teile)
        zmax = max(s.BoundBox.ZMax for _n, s in mot_teile)
    z_mitte = 0.5 * (zmin + zmax)
    satz_teile = []
    for o in satz.Objects:
        sh = getattr(o, "Shape", None)
        if sh is None or sh.isNull() or not sh.Solids:
            continue
        if len(sh.Solids) > 1:                 # der Verbund, nicht die Teile
            continue
        satz_teile.append((o.Label, sh.copy()))
    if not satz_teile:
        for o in satz.Objects:
            sh = getattr(o, "Shape", None)
            if sh is not None and not sh.isNull() and sh.Solids:
                for i, s in enumerate(sh.Solids):
                    satz_teile.append(("Getriebe_%d" % i, s.copy()))
                break
    gz0 = min(s.BoundBox.ZMin for _n, s in satz_teile)
    gz1 = max(s.BoundBox.ZMax for _n, s in satz_teile)
    dz = z_mitte - 0.5 * (gz0 + gz1)
    for _n, s in satz_teile:
        s.translate(Vector(0, 0, dz))

    # --- Nachmessen: passt er wirklich hinein? ----------------------------
    #
    # Getriebe gegen Motor, jedes Paar. Das ist die eigentliche Probe: die
    # Rechnung sagt „der Satz braucht d mm Bohrung", hier wird nachgesehen,
    # ob im gezeichneten Eisen wirklich Platz ist.
    schlimm, funde = 0.0, []
    for gn, gs in satz_teile:
        for mn, ms in mot_teile:
            if not gs.BoundBox.intersect(ms.BoundBox):
                continue
            try:
                v = gs.common(ms).Volume
            except Exception:
                print("MOTOR_DURCHDRINGUNG_UNKLAR:%s x %s" % (gn, mn))
                continue
            klein = min(gs.Volume, ms.Volume)
            if abs(v - klein) < 1e-6 * max(klein, 1.0):
                print("MOTOR_DURCHDRINGUNG_UNKLAR:%s x %s (Schnitt entartet)"
                      % (gn, mn))
                continue
            rel = 100.0 * v / max(klein, 1e-9)
            if rel > 0.02:
                schlimm = max(schlimm, rel)
                funde.append("%s x %s: %.1f mm3 (%.2f %%)" % (gn, mn, v, rel))
    print("MOTOR_DURCHDRINGUNG:%.4f" % schlimm)
    for f in funde[:12]:
        print("MOTOR_DURCHDRINGUNG_PAAR:" + f)

    for gn, gs in satz_teile:
        o = mot.addObject("Part::Feature", gn)
        o.Shape = gs
    mot.recompute()
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool(
        "CreateBackupFiles", False)
    mot.saveAs({ziel!r})
    print("SAVED:" + {ziel!r})
    try:
        Part.export([o for o in mot.Objects
                     if getattr(o, "Shape", None) is not None
                     and not o.Shape.isNull()], {step!r})
        print("STEP_SAVED:" + {step!r})
    except Exception as e:
        print("STEP_FAIL:" + str(e)[:200])
    print("CAD_SUCCESS")
except Exception as e:
    print("CAD_FEHLER:" + type(e).__name__ + ": " + str(e)[:300])
    traceback.print_exc()
'''


def _STUFENABSTAND() -> float:
    import ema_getriebe as _G
    return float(_G.STUFENABSTAND_MM)


def in_motor_bauen(erg: dict, motor_fcstd: str, projekt_dir: str, *,
                   name: str = "motor_mit_getriebe", axial_mm: float = 0.0,
                   timeout: int = 600) -> dict:
    """Den Planetensatz in den GEBAUTEN Motor legen -- ein Dokument, ein Bild.

    Warum ein zweiter Lauf und kein dritter Erzeuger: den Motor zeichnet
    ``ema_freecad.build_full_motor_script``, das Getriebe ``bauen`` hier. Beide
    noch einmal in einer gemeinsamen Funktion hinzuschreiben waere die dritte
    Abschrift derselben Geometrie -- dieselbe Stelle, an der schon zweimal etwas
    auseinandergelaufen ist (der kegelige Polkern, die Innenschneider). Statt
    dessen wird das fertige Motordokument GEOEFFNET und der Satz hineingelegt.

    Und dabei wird gemessen statt angenommen: der Bohrungsdurchmesser wird am
    Laeuferkoerper ABGELESEN (kleinster Zylinderradius um die Achse), nicht aus
    dem Payload genommen. Passt der Satz nicht, ist das ein Befund mit zwei
    Zahlen und keine Zeichnung, in der sich Eisen und Zahnrad durchdringen.
    """
    if not erg.get("ok"):
        return {"ok": False, "grund": "keine gueltige Auslegung"}
    if str(erg.get("art")) != "planeten":
        return {"ok": False,
                "grund": (f"Nur ein Planetensatz sitzt in der Welle -- "
                          f"'{erg.get('art')}' arbeitet achsparallel.")}
    if not os.path.isfile(motor_fcstd):
        return {"ok": False, "grund": f"Motordokument fehlt: {motor_fcstd}"}

    stufen_p = erg.get("stufen") or []
    if not stufen_p:
        return {"ok": False, "grund": "keine Stufe in der Auslegung"}
    d_satz = max(float(st["d_aussen_mm"]) for st in stufen_p)
    laenge = (sum(float(st["b_mm"]) for st in stufen_p)
              + _STUFENABSTAND() * (len(stufen_p) - 1))

    # Das Getriebe wird EINMAL gebaut -- in ein eigenes Dokument, aus dem der
    # Verbund dann geholt wird. Damit zeichnet genau eine Funktion den Satz.
    hilf = bauen(erg, projekt_dir, name=name + "_satz", mit_welle=False,
                 timeout=timeout)
    if not hilf.get("ok"):
        return {"ok": False, "grund": "Getriebe liess sich nicht zeichnen: "
                                      + str(hilf.get("grund"))}
    satz_fcstd = hilf.get("fcstd") or os.path.join(
        projekt_dir, name + "_satz.FCStd")

    ziel = os.path.join(projekt_dir, name + ".FCStd")
    ziel_step = os.path.join(projekt_dir, name + ".step")
    quelle = _MOTOR_SKRIPT.format(
        motor=motor_fcstd, satz=satz_fcstd, ziel=ziel, step=ziel_step,
        d_satz=d_satz, laenge=laenge, axial=float(axial_mm or 0.0))
    import freecad_runner                      # erst im Aufruf, s. Modulkopf
    erg_lauf = freecad_runner.run_freecad_script(quelle, timeout=timeout)
    out = erg_lauf.get("stdout") or ""

    def _zahl(marke, vorgabe=None):
        for z in out.splitlines():
            if z.startswith(marke):
                try:
                    return float(z.split(":", 1)[1])
                except ValueError:
                    return vorgabe
        return vorgabe

    d_bohrung = _zahl("BOHRUNG_GEMESSEN:")
    durchdr = _zahl("MOTOR_DURCHDRINGUNG:")
    paare = [z.split(":", 1)[1] for z in out.splitlines()
             if z.startswith("MOTOR_DURCHDRINGUNG_PAAR:")]
    return {
        "ok": "CAD_SUCCESS" in out,
        "fcstd": ziel if "SAVED:" in out else "",
        "step": ziel_step if "STEP_SAVED:" in out else "",
        "d_bohrung_gemessen_mm": d_bohrung,
        "d_satz_mm": round(d_satz, 2),
        "laenge_satz_mm": round(laenge, 2),
        "passt": (None if d_bohrung is None else bool(d_satz <= d_bohrung)),
        "durchdringung_pct": durchdr,
        "durchdringung_paare": paare,
        "grund": "" if "CAD_SUCCESS" in out else out[-600:],
    }

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
        lambda var, z, m, b, innen, beta=0.0, x=0.0, lage=(0, 0, 0),
        dreh=0.0, wand=0.0, pfeil=False, bohrung=0.0:
        _ersatz_rad(var, z, m, b, innen, x, lage, dreh, bohrung))
    # Verzahnungsart: gerade (Vorgabe), schraeg oder Pfeil. Die Schraegung ist
    # im Fahrzeuggetriebe der Normalfall (Ueberdeckung, Geraeusch) und kostet
    # eine Axialkraft; die Pfeilverzahnung hebt sie durch die zweite Haelfte
    # wieder auf. `beta` rechnet `ema_getriebe.zahnform` laengst mit --
    # GEZEICHNET wurde es bisher nur bei der Stirnradstufe.
    beta_g = float(erg.get("beta_grad") or 0.0)
    pfeil_v = str(erg.get("verzahnung") or "").lower() == "pfeil"

    if art == "planeten":
        # Mehrere Stufen liegen KOAXIAL hintereinander -- dieselbe Achse, um die
        # Zahnbreite plus eine Fuge versetzt. Genau so sitzen sie in der Welle.
        import ema_getriebe as _G
        stufen_p = erg.get("stufen") or []
        z_off, laenge = 0.0, 0.0
        d_welle = (float(erg.get("d_welle_mm") or 0.0)
                   or (max(8.0, 0.45 * stufen_p[0]["d_sonne_mm"])
                       if stufen_p else 10.0))
        for si, st in enumerate(stufen_p):
            m, b = st["m_mm"], st["b_mm"]
            a_sp = st["a_sonne_planet_mm"]
            n_p = int(st["n_planeten"])
            vs = "" if len(stufen_p) == 1 else f"_S{si + 1}"
            st_t = max(6.0, 0.35 * b)                     # Dicke einer Stegwange
            z_v = z_off                                   # vordere Wange
            z_g = z_v + st_t                              # Verzahnungsebene
            d_bolzen = max(6.0, 0.5 * d_welle)
            code.append(rad(f"Sonne{vs}", st["z_sonne"], m, b, False,
                            beta=beta_g, lage=(0.0, 0.0, z_g), pfeil=pfeil_v,
                            bohrung=d_welle))
            for k in range(n_p):
                w = 2.0 * math.pi * k / n_p
                # DIE PHASE IST NICHT FREI -- und sie ist nicht die, die man
                # erwartet. FCGear setzt auf JEDES Rad einen Zahn auf die
                # +x-Achse; zwei so erzeugte Raeder stehen damit Zahn auf Zahn.
                # Ein kaemmendes Paar braucht deshalb den halben Zahnschritt
                # SEINES EIGENEN Rades, und zwar unabhaengig davon, wo das Rad
                # steht. Gemessen ueber einen Versatzlauf in 12 Schritten, an
                # einem Planeten bei 0 Grad UND bei 120 Grad: 0 Grad -> 336,7
                # bzw. 358,4 mm3 Durchdringung, 9,00 Grad = genau eine halbe
                # Teilung -> 0,000 mm3 in beiden Faellen.
                #
                # Der naheliegende Zusatzterm `Stellwinkel * z_Sonne/z_Planet`
                # (die Verdrehung, die ein abrollender Planet erfaehrt) ist
                # hier FALSCH: er gehoert zur Kinematik, nicht zur Zeichnung.
                # Mit ihm blieben gemessen 262,9 mm3 stehen, ohne ihn 0,0.
                phase = 180.0 / float(st["z_planet"])
                code.append(rad(f"Planet{si}_{k}", st["z_planet"], m, b, False,
                                beta=-beta_g, dreh=phase, pfeil=pfeil_v,
                                bohrung=d_bolzen + 0.4,
                                lage=(a_sp * math.cos(w), a_sp * math.sin(w),
                                      z_g)))
                # Der Planetenbolzen traegt das Rad im Steg -- er ist das, was
                # aus drei losen Raedern einen Planetentraeger macht.
                code.append(_zylinder(
                    f"Bolzen{si}_{k}", d_bolzen / 2.0, b + 2.0 * st_t,
                    (a_sp * math.cos(w), a_sp * math.sin(w), z_v)))
            # Das Hohlrad ebenso -- halber Zahnschritt SEINES Rades. Gemessen
            # ueber denselben Versatzlauf: 0 Grad -> 437,0 mm3, das Minimum
            # liegt bei 2,77 Grad = einer halben Hohlradteilung.
            code.append(rad(f"Hohlrad{vs}", st["z_hohlrad"], m, b, True,
                            beta=-beta_g, pfeil=pfeil_v,
                            dreh=180.0 / float(st["z_hohlrad"]),
                            wand=max(4.0, 3.0 * m), lage=(0.0, 0.0, z_g)))
            # Die beiden Stegwangen -- mit der Sonnenwelle und den Bolzen als
            # BOHRUNGEN. Ohne sie steckt jeder Bolzen im Vollmaterial, und der
            # Steg ist keiner.
            r_steg = a_sp + m * (st["z_planet"] + 2) / 2.0 + 2.0
            for nr, zw in (("v", z_v), ("h", z_g + b)):
                bohrungen = [(0.0, 0.0, d_welle / 2.0 + 0.2)]
                for k in range(n_p):
                    w = 2.0 * math.pi * k / n_p
                    bohrungen.append((a_sp * math.cos(w), a_sp * math.sin(w),
                                      d_bolzen / 2.0 + 0.2))
                code.append(_scheibe_mit_loechern(
                    f"Stegwange{si}_{nr}", r_steg, st_t, zw, bohrungen))
            laenge = z_g + b + st_t
            z_off = laenge + _G.STUFENABSTAND_MM
        # Sonnenwelle durch alles hindurch, Stegwelle als Abtrieb.
        if stufen_p:
            code.append(_zylinder("Sonnenwelle", d_welle / 2.0, laenge + 40.0,
                                  (0.0, 0.0, -20.0)))
            code.append(_scheibe_mit_loechern(
                "Stegwelle", d_welle / 2.0 + 6.0, 20.0, laenge,
                [(0.0, 0.0, d_welle / 2.0 + 0.2)]))
        if mit_welle and erg.get("einbau") == "in_welle" and stufen_p:
            iw = erg.get("in_welle") or {}
            d_i = float(iw.get("d_noetig_mm")
                        or max(st["d_aussen_mm"] for st in stufen_p))
            d_a = d_i + 2.0 * 8.0
            code.append(f'''
_w = Part.makeCylinder({d_a / 2.0}, {laenge + 24.0}, Vector(0, 0, {-12.0}))
_w = _w.cut(Part.makeCylinder({d_i / 2.0}, {laenge + 26.0}, Vector(0, 0, {-13.0})))
_koerper.append(("Hohlwelle", _w))
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
_koerper.append(("{var}", _s))
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
_koerper.append(("Schnecke", Schnecke.Shape.copy()))
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
    # Was am GEBAUTEN Koerper gemessen wurde, gehoert ins Ergebnis -- sonst
    # steht es in einer stdout, die niemand liest.
    _dd = next((float(z.split(":", 1)[1]) for z in out.splitlines()
                if z.startswith("CAD_DURCHDRINGUNG:")), None)
    _paare = [z.split(":", 1)[1] for z in out.splitlines()
              if z.startswith("CAD_DURCHDRINGUNG_PAAR:")]
    _unklar = [z.split(":", 1)[1] for z in out.splitlines()
               if z.startswith("CAD_DURCHDRINGUNG_UNKLAR:")]
    return {"ok": bool(erfolg), "zeichner": zeichner, "koerper": n_koerper,
            "durchdringung_pct": _dd,
            "durchdringung_paare": _paare,
            "durchdringung_unklar": _unklar,
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

    stufen_p = erg.get("stufen") or []
    if art == "planeten" and len(stufen_p) > 1:
        # LAENGSSCHNITT. Von vorn gesehen liegen zwei koaxiale Stufen genau
        # uebereinander -- das Bild zeigte dann zwei Saetze konzentrischer Kreise
        # und gerade nicht das, worum es beim Einbau in der Welle geht: dass sie
        # HINTEREINANDER und mittig in der Bohrung sitzen. Also r ueber z.
        import ema_getriebe as _G
        iw = erg.get("in_welle") or {}
        d_v = float(iw.get("d_verfuegbar_mm") or 0)
        lager = 12.0
        l_ges = float(iw.get("l_noetig_mm") or 0)
        l_frei = float(iw.get("l_verfuegbar_mm") or 0)
        luft = float(iw.get("luft_je_seite_mm") or 0)
        # z = 0 ist der Anfang des verfuegbaren Bauraums; der Satz sitzt mittig.
        z0 = luft + lager
        if d_v > 0:
            for vz in (+1, -1):
                ax.plot([0, max(l_frei, l_ges)], [vz * d_v / 2.0] * 2,
                        color="#ffb454", lw=2.2, ls="--", zorder=1)
            ax.text(max(l_frei, l_ges) / 2.0, d_v / 2.0 + 4,
                    f"verfuegbare Bohrung {d_v:.1f} mm "
                    f"({iw.get('bindend', '')})", color="#ffb454",
                    ha="center", fontsize=9)
        if l_frei > 0:
            ax.plot([0, 0], [-d_v / 2.0, d_v / 2.0], color="#5a6570", lw=1.0)
            ax.plot([l_frei, l_frei], [-d_v / 2.0, d_v / 2.0],
                    color="#5a6570", lw=1.0)
            ax.text(l_frei / 2.0, -d_v / 2.0 - 12,
                    f"Bauraum {l_frei:.0f} mm  ·  Satz {l_ges:.1f} mm  ·  "
                    f"{luft:.1f} mm Luft je Seite (mittig)",
                    color="#93a1b1", ha="center", fontsize=9)
        farben = ("#4ea1ff", "#4ec98f")
        z = z0
        for si, st in enumerate(stufen_p):
            f = farben[si % 2]
            b = st["b_mm"]
            for vz in (+1, -1):
                # Hohlradkoerper (Rechteck vom Fusskreis nach aussen), Planet und
                # Sonne -- je Haelfte gespiegelt, wie im Maschinenbau ueblich.
                ax.add_patch(plt.Rectangle(
                    (z, vz * st["d_hohlrad_mm"] / 2.0), b,
                    vz * (st["d_aussen_mm"] - st["d_hohlrad_mm"]) / 2.0,
                    facecolor=f, alpha=0.22, edgecolor=f, lw=1.6, zorder=2))
                ax.add_patch(plt.Rectangle(
                    (z, vz * (st["a_sonne_planet_mm"] - st["d_planet_mm"] / 2.0)),
                    b, vz * st["d_planet_mm"], facecolor="#ff6b6b", alpha=0.22,
                    edgecolor="#ff6b6b", lw=1.4, zorder=2))
            ax.add_patch(plt.Rectangle(
                (z, -st["d_sonne_mm"] / 2.0), b, st["d_sonne_mm"],
                facecolor="#4ec98f", alpha=0.18, edgecolor="#4ec98f",
                lw=1.4, zorder=2))
            ax.text(z + b / 2.0, 0, f"{si + 1}", color="#dfe6ee",
                    ha="center", va="center", fontsize=11, zorder=4)
            # Die Beschriftungen zweier dicht benachbarter Stufen liegen sonst
            # uebereinander (gemessen: sie ueberlappten bei 8 mm Fuge) -- also
            # abwechselnd hoeher setzen.
            ax.text(z + b / 2.0,
                    st["d_aussen_mm"] / 2.0 + (4 if si % 2 == 0 else 15),
                    f"Stufe {si + 1}: i {st['i_ist']:g} · ⌀{st['d_aussen_mm']:.0f} "
                    f"· b {b:.0f} mm", color=f, ha="center", fontsize=8.5)
            z += b + _G.STUFENABSTAND_MM
        ax.axhline(0, color="#5a6570", lw=0.8, ls="-.", zorder=1)
        ax.set_aspect("equal")
        r_max = max(d_v, max(st["d_aussen_mm"] for st in stufen_p)) / 2.0 * 1.30
        ax.set_xlim(-0.06 * max(l_frei, l_ges, 1.0), max(l_frei, l_ges) * 1.06)
        ax.set_ylim(-r_max, r_max)
        ax.set_title(f"Planetensatz, {len(stufen_p)} Stufen koaxial in der "
                     f"Hohlwelle  ·  i = {erg['i_ist']}  (Laengsschnitt)",
                     color="#dfe6ee", fontsize=11)
        ax.tick_params(colors="#4a5560", labelsize=8)
        for sp in ax.spines.values():
            sp.set_color("#2a333f")
        fuss = (f"Werkstoff {erg.get('werkstoff', '?')} "
                f"[{erg.get('werkstoff_beleg', '?')}]"
                f"   ·   Wirkungsgrad "
                f"{(erg.get('wirkungsgrad') or {}).get('eta_nenn', '?')}"
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
