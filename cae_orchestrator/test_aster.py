"""Code Aster als DRITTER Loeser auf demselben Netz — ohne Aster pruefbar.

Der Sinn des dritten Loesers ist der Vergleich, nicht die dritte Zahl: wo drei
Loeser auf EINEM Netz dieselbe Zahl liefern, liegt ein Fehler mit Sicherheit
nicht im Loeser. Damit das trägt, muss zweierlei stimmen, und beides faellt
still aus, wenn es falsch ist:

* **Die Nummern muessen dieselben sein.** Ein Befund an Element 17.412 muss in
  allen drei Rechnungen dasselbe Element meinen, sonst vergleicht man Karten
  verschiedener Staedte.
* **Der Lastfall muss WORTGLEICH derselbe sein** — Fliehkraft bei ``rpm``, beide
  Stirnflaechen axial gehalten, Bohrung NICHT eingespannt, drei Punktfesseln.
  Eine andere Einspannung ergibt plausible Zahlen fuer ein anderes Problem.

Dazu drei gemessene Fallen, jede mit eigenem Test:

* **Aster dualisiert Dirichlet-Randbedingungen mit Lagrange-Multiplikatoren**,
  und die stehen im selben Vektor wie die Verschiebungen. Gemessen kam aus einem
  ``getValues().reshape(-1,3)`` eine "Verschiebung" von **1397 mm** heraus,
  waehrend die Spannungen mit 157,6 MPa voellig plausibel waren — das war keine
  Verschiebung, sondern eine Reaktionskraft. Geholt wird sie deshalb ueber
  ``toSimpleFieldOnNodes`` samt Gueltigkeitsmaske.
* **Die Dichte geht in t/mm^3 hinein** (``density/1e12``). Mit kg/m^3 rechnet
  Aster klaglos weiter und liefert Spannungen um zwoelf Groessenordnungen
  daneben — oder, was schlimmer ist, mit g/mm^3 um drei.
* **Ein vorgegebener Arbeitsordner muss nicht existieren.** ``loese`` legt ihn
  an; ohne das scheitert der Lauf erst beim Schreiben der ``fort.20``.

Aufruf: ``venv/bin/python test_aster.py``   (``--echt`` rechnet zusaetzlich
wirklich — Aster gegen CalculiX auf demselben Netz, dauert gut eine Minute.)
"""

import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_aster as A
import ema_deck as D

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


# Ein winziges Netz von Hand — kein gmsh, kein Aster, keine Sekunde Wartezeit.
# Die Bohrungsknoten liegen bei 0/90/180/270 Grad auf z=0, damit
# ``ema_deck._ebene_fesseln`` wirklich seine drei Knoten findet.
def _mininetz(ordnung=1):
    kn = {}
    for k, (x, y) in enumerate(((10, 0), (0, 10), (-10, 0), (0, -10)), start=1):
        kn[k] = (float(x), float(y), 0.0)                      # Bohrung, z=0
    for k, (x, y) in enumerate(((20, 0), (0, 20), (-20, 0), (0, -20)), start=5):
        kn[k] = (float(x), float(y), 0.0)                      # Rand, z=0
    for k, (x, y) in enumerate(((20, 0), (0, 20), (-20, 0), (0, -20)), start=9):
        kn[k] = (float(x), float(y), 30.0)                     # Rand, z=L
    return D.Netz(knoten=kn,
                  elemente={1: (1, 5, 6, 9), 2: (2, 6, 7, 10)},
                  ordnung=ordnung,
                  nset_bohrung=[1, 2, 3, 4],
                  nset_stirn_a=list(range(1, 9)),
                  nset_stirn_b=[9, 10, 11, 12],
                  poles=6, sektoren=0,
                  r_rot=20.0, r_shaft=10.0, axial_len=30.0)


print("1. Das Netz — dieselben Nummern wie bei CalculiX und Z88")
netz = _mininetz()
with tempfile.TemporaryDirectory() as tmp:
    pfad = os.path.join(tmp, "fort.20")
    info = A.schreibe_mail(netz, pfad)
    txt = open(pfad, encoding="utf-8").read()

pruefe(txt.rstrip().endswith("FIN"), "die .mail endet mit FIN")
pruefe("COOR_3D" in txt and "TETRA4" in txt, "COOR_3D und TETRA4 stehen drin")
pruefe(all(f"N{i} " in txt or f"N{i}\n" in txt or f" N{i}" in txt
           for i in netz.knoten),
       "JEDER Knoten steht unter seiner EIGENEN Nummer (N1…N5) — eine "
       "Umnummerierung machte einen Befund an Element X unvergleichbar")
pruefe(all(f"M{i}" in txt for i in netz.elemente),
       "und jedes Element als M<i>")
for grp in ("ROTOR", "STIRN_A", "STIRN_B", "BOHRUNG", "FESSEL0", "FESSEL1",
            "FESSEL2"):
    pruefe(grp in txt, f"Gruppe {grp} vorhanden")
pruefe(txt.count("TETRA10") == 0, "Tet4-Netz schreibt KEIN TETRA10")

