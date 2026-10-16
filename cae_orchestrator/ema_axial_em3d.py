"""Axialfluss in Elmer 3-D -- der Ringsektor, gegen den sich der Mehrschnitt messen laesst.

WOZU, und warum nicht frueher
------------------------------
``ema_axial_fdm`` loest die abgewickelte theta-z-Ebene bei mehreren Radien und
legt die Loesungen uebereinander. Das ist das Standardverfahren der
Axialflussrechnung und es traegt weit -- aber es laesst ``d/dr`` vollstaendig
fallen. Jede Scheibe rechnet, als setze sich ihre Geometrie radial unendlich
fort; die Streuung an Ri und Ro und die radialen Stromkomponenten im Wickelkopf
fehlen darin. Das steht seit dem ersten Entwurf als Grenze in jeder Ausgabe,
und die Zeile dazu sagt: **nachzumessen an Stufe 3, nicht anzunehmen.**

Dies ist Stufe 3. Gerechnet wird EIN Polsektor des Ringraums in Elmer, als
echte 3-D-Magnetostatik -- derselbe Loeser (``WhitneyAVSolver``), dieselben
anti-periodischen Winkelflaechen und dieselbe lineare Permeabilitaet wie im
radialen Ein-Pol-Sektor (``ema_em3d.run_em3d_sector``). Die Gleichheit ist
Absicht: was dort ueber Jahre geprueft wurde, soll hier nicht neu erfunden
werden, und eine Abweichung zwischen Mehrschnitt und 3-D soll an der GEOMETRIE
liegen und nicht am Loeser.

WAS DER SEKTOR KANN, WAS DIE SCHEIBEN NICHT KOENNEN
----------------------------------------------------
Genau eines, und dafuer gibt es ihn: **den Rand.** Bei Ri und Ro hoert das
Eisen auf, und der Fluss tritt dort seitlich aus. Im Mehrschnitt ist dieser
Austritt per Konstruktion null -- die Scheibe bei Ro weiss nicht, dass
daneben nichts mehr kommt. Deshalb bekommt das Modell hier **Luftraender**
innen und aussen (``RAND_ANTEIL``), und genau in ihnen steht das, was der
Mehrschnitt nicht hat.

WAS ER NICHT KANN
------------------
* **Lineares Eisen** (``MU_R_IRON``), wie der Mehrschnitt und wie der radiale
  3-D-Pfad. Eine Saettigungsrechnung waere eine andere Stufe.
* **Kein Staenderstrom.** Die Nuten werden als Luft gebaut, aber nicht
  bestromt: der Vergleich, um den es geht, ist der LEERLAUF -- dort allein
  unterscheiden sich Mehrschnitt und 3-D in der Geometrie und sonst in nichts.
  Mit Strom kaeme die Frage nach dem Wickelkopf dazu, und der ist hier so wenig
  gebaut wie im radialen Sektor.
* **Ein Pol.** Was ueber eine Polteilung hinausgeht (Schraegung, Unwucht,
  ungleiche Pole), ist darin nicht darstellbar.

DIE EINHEIT IST MILLIMETER, wie im radialen 3-D-Pfad und aus demselben Grund:
die Magnetostatik ist skaleninvariant, und zwei Einheitensysteme in einer
Werkzeugkette sind die Stelle, an der jemand den Faktor 1000 sucht (gemessen
am harmonischen Loeser, der in METERN rechnet -- s. ``ema_em3d_harm``).
"""
from __future__ import annotations

import math
import os

MU0 = 4.0e-7 * math.pi

#: Lineare Permeabilitaeten -- dieselben Zahlen wie ``ema_analysis`` und
#: ``ema_em3d``, damit eine Abweichung zwischen den Wegen nicht am Werkstoff
#: liegen kann.
MU_R_IRON = 500.0
MU_R_MAG = 1.05

#: Luftrand innen und aussen, als Anteil der RINGBREITE (Ro - Ri). Er traegt
#: die radiale Streuung -- den einen Effekt, fuer den es diesen Sektor gibt.
#: Zu schmal gewaehlt klemmt die Randbedingung den Austritt ab und das Modell
#: faende genau nichts; `rand_pruefen` misst deshalb nach, wieviel Fluss im
#: Rand ankommt.
RAND_ANTEIL = 0.35

#: Luftpolster ueber dem aeusseren Joch, als Anteil der Jochdicke. Null waere
#: die Aussage „das Joch schliesst den Fluss vollstaendig ein"; das stimmt
#: naeherungsweise und ist die Randbedingung des Mehrschnitts. Ein duennes
#: Polster laesst dem 3-D-Modell die Moeglichkeit, es zu widerlegen.
DECKEL_ANTEIL = 0.25


def _lagen(geom: dict) -> list:
    """Die axiale Schichtung -- delegiert an ``ema_axial_fdm.lagen``.

    Sie stand hier als eigene Fassung und war im ersten Entwurf prompt falsch
    (zwei Zahnbaender beim YASA, 90 mm statt 65). Seit dem 07.10.2026 ist die
    Quelle ``ema_axial_fdm.lagen``, weil mit dem CAD ein dritter Leser dazukam;
    diese Huelle bleibt, damit Aufrufer und Test unveraendert weiterlaufen.
    """
    import ema_axial_fdm as AF
    return AF.lagen(geom)


def _sektor(occ, r_i: float, r_a: float, z0: float, dz: float,
            a0: float, da: float) -> int:
    """Ein Ringsektor als Volumen: Zylinderkeil minus innerem Zylinderkeil.

    ``addCylinder`` mit Winkel gibt einen Tortenkeil; die Differenz zweier
    konzentrischer Keile ist der Ringsektor. Das ist derselbe Weg wie in
    ``ema_em3d._build_sector_mesh`` -- und er ist der robuste: ein aus Boegen
    zusammengesetzter Polygonzug laesst OCC an der Rundung Splitter stehen.
    """
    gross = occ.addCylinder(0, 0, z0, 0, 0, dz, r_a, angle=da)
    occ.rotate([(3, gross)], 0, 0, 0, 0, 0, 1, a0)
    if r_i <= 1e-6:
        return gross
    klein = occ.addCylinder(0, 0, z0 - 1.0, 0, 0, dz + 2.0, r_i, angle=da)
    occ.rotate([(3, klein)], 0, 0, 0, 0, 0, 1, a0)
    aus = occ.cut([(3, gross)], [(3, klein)])
    return aus[0][0][1]


