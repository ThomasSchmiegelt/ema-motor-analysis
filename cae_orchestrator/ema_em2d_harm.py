"""ASM-Feldstufe: harmonische 2-D-Feldrechnung mit Elmer (Stufe B).

Warum nicht die vorhandene FDM
------------------------------

Die 2-D-FDM des Hauses (``ema_analysis._rasterise`` / ``_build_fv_matrix`` /
``_solve_fdm``) ist **reell, linear und magnetostatisch**: kein ``sigma``, kein
``dA/dt``, keine komplexe Arithmetik. Ein Kaefiglaeufer lebt aber genau davon --
sein Moment entsteht aus Stroemen, die das Statorfeld erst induziert. In der FDM
gibt es diese Stroeme nicht; sie wuerde ein Feld ausrechnen, das aussieht wie ein
Ergebnis und keines ist. Deshalb laeuft diese Stufe ueber Elmers
``MagnetoDynamics2DHarmonic`` -- nachgemessen vorhanden in
``/usr/share/elmersolver/lib/MagnetoDynamics2D.so`` -- und **nicht** ueber die FDM.

Der PSM-Weg bleibt davon vollstaendig unberuehrt und Vorgabe.

Die Schlupf-Leitfaehigkeit -- und warum sie ``sigma*s`` ist, nicht ``sigma/s``
------------------------------------------------------------------------------

Gerechnet wird im **Staenderbezugssystem** bei Speisefrequenz ``w1``, in **einem**
Lauf. Der Laeufer dreht darin; seine Staebe sehen nicht ``w1``, sondern die
Schlupffrequenz ``w2 = s*w1``. Die induzierte Stromdichte ist

    J = -sigma * dA/dt |_Laeufer = -j*w2*sigma*A_tilde .

Dieselbe Groesse im Staenderrahmen als ``-j*w1*sigma_eff*A_tilde`` geschrieben
ergibt

    sigma_eff = s * sigma .

Die Probe an den Grenzen: ``s -> 0`` (Synchronlauf) gibt ``sigma_eff = 0``, also
keinen Laeuferstrom und kein Moment -- richtig. ``s = 1`` (Stillstand) gibt
``sigma_eff = sigma`` bei voller Speisefrequenz -- ebenfalls richtig.

**Die Verwechslungsgefahr ist echt und teuer.** Aus dem Ersatzschaltbild ist
``R2/s`` gelaeufig; wer das unbesehen auf das Material uebertraegt, schreibt
``sigma/s`` hin -- bei 2 % Schlupf ein Faktor 2500 im Laeuferstrom, und das
Ergebnis widerspricht nicht, es ist nur falsch. Widerstand ist ``1/sigma``,
darum entspricht ``R2/s`` gerade ``sigma*s``.

Was daraus fuer die Leistungen folgt (und leicht falsch gelesen wird):

    J_Modell   = -j*w1*sigma_eff*A = -j*w2*sigma*A = J_wirklich   (Strom stimmt)
    P_Modell   = Integral |J|^2 / (2*sigma_eff)  =  P_Luftspalt    (nicht der Laeuferverlust!)
    P_Laeufer  = s * P_Modell
    T          = P_Modell / w_syn_mech

Die im Modell verheizte Leistung ist also die **Luftspaltleistung**, nicht der
Laeuferverlust. Wer die Joule-Zahl des Loesers direkt als Kaefigverlust
uebernimmt, ueberschaetzt ihn um ``1/s`` -- bei 2 % Schlupf um das Fuenfzigfache.
Dieses Modul gibt darum beide Zahlen getrennt und beschriftet heraus.

Das Moment wird ZWEIMAL gemessen
--------------------------------

Aus derselben Loesung auf zwei unabhaengigen Wegen:

1. **Arkkio** -- Maxwellscher Spannungstensor, ueber den ganzen Luftspaltring
   gemittelt: ``T = L/(mu0*(r_a-r_i)) * Integral r * Re(B_r * conj(B_t))/2 dA``.
2. **Leistungsbilanz** -- ``T = P_Modell / w_syn_mech`` aus der Stabdissipation.

Weg 1 liest das Feld im Luftspalt, Weg 2 die Stroeme im Laeufer. Gehen sie
auseinander, ist das Netz im Luftspalt zu grob oder der Integrationsring falsch
gelegt -- eine Aussage, die eine einzelne Momentzahl nicht machen kann. Beide
werden ausgegeben, zusammen mit dem analytischen Wert aus ``ema_asm``. Die
Abweichung wird **protokolliert, nicht auf eine erhoffte Schranke gepresst.**

Was dieses Modell nicht enthaelt -- ausgesprochen
-------------------------------------------------

* **Keinen Kurzschlussring.** Ein 2-D-Schnitt hat keine Stirnseite; die Staebe
  sind hier ideal kurzgeschlossen. ``ema_asm`` schlaegt den Ring analytisch mit
  ``KURZSCHLUSSRING_ZUSCHLAG`` auf. Ein Teil der Abweichung zwischen beiden
  Stufen ist genau das und keine Ungenauigkeit.
* **Lineares Eisen, mu_r = 500**, wie in ``ema_em3d`` -- damit die 2-D- und die
  3-D-Feldstufe DIESELBE Annahme machen und nicht zwei verschiedene.
* **Keine Stromverdraengung ueber die Nuttiefe hinaus geprueft.** Am stationaeren
  Nennpunkt ist die Schlupffrequenz klein (wenige Hz); die Eindringtiefe in
  Aluminium liegt dann bei einigen Zentimetern, also weit ueber der Stabtiefe.
  ``kennzahlen()`` rechnet sie aus und sagt es, statt es vorauszusetzen.
* **Kein Oberwellenmoment, keine Nutungsoberfelder als eigene Aussage.** Sie sind
  im Feld enthalten (echte Nuten, echtes Blech), aber nicht getrennt ausgewertet.

Einheiten: das Netz wird in **Metern** gebaut. Elmers Konstanten sind SI; ein
Netz in Millimetern skaliert ``mu0`` still um drei Zehnerpotenzen.
"""

from __future__ import annotations

import cmath
import math
import os

import elmer_runner

MU0 = 4.0e-7 * math.pi

# Lineares Eisen. **Bewusst NICHT die 500 aus ``ema_em3d``** -- und der Grund
# ist gemessen, nicht geschmackssache: bei der PSM liegt der Magnet mit
# ``magThick/mu_r_mag`` (rund 6 mm) im Hauptpfad und macht die Eisenreluktanz
# nebensaechlich. Der Kaefiglaeufer hat keinen Magneten; sein Luftspalt ist
# 0,7 mm. Ein Eisenweg von rund 0,3 m Laenge entspricht bei mu_r = 500 einem
# zusaetzlichen Luftspalt von 0,3/500 = 0,6 mm -- also fast noch einmal dem
# ganzen Spalt. Nachgemessen: mit 500 kam das Luftspaltfeld auf 0,53 T statt der
# angesetzten 0,80 T heraus, und das Moment entsprechend zu klein.
#
# 5000 ist der uebliche Bereich fuer nicht kornorientiertes Elektroblech
# (M270-35A) unterhalb der Saettigung. ``kennzahlen`` gibt den zugehoerigen
# Ersatzluftspalt mit heraus, damit die Annahme im Ergebnis sichtbar bleibt
# statt nur hier im Quelltext zu stehen. Saettigung ist NICHT gerechnet -- die
# Kennzahl ``B_eisen_p99_T`` sagt, ob das noch traegt.
MU_R_EISEN = 5000.0

# Der Blechsteg ueber der Kaefignut -- und warum er NICHT mu_r = 5000 bekommt.
#
# Gemessen, mit 5000 im ganzen Laeuferblech: der 2 mm breite Steg zwischen
# Kaefignut und Luftspalt fuehrte 8-16 T, waehrend das Laeuferjoch bei 0,067 T
# stand. Der Steg hatte das gesamte Hauptfeld tangential kurzgeschlossen -- es
# kam gar nicht mehr ins Joch, und das Moment war entsprechend keines.
#
# Das ist kein Rechenfehler, sondern die richtige Antwort auf ein falsches
# Modell: ein LINEARER Steg mit mu_r = 5000 kann beliebig viel Fluss fuehren.
# Ein wirklicher Steg kann das nicht -- er saettigt bei rund 2 T, und genau
# deshalb funktioniert die geschlossene Laeufernut ueberhaupt. Ohne Saettigung
# fehlt dem Modell die Begrenzung, die die Bauart erst tragfaehig macht.
#
# Der Steg wird deshalb als **gesaettigt** angesetzt (mu_r = 1, magnetisch also
# wie Luft, die uebliche lineare Naeherung fuer den geschlossenen Nutschlitz).
# Das unterschaetzt den Fluss um die rund 2 T, die der Steg wirklich noch
# traegt; ``kennzahlen`` gibt den Stegfluss darum getrennt aus, und
# ``mu_r_steg`` laesst sich setzen. Eine echte BH-Kurve waere im
# Frequenzbereich ohnehin nicht wohldefiniert -- die Saettigung ist keine
# harmonische Groesse.
MU_R_STEG = 1.0

