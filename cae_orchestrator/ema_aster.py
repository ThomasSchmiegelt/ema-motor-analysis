"""Code_Aster als DRITTER Loeser auf demselben Netz -- neben CalculiX und Z88.

Warum ueberhaupt
----------------

Die Rotorfestigkeit rechnet hier bisher zweimal: ``ema_deck`` schreibt einen
CalculiX-Satz, ``ema_z88`` denselben Fall fuer Z88Aurora, und beide sehen
**bitgleich dasselbe Netz** (``ema_deck.Netz`` ist bewusst formatfrei). Gemessen
stimmen sie auf 0,00-0,05 % ueberein -- das prueft Loeser und Rechensatz, nicht
das Netz und nicht das Modell.

Ein dritter, voellig unabhaengiger Loeser ist deshalb kein Luxus, sondern der
naechste belastbare Punkt: Code_Aster kommt aus einer anderen Schule (EDF,
eigener Elementkatalog, eigene Integration), und wo drei Loeser auf demselben
Netz dieselbe Zahl liefern, liegt der Fehler mit Sicherheit nicht im Loeser.

Was hier gemessen und nicht angenommen wurde
--------------------------------------------

1. **Es laeuft.** 17.4.0 aus dem entpackten Salome-Meca-Abbild unter
   ``~/aster-build``; ``import code_aster`` und ``code_aster.Commands`` gelingen
   mit dem mitgelieferten ``env_aster.sh``. Ohne dieses Environment gibt es
   ``code_aster`` im System-Python **nicht** -- der Loeser laeuft darum in einem
   Unterprozess mit eigener Umgebung, genau wie ``ccx`` und ``z88r``.

2. **Das Netzformat ist Asters eigenes** (``.mail``, ``FORMAT='ASTER'``), nicht
   MED. Grund: MED braucht ``medcoupling``, das im System-Python nicht liegt;
   ``.mail`` ist reiner Text und wird aus demselben ``Netz`` geschrieben wie die
   ``.inp`` und die ``z88i*.txt``. Dasselbe Argument, aus dem Z88 seine
   Textdateien bekommt.

3. **Der Lastfall ist wortgleich der der beiden anderen:** Fliehkraft bei
   ``rpm`` (``ROTATION`` um die z-Achse), beide Stirnflaechen axial gehalten
   (ebener Verzerrungszustand -- der konservative Fall, auf den
   ``ema_rotorcheck`` schon torwacht), die Bohrung **nicht** eingespannt, und
   drei Punktfesseln gegen die ebenen Starrkoerpermoden (``ema_deck._ebene_fesseln``
   -- dieselbe Funktion, keine zweite Auswahlregel).

Was hier NICHT behauptet wird
-----------------------------

Der Sektorlauf mit zyklischer Symmetrie bleibt CalculiX vorbehalten. Aster kann
das (``LIAISON_GROUP``), aber die Paarung der Schnittflaechenknoten waere eine
zweite Umsetzung derselben Sache -- und der Vergleich braucht ohnehin den
VOLLEN Rotor, damit alle drei Loeser dieselbe Aufgabe sehen. ``sektoren=0``.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile

import ema_deck as _deck

# Das entpackte Salome-Meca-Abbild. Eine Umgebungsvariable geht vor, damit eine
# andere Maschine nichts im Quelltext aendern muss.
ASTER_HEIM = os.environ.get("CAE_ASTER_HEIM",
                            os.path.expanduser("~/aster-build"))
ENV_SKRIPT = os.path.join(ASTER_HEIM, "env_aster.sh")


def verfuegbar() -> tuple[bool, str]:
    """(ok, Begruendung) — ohne etwas auszufuehren."""
    if not os.path.isfile(ENV_SKRIPT):
        return False, f"env_aster.sh nicht gefunden unter {ASTER_HEIM}"
    py = _aster_python()
    if not py:
        return False, "ASTER_PYTHON steht nicht in env_aster.sh"
    if not os.access(py, os.X_OK):
        return False, f"{py} ist nicht ausfuehrbar"
    return True, f"Code_Aster einsatzbereit ({os.path.basename(ASTER_HEIM)})"


def _aster_python() -> str:
    """Der Python-Interpreter des Abbilds -- aus ``env_aster.sh`` gelesen.

    Nicht nachgebaut: das Skript setzt ``LD_LIBRARY_PATH``, ``PYTHONPATH`` und
    ein halbes Dutzend ``ASTER_*``-Variablen aus Pfaden, die es selbst
    zusammensucht. Eine Abschrift hier liefe beim naechsten Abbild auseinander.
    """
    try:
        with open(ENV_SKRIPT, encoding="utf-8") as f:
            for zeile in f:
                if zeile.strip().startswith("export ASTER_PYTHON="):
                    roh = zeile.split("=", 1)[1].strip().strip('"').strip("'")
                    # ``${_IM}`` aufloesen wie die Shell es taete
                    for platz, wert in (("${_IM}", os.path.join(ASTER_HEIM, "salome-img")),
                                        ("$_IM", os.path.join(ASTER_HEIM, "salome-img"))):
                        roh = roh.replace(platz, wert)
                    return roh
    except OSError:
        pass
    return ""


# ── Netz schreiben: Asters eigenes Textformat ───────────────────────────────

def schreibe_mail(netz: _deck.Netz, pfad: str) -> dict:
    """``Netz`` → ``.mail`` (``FORMAT='ASTER'``). Gibt die Gruppennamen zurueck.

    Der Aufbau ist schlicht: ``COOR_3D`` mit den Knoten, dann ein Block je
    Elementtyp, dann die Gruppen. Zwei Dinge sind dabei nicht beliebig:

    * **Die Knotennummern heissen ``N<i>``, die Elemente ``M<i>``** -- Aster will
      Namen, keine blossen Zahlen. Die Nummer bleibt dieselbe wie im ``Netz``,
      damit sich ein Befund zwischen den drei Loesern ueberhaupt zuordnen laesst.
    * **Die Tet10-Knotenreihenfolge ist die von Gmsh**, und Aster erwartet
      dieselbe (Ecken 1-4, dann die Kantenmitten 12,23,13,14,24,34). Das ist
      geprueft, nicht geglaubt: ``test_aster`` rechnet das Volumen aus dem
      geschriebenen Netz zurueck.
    """
    typ = "TETRA4" if netz.ordnung == 1 else "TETRA10"
    z = ["TITRE", "  Rotoreisen aus ema_deck", "FINSF", "",
         "COOR_3D"]
    for i, (x, y, zz) in netz.knoten.items():
        z.append(f"  N{i}  {x:.6f}  {y:.6f}  {zz:.6f}")
    z += ["FINSF", "", typ]
    for eid, knoten in netz.elemente.items():
        z.append(f"  M{eid}  " + "  ".join(f"N{n}" for n in knoten))
    z += ["FINSF", ""]

    # Gruppen: das ganze Volumen, die beiden Stirnflaechen, die Bohrung.
    z += ["GROUP_MA", "  ROTOR"]
    for eid in netz.elemente:
        z.append(f"  M{eid}")
    z += ["FINSF", ""]

    gruppen = {}
    for name, ids in (("STIRN_A", netz.nset_stirn_a),
                      ("STIRN_B", netz.nset_stirn_b),
                      ("BOHRUNG", netz.nset_bohrung)):
        if not ids:
            continue
        gruppen[name] = len(ids)
        z += ["GROUP_NO", f"  {name}"]
        z += [f"  N{i}" for i in ids]
        z += ["FINSF", ""]

    # Die drei Starrkoerperfesseln bekommen je eine EIGENE Gruppe: in Aster
    # haengt die Randbedingung am Gruppennamen, und drei Knoten mit
    # verschiedenen Freiheitsgraden lassen sich nicht in einer fassen.
    fesseln = _deck._ebene_fesseln(netz)
    for k, (knoten, fg) in enumerate(fesseln):
        name = f"FESSEL{k}"
        gruppen[name] = 1
        z += ["GROUP_NO", f"  {name}", f"  N{knoten}", "FINSF", ""]
    z.append("FIN")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("\n".join(z) + "\n")
    return {"typ": typ, "gruppen": gruppen,
            "fesseln": [(k, fg) for k, fg in fesseln]}


# ── Der Rechensatz als Python -- Aster 17 wird als Bibliothek gefahren ──────

def schreibe_skript(netz: _deck.Netz, mat: dict, rpm: float, ordner: str,
                    mail: str, info: dict) -> str:
    """Das ``code_aster``-Skript. Rueckgabe: Pfad.

    Aster 17 laesst sich als gewoehnliche Bibliothek fahren (``code_aster.CA``)
    -- kein ``as_run``, kein ``.export``, keine Studienverwaltung. Das ist der
    Weg, den das mitgelieferte ``env_aster.sh`` selbst beschreibt, und er macht
    den Lauf zu dem, was er hier sein soll: ein Unterprozess mit einer Eingabe
    und einer Ausgabe.
    """
    omega = 2.0 * math.pi * float(rpm) / 60.0
    # Einheiten wie im ccx-Satz: mm, N, MPa. Dichte in t/mm^3, damit
    # rho*omega^2*r als N/mm^3 herauskommt.
    rho_t = float(mat["density"]) / 1e12
    e0 = float(mat["E"])
    nu = float(mat["nu"])

    # Fesseln: 1 = ux, 2 = uy (wie ``_ebene_fesseln``).
    fessel_zeilen = []
    for k, (_knoten, fg) in enumerate(info["fesseln"]):
        fg_name = "DX" if fg == 1 else "DY"
        fessel_zeilen.append(f"        _F(GROUP_NO='FESSEL{k}', {fg_name}=0.0),")

    stirn = []
    if "STIRN_A" in info["gruppen"]:
        stirn.append("        _F(GROUP_NO='STIRN_A', DZ=0.0),")
    if "STIRN_B" in info["gruppen"]:
        stirn.append("        _F(GROUP_NO='STIRN_B', DZ=0.0),")

    quelle = f'''# Erzeugt von ema_aster -- nicht von Hand aendern.
import json
import code_aster
from code_aster.Commands import (
    DEBUT, FIN, LIRE_MAILLAGE, AFFE_MODELE, DEFI_MATERIAU, AFFE_MATERIAU,
    AFFE_CHAR_MECA, MECA_STATIQUE, CALC_CHAMP, CREA_CHAMP,
)

DEBUT(PAR_LOT='NON', INFO=1)

MA = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)

MO = AFFE_MODELE(MAILLAGE=MA,
                 AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE',
                         MODELISATION='3D'))

ACIER = DEFI_MATERIAU(ELAS=_F(E={e0!r}, NU={nu!r}, RHO={rho_t!r}))

CHMAT = AFFE_MATERIAU(MAILLAGE=MA, AFFE=_F(TOUT='OUI', MATER=ACIER))

# Fliehkraft um die z-Achse -- derselbe Lastfall wie im ccx- und im Z88-Satz.
CHAR = AFFE_CHAR_MECA(
    MODELE=MO,
    ROTATION=_F(VITESSE={omega!r}, AXE=(0.0, 0.0, 1.0), CENTRE=(0.0, 0.0, 0.0)),
    DDL_IMPO=(
{chr(10).join(stirn)}
{chr(10).join(fessel_zeilen)}
    ),
)

RESU = MECA_STATIQUE(MODELE=MO, CHAM_MATER=CHMAT,
                     EXCIT=_F(CHARGE=CHAR))

# Spannungen je Element, an den Gausspunkten gemittelt -- dieselbe Groesse, die
# der ccx-Satz ueber *EL PRINT ausgibt (das .frd traegt knotengemittelte Werte,
# und die sind mit Z88 nicht vergleichbar).
RESU = CALC_CHAMP(reuse=RESU, RESULTAT=RESU, CONTRAINTE=('SIEF_ELGA', 'SIGM_ELNO'))

sief = RESU.getField('SIEF_ELGA', 1)
depl = RESU.getField('DEPL', 1)

# Ausgabe als JSON -- der aufrufende Prozess hat kein code_aster.
sp = {{}}
vals = sief.getValues()
n_komp = 6
mesh = MA
# Elementweise mitteln: Aster legt je Gausspunkt sechs Komponenten ab.
try:
    beschr = sief.getDescription()
    n_pg = {{}}
except Exception:
    beschr = None

import numpy as _np
arr = _np.asarray(vals, dtype=float)
n_el = mesh.getNumberOfCells()
if arr.size % n_komp:
    raise RuntimeError(f'SIEF_ELGA: {{arr.size}} Werte sind kein Vielfaches von 6')
blocks = arr.reshape(-1, n_komp)
# Gleichmaessige Aufteilung auf die Elemente (Tet4: 1 Gausspunkt, Tet10: 5)
if blocks.shape[0] % n_el:
    raise RuntimeError(f'{{blocks.shape[0]}} Gausspunkte auf {{n_el}} Elemente')
je = blocks.shape[0] // n_el
mittel = blocks.reshape(n_el, je, n_komp).mean(axis=1)

namen = mesh.getCellName if hasattr(mesh, 'getCellName') else None
for i in range(n_el):
    nm = namen(i) if namen else f'M{{i + 1}}'
    eid = int(str(nm).lstrip('M') or 0)
    sxx, syy, szz, sxy, sxz, syz = (float(v) for v in mittel[i])
    sp[eid] = (sxx, syy, szz, sxy, sxz, syz)

# Verschiebungen: NICHT ueber getValues(). Aster dualisiert Dirichlet-
# Randbedingungen mit Lagrange-Multiplikatoren, und die stehen im selben
# Vektor -- gemessen kam so eine "Verschiebung" von 1397 mm heraus, waehrend
# die Spannungen (157 MPa Spitze) voellig plausibel waren. Das war keine
# Verschiebung, sondern eine Reaktionskraft. ``toSimpleFieldOnNodes`` liefert
# je Knoten die PHYSIKALISCHEN Komponenten mit einer Gueltigkeitsmaske.
u = {{}}
try:
    sf = depl.toSimpleFieldOnNodes()
    werte, maske = sf.getValues()
    werte = _np.asarray(werte, dtype=float)
    maske = _np.asarray(maske, dtype=bool)
    komp = list(sf.getComponents())
    ix = [komp.index(c) for c in ('DX', 'DY', 'DZ')]
    for i in range(werte.shape[0]):
        if maske[i, ix].all():
            u[i + 1] = tuple(float(werte[i, j]) for j in ix)
except Exception as _e:                    # Fassungsunterschiede: dann lieber
    u = {{}}                                 # KEINE Zahl als eine falsche.

with open('ergebnis.json', 'w') as f:
    json.dump({{'spannungen': {{str(k): v for k, v in sp.items()}},
               'verschiebungen': {{str(k): v for k, v in u.items()}},
               'n_elemente': n_el}}, f)

FIN()
'''
    pfad = os.path.join(ordner, "rechnung.py")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(quelle)
    return pfad


def loese(netz: _deck.Netz, mat: dict, rpm: float, ordner: str = "",
          timeout: int = 3600) -> dict:
    """Netz schreiben, Aster fahren, Ergebnis einlesen.

    Der Loeser laeuft in einem Unterprozess mit der Umgebung aus
    ``env_aster.sh`` -- ``code_aster`` gibt es im System-Python nicht, und ein
    ``sys.path``-Kniff waere eine Behauptung ueber Bibliotheken, die im Abbild
    liegen.
    """
    ok, grund = verfuegbar()
    if not ok:
        return {"solver_status": "ASTER_FEHLT", "meldung": grund}
    if netz.sektoren:
        return {"solver_status": "NUR_VOLLROTOR",
                "meldung": ("Der Sektorlauf mit zyklischer Symmetrie bleibt "
                            "CalculiX vorbehalten; fuer den Vergleich braucht es "
                            "ohnehin den vollen Rotor (sektoren=0).")}

    eigener = not ordner
    ordner = ordner or tempfile.mkdtemp(prefix="aster_")
    os.makedirs(ordner, exist_ok=True)   # ein vorgegebener Ordner muss nicht da sein
    try:
        mail = os.path.join(ordner, "fort.20")     # UNITE=20
        info = schreibe_mail(netz, mail)
        skript = schreibe_skript(netz, mat, rpm, ordner, mail, info)

        py = _aster_python()
        # `env_aster.sh` sourcen und dann den Interpreter des Abbilds starten --
        # die Variablen setzt das Skript selbst, eine Abschrift hier liefe beim
        # naechsten Abbild auseinander.
        befehl = ["bash", "-lc",
                  f'source {ENV_SKRIPT!r} >/dev/null 2>&1; '
                  f'exec "$ASTER_PYTHON" {os.path.basename(skript)!r}']
        try:
            r = subprocess.run(befehl, cwd=ordner, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"solver_status": "ZEITUEBERSCHREITUNG",
                    "meldung": f"Aster ueber {timeout} s"}

        erg = os.path.join(ordner, "ergebnis.json")
        if not os.path.isfile(erg):
            fehler = [z for z in (r.stdout + r.stderr).splitlines()
                      if "<EXCEPTION" in z or "Error" in z or "erreur" in z.lower()]
            return {"solver_status": "KEINE_ERGEBNISSE",
                    "returncode": r.returncode,
                    "meldung": " | ".join(fehler[:3])
                               or (r.stdout or r.stderr or "")[-400:],
                    "ordner": ordner}
        import json as _json
        with open(erg, encoding="utf-8") as f:
            d = _json.load(f)
        return {"solver_status": "OK", "returncode": r.returncode,
                "ordner": ordner, "python": py,
                "spannungen": {int(k): tuple(v)
                               for k, v in d["spannungen"].items()},
                "verschiebungen": {int(k): tuple(v)
                                   for k, v in d["verschiebungen"].items()},
                "n_elemente": d.get("n_elemente")}
    finally:
        if eigener and os.path.isdir(ordner):
            pass        # der Ordner bleibt: bei einem Fehlschlag will man hineinsehen


def kennzahlen_aus_lauf(netz: _deck.Netz, lauf: dict,
                        yield_mpa: float = 0.0) -> dict:
    """Bequemer Abschluss: Aster-Lauf → DIESELBEN Kennzahlen wie ccx und Z88.

    Gerechnet wird in ``ema_deck.kennzahlen`` -- eine zweite Auswertung waere
    die Stelle, an der drei Loeser drei verschiedene Zahlen liefern, ohne dass
    der Loeser daran schuld waere.
    """
    if lauf.get("solver_status") != "OK":
        return {"solver_status": lauf.get("solver_status", "UNBEKANNT"),
                "meldung": lauf.get("meldung", "")}
    k = _deck.kennzahlen(netz, lauf["spannungen"], yield_mpa)
    u = lauf.get("verschiebungen") or {}
    if u:
        weit = max(math.sqrt(a * a + b * b + c * c) for a, b, c in u.values())
        k["max_displacement_mm"] = round(weit, 4)
        k["max_displacement_um"] = round(weit * 1e3, 3)
    k["solver"] = "code_aster"
    return k