def _nut_box(occ, b: float, r_i: float, r_a: float, z0: float, dz: float,
             theta: float) -> int:
    """EINE parallelflankige Nut: ein Quader der Breite ``b``, radial gelegt.

    Das ist die Signatur dieser Bauart (Igelspacher Kap. 2.1): die Nut hat
    ueber dem ganzen Radius dieselbe Breite, also werden die Zaehne nach aussen
    breiter. Ein Kreissektor als Nut waere eine andere Maschine -- dann haetten
    Zahn und Nut ueber dem Radius ein festes Verhaeltnis und der kritische
    Punkt am Innenrand existierte nicht.
    """
    laenge = r_a - r_i + 2.0
    box = occ.addBox(r_i - 1.0, -b / 2.0, z0, laenge, b, dz)
    occ.rotate([(3, box)], 0, 0, 0, 0, 0, 1, theta)
    return box


def baue_netz(geom: dict, msh_pfad: str, lc_mm: float = 0.0,
              lc_spalt_mm: float = 0.0, melde=None) -> dict:
    """Ein Polsektor des Ringraums, vernetzt.

    Der Sektor ist EINE Polteilung breit und anti-periodisch gekoppelt -- so
    wie der radiale Ein-Pol-Sektor. Zwei Polteilungen (periodisch) waeren
    doppelt so teuer und sagten dasselbe.
    """
    import gmsh
    import ema_axial_thermik as AT

    g = AT._geo(geom)
    a = g["a"]
    ri, ro = g["ri"] * 1000.0, g["ro"] * 1000.0
    poles = int(a["poles"])
    q = int(a["slots"])
    b_nut = g["b_nut"] * 1000.0
    alpha_pol = 2.0 * math.pi / poles                 # Polteilung, mechanisch
    bed = float(a["polbedeckung"])
    lagen = _lagen(geom)
    hoehe = lagen[-1]["z1"]

    rand = RAND_ANTEIL * (ro - ri)
    r_in, r_out = max(1.0, ri - rand), ro + rand
    # Luftpolster oben und unten: ohne es waere `A x n = 0` direkt auf der
    # Jochaussenflaeche die Aussage „das Joch schliesst vollstaendig ein" --
    # genau die Annahme des Mehrschnitts, die hier gepruft werden soll.
    deckel = DECKEL_ANTEIL * max(lagen[0]["d"], lagen[-1]["d"])

    # Der Luftspalt ist das duennste Merkmal und bindet die Zellgroesse.
    spalt_mm = g["spalt"] * 1000.0
    lc_gap = lc_spalt_mm or max(0.4, spalt_mm / 1.5)
    lc = lc_mm or max(lc_gap * 6.0, (ro - ri) / 9.0)

    gmsh.initialize(interruptible=False)              # s. ema_deck: Flask-Falle
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("axialsektor")
        occ = gmsh.model.occ

        # 1. Die Schichten, jede ueber den VOLLEN Radiusbereich inkl. Rand.
        #    Was Eisen ist und was Luft, entscheidet die Zuordnung spaeter am
        #    Schwerpunkt -- gebaut wird erst einmal die Schichtung.
        stuecke, kennung = [], []
        for lg in lagen:
            v = _sektor(occ, r_in, r_out, lg["z0"], lg["d"], 0.0, alpha_pol)
            stuecke.append(v); kennung.append(lg["art"])
        if deckel > 0.05:
            stuecke.append(_sektor(occ, r_in, r_out, -deckel, deckel, 0.0, alpha_pol))
            kennung.append("deckel")
            stuecke.append(_sektor(occ, r_in, r_out, hoehe, deckel, 0.0, alpha_pol))
            kennung.append("deckel")

        # 2. Die Magnete: ein Ringsektor der Breite `bed * Polteilung`, mittig
        #    in der Polteilung, NUR ueber dem aktiven Ringraum.
        mag_w = bed * alpha_pol
        mag_a0 = (alpha_pol - mag_w) / 2.0
        magnete = []
        for lg in lagen:
            if lg["art"] != "magnet":
                continue
            magnete.append(_sektor(occ, ri, ro, lg["z0"], lg["d"], mag_a0, mag_w))

        # 3. Die Nuten: parallelflankige Quader, radial gelegt, in jedem
        #    Zahnband. Nur die, die in diese Polteilung fallen.
        tau_s = 2.0 * math.pi / q
        nuten = []
        for lg in lagen:
            if lg["art"] != "stator":
                continue
            k = 0
            while k * tau_s < alpha_pol + tau_s:
                th = (k + 0.5) * tau_s
                if -1e-9 <= th <= alpha_pol + 1e-9:
                    nuten.append(_nut_box(occ, b_nut, ri, ro, lg["z0"], lg["d"], th))
                k += 1

        occ.synchronize()
        if melde:
            melde("fragmentieren", 0)
        # Die Reihenfolge der Eingaben ist der GRIFF: `fragment` gibt eine
        # Karte zurueck, die zu jedem Eingabekoerper seine Ausgabestuecke
        # nennt. Ein Magnet liegt INNERHALB seiner Schicht, also beansprucht
        # ihn die Schicht AUCH -- aber nur den Magneten beansprucht der Magnet.
        # Daran ist er eindeutig.
        #
        # Ueber den Schwerpunkt ginge es NICHT, und das ist gemessen: nach dem
        # Fragmentieren hat der Rest der Schicht (ein C um den Magneten herum)
        # denselben Schwerpunktwinkel wie der Magnet selbst (beide 11,25 Grad)
        # und liegt im selben Radiusband. Die erste Fassung erklaerte deshalb
        # beide zu Magneten -- vier statt zwei.
        n_schicht, n_mag = len(stuecke), len(magnete)
        alles = [(3, v) for v in stuecke + magnete + nuten]
        teile, karte = occ.fragment(alles, [])
        occ.synchronize()

        aus_magnet, aus_nut = {}, set()
        for k, ausgabe in enumerate(karte):
            for dim, v in ausgabe:
                if dim != 3:
                    continue
                if n_schicht <= k < n_schicht + n_mag:
                    aus_magnet[v] = k - n_schicht
                elif k >= n_schicht + n_mag:
                    aus_nut.add(v)

        # 4. Zuordnen ueber Schwerpunkt und z -- dieselbe Technik wie im
        #    radialen Sektor, weil konzentrische Ringe ihren Volumen-
        #    schwerpunkt AUF der Achse haben und die Flaeche allein nicht
        #    eindeutig ist.
        gruppen = {"eisen": [], "luft": [], "magnet": []}
        mag_info = []
        for dim, v in occ.getEntities(3):
            x, y, z = occ.getCenterOfMass(3, v)
            r = math.hypot(x, y)
            th = math.atan2(y, x) % (2.0 * math.pi)
            lg = next((l for l in lagen if l["z0"] - 1e-6 <= z < l["z1"] + 1e-6), None)
            art = lg["art"] if lg else "deckel"
            im_ring = (ri - 1e-6) <= r <= (ro + 1e-6)
            if not im_ring or art in ("deckel", "spalt"):
                gruppen["luft"].append(v); continue
            if art == "magnet":
                if v in aus_magnet:
                    gruppen["magnet"].append(v)
                    # Das Vorzeichen kommt aus der BAUFORM (`kenn`): YASA
                    # gleichsinnig (NS), TORUS gegensinnig (NN). Der Wechsel
                    # von Pol zu Pol steckt dagegen in der ANTI-Periodik der
                    # Winkelflaechen und nicht hier.
                    mag_info.append({"v": v, "z": z,
                                     "vz": float(lg.get("kenn") or 1)})
                else:
                    gruppen["luft"].append(v)
                continue
            if art == "stator":
                # In der Nut liegt Luft -- welches Stueck die Nut IST, sagt die
                # Fragment-Karte. Ueber den Schwerpunkt waere es dieselbe Falle
                # wie beim Magneten.
                gruppen["luft" if v in aus_nut else "eisen"].append(v)
                continue
            gruppen["eisen"].append(v)

        pid = {}
        lauf = 0
        for name in ("eisen", "luft"):
            if gruppen[name]:
                lauf += 1
                gmsh.model.addPhysicalGroup(3, gruppen[name], lauf, name)
                pid[name] = lauf
        mag_pid = []
        for i, m in enumerate(mag_info):
            lauf += 1
            gmsh.model.addPhysicalGroup(3, [m["v"]], lauf, f"magnet_{i}")
            mag_pid.append({"phys": lauf, "z": m["z"], "vz": m["vz"]})

        # 5. Raender: die beiden Winkelflaechen anti-periodisch, alles andere
        #    A x n = 0.
        # **Nur die AEUSSEREN Flaechen.** Der erste Entwurf steckte jede
        # 2-D-Entitaet in „aussen" -- also auch jede INNERE Grenzflaeche
        # zwischen zwei Volumen. Damit stand `A x n = 0` ueberall, und das
        # Feld kam mit 4e-15 T heraus: numerisch null, ohne Fehlermeldung.
        # Eine Randflaeche hat genau EIN angrenzendes Volumen; das ist das
        # Unterscheidungsmerkmal, und es ist exakt statt geometrisch geraten.
        rand_m, rand_s, rand_a = [], [], []
        for dim, f in occ.getEntities(2):
            oben, _ = gmsh.model.getAdjacencies(2, f)
            if len(oben) != 1:
                continue                      # innere Grenzflaeche
            x, y, zz = occ.getCenterOfMass(2, f)
            th = math.atan2(y, x)
            r = math.hypot(x, y)
            if r > 1e-6 and abs(th) < 1e-6:
                rand_m.append(f)
            elif r > 1e-6 and abs(((th - alpha_pol + math.pi) % (2 * math.pi))
                                  - math.pi) < 1e-6:
                rand_s.append(f)
            else:
                rand_a.append(f)
        lauf_f = 0
        fpid = {}
        for name, fl in (("master", rand_m), ("slave", rand_s), ("aussen", rand_a)):
            if fl:
                lauf_f += 1
                gmsh.model.addPhysicalGroup(2, fl, lauf_f, name)
                fpid[name] = lauf_f

        # 6. Groessenfeld: der Spalt fein, der Rest grob.
        gmsh.option.setNumber("Mesh.MeshSizeMin", lc_gap * 0.6)
        gmsh.option.setNumber("Mesh.MeshSizeMax", lc)
        # Je Luftspalt EIN schmales Band, nicht ein Kasten ueber die halbe
        # Maschine: der erste Entwurf deckte alles oberhalb des ersten Spalts
        # mit 0,5-mm-Zellen ab -- ueber 243.000 mm^3 waeren das Millionen
        # Elemente, und der Netzbau kam nicht zurueck. Der Spalt ist 1 mm
        # duenn; er braucht die feinen Zellen in einem Band von wenigen
        # Millimetern, sonst nirgends.
        felder = []
        for sp in [l for l in lagen if l["art"] == "spalt"]:
            fld = gmsh.model.mesh.field.add("Box")
            gmsh.model.mesh.field.setNumber(fld, "VIn", lc_gap)
            gmsh.model.mesh.field.setNumber(fld, "VOut", lc)
            gmsh.model.mesh.field.setNumber(fld, "XMin", -r_out - 1)
            gmsh.model.mesh.field.setNumber(fld, "XMax", r_out + 1)
            gmsh.model.mesh.field.setNumber(fld, "YMin", -r_out - 1)
            gmsh.model.mesh.field.setNumber(fld, "YMax", r_out + 1)
            gmsh.model.mesh.field.setNumber(fld, "ZMin", sp["z0"] - 1.5 * sp["d"])
            gmsh.model.mesh.field.setNumber(fld, "ZMax", sp["z1"] + 1.5 * sp["d"])
            gmsh.model.mesh.field.setNumber(fld, "Thickness", 3.0 * sp["d"])
            felder.append(fld)
        if felder:
            mi = gmsh.model.mesh.field.add("Min")
            gmsh.model.mesh.field.setNumbers(mi, "FieldsList", felder)
            gmsh.model.mesh.field.setAsBackgroundMesh(mi)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)

        if melde:
            melde("vernetzen", 0)
        gmsh.model.mesh.generate(3)
        os.makedirs(os.path.dirname(msh_pfad) or ".", exist_ok=True)
        gmsh.write(msh_pfad)
        knoten = len(gmsh.model.mesh.getNodes()[0])
        _, el, _ = gmsh.model.mesh.getElements(3)
        tets = sum(len(e) for e in el)
        return {"msh": msh_pfad, "knoten": int(knoten), "tets": int(tets),
                "pid": pid, "magnete": mag_pid, "flaechen": fpid,
                "alpha": alpha_pol, "lagen": lagen, "ri_mm": ri, "ro_mm": ro,
                "r_in_mm": r_in, "r_out_mm": r_out, "hoehe_mm": hoehe,
                "poles": poles, "slots": q, "n_magnet": len(mag_pid),
                "n_nut_sektor": len(nuten), "lc_mm": lc, "lc_spalt_mm": lc_gap}
    finally:
        gmsh.finalize()