# Saettigungsflussdichte des Stegs. Kein Zierwert: mit ``mu_r_steg = 1`` ist die
# Laeufernut magnetisch OFFEN -- gemessen 10,4 mm Nutbreite gegen 0,7 mm
# Luftspalt, also ein Carter-Effekt, der die Hauptinduktivitaet zusammenfallen
# laesst. Ein wirklicher Steg fuehrt seine rund 2 T weiter, und genau davon lebt
# die geschlossene Laeufernut. ``steg_saettigen`` sucht deshalb das mu_r, bei dem
# der Steg **gemessen** bei B_STEG_SAT_T steht: loesen, B_Steg ablesen, mu_r
# nachziehen, wieder loesen. Damit ist die Saettigung ein Messergebnis des
# Modells und keine gesetzte Zahl -- und sie steht als ``mu_r_steg`` im Ergebnis.
B_STEG_SAT_T = 2.0

# Radiale Elementlagen im Luftspalt. Unter drei wird der Arkkio-Ring zur
# geraden Linie und das Moment haengt am Netz statt am Feld.
GAP_LAGEN = 3

# Kleinster gerechneter Schlupf. Bei s -> 0 verschwindet sigma_eff und mit ihm
# jeder Laeuferstrom; das ist physikalisch richtig, aber als Rechenfall leer.
S_MIN = 1.0e-4

# Physikalische Gruppen-Nummern. Sie muessen **luecklos ab 1** laufen:
# ``ElmerGrid ... -autoclean`` (so ruft ``elmer_runner`` es auf) nummeriert die
# Koerper auf 1..N um. Mit Nuten ab 100 wurden aus 1..5 + 100..135 still die
# Koerper 1..41 -- die Nutkoerper im sif trafen dann ins Leere, es floss kein
# Strom, und das Feld kam ueberall exakt 0 heraus. Ein Ergebnis, das nicht
# widerspricht, sondern einfach leer ist.
GID_WELLE   = 1
GID_ROTOR   = 2
GID_STAEBE  = 3
GID_STEG    = 4            # Blechsteg ueber der Kaefignut -- eigener Koerper, s. MU_R_STEG
GID_LUFT    = 5
GID_STATOR  = 6
GID_NUT0    = 7            # Nut k -> GID_NUT0 + k
GID_RAND    = 1            # Randkurve (eigener Nummernkreis, 1D)


# ── Wicklung ──────────────────────────────────────────────────────────────────

def nutbelag(k: int, n_slots: int, p: int) -> tuple:
    """Phase und Vorzeichen der Nut ``k`` -- 60-Grad-Zonenwicklung.

    Der elektrische Winkel ``alpha = p*theta`` faellt in einen von sechs
    Guerteln, die um 0/60/120/180/240/300 Grad zentriert sind:

        A+ , C- , B+ , A- , C+ , B-

    Damit ist die Wicklung **gebaut**, nicht als Formfaktor angenommen: der
    Wicklungsfaktor ``k_w``, den ``ema_asm`` mit 0,95 ansetzt, ergibt sich hier
    aus der Anordnung selbst. Genau das macht den Vergleich der beiden Stufen zu
    einer Messung statt zu einem Zirkelschluss.

    Bei Bruchlochwicklungen (``slots/(6p)`` nicht ganzzahlig) faellt die Nut in
    den naechstgelegenen Guertel -- das ist eine echte, wenn auch nicht die
    einzige moegliche Bruchlochwicklung, und sie steht hier so da.
    """
    theta = 2.0 * math.pi * k / max(n_slots, 1)
    # Um eine HALBE Nutteilung verschoben, damit die Nutmitten in der Mitte der
    # Guertel liegen und nicht auf deren Grenzen. Ohne diese Verschiebung faellt
    # bei ganzzahliger Lochzahl jede zweite Nut exakt auf eine 60-Grad-Grenze,
    # und welchem Strang sie zufaellt, entscheidet dann die Gleitkommadarstellung:
    # gemessen kamen bei 36 Nuten und 2p = 6 die Straenge auf 14/10/12 Nuten
    # heraus -- eine unsymmetrische Wicklung, die ein Gegensystem speist und
    # trotzdem klaglos rechnet.
    gamma = 2.0 * math.pi * p / max(n_slots, 1)          # elektrische Nutteilung
    alpha = (p * theta + math.pi / 6.0 - gamma / 2.0) % (2.0 * math.pi)
    zone = int(alpha / (math.pi / 3.0)) % 6
    return (("a", +1), ("c", -1), ("b", +1), ("a", -1), ("c", +1), ("b", -1))[zone]


def stator_stroeme(geom: dict, i_pk_phys: float, a_nut_m2: float) -> dict:
    """Komplexe Stromdichte je Nut [A/m^2] -- Zeiger bei Speisefrequenz.

    Dreiphasig, eine Windung je Nut (Hauskonvention, s. ``ema_asm``):

        i_a = I*cos(w t) , i_b = I*cos(w t - 2pi/3) , i_c = I*cos(w t + 2pi/3)

    als Zeiger ``I``, ``I*e^-j2pi/3``, ``I*e^+j2pi/3``. Zusammen mit
    ``nutbelag`` ergibt das eine im Raum umlaufende Durchflutungswelle
    ``~ cos(w t - p theta)``.
    """
    n_slots = int(geom["slots"])
    p = max(int(geom["p"]), 1)
    zeiger = {"a": complex(i_pk_phys, 0.0),
              "b": i_pk_phys * cmath.exp(-2j * math.pi / 3.0),
              "c": i_pk_phys * cmath.exp(+2j * math.pi / 3.0)}
    aus = {}
    for k in range(n_slots):
        ph, vz = nutbelag(k, n_slots, p)
        aus[GID_NUT0 + k] = vz * zeiger[ph] / max(a_nut_m2, 1e-12)
    return aus


# ── Netz ──────────────────────────────────────────────────────────────────────

def masse(geom: dict, kaefig: dict) -> dict:
    """Alle Radien und Stabmasse in **Metern**, aus einer Rechnung.

    Getrennt gehalten, weil die 3-D-Stufe (``ema_em3d_harm``) genau denselben
    Querschnitt braucht. Zwei Rechnungen fuer dieselbe Geometrie waeren die
    Vervielfaeltigung, gegen die ``ema_wicklung`` gerade angetreten ist.
    """
    r_wel = float(geom["shaftD"]) / 2000.0
    r_rot = float(geom["rotorOD"]) / 2000.0
    r_si  = float(geom["statorID"]) / 2000.0
    r_so  = float(geom["statorOD"]) / 2000.0
    g = r_si - r_rot
    if g <= 0:
        raise ValueError(f"Luftspalt nicht positiv: rotorOD={geom['rotorOD']} "
                         f"statorID={geom['statorID']}")
    t_stab = float(kaefig["nuttiefe_mm"]) / 1000.0
    r_stab_a = r_rot - float(kaefig.get("steg_mm", 2.0)) / 1000.0
    return {
        "r_wel": r_wel, "r_rot": r_rot, "r_si": r_si, "r_so": r_so, "gap_m": g,
        "n_stab": int(kaefig["n_stab"]),
        "b_stab": float(kaefig["stabbreite_mm"]) / 1000.0,
        "t_stab": t_stab, "r_stab_a": r_stab_a,
        "r_stab_i": r_stab_a - t_stab,
        "r_stab_m": r_stab_a - t_stab / 2.0,
        "A_ring_m2": float(kaefig["A_ring_mm2"]) * 1e-6,
    }