netz10 = _mininetz(ordnung=2)
kn10 = dict(netz10.knoten)
for i in range(13, 19):                       # sechs Kantenmitten dazu
    kn10[i] = (float(i), 0.0, 0.0)
netz10 = D.Netz(knoten=kn10, elemente={1: (1, 5, 6, 9, 13, 14, 15, 16, 17, 18)},
                ordnung=2, nset_bohrung=netz10.nset_bohrung,
                nset_stirn_a=netz10.nset_stirn_a, nset_stirn_b=netz10.nset_stirn_b,
                poles=6, sektoren=0, r_rot=20.0, r_shaft=10.0, axial_len=30.0)
with tempfile.TemporaryDirectory() as tmp:
    p2 = os.path.join(tmp, "fort.20")
    A.schreibe_mail(netz10, p2)
    t2 = open(p2, encoding="utf-8").read()
pruefe("TETRA10" in t2 and "TETRA4" not in t2,
       "ein Tet10-Netz schreibt TETRA10 — der Elementtyp folgt dem Netz, "
       "nicht einer Vorgabe")


print("\n2. Der Lastfall — wortgleich der von CalculiX und Z88")
with tempfile.TemporaryDirectory() as tmp:
    mail = os.path.join(tmp, "fort.20")
    info = A.schreibe_mail(netz, mail)
    mat = {"E": 200000.0, "nu": 0.3, "density": 7850.0, "yield_mpa": 340.0}
    rpm = 12000.0
    skript = A.schreibe_skript(netz, mat, rpm, tmp, mail, info)
    code = open(skript, encoding="utf-8").read()

omega = 2 * math.pi * rpm / 60.0
pruefe(f"{omega!r}" in code,
       f"ROTATION mit VITESSE = {omega:.4f} rad/s (aus {rpm:.0f} min-1)")
pruefe("AXE=(0.0, 0.0, 1.0)" in code, "Drehachse ist z")
pruefe("'STIRN_A', DZ=0.0" in code and "'STIRN_B', DZ=0.0" in code,
       "BEIDE Stirnflaechen axial gehalten (ebener Verzerrungszustand — der "
       "konservative Fall, auf den ema_rotorcheck schon torwacht)")
pruefe("GROUP_NO='BOHRUNG'" not in code.split("DDL_IMPO")[1].split("MECA_STATIQUE")[0],
       "die Bohrung wird NICHT eingespannt — das waere ein anderes Problem als "
       "der frei rotierende Ring der analytischen Formel")
pruefe(code.count("GROUP_NO='FESSEL") == 3,
       "genau drei Punktfesseln gegen die Starrkoerpermoden")
pruefe("FESSEL0', DY=0.0" in code and "FESSEL1', DY=0.0" in code
       and "FESSEL2', DX=0.0" in code,
       "und jede in der Richtung, die ema_deck._ebene_fesseln vorgibt "
       "(uy@0°, uy@180°, ux@90°)")

print("\n3. Die Dichte geht in t/mm^3 — sonst rechnet Aster klaglos falsch")
pruefe(f"RHO={7850.0 / 1e12!r}" in code,
       "RHO = density/1e12 = 7.85e-09 t/mm^3 (E in MPa, Laenge in mm)")
pruefe("7850.0" not in code.split("DEFI_MATERIAU")[1].split(")")[0],
       "die rohe kg/m^3-Zahl steht NICHT im Materialsatz")

print("\n4. Die Verschiebung kommt NICHT aus getValues()")
pruefe("toSimpleFieldOnNodes" in code,
       "gelesen wird ueber toSimpleFieldOnNodes (physikalische Komponenten "
       "je Knoten, mit Gueltigkeitsmaske)")
pruefe(".reshape(-1, 3)" not in code and ".reshape(-1,3)" not in code,
       "und NICHT ueber ein reshape(-1,3) auf getValues() — dort stehen die "
       "Lagrange-Multiplikatoren der dualisierten Dirichlet-Bedingungen mit "
       "drin; gemessen kam so eine 'Verschiebung' von 1397 mm heraus, "
       "waehrend die Spannungen plausibel blieben")
_block = code.split("try:")[-1]
pruefe("except Exception" in _block and "u = {}" in _block,
       "und bei einer Fassungsabweichung bleibt u LEER — lieber keine Zahl als "
       "eine falsche; eine halb gefuellte Verschiebung saehe aus wie ein Ergebnis")

print("\n5. Was der Loeser ablehnt, bevor er laeuft")
sek = _mininetz()
sek.sektoren = 1
r = A.loese(sek, mat, rpm)
pruefe(r["solver_status"] == "NUR_VOLLROTOR",
       "ein Polsektor wird ABGEWIESEN statt genaehert — die zyklische Symmetrie "
       "steht als CalculiX-*EQUATION im .inp und hat in der .mail keine "
       "Entsprechung")
pruefe(bool(r.get("meldung")), "mit Begruendung")