def schreibe_sif(geom: dict, netz: dict, work_dir: str,
                 mesh_name: str = "mesh") -> str:
    """``case.sif`` fuer den Polsektor -- derselbe Bau wie im radialen Sektor.

    Magnetostatik (``WhitneyAVSolver``), Magnete als ``Body Force
    Magnetization``, die beiden Winkelflaechen **anti-periodisch** (`Periodic
    BC` + `Rotate` + `Scale = -1` + Lagrange), alles andere ``A x n = 0``.

    **Keine Coordinate Scaling**: gerechnet wird in Millimetern wie im radialen
    3-D-Pfad. Die Magnetostatik ist skaleninvariant, und zwei Einheitensysteme
    in einer Kette sind die Stelle, an der jemand den Faktor 1000 sucht.

    **Die Magnetisierung zeigt AXIAL** (z), nicht radial -- das ist der ganze
    Unterschied zur Radialmaschine und die Stelle, an der ein uebernommener
    Radialzweig still falsch waere.
    """
    from ema_pipeline import MAGNETS
    mag = MAGNETS.get(geom.get("magnet", "ndfeb_n35"), MAGNETS["ndfeb_n35"])
    Hc = float(mag["Br"]) / MU0
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)

    f = netz["flaechen"]
    alpha_deg = math.degrees(netz["alpha"])
    S = [f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n',
         "Simulation\n  Max Output Level = 4\n  Coordinate System = Cartesian\n"
         "  Simulation Type = Steady State\n  Steady State Max Iterations = 1\n"
         "  Output Intervals = 1\nEnd\n",
         f"Constants\n  Permeability of Vacuum = {MU0:.12e}\nEnd\n",
         'Solver 1\n  Equation = "MgDyn"\n'
         '  Procedure = "MagnetoDynamics" "WhitneyAVSolver"\n'
         '  Variable = "AV"\n  Use Tree Gauge = Logical True\n'
         # **Direkt, nicht iterativ** -- und das ist Hauserfahrung, keine
         # Vorliebe: fuer genau diesen Loeser auf Tetraedern steht in
         # CLAUDE.md „Solver 1 = Direct/MUMPS (Iterativ stagniert)", und der
         # radiale Ein-Pol-Sektor macht es ebenso. Der erste Entwurf hier nahm
         # BiCGStabL+ILU1 und lief ueber 200 s ohne eine einzige Ausgabezeile.
         # (Beim HEX-Netz gilt das Umgekehrte -- dort ist MUMPS unvertraeglich
         # und Tree Gauge auch; dieser Sektor ist tetraedrisch.)
         '  Linear System Solver = Direct\n'
         '  Linear System Direct Method = MUMPS\n'
         '  Nonlinear System Max Iterations = 1\nEnd\n',
         'Solver 2\n  Equation = "MgDynCalc"\n'
         '  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"\n'
         '  Potential Variable = "AV"\n  Calculate Magnetic Flux Density = True\n'
         '  Linear System Solver = Iterative\n  Linear System Iterative Method = CG\n'
         '  Linear System Preconditioning = ILU0\n'
         '  Linear System Max Iterations = 5000\n'
         '  Linear System Convergence Tolerance = 1.0e-8\nEnd\n',
         'Solver 3\n  Equation = "ResultOutput"\n'
         '  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
         '  Output File Name = "case"\n  Output Directory = "results"\n'
         '  Vtu Format = Logical True\n  Save Geometry Ids = Logical True\nEnd\n',
         "Equation 1\n  Active Solvers(2) = 1 2\nEnd\n",
         f'Material 1\n  Name = "eisen"\n  Relative Permeability = {MU_R_IRON}\nEnd\n',
         'Material 2\n  Name = "luft"\n  Relative Permeability = 1.0\nEnd\n',
         f'Material 3\n  Name = "magnet"\n  Relative Permeability = {MU_R_MAG}\nEnd\n']

    # **Die Body-Reihenfolge MUSS die Koerpernummer sein.** Elmers
    # ``Save Geometry Ids`` schreibt den INDEX des Body-Blocks, nicht die
    # Nummer aus ``Target Bodies`` -- gemessen am 20.09.2026 in
    # ``ema_em2d_stat``, und dort las die Auswertung unter „Luftspalt" die
    # Flussbarrieren (0,0042 statt 0,951 T, Faktor 225, ohne Fehlermeldung).
    koerper = []
    for name, mat in (("eisen", 1), ("luft", 2)):
        if netz["pid"].get(name):
            koerper.append((netz["pid"][name], name, mat, None))
    for i, m in enumerate(netz["magnete"]):
        koerper.append((m["phys"], f"magnet_{i}", 3, m["vz"]))
    koerper.sort(key=lambda t: t[0])
    erwartet = 1
    for nummer, name, mat, vz in koerper:
        if nummer != erwartet:
            raise RuntimeError(
                f"Koerpernummern nicht luecklos: {name} hat {nummer}, "
                f"erwartet {erwartet}. Elmers Save Geometry Ids schriebe dann "
                f"den Block-Index und die Auswertung laese den falschen Koerper.")
        erwartet += 1
    bf = 0
    for nummer, name, mat, vz in koerper:
        if vz is None:
            S.append(f'Body {nummer}\n  Name = "{name}"\n  Equation = 1\n'
                     f'  Material = {mat}\nEnd\n')
        else:
            bf += 1
            S.append(f'Body {nummer}\n  Name = "{name}"\n  Equation = 1\n'
                     f'  Material = {mat}\n  Body Force = {bf}\nEnd\n')
            # AXIAL magnetisiert -- die Scheibe, nicht der Zylinder.
            S.append(f'Body Force {bf}\n  Magnetization 1 = Real 0.0\n'
                     f'  Magnetization 2 = Real 0.0\n'
                     f'  Magnetization 3 = Real {Hc * vz:.6e}\nEnd\n')

    S.append(f'Boundary Condition {f["aussen"]}\n'
             f'  Target Boundaries(1) = {f["aussen"]}\n'
             '  AV {e} = Real 0\n  AV = Real 0\nEnd\n')
    S.append(f'Boundary Condition {f["slave"]}\n'
             f'  Target Boundaries(1) = {f["slave"]}\n'
             f'  Periodic BC = {f["master"]}\n'
             f'  Periodic BC Rotate(3) = 0 0 {alpha_deg:.10f}\n'
             '  Periodic BC Scale = Real -1.0\n'
             '  Periodic BC Use Lagrange Coefficient = Logical True\nEnd\n')
    sif = os.path.join(work_dir, "case.sif")
    with open(sif, "w", encoding="utf-8") as fh:
        fh.write("\n".join(S))
    return sif