def quer_flaechen(gmsh, geom: dict, kaefig: dict) -> dict:
    """Den Querschnitt bauen und die Flaechen den Koerpern zuordnen.

    Die Zuordnung nach dem Verschneiden laeuft ueber die **Abbildung von
    ``occ.fragment``**, nicht ueber Schwerpunktabstaende: jedes Eingangsobjekt
    sagt selbst, welche Ausgangsflaechen aus ihm entstanden sind. Damit gibt es
    hier keine Toleranzen, an denen eine Zuordnung kippen kann.

    Gibt die Flaechen je Koerper zurueck -- OHNE physikalische Gruppen und ohne
    zu vernetzen, damit die 3-D-Stufe denselben Querschnitt extrudieren kann.
    """
    import ema_em3d
    m = masse(geom, kaefig)
    occ = gmsh.model.occ

    nuten = ema_em3d.slot_rects(geom)
    if not nuten:
        raise ValueError("Statornuten fehlen (slots/slotDepth) -- ohne Nuten "
                         "gibt es keine Wicklung, die eingepraegt werden koennte")

    n_stab = m["n_stab"]
    welle  = occ.addDisk(0, 0, 0, m["r_wel"], m["r_wel"])
    rotor  = _ring(occ, m["r_wel"], m["r_rot"])
    luft   = _ring(occ, m["r_rot"], m["r_si"])
    stator = _ring(occ, m["r_si"], m["r_so"])

    staebe, stege = [], []
    for j in range(n_stab):
        a = 2.0 * math.pi * j / n_stab
        s = occ.addRectangle(-m["t_stab"] / 2.0, -m["b_stab"] / 2.0, 0.0,
                             m["t_stab"], m["b_stab"])
        occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, a)
        occ.translate([(2, s)], m["r_stab_m"] * math.cos(a),
                      m["r_stab_m"] * math.sin(a), 0)
        staebe.append(s)
        # Der Steg genau UEBER dem Stab, gleiche tangentiale Breite: nur dieses
        # Stueck Blech schliesst die Nut, das Blech zwischen zwei Nuten ist
        # gewoehnlicher Laeuferzahn und bleibt Eisen.
        g_ = occ.addRectangle(m["r_stab_a"], -m["b_stab"] / 2.0, 0.0,
                              max(m["r_rot"] - m["r_stab_a"], 1e-6), m["b_stab"])
        occ.rotate([(2, g_)], 0, 0, 0, 0, 0, 1, a)
        stege.append(g_)

    nut_tags = []
    for n in nuten:
        s = occ.addRectangle(-float(n["length"]) / 2000.0,
                             -float(n["thick"]) / 2000.0, 0.0,
                             float(n["length"]) / 1000.0,
                             float(n["thick"]) / 1000.0)
        occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, float(n["ang"]))
        occ.translate([(2, s)], float(n["cx"]) / 1000.0, float(n["cy"]) / 1000.0, 0)
        nut_tags.append(s)

    eingang = [welle, rotor, luft, stator] + staebe + stege + nut_tags
    _, abb = occ.fragment([(2, eingang[0])], [(2, t) for t in eingang[1:]])
    occ.synchronize()

    aus = [[t for (d, t) in grp if d == 2] for grp in abb]
    i_wel, i_rot, i_luf, i_sta = 0, 1, 2, 3
    i_stab0 = 4
    i_steg0 = 4 + n_stab
    i_nut0 = 4 + 2 * n_stab

    f_rotor = set(aus[i_rot])
    f_stator = set(aus[i_sta])
    # Nur die Anteile behalten, die WIRKLICH im jeweiligen Eisen liegen -- ein
    # Stab, der ueber den Laeuferrand hinausragte, kaeme sonst als
    # Luftspaltkoerper mit Leitfaehigkeit heraus.
    stab_f, steg_f, nut_f = [], [], []
    for j in range(n_stab):
        stab_f.append(sorted(f_rotor.intersection(aus[i_stab0 + j])))
    alle_stab = set().union(*stab_f) if stab_f else set()
    for j in range(n_stab):
        steg_f.append(sorted(f_rotor.intersection(aus[i_steg0 + j]) - alle_stab))
    for k in range(len(nut_tags)):
        nut_f.append(sorted(f_stator.intersection(aus[i_nut0 + k])))
    fehlend = [j for j, f in enumerate(stab_f) if not f]
    if fehlend:
        raise ValueError(f"{len(fehlend)} Kaefigstaebe liegen nicht im "
                         f"Laeuferblech -- Geometrie pruefen")
    fehlend = [j for j, f in enumerate(steg_f) if not f]
    if fehlend:
        raise ValueError(f"{len(fehlend)} Laeuferstege fehlen -- der Steg ueber "
                         f"der Kaefignut muss ein eigener Koerper sein")
    fehlend = [k for k, f in enumerate(nut_f) if not f]
    if fehlend:
        raise ValueError(f"{len(fehlend)} Statornuten liegen nicht im "
                         f"Statorblech -- slotDepth pruefen")

    belegt = set()
    for f in stab_f + steg_f + nut_f:
        belegt.update(f)

    return {
        "masse": m, "nuten": nuten,
        "welle": sorted(aus[i_wel]),
        "rotor": sorted(f_rotor - belegt),
        "staebe": sorted(alle_stab),
        "stege": sorted(set().union(*steg_f)),
        "luft": sorted(aus[i_luf]),
        "stator": sorted(f_stator - belegt),
        "nut_f": nut_f,
        "A_nut_m2": float(nuten[0]["length"]) * float(nuten[0]["thick"]) * 1e-6,
    }


def groessenfeld(gmsh, m: dict, gap_lagen: int, lc_eisen_m: float) -> float:
    """Glockenfoermiges Verfeinerungsband um den Luftspalt. Gibt ``lc_gap`` zurueck.

    Keine Sprungstelle im Netz, und die Lagen im Spalt stehen unabhaengig von
    der Groesse der Maschine.
    """
    lc_gap = m["gap_m"] / max(int(gap_lagen), 1)
    lc_eisen = max(lc_eisen_m, lc_gap)
    r_mitte = 0.5 * (m["r_rot"] + m["r_si"])
    f = gmsh.model.mesh.field.add("MathEval")
    # Kleinbuchstaben und ausgeschriebenes Quadrat: der MathEval-Parser von gmsh
    # kennt weder "Exp" noch zuverlaessig "^" -- ein Tippfehler darin faellt
    # nicht auf, das Feld liefert dann still 0 und das Netzen bricht ab.
    rr = "sqrt(x*x+y*y)"
    u = f"(({rr}-{r_mitte!r})/{2.0 * m['gap_m']!r})"
    gmsh.model.mesh.field.setString(
        f, "F", f"{lc_eisen!r} + ({lc_gap!r} - {lc_eisen!r})*exp(-{u}*{u})")
    gmsh.model.mesh.field.setAsBackgroundMesh(f)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    return lc_gap


def baue_netz(geom: dict, kaefig: dict, msh_pfad: str,
              gap_lagen: int = GAP_LAGEN, lc_eisen_mm: float = 0.0) -> dict:
    """2-D-Querschnitt in **Metern** nach ``msh_pfad`` (MSH 2.2 fuer ElmerGrid).

    Koerper: Welle, Laeufereisen, ``n_stab`` Kaefigstaebe, deren Blechstege,
    Luftspalt, Statoreisen, ``slots`` Statornuten (jede eine eigene Gruppe, weil
    jede eine eigene Stromdichte traegt).
    """
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        gmsh.model.add("asm2d")
        q = quer_flaechen(gmsh, geom, kaefig)
        m = q["masse"]

        gmsh.model.addPhysicalGroup(2, q["welle"], GID_WELLE, "welle")
        gmsh.model.addPhysicalGroup(2, q["rotor"], GID_ROTOR, "rotoreisen")
        gmsh.model.addPhysicalGroup(2, q["staebe"], GID_STAEBE, "kaefigstaebe")
        gmsh.model.addPhysicalGroup(2, q["stege"], GID_STEG, "laeuferstege")
        gmsh.model.addPhysicalGroup(2, q["luft"], GID_LUFT, "luftspalt")
        gmsh.model.addPhysicalGroup(2, q["stator"], GID_STATOR, "statoreisen")
        for k, f in enumerate(q["nut_f"]):
            gmsh.model.addPhysicalGroup(2, f, GID_NUT0 + k, f"nut{k}")

        # Aussenrand: alle Kurven auf r_so. Nicht ueber den Schwerpunkt suchen:
        # der eines VOLLKREISES liegt im Mittelpunkt, also bei jedem Radius
        # gleich. Die Huellbox unterscheidet.
        rand = []
        for (d, t) in gmsh.model.getEntities(1):
            bb = gmsh.model.getBoundingBox(1, t)
            weite = max(bb[3] - bb[0], bb[4] - bb[1]) / 2.0
            if abs(weite - m["r_so"]) < 1e-4 * m["r_so"] + 1e-9:
                rand.append(t)
        if not rand:
            raise ValueError("Aussenrand nicht gefunden")
        gmsh.model.addPhysicalGroup(1, rand, GID_RAND, "aussenrand")

        lc_eisen = (lc_eisen_mm / 1000.0) if lc_eisen_mm > 0 else min(
            3.0e-3, m["b_stab"] / 3.0, float(q["nuten"][0]["thick"]) / 3000.0)
        lc_gap = groessenfeld(gmsh, m, gap_lagen, lc_eisen)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.mesh.generate(2)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.SaveAll", 0)
        os.makedirs(os.path.dirname(os.path.abspath(msh_pfad)) or ".", exist_ok=True)
        gmsh.write(msh_pfad)

        knoten = len(gmsh.model.mesh.getNodes()[0])
        _, elems, _ = gmsh.model.mesh.getElements(2)
        dreiecke = sum(len(e) for e in elems)
    finally:
        gmsh.finalize()

    return {"msh": msh_pfad, "knoten": int(knoten), "dreiecke": int(dreiecke),
            "n_stab": m["n_stab"], "n_nut": len(q["nuten"]),
            "steg_mm": 1000.0 * (m["r_rot"] - m["r_stab_a"]),
            "b_stab_m": m["b_stab"],
            "r_wel": m["r_wel"], "r_rot": m["r_rot"], "r_si": m["r_si"],
            "r_so": m["r_so"], "gap_m": m["gap_m"], "lc_gap_m": lc_gap,
            "lc_eisen_m": max(lc_eisen, lc_gap),
            "A_stab_m2": float(kaefig["A_stab_mm2"]) * 1e-6,
            "A_nut_m2": q["A_nut_m2"]}