ok, grund = A.verfuegbar()
pruefe(isinstance(ok, bool) and isinstance(grund, str),
       f"verfuegbar() antwortet ohne zu rechnen: {ok} ({grund[:60]})")

print("\n6. Die Kennzahlen kommen aus DERSELBEN Quelle wie bei ccx und Z88")
import inspect
quelle = inspect.getsource(A.kennzahlen_aus_lauf)
pruefe("_deck.kennzahlen(" in quelle,
       "kennzahlen_aus_lauf delegiert an ema_deck.kennzahlen — eine zweite "
       "Auswertung waere die Stelle, an der drei Loeser drei Zahlen liefern, "
       "ohne dass der Loeser daran schuld waere")
lauf = {"solver_status": "OK",
        "spannungen": {1: (100.0, 0, 0, 0, 0, 0), 2: (50.0, 0, 0, 0, 0, 0)},
        "verschiebungen": {1: (0.003, 0.004, 0.0)}}
k = A.kennzahlen_aus_lauf(netz, lauf, yield_mpa=340.0)
pruefe(k["solver"] == "code_aster", "und markiert den Loeser")
pruefe(abs(k["max_displacement_um"] - 5.0) < 1e-6,
       "u_max ist der BETRAG (0,003/0,004/0 mm → 5,000 um), nicht eine Komponente")
schlecht = A.kennzahlen_aus_lauf(netz, {"solver_status": "ASTER_FEHLT",
                                        "meldung": "x"}, 340.0)
pruefe(schlecht["solver_status"] == "ASTER_FEHLT" and "stress_peak_MPa" not in schlecht,
       "ein gescheiterter Lauf liefert KEINE Kennzahlen statt Nullen")

print("\n7. Ein vorgegebener Ordner muss nicht existieren")
quelle_l = inspect.getsource(A.loese)
pruefe("makedirs" in quelle_l.split("tempfile.mkdtemp")[1][:400],
       "loese legt den Arbeitsordner an — gemessen scheiterte der Lauf sonst "
       "erst beim Schreiben der fort.20")
pruefe("finally" in quelle_l and "rmtree" not in quelle_l,
       "und raeumt ihn NICHT weg — bei einem Fehlschlag will man in die "
       ".mess/.resu hineinsehen, und ein geloeschter Arbeitsordner ist die "
       "Stelle, an der die Ursache verschwindet")


if "--echt" in sys.argv:
    print("\n8. Der eigentliche Punkt: Aster GEGEN CalculiX auf EINEM Netz")
    import cae_cli
    g = dict(cae_cli.frischer_payload()["geom"]); g["axialLen"] = 80.0
    n = D.baue(g, mesh_mm=8.0, ordnung=1, sektoren=0)
    m = {"E": 200000.0, "nu": 0.3, "density": 7850.0, "yield_mpa": 340.0,
         "yield": 340.0}
    print(f"  Netz: {n.n_knoten} Knoten / {n.n_elemente} Tet4")
    t = tempfile.mkdtemp(prefix="test_aster_")
    inp = D.schreibe_inp(n, m, 12000.0, os.path.join(t, "rotor.inp"))
    rc = D.loese_ccx(inp)
    pruefe(rc["solver_status"] == "OK", "CalculiX gerechnet")
    ra = A.loese(n, m, 12000.0, ordner=os.path.join(t, "aster"), timeout=900)
    pruefe(ra["solver_status"] == "OK",
           f"Code Aster gerechnet ({str(ra.get('meldung',''))[:80]})")
    if rc["solver_status"] == "OK" and ra["solver_status"] == "OK":
        sc = D.lies_dat_spannungen(rc["dat"])
        sa = ra["spannungen"]
        gem = set(sc) & set(sa)
        pruefe(len(gem) == n.n_elemente,
               f"beide liefern ALLE {n.n_elemente} Elemente, unter denselben Nummern")
        dmax = max(abs(D.von_mises(*sc[e]) - D.von_mises(*sa[e])) for e in gem)
        smax = max(D.von_mises(*sc[e]) for e in gem)
        print(f"     sigma_v Spitze {smax:.3f} MPa, groesste Abweichung "
              f"{dmax:.2e} MPa = {dmax / smax * 100:.2e} %")
        pruefe(dmax / smax < 1e-4,
               "die Vergleichsspannung stimmt je Element auf Rundungsniveau — "
               "bei Tet4 (konstante Dehnung) ist das die richtige Erwartung, "
               "und eine BITgleiche Zahl waere der Verdachtsfall")
        pruefe(dmax > 0,
               "aber NICHT bitgleich — es sind wirklich zwei Rechnungen")
        u = ra["verschiebungen"]
        weit = max(math.dist((0, 0, 0), v) for v in u.values())
        print(f"     u_max {weit * 1e3:.3f} um")
        pruefe(0.001 < weit < 1.0,
               "u_max liegt in der Groessenordnung eines Rotors (mm-Bruchteile) "
               "— vor dem Lagrange-Fix standen hier 1397 mm")
else:
    print("\n8. (echter Loeserlauf uebersprungen — mit --echt anfordern)")


print("\n" + "=" * 66)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