def luftspaltfeld(vtu_pfad: str, netz: dict, n_r: int = 24,
                  n_theta: int = 120) -> dict:
    """``B_z(r, theta)`` in der Spaltmitte -- die Groesse, die den Vergleich traegt.

    Abgetastet wird auf einem Gitter ueber (r, theta) IN der Spaltmitte. Daraus
    fallen zwei Dinge:

    * ``B_gap(r)`` -- die Grundwelle ueber dem Radius. Das ist die Kurve, die
      der Mehrschnitt ebenfalls liefert, und an ihr wird er gemessen.
    * der **Randabfall**: wieviel von B_gap bei Ri und Ro uebrig ist. Genau das
      kann der Mehrschnitt nicht -- dort setzt sich jede Scheibe radial
      unendlich fort, der Abfall ist per Konstruktion null.
    """
    import numpy as np
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    sp = [l for l in netz["lagen"] if l["art"] == "spalt"]
    if not sp:
        return {"ok": False, "grund": "keine Spaltschicht im Netz"}
    z_m = 0.5 * (sp[0]["z0"] + sp[0]["z1"])

    ls = vtk.vtkXMLUnstructuredGridReader()
    ls.SetFileName(vtu_pfad)
    ls.Update()
    gitter = ls.GetOutput()

    ri, ro = netz["ri_mm"], netz["ro_mm"]
    alpha = netz["alpha"]
    rr = np.linspace(ri + 0.02 * (ro - ri), ro - 0.02 * (ro - ri), n_r)
    tt = np.linspace(0.0, alpha, n_theta, endpoint=False)
    pts = vtk.vtkPoints()
    for r in rr:
        for t in tt:
            pts.InsertNextPoint(r * math.cos(t), r * math.sin(t), z_m)
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    probe = vtk.vtkProbeFilter()
    probe.SetInputData(poly)
    probe.SetSourceData(gitter)
    probe.Update()
    aus = probe.GetOutput()

    name = None
    for i in range(aus.GetPointData().GetNumberOfArrays()):
        n = aus.GetPointData().GetArrayName(i)
        if n and "magnetic flux density" in n.lower():
            name = n
            break
    if name is None:
        return {"ok": False, "grund": "keine Flussdichte in der VTU"}
    B = vtk_to_numpy(aus.GetPointData().GetArray(name)).reshape(n_r, n_theta, -1)
    # ``vtkProbeFilter`` gibt ausserhalb des Netzes stillschweigend NULLEN
    # zurueck -- dieselbe Falle wie bei den Feldlinien in ``ema_em3d_harm``,
    # wo eine gueltige LEERE Datei entstand und der Lauf „geschrieben" meldete.
    gueltig = vtk_to_numpy(aus.GetPointData().GetArray("vtkValidPointMask")) \
        .reshape(n_r, n_theta).astype(bool)
    Bz = np.where(gueltig, B[..., 2], np.nan)

    # **Die Grundwelle, und zwar DIESELBE Groesse wie im Mehrschnitt.**
    #
    # Der Mehrschnitt rechnet `2*|k[h1]|` -- die Amplitude der ersten
    # Harmonischen der Normalkomponente ueber seinem Fenster. Hier ist das
    # Fenster EINE Polteilung, also eine HALBE Periode: ueber ihr hat die
    # Grundwelle eine halbe Schwingung. Projiziert wird deshalb auf
    # `exp(-i*pi*k/n)`, und der Faktor ist 2/n -- die Haelfte des Integrals
    # ueber die volle Periode faellt wegen der Antiperiodik gleich aus.
    #
    # Der erste Entwurf nahm `mittelwert(|B|) * pi/2`. Das ist bei 85 %
    # Polbedeckung um 8 % daneben und bei anderer Bedeckung um mehr -- eine
    # Naeherung an der Stelle, an der gerade verglichen werden soll.
    ph = np.exp(-1j * math.pi * np.arange(n_theta) / n_theta)
    b_r, belegt = [], []
    for k in range(n_r):
        m = np.isfinite(Bz[k])
        belegt.append(float(m.sum()) / n_theta)
        if m.sum() < n_theta * 0.6:
            b_r.append(float("nan"))
            continue
        z_ = np.where(m, Bz[k], 0.0)
        b_r.append(float(2.0 * abs(np.sum(z_ * ph)) / n_theta))

    b_r = np.array(b_r)
    gut = np.isfinite(b_r)
    mitte = b_r[gut][len(b_r[gut]) // 2] if gut.any() else float("nan")
    return {"ok": bool(gut.any()), "r_mm": rr.tolist(), "B_gap_T": b_r.tolist(),
            "belegt": belegt, "z_spalt_mm": z_m, "feld": name,
            "B_gap_mitte_T": float(mitte),
            "rand_innen": float(b_r[gut][0] / mitte) if gut.any() and mitte else None,
            "rand_aussen": float(b_r[gut][-1] / mitte) if gut.any() and mitte else None}


def lauf(geom: dict, work_dir: str, lc_mm: float = 0.0,
         lc_spalt_mm: float = 0.0, melde=None) -> dict:
    """Netz bauen, Elmer rechnen, das Spaltfeld auslesen.

    Derselbe Ablauf wie jeder andere Elmer-Weg hier: gmsh -> ElmerGrid ->
    ElmerSolver -> VTU auswerten, und jede Stufe meldet, was sie wirklich
    getan hat statt dass am Ende eine Zahl ohne Herkunft steht.
    """
    import elmer_runner

    if not elmer_runner.ELMER_OK:
        return {"ok": False, "grund": "Elmer nicht gefunden (ElmerGrid/ElmerSolver)"}
    os.makedirs(work_dir, exist_ok=True)
    msh = os.path.join(work_dir, "sektor.msh")

    if melde:
        melde("netz", 0)
    netz = baue_netz(geom, msh, lc_mm=lc_mm, lc_spalt_mm=lc_spalt_mm, melde=melde)

    if melde:
        melde("elmergrid", 0)
    mesh_dir = os.path.join(work_dir, "mesh")
    rg = elmer_runner.run_elmergrid(msh, mesh_dir)
    if not rg.get("ok"):
        return {"ok": False, "grund": f"ElmerGrid: {rg.get('error')}", "netz": netz}

    sif = schreibe_sif(geom, netz, work_dir)
    if melde:
        melde("elmersolver", 0)
    rs = elmer_runner.run_elmersolver(sif, work_dir)
    if not rs.get("ok"):
        return {"ok": False, "grund": f"ElmerSolver: {rs.get('error')}",
                "netz": netz, "sif": sif}

    vtu = None
    erg = os.path.join(work_dir, "results")
    if os.path.isdir(erg):
        kand = sorted(x for x in os.listdir(erg) if x.endswith(".vtu"))
        if kand:
            vtu = os.path.join(erg, kand[-1])
    if not vtu:
        return {"ok": False, "grund": "keine VTU geschrieben", "netz": netz}

    feld = luftspaltfeld(vtu, netz)
    return {"ok": bool(feld.get("ok")), "netz": netz, "vtu": vtu, "sif": sif,
            "feld": feld, "grenzen": grenzen(netz)}


def grenzen(netz: dict) -> list:
    """Was dieser Sektor NICHT sagt -- an jedem Ergebnis, nicht nur im Kopf."""
    return [
        "Lineares Eisen (MU_R_IRON = 500), wie der Mehrschnitt und der radiale "
        "3-D-Pfad. Saettigung ist nicht gerechnet.",
        "KEIN Staenderstrom: verglichen wird der LEERLAUF. Dort allein "
        "unterscheiden sich Mehrschnitt und 3-D in der Geometrie und sonst in "
        "nichts; mit Strom kaeme der Wickelkopf dazu, und der ist hier so wenig "
        "gebaut wie im radialen Sektor.",
        f"EIN Pol ({math.degrees(netz['alpha']):.1f} Grad), anti-periodisch "
        f"gekoppelt. Schraegung, ungleiche Pole und Unwucht sind darin nicht "
        f"darstellbar.",
        f"Luftrand innen und aussen {RAND_ANTEIL:.0%} der Ringbreite. Zu schmal "
        f"gewaehlt klemmt die Randbedingung den seitlichen Austritt ab -- genau "
        f"den Effekt, fuer den es diesen Sektor gibt. `vergleich` misst deshalb "
        f"nach, ob der Rand ueberhaupt Fluss traegt.",
    ]


#: Startpunkte der Feldlinien: Ringe x Winkel JE POL x axiale Ebenen. Der
#: Winkelwert ist bewusst je Pol angegeben und nicht als Gesamtzahl -- eine
#: 4-polige und eine 32-polige Scheibe sollen gleich dicht aussehen.
LINIEN_RINGE, LINIEN_WINKEL_JE_POL, LINIEN_EBENEN = 5, 3, 10


def browser_startpunkte(netz: dict, ringe: int = LINIEN_RINGE,
                        je_pol: int = LINIEN_WINKEL_JE_POL,
                        ebenen: int = LINIEN_EBENEN) -> list:
    """Wo die Feldlinien der SCHEIBE anfangen -- und warum nicht dort, wo radial.

    `ema_em3d.export_browser_streamlines` verteilt seine Startpunkte ueber
    Ringe vom Wellenrand bis zum Statoraussenrand und ueber die BauLAENGE. Das
    ist die Geometrie eines Zylinders. Bei der Scheibe liegt der Ringraum
    zwischen Ri und Ro, die „Laenge" ist die STAPELHOEHE, und innerhalb von Ri
    ist gar keine Maschine -- jeder Startpunkt dort faellt aus dem Netz, und
    `vtkStreamTracer` sagt das nicht, er traced schlicht weniger Linien.

    Gesetzt wird ueber den vollen Umfang, weil die Linien im GESPIEGELTEN
    Vollkranz getract werden (`ema_em3d._pattern_full_motor`) und nicht im
    Sektor: eine Feldlinie, die an der Periodikflaeche endet, waere kein
    Flusspfad, sondern der Rand des Rechengebiets.

    Ueber die Hoehe wird gleichmaessig gesaet, nicht nur in die Spaltmitte:
    der Flusspfad der Scheibe laeuft axial durch Magnet, Spalt und Zahn und
    schliesst sich UMFANGS im Joch -- wer nur im Spalt saet, sieht die eine
    Haelfte und nicht die andere.
    """
    ri, ro = float(netz["ri_mm"]), float(netz["ro_mm"])
    hoehe = float(netz["hoehe_mm"])
    poles = max(1, int(netz["poles"]))
    n_th = max(poles, poles * max(1, int(je_pol)))
    ringe = max(1, int(ringe))
    ebenen = max(1, int(ebenen))
    saum = 0.06 * (ro - ri)
    pkt = []
    for iz in range(ebenen):
        z = hoehe * (0.03 + 0.94 * (iz / max(ebenen - 1, 1) if ebenen > 1 else 0.5))
        for ir in range(ringe):
            r = (ri + saum) + ((ro - saum) - (ri + saum)) * (
                ir / max(ringe - 1, 1) if ringe > 1 else 0.5)
            for ia in range(n_th):
                # Auf die halbe Teilung versetzt, damit kein Startpunkt GENAU
                # auf einer Periodikflaeche des gespiegelten Kranzes sitzt.
                a = 2.0 * math.pi * (ia + 0.5) / n_th
                pkt.append((r * math.cos(a), r * math.sin(a), z))
    return pkt


def browser_dateien(vtu_pfad: str, out_dir: str, netz: dict, log=None) -> dict:
    """Aus der Sektor-VTU dieselben Browser-Dateien wie beim PSM-Pfad.

    Gemeldet als: *„die ergebnisse der 3d feld berechnung in elmer der
    axialflussmaschine will ich auch im browser sehen. ich moechte die
    magnetfeldlinien sehen."* Und der Lauf gab dafuer bis zum 11.10.2026
    **gar nichts** her: `ui_nach.bilder` war 0, es gab eine Kennwerttabelle und
    sonst nichts -- waehrend der radiale Lauf daneben sechs Bilder und den
    eingebetteten 3-D-Betrachter zeigte. Die VTU lag die ganze Zeit auf der
    Platte; was fehlte, war der Schritt von ihr zu den zwei Dateien, die der
    Betrachter laedt. Dieselbe Luecke und dieselbe Antwort wie beim
    harmonischen ASM-Lauf (`ema_em3d_harm.browser_dateien`).

    Drei Dinge muss dieser Adapter leisten, und alle drei sind inhaltlich:

    1. **Gezeigt wird der VOLLE KRANZ, nicht der Sektor.** Gerechnet wird EINE
       Polteilung (hier 22,5 Grad); ein Tortenstueck von 22,5 Grad ist aber
       nichts, woran man eine Maschine erkennt, und eine Feldlinie, die an der
       Periodikflaeche aufhoert, saehe aus wie ein Ende des Flusses. Gespiegelt
       wird mit `ema_em3d._pattern_full_motor` -- 2p Kopien, je um k*alpha
       gedreht, B mitgedreht und mit `(-1)^k` gewendet. Das ist **dieselbe**
       Symmetrie wie beim radialen Ein-Pol-Sektor (Drehung um z, antiperiodisch),
       deshalb wird sie hier nicht neu geschrieben.

    2. **Die Startpunkte muessen zur Scheibe passen** -- s. `browser_startpunkte`.

    3. **Fest steht, was der Betrachter als Festkoerper stehenlaesst:** Eisen
       und Magnete, Luft heraus. Die Zuordnung liegt in `netz["pid"]` /
       `netz["magnete"]`; `GeometryIds` schreibt die `case.sif` mit.
    """
    import ema_em3d

    def _sag(t):
        if log:
            try:
                log(t)
            except Exception:                                # noqa: BLE001
                pass

    gitter = ema_em3d._read_grid(vtu_pfad)
    bname = ema_em3d._b_array_name(gitter)
    if not bname:
        raise RuntimeError("Die Ergebnisdatei enthaelt keine Flussdichte — "
                           "MagnetoDynamicsCalcFields hat nicht gerechnet.")

    poles = max(1, int(netz["poles"]))
    tags = {
        # Eisen UND Magnete sind der Festkoerper; die Luft (Nut, Spalt, Rand,
        # Deckel) faellt heraus, sonst zeigt der Betrachter einen Klotz.
        "bodies": {"rotor": int(netz["pid"]["eisen"])} if netz["pid"].get("eisen") else {},
        "magnets": [{"phys": int(m["phys"])} for m in (netz.get("magnete") or [])],
        # `r_so` ist hier der AUSSERE LUFTRAND und nicht Ro: an ihm haengen
        # Schrittweite, Verfolgungslaenge und die Abschneidegrenze, und der
        # seitliche Austritt in genau diesen Rand ist der Effekt, fuer den es
        # diesen Sektor ueberhaupt gibt (s. RAND_ANTEIL).
        "dims": {"r_shaft": float(netz.get("r_in_mm") or 0.0),
                 "r_rot": float(netz["ri_mm"]),
                 "r_si": float(netz["ri_mm"]),
                 "r_so": float(netz["r_out_mm"])},
        "L": float(netz["hoehe_mm"]),
        "alpha": float(netz["alpha"]),
        "poles": poles,
    }

    voll = ema_em3d._pattern_full_motor(gitter, tags)
    _sag(f"Vollkranz gespiegelt: {poles} Polteilungen "
         f"({math.degrees(netz['alpha']):.1f} Grad je Kopie)")

    os.makedirs(out_dir, exist_ok=True)
    erg = {}

    try:
        erg["vtp"] = ema_em3d.export_browser_vtp(
            voll, bname, tags, os.path.join(out_dir, "browser.vtp"))
        _sag("Browser-Oberflaeche geschrieben (Farbe = |B|)")
    except Exception as e:                                   # noqa: BLE001
        erg["vtp_fehler"] = f"{type(e).__name__}: {e}"
        _sag(f"\u26a0 Browser-Oberflaeche nicht geschrieben: {e}")

    try:
        pkt = browser_startpunkte(netz)
        erg["n_startpunkte"] = len(pkt)
        lp = ema_em3d.export_browser_streamlines(
            voll, bname, tags, os.path.join(out_dir, "browser_lines.vtp"),
            seeds=pkt)
        # Gezaehlt wird, was WIRKLICH drin steht -- s. `ema_em3d.zaehle_linien`.
        n = ema_em3d.zaehle_linien(lp)
        erg["n_linien"] = n
        if n <= 0:
            erg["lines_fehler"] = (
                "keine einzige Feldlinie getract — die Startpunkte liegen "
                "ausserhalb des Netzes oder das Feld ist ueberall unter der "
                "Abbruchschwelle")
            _sag("\u26a0 Feldlinien: NULL Linien getract — Datei verworfen")
            try:
                os.remove(lp)
            except OSError:
                pass
        else:
            erg["lines"] = lp
            _sag(f"Feldlinien geschrieben: {n} Linien aus {len(pkt)} Startpunkten")
    except Exception as e:                                   # noqa: BLE001
        erg["lines_fehler"] = f"{type(e).__name__}: {e}"
        _sag(f"\u26a0 Feldlinien nicht geschrieben: {e}")

    erg["hinweis"] = (
        f"Gerechnet ist EIN Pol ({math.degrees(netz['alpha']):.1f} Grad), "
        f"anti-periodisch gekoppelt; gezeigt wird der daraus gespiegelte "
        f"Vollkranz ({poles} Pole). Die Farbe ist |B| im Leerlauf, lineares "
        f"Eisen (mu_r = {MU_R_IRON:.0f}) — Saettigung ist nicht gerechnet. "
        f"Schraegung, ungleiche Pole und Unwucht sind in einem Pol nicht "
        f"darstellbar und stehen deshalb auch nicht im Bild.")
    return erg


def vergleich(geom: dict, work_dir: str, k_schnitte: int = 7, N: int = 300,
              lc_mm: float = 0.0, lc_spalt_mm: float = 0.0, melde=None) -> dict:
    """**Der eigentliche Zweck:** Mehrschnitt gegen 3-D, auf EINER Geometrie.

    Beide rechnen denselben Leerlauf mit demselben linearen Eisen. Was uebrig
    bleibt, ist der Unterschied der GEOMETRIE -- und das ist genau der Term,
    den der Mehrschnitt fallen laesst (``d/dr``).
    """
    import numpy as np
    import ema_axial_fdm as AF

    drei = lauf(geom, work_dir, lc_mm=lc_mm, lc_spalt_mm=lc_spalt_mm, melde=melde)
    if not drei.get("ok"):
        return {"ok": False, "grund": drei.get("grund"), "drei": drei}
    if melde:
        melde("mehrschnitt", 0)
    viele = AF.felder(geom, k_schnitte=k_schnitte, N=N, rpm=1000.0, last_nm=0.0)

    f3 = drei["feld"]
    r3 = np.array(f3["r_mm"]) / 1000.0
    b3 = np.array(f3["B_gap_T"])
    # **Der Radiusvektor wird GELESEN, nicht erfunden.** Hier stand bis zum
    # 11.10.2026 `viele.get("r_schnitte_m") or np.linspace(...)` -- und
    # `felder` liefert den Vektor unter `radien_m`. Der erste Zweig griff also
    # NIE, und verglichen wurde gegen eine gleichmaessig ueber den Ringraum
    # gelegte Ersatzachse statt gegen die wirklichen Schnittradien (die als
    # Scheibenmitten bei `ri + (ro-ri)*(k+0.5)/k` liegen). Derselbe
    # Schluesselfehler stand in `ema_pipeline._axial_bgap_chart`, wo er das
    # Diagramm ganz verschwinden liess; hier hat ihn der Rueckfall verdeckt.
    # Ein stiller Rueckfall auf eine geratene Achse ist schlimmer als ein
    # Fehlschlag: die Kurve sieht richtig aus.
    _r2 = viele.get("radien_m")
    if not _r2 or len(_r2) != len(viele["B_gap_ueber_r_T"]):
        return {"ok": False, "drei": drei,
                "grund": (f"Mehrschnitt ohne brauchbare Radiusachse: "
                          f"radien_m={len(_r2 or [])}, "
                          f"B_gap_ueber_r_T={len(viele['B_gap_ueber_r_T'])}")}
    r2 = np.array(_r2, dtype=float)
    b2 = np.array(viele["B_gap_ueber_r_T"])
    # Auf das 3-D-Gitter interpolieren -- die Schnittzahl ist klein, das
    # Abtastgitter nicht.
    b2i = np.interp(r3, r2, b2)
    gut = np.isfinite(b3) & np.isfinite(b2i) & (b2i > 1e-9)
    abw = (b3[gut] / b2i[gut] - 1.0) * 100.0 if gut.any() else np.array([])
    return {
        "ok": True, "drei": drei, "mehrschnitt": {
            "r_m": r2.tolist(), "B_gap_T": b2.tolist(),
            "mittel_T": viele["B_gap_grundwelle_mittel_T"]},
        "r_mm": f3["r_mm"], "B_3d_T": f3["B_gap_T"], "B_2d_T": b2i.tolist(),
        "abweichung_pct": abw.tolist(),
        "abw_mittel_pct": float(np.mean(abw)) if abw.size else None,
        "abw_max_pct": float(np.max(np.abs(abw))) if abw.size else None,
        "rand_innen": f3.get("rand_innen"), "rand_aussen": f3.get("rand_aussen"),
        "grenzen": drei["grenzen"],
    }