def _ring(occ, r_i: float, r_a: float) -> int:
    aussen = occ.addDisk(0, 0, 0, r_a, r_a)
    innen = occ.addDisk(0, 0, 0, r_i, r_i)
    out, _ = occ.cut([(2, aussen)], [(2, innen)])
    return out[0][1]


# ── Fallbeschreibung ──────────────────────────────────────────────────────────

def schreibe_sif(netz: dict, geom: dict, omega1: float, sigma_eff: float,
                 j_nut: dict, work_dir: str, mesh_name: str = "mesh",
                 mu_r_steg: float = MU_R_STEG) -> str:
    """``case.sif`` fuer ``MagnetoDynamics2DHarmonic`` schreiben."""
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)
    n_nut = int(netz["n_nut"])

    S = [f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n',
         "Simulation\n"
         "  Max Output Level = 4\n"
         "  Coordinate System = Cartesian 2D\n"
         "  Simulation Type = Steady State\n"
         "  Steady State Max Iterations = 1\n"
         "  Output Intervals = 1\nEnd\n",
         f"Constants\n  Permeability of Vacuum = {MU0:.12e}\nEnd\n"]

    # Koerper: Material 1 Eisen, 2 Luft, 3 Kaefigstab, 4 Nut (Luft mit Strom).
    koerper = [(GID_WELLE, 1, None), (GID_ROTOR, 1, None), (GID_STAEBE, 3, None),
               (GID_STEG, 4, None), (GID_LUFT, 2, None), (GID_STATOR, 1, None)]
    koerper += [(GID_NUT0 + k, 2, k + 1) for k in range(n_nut)]
    for i, (gid, mat, bf) in enumerate(koerper, start=1):
        S.append(f"Body {i}\n  Target Bodies(1) = {gid}\n  Equation = 1\n"
                 f"  Material = {mat}\n"
                 + (f"  Body Force = {bf}\n" if bf else "") + "End\n")

    S.append(f"Material 1\n  Relative Permeability = {MU_R_EISEN}\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    S.append("Material 2\n  Relative Permeability = 1.0\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    # sigma_eff = s*sigma -- die Herleitung steht im Modulkopf. Der Kommentar
    # bleibt IM sif stehen, weil die Datei einzeln gelesen und wiederverwendet wird.
    S.append("! Leitfaehigkeit des Kaefigs im Staenderrahmen: sigma_eff = s*sigma\n"
             "! (nicht sigma/s -- Widerstand ist 1/sigma, R2/s entspricht sigma*s).\n"
             f"Material 3\n  Relative Permeability = 1.0\n"
             f"  Electric Conductivity = {sigma_eff:.6e}\nEnd\n")

    S.append("! Gesaettigter Steg ueber der Kaefignut (s. MU_R_STEG). Mit dem\n"
             "! vollen mu_r des Blechs schliesst er das Hauptfeld tangential kurz.\n"
             f"Material 4\n  Relative Permeability = {mu_r_steg}\n"
             "  Electric Conductivity = 0.0\nEnd\n")

    for k in range(n_nut):
        j = j_nut.get(GID_NUT0 + k, 0j)
        S.append(f"Body Force {k + 1}\n"
                 f"  Current Density = Real {j.real:.6e}\n"
                 f"  Current Density im = Real {j.imag:.6e}\nEnd\n")

    S.append("Solver 1\n"
             '  Equation = "MgDyn2DHarmonic"\n'
             '  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2DHarmonic"\n'
             '  Variable = "Potential[Potential re:1 Potential im:1]"\n'
             f"  Angular Frequency = Real {omega1:.9e}\n"
             "  Linear System Solver = Direct\n"
             "  Linear System Direct Method = UMFPACK\n"
             "  Steady State Convergence Tolerance = 1.0e-8\n"
             "End\n")
    S.append("Solver 2\n"
             '  Equation = "ErgebnisAusgabe"\n'
             '  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
             '  Output File Name = "asm2d"\n'
             '  Output Format = String "vtu"\n'
             "  Save Geometry Ids = Logical True\n"
             '  Output Directory = "results"\n'
             "  Vtu Format = Logical True\n"
             "End\n")
    S.append("Equation 1\n  Active Solvers(2) = 1 2\nEnd\n")
    # A = 0 auf dem Aussenrand: der Fluss bleibt im Blech. Bei einem Statorjoch,
    # das den Fluss traegt, ist das die uebliche und hier zutreffende Annahme.
    S.append(f"Boundary Condition 1\n  Target Boundaries(1) = {GID_RAND}\n"
             "  Potential re = Real 0.0\n  Potential im = Real 0.0\nEnd\n")

    pfad = os.path.join(work_dir, "case.sif")
    with open(pfad, "w") as fh:
        fh.write("\n".join(S))
    with open(os.path.join(work_dir, "ELMERSOLVER_STARTINFO"), "w") as fh:
        fh.write("case.sif\n1\n")
    return pfad


# ── Auswertung ────────────────────────────────────────────────────────────────

def _lies_vtu(vtu_pfad: str):
    """Knoten, Dreiecke, Koerper-Id und das komplexe Potential aus der Elmer-VTU."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    rd = vtk.vtkXMLUnstructuredGridReader()
    rd.SetFileName(vtu_pfad)
    rd.Update()
    grid = rd.GetOutput()

    pts = vtk_to_numpy(grid.GetPoints().GetData())[:, :2]
    pd = grid.GetPointData()
    namen = [pd.GetArrayName(i) for i in range(pd.GetNumberOfArrays())]

    def hole(teil):
        for n in namen:
            if n and n.lower().replace("_", " ").strip() == teil:
                return vtk_to_numpy(pd.GetArray(n))
        for n in namen:
            if n and teil.split()[-1] in n.lower() and "potential" in n.lower():
                return vtk_to_numpy(pd.GetArray(n))
        raise KeyError(f"'{teil}' nicht in der VTU (vorhanden: {namen})")

    a_re, a_im = hole("potential re"), hole("potential im")

    import numpy as np
    n_c = grid.GetNumberOfCells()
    conn = np.empty((n_c, 3), dtype=np.int64)
    gute = np.zeros(n_c, dtype=bool)
    for i in range(n_c):
        c = grid.GetCell(i)
        if c.GetNumberOfPoints() == 3:
            ids = c.GetPointIds()
            conn[i] = (ids.GetId(0), ids.GetId(1), ids.GetId(2))
            gute[i] = True
    cd = grid.GetCellData().GetArray("GeometryIds")
    if cd is None:
        raise KeyError("GeometryIds fehlen in der VTU "
                       "(Save Geometry Ids = Logical True gesetzt?)")
    gid = vtk_to_numpy(cd).astype(np.int64)
    return pts, conn[gute], gid[gute], np.asarray(a_re), np.asarray(a_im)


def _b_je_dreieck(pts, conn, a):
    """B = (dA/dy, -dA/dx) je Dreieck (P1: elementweise konstant und exakt)."""
    import numpy as np
    x = pts[conn, 0]
    y = pts[conn, 1]
    v = a[conn]
    zwei_flaeche = ((x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0])
                    - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0]))
    sicher = np.where(np.abs(zwei_flaeche) < 1e-20, 1e-20, zwei_flaeche)
    dadx = (v[:, 0] * (y[:, 1] - y[:, 2]) + v[:, 1] * (y[:, 2] - y[:, 0])
            + v[:, 2] * (y[:, 0] - y[:, 1])) / sicher
    dady = (v[:, 0] * (x[:, 2] - x[:, 1]) + v[:, 1] * (x[:, 0] - x[:, 2])
            + v[:, 2] * (x[:, 1] - x[:, 0])) / sicher
    return dady, -dadx, 0.5 * np.abs(zwei_flaeche)


def arkkio_moment(br, bt, r, flaeche, axial_m: float,
                  r_i: float, r_a: float) -> float:
    """Arkkios Momentintegral ueber den Luftspaltring.

        T = L / (mu0 * (r_a - r_i)) * Integral r * <B_r * B_t> dA

    ``br``/``bt`` sind komplexe **Zeiger**; der Zeitmittelwert des Produkts ist
    darum ``0,5 * Re(B_r * conj(B_t))`` und nicht das Produkt selbst. Getrennt
    von ``kennzahlen``, damit sich das Integral gegen eine von Hand gerechnete
    Ringloesung pruefen laesst -- es ist die eine Zahl, an der die ganze Stufe
    haengt.
    """
    import numpy as np
    if len(br) == 0:
        return 0.0
    return float(axial_m / (MU0 * max(r_a - r_i, 1e-12))
                 * np.sum(0.5 * np.real(np.asarray(br) * np.conj(np.asarray(bt)))
                          * np.asarray(r) * np.asarray(flaeche)))


def _perzentil(werte, gewicht, q: float) -> float:
    """Flaechengewichtetes Perzentil -- grosse und kleine Dreiecke zaehlen richtig."""
    import numpy as np
    if len(werte) == 0:
        return 0.0
    o = np.argsort(werte)
    w = np.cumsum(gewicht[o])
    return float(werte[o][int(np.searchsorted(w, q * w[-1]))])


def _eisenweg(netz: dict) -> float:
    """Laenge des Eisenpfads einer Polteilung [m] -- Joch + Zaehne, hin und zurueck."""
    return 2.0 * ((netz["r_so"] - netz["r_si"]) + (netz["r_rot"] - netz["r_wel"])) \
        + math.pi * netz["r_si"]


def kennzahlen(vtu_pfad: str, netz: dict, omega1: float, sigma_eff: float,
               schlupf: float, p: int, axial_m: float) -> dict:
    """Moment (zweimal), Luftspaltleistung, Laeuferverlust und Feldkennwerte."""
    import numpy as np
    pts, conn, gid, a_re, a_im = _lies_vtu(vtu_pfad)

    bx_r, by_r, flaeche = _b_je_dreieck(pts, conn, a_re)
    bx_i, by_i, _ = _b_je_dreieck(pts, conn, a_im)
    mx = pts[conn, 0].mean(axis=1)
    my = pts[conn, 1].mean(axis=1)
    r = np.hypot(mx, my)
    r_s = np.where(r < 1e-12, 1e-12, r)
    cs, sn = mx / r_s, my / r_s

    br = (bx_r * cs + by_r * sn) + 1j * (bx_i * cs + by_i * sn)
    bt = (-bx_r * sn + by_r * cs) + 1j * (-bx_i * sn + by_i * cs)

    # 1) Arkkio ueber den Luftspaltring.
    luft = gid == GID_LUFT
    r_i, r_a = netz["r_rot"], netz["r_si"]
    t_arkkio = arkkio_moment(br[luft], bt[luft], r[luft], flaeche[luft],
                             axial_m, r_i, r_a)

    # 2) Leistungsbilanz aus der Stabdissipation. J = -j*w1*sigma_eff*A ist die
    #    WIRKLICHE Stromdichte; die im Modell verheizte Leistung ist die
    #    LUFTSPALTLEISTUNG (Herleitung im Modulkopf).
    stab = gid == GID_STAEBE
    a_abs2 = (a_re[conn].mean(axis=1) ** 2 + a_im[conn].mean(axis=1) ** 2)
    j_abs2 = (omega1 * sigma_eff) ** 2 * a_abs2
    p_luftspalt = float(np.sum(j_abs2[stab] / (2.0 * max(sigma_eff, 1e-30))
                               * flaeche[stab]) * axial_m)
    p_laeufer = schlupf * p_luftspalt
    omega_syn_mech = omega1 / max(p, 1)
    t_leistung = p_luftspalt / max(omega_syn_mech, 1e-12)

    j_stab_eff = float(np.sqrt(np.sum(j_abs2[stab] * flaeche[stab])
                               / max(np.sum(flaeche[stab]), 1e-30)) / math.sqrt(2.0))
    i_stab = j_stab_eff * float(netz["A_stab_m2"]) * math.sqrt(2.0)   # Amplitude

    # Grundwelle statt Maximum. Bei offener Laeufernut steht am Zahnkopf ein
    # oertlicher Zacken, der als ``max(|B_r|)`` das Luftspaltfeld um mehr als das
    # Doppelte zu gross meldet -- und damit auch die daraus abgeleitete
    # Hauptinduktivitaet. Der Vergleich mit ``ema_asm.ziel_feld`` (einer
    # GRUNDWELLE) waere dann keiner. Die p-te Raumharmonische des komplexen
    # B_r ueber dem Spaltring ist die Groesse, die beide Stufen meinen.
    if luft.any():
        th = np.arctan2(my[luft], mx[luft])
        gew = flaeche[luft]
        # KEIN Faktor 2: ``br`` ist bereits ein komplexer Zeiger, die Welle
        # also ``B_r(theta) = B1 * exp(-j p theta)`` und nicht ein reeller
        # Kosinus. Mit dem sonst ueblichen Faktor 2 kam die Grundwelle groesser
        # heraus als das oertliche Maximum -- unmoeglich, und darum die Probe
        # unten.
        b_gap_1 = float(abs(np.sum(br[luft] * np.exp(1j * p * th) * gew)
                            / max(np.sum(gew), 1e-30)))
        b_gap_amp = float(np.max(np.abs(br[luft])))
        b_gap_eff = float(np.sqrt(np.mean(np.abs(br[luft]) ** 2) / 2.0))
        if b_gap_1 > 1.001 * b_gap_amp:
            raise AssertionError(
                f"Grundwelle {b_gap_1:.3f} T groesser als das oertliche Maximum "
                f"{b_gap_amp:.3f} T -- die Raumharmonische ist falsch gebildet")
    else:
        b_gap_1 = b_gap_amp = b_gap_eff = 0.0
    # Nicht das Maximum: an einer Nutecke steht auf einem einzigen Dreieck ein
    # Gradientensprung, der gemessen 56 T ergab -- eine Zahl, die niemand fuer
    # ein Feld haelt, die aber jede Saettigungsaussage unbrauchbar macht. Das
    # flaechengewichtete 99. Perzentil sagt, wo das Blech wirklich steht.
    # Was der Steg wirklich fuehrt -- die Zahl, an der man sieht, ob die
    # Saettigungsannahme (mu_r_steg) traegt oder das Modell schoenrechnet.
    steg = gid == GID_STEG
    b_steg = _perzentil(np.hypot(np.abs(br[steg]), np.abs(bt[steg])),
                        flaeche[steg], 0.5) if steg.any() else 0.0

    eisen = (gid == GID_ROTOR) | (gid == GID_STATOR)
    b_eisen_p99 = _perzentil(np.hypot(np.abs(br[eisen]), np.abs(bt[eisen])),
                             flaeche[eisen], 0.99) if eisen.any() else 0.0
    b_eisen_max = float(np.max(np.hypot(np.abs(br[eisen]), np.abs(bt[eisen])))) \
        if eisen.any() else 0.0

    # Eindringtiefe bei der SCHLUPFfrequenz -- damit steht nachpruefbar da, ob
    # die Vernachlaessigung der Stromverdraengung an diesem Punkt traegt.
    f2 = schlupf * omega1 / (2.0 * math.pi)
    sigma_wahr = sigma_eff / max(schlupf, 1e-30)
    delta = math.sqrt(2.0 / (2.0 * math.pi * max(f2, 1e-12) * MU0 * max(sigma_wahr, 1e-30)))

    return {
        "T_arkkio_Nm":     round(t_arkkio, 3),
        "T_leistung_Nm":   round(t_leistung, 3),
        "T_abweichung_pct": round(100.0 * abs(t_arkkio - t_leistung)
                                  / max(abs(t_leistung), 1e-9), 2),
        "P_luftspalt_W":   round(p_luftspalt, 1),
        "P_laeufer_W":     round(p_laeufer, 1),
        "I_stab_A":        round(i_stab, 1),
        "B_gap_1_T":       round(b_gap_1, 4),
        "B_gap_amp_T":     round(b_gap_amp, 4),
        "B_gap_eff_T":     round(b_gap_eff, 4),
        "B_steg_T":        round(b_steg, 3),
        "B_eisen_p99_T":   round(b_eisen_p99, 3),
        "B_eisen_max_T":   round(b_eisen_max, 3),
        "ersatzspalt_eisen_mm": round(1000.0 * _eisenweg(netz) / MU_R_EISEN, 3),
        "f_schlupf_Hz":    round(f2, 3),
        "eindringtiefe_mm": round(delta * 1000.0, 1),
        "stabtiefe_mm":    round(float(netz.get("nuttiefe_mm", 0.0)), 2),
        "dreiecke":        int(len(conn)),
    }


# ── Lauf ──────────────────────────────────────────────────────────────────────

def vorbereiten(payload: dict, rpm: float, last_nm: float, work_dir: str,
                gap_lagen: int = GAP_LAGEN, lc_eisen_mm: float = 0.0,
                log=None) -> dict:
    """Alles, was NICHT vom Schlupf abhaengt: Betriebspunkt, Netz, ElmerGrid.

    Getrennt gehalten, weil die Schlupfsuche das Netz sonst bei jedem Punkt neu
    baute -- gemessen 1,5 s Netz und 0,3 s ElmerGrid gegen 2 s Loesen. Der
    Schlupf steckt allein in ``sigma_eff``, also im sif, nicht in der Geometrie.
    """
    import ema_asm
    import ema_maschinenart
    from ema_pipeline import HAIRPIN_MATS

    def _log(t):
        if log:
            log(t)

    geom = payload.get("geom", payload)
    art = ema_maschinenart.art_code(payload)
    ema_maschinenart.pruefe_stufe(art, "feld")
    import ema_radien
    ema_radien.pruefe_bauform(payload, "feld")   # Netz ist auf Innenlaeufer gebaut
    if art != "asm":
        raise ema_maschinenart.ArtNichtUnterstuetzt(
            f"Die harmonische 2-D-Stufe ist die Kaefiglaeufer-Stufe; "
            f"'{art}' gehoert nicht hierher.")

    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    p = max(int(geom["p"]), 1)
    bp = ema_asm.betriebspunkt(geom, axial, rpm, last_nm)
    kf = dict(bp["kaefig"])
    kf["steg_mm"] = ema_asm.KAEFIG_STEG_MM

    mat = HAIRPIN_MATS.get(geom.get("barMat") or ema_asm.KAEFIG_VORGABE,
                           HAIRPIN_MATS[ema_asm.KAEFIG_VORGABE])
    omega1 = 2.0 * math.pi * p * float(rpm) / 60.0

    os.makedirs(work_dir, exist_ok=True)
    msh = os.path.join(work_dir, "asm2d.msh")
    _log("Netz: 2-D-Querschnitt mit Kaefignuten…")
    netz = baue_netz(geom, kf, msh, gap_lagen=gap_lagen, lc_eisen_mm=lc_eisen_mm)
    netz["nuttiefe_mm"] = kf["nuttiefe_mm"]

    mesh_dir = os.path.join(work_dir, "mesh")
    _log(f"ElmerGrid: {netz['dreiecke']} Dreiecke…")
    rg = elmer_runner.run_elmergrid(msh, mesh_dir)
    if not rg.get("ok"):
        raise RuntimeError("ElmerGrid: " + (rg.get("stderr") or rg.get("error", ""))[:300])
    pruefe_koerpernummern(mesh_dir, GID_NUT0 - 1 + netz["n_nut"])

    # Hausskala -> physikalische Amperes. ``bp["I_s_A"]`` steht in der
    # normierten Hausskala (s. ``ema_asm.k_norm``); eingepraegt wird der
    # physikalische Strom, sonst waere das Feld um genau diesen Faktor daneben.
    i_pk_phys = float(bp["I_s_A"]) / max(ema_asm.k_norm(geom), 1e-12)
    j_nut = stator_stroeme(geom, i_pk_phys, netz["A_nut_m2"])

    return {"geom": geom, "p": p, "axial_m": axial / 1000.0, "bp": bp,
            "netz": netz, "work_dir": work_dir, "omega1": omega1,
            "sigma": 1.0 / float(mat["rho_el"]), "stabmaterial": mat["label"],
            "j_nut": j_nut, "i_pk_phys": i_pk_phys, "gap_lagen": gap_lagen,
            "T_soll_Nm": float(bp["T_ist_Nm"]), "rpm": float(rpm), "log": log}


def loese(ctx: dict, schlupf: float, mu_r_steg: float = MU_R_STEG,
          timeout: int = 1800) -> dict:
    """EIN harmonischer Lauf bei gegebenem Schlupf. Netz wird wiederverwendet."""
    s = max(float(schlupf), S_MIN)
    sigma_eff = s * ctx["sigma"]                        # s*sigma, s. Modulkopf
    schreibe_sif(ctx["netz"], ctx["geom"], ctx["omega1"], sigma_eff,
                 ctx["j_nut"], ctx["work_dir"], mu_r_steg=mu_r_steg)
    rs = elmer_runner.run_elmersolver(os.path.join(ctx["work_dir"], "case.sif"),
                                      ctx["work_dir"], timeout=timeout)
    if not rs.get("ok"):
        raise RuntimeError("ElmerSolver: "
                           + (rs.get("stderr") or rs.get("error", ""))[:400]
                           + "\n" + rs.get("stdout", "")[-1200:])
    vtu = _finde_vtu(os.path.join(ctx["work_dir"], "results"))
    if not vtu:
        raise RuntimeError("Keine VTU geschrieben — ResultOutputSolver pruefen")
    kz = kennzahlen(vtu, ctx["netz"], ctx["omega1"], sigma_eff, s,
                    ctx["p"], ctx["axial_m"])
    kz.update({"schlupf": round(s, 6), "sigma_eff_S_m": round(sigma_eff, 1),
               "mu_r_steg": mu_r_steg, "vtu": vtu})
    return kz


def steg_saettigen(ctx: dict, schlupf: float, b_sat: float = B_STEG_SAT_T,
                   max_schritte: int = 5, timeout: int = 1800) -> dict:
    """Die Steg-Permeabilitaet **messen** statt setzen.

    Der Steg ueber der Kaefignut ist der Punkt, an dem ein lineares Modell die
    Bauart entweder verfehlt oder erfindet:

    * mit dem vollen ``mu_r`` des Blechs schliesst er das Hauptfeld tangential
      kurz (gemessen 8-16 T im Steg gegen 0,07 T im Laeuferjoch);
    * mit ``mu_r = 1`` ist die Nut magnetisch offen, und der Carter-Effekt einer
      10 mm breiten Nut ueber 0,7 mm Luftspalt frisst die Hauptinduktivitaet.

    Beides ist falsch, und der wirkliche Steg liegt dazwischen: er fuehrt seine
    Saettigungsflussdichte und nicht mehr. Also wird sie eingestellt --
    loesen, ``B_steg`` ablesen, ``mu_r_steg`` mit ``b_sat/B_steg`` nachziehen,
    wieder loesen. Was herauskommt, ist ein Steg, der **gemessen** bei ``b_sat``
    steht, und ein ``mu_r_steg``, das im Ergebnis sichtbar bleibt.

    Eine echte BH-Kurve waere hier nicht nur aufwendiger, sondern im
    Frequenzbereich gar nicht wohldefiniert: Saettigung ist keine harmonische
    Groesse.
    """
    mu = MU_R_EISEN
    weg = []
    kz = None
    for _ in range(max(int(max_schritte), 1)):
        kz = loese(ctx, schlupf, mu_r_steg=mu, timeout=timeout)
        b = float(kz["B_steg_T"])
        weg.append((round(mu, 1), round(b, 3)))
        if b <= 1e-6:
            break
        neu_mu = min(max(mu * b_sat / b, 1.0), MU_R_EISEN)
        if abs(neu_mu - mu) <= 0.02 * mu:
            mu = neu_mu
            break
        mu = neu_mu
    if kz is not None:
        kz["steg_weg"] = weg
    return {"mu_r_steg": mu, "weg": weg, "kz": kz}


def leerlauf_carter(ctx: dict, mu_r_steg: float, timeout: int = 1800) -> dict:
    """Den Carter-Faktor der GEZEICHNETEN Geometrie messen.

    ``ema_asm`` setzt ``K_CARTER = 1,15`` an -- ein ueblicher Wert fuer
    halbgeschlossene Nuten mit schmalem Schlitz. Gezeichnet wird hier aber, was
    ``ema_em3d.slot_rects`` liefert und was das Netz baut: eine **offene** Nut
    ueber die volle Nutbreite. Bei 9,4 mm Nutoeffnung ueber 0,7 mm Luftspalt ist
    das ein voellig anderer Carter-Faktor, und die Hauptinduktivitaet haengt
    unmittelbar daran.

    Gemessen wird bei praktisch synchronem Lauf (``S_MIN``): dann fliesst kein
    nennenswerter Laeuferstrom, und die Luftspalt-Grundwelle stammt allein vom
    eingepraegten Statorstrom. Aus ``B ~ 1/g_eff`` folgt

        k_c_gemessen = K_CARTER * B_erwartet / B_gemessen .

    Das ist die Zahl, die die analytische Stufe uebernehmen koennte -- und der
    Grund, warum ihr Moment und das Feldmoment auseinandergehen, in EINER
    Groesse statt in einer Abweichung ohne Adresse.
    """
    import ema_asm
    kz = loese(ctx, S_MIN, mu_r_steg=mu_r_steg, timeout=timeout)
    mg = ema_asm.magnetisierungsstrom(ctx["geom"])
    b_erwartet = float(mg["B_m_T"]) * ctx["i_pk_phys"] / max(mg["i_mag_phys_A"], 1e-12)
    b_gemessen = float(kz["B_gap_1_T"])
    k_c = ema_asm.K_CARTER * b_erwartet / max(b_gemessen, 1e-9)
    return {"k_carter_gemessen": round(k_c, 3),
            "k_carter_angesetzt": ema_asm.K_CARTER,
            "B_leerlauf_erwartet_T": round(b_erwartet, 4),
            "B_leerlauf_gemessen_T": round(b_gemessen, 4),
            "g_eff_gemessen_mm": round(k_c * 1000.0 * ctx["netz"]["gap_m"], 3),
            "kz": kz}


def schlupfkennlinie(ctx: dict, s_start: float, t_soll: float,
                     mu_r_steg: float = MU_R_STEG, max_laeufe: int = 12) -> dict:
    """Den Schlupf suchen, bei dem das Feld das geforderte Moment WIRKLICH liefert.

    Der analytische Betriebspunkt setzt den Schlupf aus einer Leistungsbilanz an
    (``P_Kaefig / P_Luftspalt``). Ob das Feld bei diesem Schlupf dasselbe Moment
    hergibt, ist damit noch nicht gesagt -- und genau das ist die Frage, fuer die
    es diese Stufe gibt. Statt eine einzelne Abweichung zu melden, wird hier die
    **Momenten-Schlupf-Kennlinie** abgetastet.

    Abgetastet wird nach BEIDEN Seiten. Bei Speisung aus einer Stromquelle --
    und das ist es, was hier eingepraegt wird -- liegt das Kippmoment bei
    ``s_kipp = R2/(X_m + X2)``, also bei einem SEHR kleinen Schlupf; gemessen
    lag es unter dem analytisch angesetzten Wert. Eine Suche, die nur nach oben
    verdoppelt, laeuft dann vom Kippmoment weg und meldet den Startpunkt als
    Maximum. Das ist keine graue Theorie, sondern der erste Messlauf hier.

    Es wird nichts angepasst und nichts kalibriert -- die Kennlinie steht da, wie
    sie herauskommt, samt Kippmoment.
    """
    punkte, gesehen = [], {}

    def bei(s):
        s = min(max(float(s), S_MIN), 0.9)
        schl = round(s, 6)
        if schl not in gesehen:
            kz = loese(ctx, schl, mu_r_steg=mu_r_steg)
            gesehen[schl] = kz
            punkte.append((schl, kz["T_arkkio_Nm"], kz["T_leistung_Nm"],
                           kz["P_luftspalt_W"]))
        return gesehen[schl]

    s0 = min(max(float(s_start), S_MIN), 0.9)
    leiter = [s0]
    for f in (3.0, 9.0, 27.0):
        leiter += [s0 / f, s0 * f]
    leiter = sorted({min(max(v, S_MIN), 0.9) for v in leiter})
    for v in leiter:
        if len(punkte) >= max_laeufe:
            break
        bei(v)

    # Solange das Moment am oberen Rand noch steigt, weiter nach oben.
    while len(punkte) < max_laeufe:
        punkte.sort()
        if punkte[-1][1] <= punkte[-2][1] or punkte[-1][0] >= 0.9:
            break
        bei(min(punkte[-1][0] * 3.0, 0.9))

    punkte.sort()
    kipp = max(punkte, key=lambda q: q[1])
    erreicht = kipp[1] >= t_soll
    if erreicht:
        # Auf der steigenden Flanke einklemmen und einhalbieren.
        lo = max([q[0] for q in punkte if q[0] <= kipp[0] and q[1] < t_soll],
                 default=S_MIN)
        hi = kipp[0]
        while len(punkte) < max_laeufe and (hi - lo) > 0.03 * hi:
            mid = math.sqrt(max(lo, S_MIN) * hi)
            if bei(mid)["T_arkkio_Nm"] < t_soll:
                lo = mid
            else:
                hi = mid
        treffer = hi
    else:
        treffer = kipp[0]

    punkte.sort()
    return {"punkte": punkte, "s_feld": treffer, "erreicht": erreicht,
            "T_kipp_Nm": kipp[1], "s_kipp": kipp[0],
            "laeufe": len(punkte), "kz": gesehen[round(treffer, 6)]}


def rechne(payload: dict, rpm: float, last_nm: float, work_dir: str,
           gap_lagen: int = GAP_LAGEN, lc_eisen_mm: float = 0.0,
           mu_r_steg: float = 0.0, schlupf_suche: bool = True,
           timeout: int = 1800, log=None) -> dict:
    """Voller ASM-Feldlauf in drei Messschritten.

    1. **Steg saettigen** -- ``mu_r_steg`` wird gemessen, nicht gesetzt
       (``steg_saettigen``). ``mu_r_steg > 0`` uebergibt einen festen Wert und
       ueberspringt diesen Schritt.
    2. **Leerlauf** -- der Carter-Faktor der gezeichneten Geometrie
       (``leerlauf_carter``). Er sagt, wieviel der Abweichung gegen die
       analytische Stufe schon in der Nutform steckt.
    3. **Momenten-Schlupf-Kennlinie** -- bei welchem Schlupf das Feld das
       geforderte Moment wirklich traegt, und wo das Kippmoment liegt.

    ``rpm`` ist die **synchrone** Drehzahl (wie in ``ema_asm.betriebspunkt``);
    die Laeuferdrehzahl folgt aus dem Schlupf.
    """
    def _log(t):
        if log:
            log(t)

    ctx = vorbereiten(payload, rpm, last_nm, work_dir,
                      gap_lagen=gap_lagen, lc_eisen_mm=lc_eisen_mm, log=log)
    bp = ctx["bp"]
    s_analytisch = max(float(bp["schlupf"]), S_MIN)
    t_soll = ctx["T_soll_Nm"]
    f1 = ctx["omega1"] / (2 * math.pi)

    if mu_r_steg > 0:
        steg = {"mu_r_steg": float(mu_r_steg), "weg": []}
    else:
        _log(f"Steg saettigen (Ziel {B_STEG_SAT_T:.1f} T)…")
        steg = steg_saettigen(ctx, s_analytisch, timeout=timeout)
    mu = steg["mu_r_steg"]

    _log("Leerlauf: Carter-Faktor der gezeichneten Nut messen…")
    carter = leerlauf_carter(ctx, mu, timeout=timeout)

    _log(f"ElmerSolver: harmonisch bei {f1:.1f} Hz, analytischer Schlupf "
         f"{100 * s_analytisch:.2f} %…")
    kz = loese(ctx, s_analytisch, mu_r_steg=mu, timeout=timeout)
    kurve = None
    if schlupf_suche:
        _log("Momenten-Schlupf-Kennlinie abtasten…")
        kurve = schlupfkennlinie(ctx, s_analytisch, t_soll, mu_r_steg=mu)

    kz.update({
        "T_analytisch_Nm": round(t_soll, 3),
        "abw_arkkio_pct": round(100.0 * (kz["T_arkkio_Nm"] - t_soll)
                                / max(abs(t_soll), 1e-9), 2),
        "P_kaefig_analytisch_W": float(bp["P_kaefig_W"]),
        "schlupf_analytisch": round(s_analytisch, 6),
        "f1_Hz": round(f1, 2),
        "I_s_A": float(bp["I_s_A"]),
        "I_s_phys_A": round(ctx["i_pk_phys"], 1),
        "stabmaterial": ctx["stabmaterial"],
        "work_dir": work_dir, "knoten": ctx["netz"]["knoten"],
        "gap_lagen": gap_lagen, "analytisch": bp,
        "mu_r_steg": round(mu, 1), "steg_weg": steg["weg"],
        "B_gap_analytisch_T": float(bp["B_m_T"]),
    })
    kz.update({k: v for k, v in carter.items() if k != "kz"})
    if kurve:
        kz["kennlinie"] = kurve["punkte"]
        kz["s_feld"] = kurve["s_feld"]
        kz["s_feld_pct"] = round(100.0 * kurve["s_feld"], 3)
        kz["moment_erreicht"] = kurve["erreicht"]
        kz["T_kipp_Nm"] = kurve["T_kipp_Nm"]
        kz["s_kipp_pct"] = round(100.0 * kurve["s_kipp"], 3)
        kz["schlupf_faktor"] = round(kurve["s_feld"] / max(s_analytisch, 1e-12), 2)
        kz["feld_laeufe"] = kurve["laeufe"]
    return kz


def pruefe_koerpernummern(mesh_dir: str, erwartet: int) -> None:
    """Nachsehen, welche Koerpernummern ElmerGrid WIRKLICH geschrieben hat.

    ``-autoclean`` nummeriert um. Stimmt die Nummerierung nicht mit der im sif
    ueberein, trifft jede ``Target Bodies``-Zeile ins Leere -- und der Loeser
    meldet das **nicht**: er rechnet ein Feld ohne Quellen und gibt ueberall 0
    heraus. Genau so ist dieser Lauf beim ersten Mal ausgegangen. Deshalb wird
    hier gemessen statt vertraut.
    """
    pfad = os.path.join(mesh_dir, "mesh.elements")
    if not os.path.exists(pfad):
        raise RuntimeError(f"mesh.elements fehlt in {mesh_dir}")
    ids = set()
    with open(pfad) as fh:
        for zeile in fh:
            t = zeile.split()
            if len(t) > 1:
                ids.add(int(t[1]))
    soll = set(range(1, erwartet + 1))
    if ids != soll:
        fehlt = sorted(soll - ids)[:6]
        zuviel = sorted(ids - soll)[:6]
        raise RuntimeError(
            f"ElmerGrid hat die Koerper umnummeriert: {len(ids)} Nummern "
            f"{min(ids)}..{max(ids)}, erwartet 1..{erwartet}"
            + (f"; fehlend {fehlt}" if fehlt else "")
            + (f"; unerwartet {zuviel}" if zuviel else ""))


def _finde_vtu(ordner: str) -> str:
    if not os.path.isdir(ordner):
        return ""
    treffer = sorted(f for f in os.listdir(ordner) if f.endswith(".vtu"))
    return os.path.join(ordner, treffer[-1]) if treffer else ""


def bericht(kz: dict) -> str:
    """Der Lauf als Text -- mit den Abweichungen, nicht ohne sie."""
    z = []
    z.append(f"ASM-Feld harmonisch (Elmer 2-D), {kz['f1_Hz']:.1f} Hz, "
             f"Schlupf {100 * kz['schlupf']:.2f} % (analytisch angesetzt)")
    z.append(f"  Netz            {kz['dreiecke']} Dreiecke, "
             f"{kz['gap_lagen']} Lagen im Luftspalt")
    z.append(f"  Moment Arkkio   {kz['T_arkkio_Nm']:9.2f} Nm   (Maxwell im Luftspalt)")
    z.append(f"  Moment Leistung {kz['T_leistung_Nm']:9.2f} Nm   (aus der Stabdissipation)")
    z.append(f"  Moment analyt.  {kz['T_analytisch_Nm']:9.2f} Nm   (ema_asm)")
    z.append(f"  Abweichung      {kz['T_abweichung_pct']:6.2f} % zwischen den beiden "
             f"Feldwegen, {kz['abw_arkkio_pct']:+.2f} % gegen analytisch")
    z.append(f"  Luftspaltleistung {kz['P_luftspalt_W']:.0f} W, davon Laeuferverlust "
             f"{kz['P_laeufer_W']:.0f} W (= s * P_Luftspalt)")
    z.append(f"  Kaefigverlust analytisch {kz['P_kaefig_analytisch_W']:.0f} W "
             f"(mit Kurzschlussring; das 2-D-Feld hat keinen)")
    z.append(f"  B_Luftspalt {kz['B_gap_1_T']:.3f} T Grundwelle "
             f"({kz['B_gap_amp_T']:.3f} T oertliches Maximum), "
             f"B_Eisen (99 %) {kz['B_eisen_p99_T']:.2f} T "
             f"[Ersatzluftspalt des Eisens {kz['ersatzspalt_eisen_mm']:.2f} mm "
             f"bei mu_r = {MU_R_EISEN:.0f}]")
    if "kennlinie" in kz:
        z.append("  Momenten-Schlupf-Kennlinie (Arkkio):")
        for s_, ta, tl, pl in kz["kennlinie"]:
            z.append(f"      s = {100 * s_:6.2f} %   T = {ta:8.2f} Nm   "
                     f"(Leistungsweg {tl:8.2f} Nm)")
        if kz.get("moment_erreicht"):
            z.append(f"  -> Das Feld traegt {kz['T_analytisch_Nm']:.1f} Nm erst bei "
                     f"{kz['s_feld_pct']:.2f} % Schlupf, nicht bei "
                     f"{100 * kz['schlupf_analytisch']:.2f} % "
                     f"(Faktor {kz['schlupf_faktor']:.1f} gegen die Leistungsbilanz)")
        else:
            z.append(f"  -> Das Feld traegt {kz['T_analytisch_Nm']:.1f} Nm bei KEINEM "
                     f"Schlupf: Kippmoment {kz['T_kipp_Nm']:.1f} Nm bei "
                     f"{kz['s_kipp_pct']:.2f} %")
    z.append(f"  Steg ueber der Kaefignut: {kz['B_steg_T']:.2f} T bei gemessenem "
             f"mu_r = {kz.get('mu_r_steg', MU_R_STEG):.0f} "
             f"(Ziel {B_STEG_SAT_T:.1f} T; Weg {kz.get('steg_weg', [])})")
    if "k_carter_gemessen" in kz:
        z.append(f"  Carter-Faktor der GEZEICHNETEN Nut: "
                 f"{kz['k_carter_gemessen']:.2f}  "
                 f"(ema_asm rechnet mit {kz['k_carter_angesetzt']:.2f}) -> "
                 f"Ersatzluftspalt {kz['g_eff_gemessen_mm']:.2f} mm")
        z.append(f"     Leerlauf-Grundwelle {kz['B_leerlauf_gemessen_T']:.3f} T "
                 f"gegen analytisch erwartete {kz['B_leerlauf_erwartet_T']:.3f} T "
                 f"bei gleichem Strom -- hierin steckt der groesste Teil der "
                 f"Momentabweichung, mit Adresse")
    z.append(f"  Eindringtiefe bei {kz['f_schlupf_Hz']:.2f} Hz: "
             f"{kz['eindringtiefe_mm']:.0f} mm gegen {kz['stabtiefe_mm']:.1f} mm Stabtiefe"
             + ("  -> Stromverdraengung vernachlaessigbar"
                if kz['eindringtiefe_mm'] > 3 * max(kz['stabtiefe_mm'], 1e-9)
                else "  -> ACHTUNG: Stromverdraengung nicht mehr vernachlaessigbar"))
    return "\n".join(z)
