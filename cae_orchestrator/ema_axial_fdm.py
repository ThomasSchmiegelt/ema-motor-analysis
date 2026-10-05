"""Feldstufe des Axialflusses: abgewickelter Mehrschnitt -- Stufe 2 aus ``AXIALFLUSS.md``.

Welche Ebene -- und welche ausdruecklich NICHT
----------------------------------------------

Der Haus-FDM loest ``A_z`` mit EINER Komponente senkrecht zur Ebene, und das
setzt Invarianz in dieser Richtung voraus. Daran entscheidet sich alles:

====================== ================== =================== ==============
Ebene                  Invarianzrichtung  traegt die Pole?    gilt
====================== ================== =================== ==============
r-theta (heute)        z ("unendlich lang")      ja           Radialfluss
r-z (DURCH die Achse)  **theta**                 **nein**     --
theta-z (tangential)   r (lokal)                 ja           Axialfluss
====================== ================== =================== ==============

Eine Ebene **durch die Achse** verlangt Invarianz in theta -- und genau dort
liegt der Polwechsel. Ein r-z-Modell stellt eine Maschine OHNE Pole dar: es gibt
Streuung und mittleren Flusspfad, aber **kein Moment**. Das ist der naheliegende
Irrweg, und er ist deshalb hier aufgeschrieben.

Die loesbare Ebene ist um 90 Grad gekippt, aber **tangential im Abstand r** --
der abgewickelte Zylinderschnitt. Dort ist die Invarianzrichtung r, und die gilt
nur LOKAL: Pol- und Nutteilung wachsen mit dem Radius, das Verhaeltnis
Spalt/Polteilung aendert sich ueber dem Ringraum um 1/lambda (gemessen 1,73).
Deshalb mehrere Schnitte und keine einzige Ebene.

Was unveraendert benutzt wird
-----------------------------

``ema_analysis._solve_fdm``, ``_build_fv_matrix``, ``_material_labels``,
``_curl_a`` -- sie nehmen nur Material- und Stromfelder auf einem gleichmaessigen
kartesischen Gitter und kennen keinen Radius. Radiusgebunden sind allein
``_rasterise`` und ``_sample_airgap``, und die werden hier ersetzt, nicht
geaendert. Belegt in ``axialfluss_scheibenprobe.py`` (400x400, Grundwelle
1,264 x Spitze gegen 4/pi = 1,273, Linearitaetsprobe 2,000000).

Der eine Trick, ohne den es nicht geht
---------------------------------------

Das Fenster ist **genau ganzzahlig viele Polteilungen** breit, mit der Polgrenze
bei x = 0. Dann ist das hauseigene Dirichlet ``A = 0`` am Seitenrand die
RICHTIGE Bedingung (``A ~ sin(pi*x/tau)`` hat dort Nullen) und nicht nur eine
weit genug entfernte -- es braucht kein periodisches Verfahren und keinen
zweiten Loeser.

Zwei Dinge, die der quadratische Gitterzwang erzwingt
-----------------------------------------------------

``_build_fv_matrix`` legt ``cid`` als ``(N, N)`` an und rechnet mit EINER
Maschenweite; das Gebiet muss also quadratisch sein und gleich feiner Teilung in
beiden Richtungen folgen. Daraus folgt zweierlei, und beides ist Modellwahl, die
hier ausgesprochen wird statt stillschweigend zu wirken:

* **Nach oben und unten wird mit EISEN aufgefuellt**, bis das Gebiet quadratisch
  ist -- nicht mit Luft. Das war der erste Entwurf und er war falsch, und zwar
  messbar: mit Luftpolsterung haengt das Ergebnis an der FENSTERBREITE, weil mit
  dem Quadrat auch das Luftvolumen waechst und der Fluss hinaus streut. Gemessen
  bei r = 102,5 mm und gleicher Maschenweite::

      Polteilungen   Fenster   Luft je Seite   B1
          2           80,5 mm      7,7 mm     0,86410 T
          4          161,0 mm     47,9 mm     0,84730 T   (-1,94 %)
          6          241,5 mm     88,2 mm     0,83494 T   (-1,46 %)
          8          322,0 mm    128,4 mm     0,82445 T   (-1,26 %)

  Es konvergiert nicht -- es faellt weiter, weil mehr Luft mehr Streuweg ist.
  Und das war nicht harmlos: die noetige Fensterbreite SPRINGT mit dem Radius
  (innen ist die Polteilung kleiner), also sprang mit ihr das Ergebnis, und die
  Schnittreihe war dadurch nicht monoton -- k = 4 lag weiter von k = 8 entfernt
  als k = 2. Das sah nach einem Verfahren aus, das nicht konvergiert.

  Mit Eisen ist die Polsterung **wirkungslos**: jenseits des Joches gibt es
  keine Quelle, das zusaetzliche Eisen fuehrt keinen Fluss, und ``A = 0`` darauf
  sagt genau das, was ein Joch tut -- es schliesst den Fluss ein. Die
  Fensterbreite faellt damit aus dem Ergebnis heraus, und das ist nachgemessen
  (``test_axial_fdm.py``).
* **Ist der Stapel HOEHER als zwei Polteilungen breit**, wird das Fenster auf
  mehr Polteilungen verbreitert, bis es passt. Das kostet Aufloesung bei festem
  N (die Polteilung bekommt weniger Bildpunkte) und wird deshalb im Ergebnis
  gemeldet. Am Innenrand des Ringraums tritt dieser Fall wirklich ein: dort ist
  die Polteilung am kleinsten.

Was dieser Weg NICHT gibt
--------------------------

Der Mehrschnitt vernachlaessigt die **radiale Streuung** an Ri und Ro und die
radialen Stromkomponenten im Wickelkopf -- jeder Schnitt rechnet, als setze sich
seine Geometrie radial unendlich fort. Fuer das Moment sind das bei moderatem
lambda typisch wenige Prozent; **nachzumessen an Stufe 3, nicht anzunehmen**.
Und wie ueberall hier ist das Eisen linear (``MU_R_IRON``), der FDM also ohne
Saettigung.
"""

from __future__ import annotations

import math

import numpy as np

import ema_analysis as EA

MU0 = 4.0e-7 * math.pi

#: Carterfaktor -- derselbe Wert und dieselbe Rolle wie in ``_analytical_Bgap``
#: und ``_analytical_Barm``. Eine zweite Zahl hier waere die Stelle, an der die
#: Eichung des Scheibenwegs von der des Radialwegs abweicht, ohne dass es jemand
#: merkt.
KC = 1.15

#: Mindestbreite des Fensters in Polteilungen. Zwei sind eine volle elektrische
#: Periode -- die kleinste Breite, in der Magnet- UND Strombelag periodisch sind.
POLTEILUNGEN_MIN = 2

#: Wieviele Bildpunkte der Luftspalt mindestens bekommt. Darunter ist er nicht
#: aufgeloest und der Spaltwert liest das Eisen -- derselbe Befund wie
#: ``ema_analysis.AIRGAP_MIN_PX``, nur hier in der anderen Richtung.
SPALT_PX_MIN = 3.0


#: **ZWEI MOMENTWEGE, GEMESSEN FAKTOR ~3 AUSEINANDER -- und das wird gesagt.**
#:
#: ``T_maxwell_Nm`` kommt aus der Maxwellschen Schubspannung des geloesten Feldes,
#: ``T_aus_Kt_Nm`` aus ``1,5*p*psi*i_q``. Gemessen am Vorgabe-Payload:
#:
#:     Last   i_q      T_maxwell   Kt*i_q   Verhaeltnis
#:       50    83,4      164,35     52,25     3,145
#:      100   159,1      311,57    100,90     3,088
#:      200   308,9      600,73    204,86     2,932
#:
#: Das Verhaeltnis ist ueber den Strom nahezu KONSTANT -- also ein Normierungs-
#: und kein Physikfehler. Die beiden Wege stehen auf verschiedenen Bezuegen:
#: ``psi`` ist auf **eine Windung je Nut** normiert (so rechnet
#: ``compute_performance``, ``conductorsPerSlot`` geht dort gar nicht ein),
#: waehrend ``_analytical_Barm`` -- der Eichanker des Ankerfeldes und damit von
#: ``B_t`` -- mit der **physikalischen** Durchflutung ``N_ph = slots/3`` rechnet.
#: Genau diese Bruecke heisst in ``ema_asm`` ``k_norm = pi*k_w*N_ph/p^2``, und
#: dort steht auch, was passiert, wenn man sie vergisst: man vergleicht zwei
#: verschieden grosse Ampere.
#:
#: **Hier wird NICHT einer auf den anderen skaliert.** Welcher Bezug gilt, ist an
#: einem unabhaengigen Loeser zu entscheiden (Stufe 3, Elmer-Ringsektor) und nicht
#: durch einen Faktor, der die Abweichung verschwinden laesst. Dasselbe Verfahren
#: wie bei ``ema_leistung``, das den Widerspruch zwischen ``rated_torque`` und dem
#: LPTN ueber die Kennlinie schreibt statt ihn aufzuloesen. Befund in
#: ``BEFUNDE.md``, 05.10.2026.
_WIDERSPRUCH = (
    "WIDERSPRUCH im Werkzeug: T_maxwell (geloeste Schubspannung) und T_aus_Kt "
    "(1,5*p*psi*i_q) liegen um den Faktor ~3 auseinander, ueber den Strom nahezu "
    "konstant -- also ein Normierungsunterschied (psi auf 1 Windung/Nut, "
    "_analytical_Barm auf N_ph = slots/3; vgl. ema_asm.k_norm). Welcher Bezug "
    "gilt, entscheidet Stufe 3 und nicht ein Korrekturfaktor.")


# ── Schichtung: welche Bauform welchen Stapel hat ────────────────────────────
#
# Jede Bauform ist eine Folge von Schichten in AXIALER Richtung, und jede sagt
# dazu, wie die Magnetisierung zeigt. Das ist nicht Kosmetik: bei der NS-Bauform
# (yasa) zeigen beide Magnetlagen GLEICHsinnig, der Fluss geht axial durch den
# Zahn durch und der Staender braucht kein Joch -- daher "yokeless". Bei NN
# zeigen sie gegensinnig, der Fluss muss im Staender umfangs weiterlaufen, und
# dafuer braucht es ein Joch. Wer das vertauscht, rechnet eine andere Maschine.
#
# ``mag``:  +1 / -1 = axiale Richtung der Magnetisierung dieser Lage
# ``nut``:  von welcher Flaeche die Nut einschneidet ("unten"/"oben"/"durch")
_BAUFORMEN = {
    "yasa": {
        "spalte": 2, "joch": False,
        "stapel": [("ruecken", "fe"), ("magnet", +1), ("spalt", None),
                   ("stator", "durch"), ("spalt", None), ("magnet", +1),
                   ("ruecken", "fe")],
        "aussage": "NS: beide Lagen gleichsinnig, Fluss AXIAL durch den Zahn, "
                   "Staender jochlos",
    },
    "torus_nn": {
        "spalte": 2, "joch": True,
        "stapel": [("ruecken", "fe"), ("magnet", +1), ("spalt", None),
                   ("stator", "beide"), ("spalt", None), ("magnet", -1),
                   ("ruecken", "fe")],
        "aussage": "NN: Lagen gegensinnig, Fluss laeuft im Staender UMFANGS -- "
                   "Umfangsjoch noetig",
    },
    "afir": {
        "spalte": 2, "joch": True,
        "stapel": [("stator", "oben"), ("spalt", None), ("magnet", +1),
                   ("ruecken", "fe"), ("magnet", +1), ("spalt", None),
                   ("stator", "unten")],
        "aussage": "zwei Staender, ein Laeufer -- Wicklung aussen, gut kuehlbar",
    },
    "einseitig": {
        "spalte": 1, "joch": True,
        "stapel": [("ruecken", "fe"), ("magnet", +1), ("spalt", None),
                   ("stator", "unten")],
        "aussage": "ein Luftspalt -- die Anzugskraft liegt unausgeglichen am Lager",
    },
}


def polteilungen(geom: dict, r_m: float) -> int:
    """Wieviele Polteilungen das Fenster braucht.

    Drei Bedingungen, alle zwingend:

    * **ganzzahlig viele Polteilungen** -- sonst ist Dirichlet am Rand falsch;
    * **GERADZAHLIG viele** -- sonst liegt im Fenster keine ganze Zahl
      elektrischer Perioden, und die Grundwelle faellt zwischen zwei
      FFT-Faecher. Drei Polteilungen sind 1,5 Perioden; beim Bauen kam am
      Innenrand genau das heraus, und die „Grundwelle" waere dort auf zwei
      Faecher verschmiert gewesen, ohne dass etwas widersprochen haette;
    * **ganzzahlig viele Nutteilungen** -- sonst ist der Strombelag am Rand
      unstetig.

    Dazu die Hoehenbedingung aus dem quadratischen Gitter (s. Modulkopf).

    Bei einer **Bruchlochwicklung** kann das Fenster dadurch sehr breit werden:
    die Periodizitaet ist dann 2p/ggT(Q, p) Polteilungen, im Grenzfall die ganze
    Maschine. Das ist keine Schwaeche des Verfahrens, sondern die Symmetrie der
    Wicklung -- gemeldet wird es als Aufloesungskosten, nicht abgewiesen.
    """
    import ema_axial

    a = ema_axial.auslegung(geom)
    q_je_pol = a["slots"] / a["poles"]
    h = stapelhoehe(geom)                                    # mm
    tau_p = 2.0 * math.pi * r_m / a["poles"] * 1000.0        # mm -- MUSS mm sein,
    # sonst vergleicht die Hoehenbedingung unten Meter gegen Millimeter und ist
    # immer falsch (beim Bauen genau so passiert).
    n = POLTEILUNGEN_MIN
    while n <= 64:
        ganze_nuten = abs(n * q_je_pol - round(n * q_je_pol)) < 1e-9
        passt_hoehe = n * tau_p >= h
        if n % 2 == 0 and ganze_nuten and passt_hoehe:
            return n
        n += 1
    raise ValueError(
        f"kein Fenster gefunden: {a['slots']} Nuten auf {a['poles']} Pole "
        f"ergeben {q_je_pol:.4f} Nuten je Pol, und der Stapel ist "
        f"{h:.1f} mm hoch gegen {tau_p:.1f} mm Polteilung bei r = "
        f"{r_m*1000:.1f} mm. Nutzahl oder Polzahl aendern.")


def stapelhoehe(geom: dict) -> float:
    """Axiale Hoehe des aktiven Stapels in **Millimetern** (ohne Luftpolster)."""
    import ema_axial

    a = ema_axial.auslegung(geom)
    g = geom or {}
    bf = _BAUFORMEN[a["bauform"]]
    t_mag = a["magnet_dicke_m"] * 1000.0
    t_spalt = a["luftspalt_m"] * 1000.0
    t_stator = float(g.get("slotDepth", 25.0) or 25.0)
    if bf["joch"]:
        t_stator += _jochhoehe(geom)
    t_ruecken = _rueckenhoehe(geom)
    h = 0.0
    for art, _ in bf["stapel"]:
        h += {"ruecken": t_ruecken, "magnet": t_mag,
              "spalt": t_spalt, "stator": t_stator}[art]
    return h


def _rueckenhoehe(geom: dict) -> float:
    """Rueckenblech [mm] -- aus ``ema_axial.ruecken``, nicht neu geschaetzt."""
    import ema_axial
    g = geom or {}
    vor = float(g.get("axialRueckenMm", 0) or 0.0)
    if vor > 0:
        return vor
    try:
        return ema_axial.ruecken(geom, eichung_magnet(geom))["t_soll_m"] * 1000.0
    except Exception:                                                # noqa: BLE001
        return 12.0


def _jochhoehe(geom: dict) -> float:
    """Staenderjoch [mm], wo die Bauform eines braucht (NN, AFIR, einseitig).

    Bemessen wie das Rueckenblech: es fuehrt die Haelfte des Polflusses umfangs.
    """
    import ema_axial
    a = ema_axial.auslegung(geom)
    ro, ri = a["r_aussen_m"], a["r_innen_m"]
    phi = (eichung_magnet(geom) * a["polbedeckung"]
           * math.pi * (ro ** 2 - ri ** 2) / a["poles"])
    return max(2.0, phi / (2.0 * (ro - ri) * ema_axial.B_FE_ZUL_VORGABE) * 1000.0)


# ── Eichung: die beiden analytischen Anker ───────────────────────────────────

def eichung_magnet(geom: dict) -> float:
    """Analytisches Luftspaltfeld der Magnete [T] -- der axiale Anker.

    Der FDM eicht seine Amplitude auf eine analytische Zahl
    (``sf = B_analytisch / pk_fdm``), und **die ist der Grund, warum am
    20.09.2026 fuenf Maschinenarten dieselben 0,63 T meldeten, obwohl im Raster
    fuenf verschiedene Laeufer standen**: ``_analytical_Bgap`` kennt die Bauart
    nicht. Axial denselben Fehler zu machen ist leicht -- sie kennt den Flussweg
    auch nicht, und ihr IPM-Zweig rechnet mit einer Polteilung aus ``statorID``.

    Der axiale Fall ist dafuer der einfachste, den es gibt: der Magnet liegt
    FLACH am Spalt, ohne Tasche, ohne Steg, ohne Konzentration. Es bleibt die
    Arbeitsgerade

        B_gap = Br * hm / (hm + mu_r * kc * g) * alpha_i

    Gemessen in ``axialfluss_scheibenprobe.py``: Permeanz 0,8325 -> 0,9573 T,
    und der geloeste Spaltwert trifft das.
    """
    import ema_axial
    a = ema_axial.auslegung(geom)
    hm = a["magnet_dicke_m"] * 1000.0
    g = a["luftspalt_m"] * 1000.0
    perm = hm / (hm + EA.MU_R_MAG * KC * g)
    return float(np.clip(EA.Br_NdFeB * perm * a["polbedeckung"], 0.01, 2.0))


def eichung_anker(geom: dict, i_pk: float) -> float:
    """Analytisches Ankerfeld [T] -- ueber ``ema_analysis._analytical_Barm``.

    Die Formel braucht Wicklung und Spalt, aber **keinen Radius**: sie gilt
    unveraendert, seit ``luftspalt_mm`` einen axialen Zweig hat. Hier wird sie
    deshalb nur weitergereicht, statt eine zweite daneben zu stellen -- das waere
    genau die Stelle, an der die Eichung der beiden Flusswege auseinanderlaeuft.
    """
    return EA._analytical_Barm(geom, i_pk)


# ── Der Rasterer: eine abgewickelte Scheibe ──────────────────────────────────

def rastere_scheibe(geom: dict, r_m: float, N: int = 400,
                    iq: float = 0.0, id_: float = 0.0,
                    rotor_winkel: float = 0.0, nuten: bool = True,
                    n_pol: int | None = None) -> dict:
    """``mu``, ``J_magnet`` und ``J_anker`` einer abgewickelten Scheibe bei r.

    x = Umfang (abgewickelt), y = axial. Das Gegenstueck zu
    ``ema_analysis._rasterise``, nur ohne Radien: dort ``R = hypot(X, Y)``-Ringe,
    hier waagerechte Baender und senkrechte Nuten.

    **Magnet- und Ankerstrom werden GETRENNT zurueckgegeben**, weil sie getrennt
    geeicht werden muessen: die beiden Ersatzstromsysteme (dipolares ``curl M``
    gegen Nettostrom je Nut) haben sehr verschiedene Feldverstaerkungen, und ein
    gemeinsamer Faktor hat radial gemessen das Staenderfeld auf >100 T getrieben
    oder die Magnete auf ~0 gedrueckt. Dieselbe Trennung wie in
    ``run_em_analysis``.
    """
    import ema_axial

    a = ema_axial.auslegung(geom)
    bf = _BAUFORMEN[a["bauform"]]
    poles, q = a["poles"], a["slots"]
    n_pol = int(n_pol) if n_pol else polteilungen(geom, r_m)
    tau_p = 2.0 * math.pi * r_m / poles * 1000.0            # mm
    tau_s = 2.0 * math.pi * r_m / q * 1000.0                # mm
    seite = n_pol * tau_p                                    # quadratisches Fenster
    sc = N / seite                                           # px/mm
    h_stapel = stapelhoehe(geom)
    y0 = (seite - h_stapel) / 2.0                            # Luftpolster, mittig
    if y0 < 0:
        raise ValueError(f"Stapel {h_stapel:.1f} mm hoeher als Fenster "
                         f"{seite:.1f} mm -- polteilungen() haette das abfangen muessen")

    t_mag = a["magnet_dicke_m"] * 1000.0
    t_spalt = a["luftspalt_m"] * 1000.0
    t_nut = float((geom or {}).get("slotDepth", 25.0) or 25.0)
    t_joch = _jochhoehe(geom) if bf["joch"] else 0.0
    t_ruecken = _rueckenhoehe(geom)

    lagen, y = [], y0
    for art, kenn in bf["stapel"]:
        d = {"ruecken": t_ruecken, "magnet": t_mag, "spalt": t_spalt,
             "stator": t_nut + t_joch}[art]
        lagen.append({"art": art, "kenn": kenn, "y0": y, "y1": y + d})
        y += d

    Y, X = np.meshgrid(np.arange(N) / sc, np.arange(N) / sc, indexing="ij")

    # Die Polsterung ist EISEN, nicht Luft (s. Modulkopf): sie setzt die
    # aeusserste Eisenlage bis an den Rand fort, fuehrt selbst keinen Fluss und
    # macht das Ergebnis damit unabhaengig von der Fensterbreite.
    mu = np.full((N, N), EA.MU_R_IRON)
    mu[(Y >= lagen[0]["y0"]) & (Y < lagen[-1]["y1"])] = 1.0
    My = np.zeros((N, N))
    j_ank = np.zeros((N, N))
    swr = min(0.8, max(0.2, float((geom or {}).get("slotWidthRatio", 0.5) or 0.5)))
    amp = EA.Br_NdFeB / (MU0 * EA.MU_R_MAG)
    # Polvorzeichen: wechselt je Polteilung, mit der Polgrenze bei x = 0.
    pol = np.floor(X / tau_p).astype(int) % 2
    vz = np.where(pol == 0, 1.0, -1.0)

    for lg in lagen:
        band = (Y >= lg["y0"]) & (Y < lg["y1"])
        if lg["art"] == "ruecken":
            mu[band] = EA.MU_R_IRON
        elif lg["art"] == "magnet":
            mu[band] = EA.MU_R_MAG
            # Polbedeckung < 1: der Magnet fuellt die Polteilung nicht ganz aus.
            mitte = (X % tau_p) / tau_p
            belegt = np.abs(mitte - 0.5) <= a["polbedeckung"] / 2.0
            My[band & belegt] = amp * lg["kenn"] * vz[band & belegt]
            mu[band & ~belegt] = 1.0
        elif lg["art"] == "stator":
            mu[band] = EA.MU_R_IRON
            # ``nuten=False`` gibt den NUTLOSEN Staender: massives Eisen, kein
            # Strom. Das ist der Bezugsfall, an dem sich zwei Dinge messen
            # lassen, die sonst in einer Zahl steckten -- die Form der reinen
            # Magnetwelle (sie muss gegen 4/pi laufen) und der Carterfaktor
            # dieser Nut (``carter``). Er ist kein Testschalter: ohne Bezugsfall
            # ist eine gemessene Nutwirkung keine.
            if nuten:
                _nuten(mu, j_ank, band, X, Y, lg, tau_s, swr, t_nut, seite,
                       r_m, iq, id_, rotor_winkel, N, a)

    # J = curl M = dMy/dx  (Mx = 0) -- derselbe Ansatz wie im radialen Rasterer
    j_mag = np.zeros((N, N))
    j_mag[:, 1:-1] = (My[:, 2:] - My[:, :-2]) / 2.0
    return {"mu": mu, "j_magnet": j_mag, "j_anker": j_ank, "lagen": lagen,
            "sc": sc, "seite_mm": seite, "n_polteilungen": n_pol,
            "tau_p_mm": tau_p, "tau_s_mm": tau_s,
            "spalt_px": t_spalt * sc, "N": N, "r_m": r_m,
            "bauform": a["bauform"], "n_spalte": a["n_spalte"]}


def _nuten(mu, j_ank, band, X, Y, lg, tau_s, swr, t_nut, seite_mm,
           r_m, iq, id_, rotor_winkel, N, a):
    """Nuten als Luft, dazu der dreiphasige Nutstrom.

    Die Strombelegung ist **zeichengetreu** die des radialen Rasterers
    (``ema_analysis._rasterise``, Block „Stator slots"):

        cur = (id*cos(elAng - rotor*p) - iq*sin(elAng - rotor*p)) / IQ_REF
        J[Nut] += cur * 5/N

    ``elAng = p*theta`` wird dabei zu ``p*x/r`` -- dieselbe Groesse, nur
    abgewickelt. Zwei verschiedene Strombelegungen fuer dieselbe Wicklung waeren
    die Stelle, an der Radial- und Axialweg unvergleichbar werden.
    """
    p_pairs = max(1, a["poles"] // 2)
    IQ_REF, j_scale = 2.0, 5.0 / N
    hat_strom = (abs(iq) + abs(id_)) > 0.1
    von_oben = lg["kenn"] in ("oben", "durch", "beide")
    von_unten = lg["kenn"] in ("unten", "durch", "beide")
    anzahl = int(round(seite_mm / tau_s))
    for s_i in range(anzahl):
        x_m = (s_i + 0.5) * tau_s
        nut = np.abs(X - x_m) <= swr * tau_s / 2.0
        tiefe = np.zeros_like(band)
        if von_oben:
            tiefe |= (Y >= lg["y1"] - t_nut)
        if von_unten:
            tiefe |= (Y <= lg["y0"] + t_nut)
        m = band & nut & tiefe
        if not m.any():
            continue
        mu[m] = 1.0
        if hat_strom:
            el = (x_m / 1000.0) / max(r_m, 1e-9) * p_pairs
            cur = (id_ * math.cos(el - rotor_winkel * p_pairs)
                   - iq * math.sin(el - rotor_winkel * p_pairs)) / IQ_REF
            j_ank[m] += cur * j_scale


# ── Loesen und abtasten ──────────────────────────────────────────────────────

def _spaltlinie(sch: dict, welcher: int = 0) -> tuple:
    """``(jy, name)`` der Gitterzeile in der Mitte des gewaehlten Luftspalts."""
    spalte = [lg for lg in sch["lagen"] if lg["art"] == "spalt"]
    lg = spalte[min(welcher, len(spalte) - 1)]
    return int(round((lg["y0"] + lg["y1"]) / 2.0 * sch["sc"])), lg


def schnitt(geom: dict, r_m: float, N: int = 400, iq: float = 0.0,
            id_: float = 0.0, rotor_winkel: float = 0.0,
            nuten: bool = True, n_pol: int | None = None) -> dict:
    """EINE Scheibe: rastern, mit dem HAUS-Loeser loesen, getrennt eichen.

    Zwei Loesungen auf DEMSELBEN ``mu`` -- Magnet und Anker --, also eine
    Faktorisierung und eine Ruecksubstitution: der LU-Cache des Hauses greift
    hier genauso wie radial, weil er nach ``(N, hash(mu))`` schluesselt und
    ``mu`` nicht am Strom haengt.
    """
    sch = rastere_scheibe(geom, r_m, N, iq, id_, rotor_winkel, nuten, n_pol)
    lbl = EA._material_labels(sch["mu"])

    a_mag = EA._solve_fdm(sch["mu"], sch["j_magnet"], cache=True)
    bx_m, by_m = EA._curl_a(a_mag, lbl)
    jy, _ = _spaltlinie(sch)
    pk_m = float(np.abs(by_m[jy, :]).max())
    b_an = eichung_magnet(geom)
    sf_m = b_an / max(pk_m, 1e-30)

    i_pk = math.hypot(iq, id_)
    if i_pk > 1e-6:
        a_ank = EA._solve_fdm(sch["mu"], sch["j_anker"], cache=True)
        bx_a, by_a = EA._curl_a(a_ank, lbl)
        pk_a = float(np.abs(by_a[jy, :]).max())
        sf_a = eichung_anker(geom, i_pk) / max(pk_a, 1e-30)
    else:
        bx_a = by_a = np.zeros_like(bx_m)
        sf_a, pk_a = 0.0, 0.0

    bn = by_m[jy, :] * sf_m + by_a[jy, :] * sf_a
    bt = bx_m[jy, :] * sf_m + bx_a[jy, :] * sf_a

    # Grundwelle der POLWELLE: das Fenster haelt n_polteilungen/2 Perioden.
    k = np.fft.rfft(bn) / len(bn)
    # Das Fenster ist geradzahlig viele Polteilungen breit (s.
    # ``polteilungen``), also liegt die Polwelle genau auf Fach
    # n_polteilungen/2 -- keine Rundung, kein Verschmieren.
    h1 = sch["n_polteilungen"] // 2
    klirr = (math.sqrt(sum(abs(k[h]) ** 2 for h in range(h1 + 1, 40 * h1)
                           if h < len(k)))
             / max(abs(k[h1]), 1e-30))

    # Maxwellsche Schubspannung in der Spaltmitte, ueber das Fenster gemittelt.
    sigma_t = float(np.mean(bn * bt) / MU0)
    sigma_n = float(np.mean(bn ** 2) / (2.0 * MU0))
    return {
        "r_m": r_m, "N": N, "n_polteilungen": sch["n_polteilungen"],
        "seite_mm": sch["seite_mm"], "spalt_px": sch["spalt_px"],
        "spalt_aufgeloest": sch["spalt_px"] >= SPALT_PX_MIN,
        "b_n_spitze_T": float(np.abs(bn).max()),
        "b_n_grundwelle_T": float(2 * abs(k[h1])),
        "b_t_spitze_T": float(np.abs(bt).max()),
        "klirranteil": float(klirr),
        "sigma_t_pa": sigma_t, "sigma_n_pa": sigma_n,
        "eichfaktor_magnet": sf_m, "eichfaktor_anker": sf_a,
        "b_an_magnet_T": b_an,
        "b_an_anker_T": eichung_anker(geom, i_pk) if i_pk > 1e-6 else 0.0,
        "nuten": nuten,
        "bn": bn, "bt": bt, "raster": sch,
    }


def carter(geom: dict, r_m: float, N: int = 400) -> dict:
    """Der Carterfaktor DIESER Nut -- gemessen, nicht angenommen.

    ``_analytical_Bgap`` und ``_analytical_Barm`` rechnen mit ``KC = 1,15``. Das
    ist ein Richtwert fuer eine halbgeschlossene Nut; dieses Werkzeug zeichnet
    **offene** Nuten (es gibt keinen Nutverschluss, s. ``ema_rastmoment``), und
    bei ``slotWidthRatio = 0,5`` ist die halbe Umfangslaenge offener Nutschlitz.
    Derselbe Befund ist am Kaefiglaeufer schon gemessen worden: der 2-D-Lauf fand
    dort **3,2** gegen die analytisch angenommenen 1,15.

    Gerechnet wird am Verhaeltnis der **GRUNDWELLEN ohne Eichung** -- und beides
    ist noetig. Ohne Eichung, weil der Eichfaktor den gesuchten Unterschied
    gerade herauskuerzt. Und an der Grundwelle und ausdruecklich **nicht an der
    Spitze**: beim Bauen zuerst an der Spitze gemessen kam ein Carterfaktor von
    **0,82** heraus, also kleiner als eins, was es nicht geben kann. Der Grund
    ist physikalisch und kein Rechenfehler -- ueber einem ZAHN ist der Fluss
    gebuendelt, die lokale Spitze steigt durch die Nutung, waehrend der Fluss je
    Pol faellt. Carter ist eine Aussage ueber den mittleren Fluss.
    """
    o = schnitt(geom, r_m, N, nuten=False)
    m = schnitt(geom, r_m, N, nuten=True)
    # Rohe Grundwellen: die ausgegebene ist geeicht, sf haengt davor.
    h1_o = o["b_n_grundwelle_T"] / max(o["eichfaktor_magnet"], 1e-30)
    h1_m = m["b_n_grundwelle_T"] / max(m["eichfaktor_magnet"], 1e-30)
    kc_gem = h1_o / max(h1_m, 1e-30)
    return {
        "r_m": r_m, "kc_gemessen": float(kc_gem), "kc_angenommen": KC,
        "faktor": float(kc_gem / KC),
        "grundwelle_nutlos_T": o["b_n_grundwelle_T"],
        "grundwelle_genutet_T": m["b_n_grundwelle_T"],
        "grundwelle_roh_nutlos": float(h1_o), "grundwelle_roh_genutet": float(h1_m),
        "form_nutlos": o["b_n_grundwelle_T"] / max(o["b_n_spitze_T"], 1e-30),
        "form_genutet": m["b_n_grundwelle_T"] / max(m["b_n_spitze_T"], 1e-30),
        "aussage": (
            f"gemessener Carterfaktor {kc_gem:.2f} gegen angenommene {KC:.2f} "
            f"({kc_gem/KC:.2f}x). Die analytische Eichung rechnet damit das "
            f"Luftspaltfeld zu GROSS; der geloeste Verlauf ueber dem Umfang ist "
            f"davon unberuehrt, die Amplitude nicht."),
    }


def felder(geom: dict, k_schnitte: int = 5, N: int = 400, rpm: float = 1000.0,
           last_nm: float = 0.0, axial_mm: float | None = None) -> dict:
    """Der Mehrschnitt: k Scheiben ueber dem Ringraum, aufsummiert.

    Die beiden Integrale werden **ueber die Schnitte** gebildet, mit genau den
    Gewichten aus ``ema_fluss`` -- Fluss mit r^1, Moment mit r^2::

        psi  = n_spalte * p * (2/pi) * SUM B1(r_i) * r_i * dr
        T    = n_spalte * 2*pi * SUM sigma_t(r_i) * r_i^2 * dr

    Dass dieselben Gewichte hier und dort stehen, ist der Sinn der Sache: Stufe 1
    rechnet sie mit einem analytischen ``B_gap``, Stufe 2 mit einem geloesten
    ``B1(r)``. Kommt dabei etwas anderes heraus, ist das eine Aussage ueber die
    Formel und nicht ueber die Summation.
    """
    import ema_axial
    import ema_fluss

    a = ema_axial.auslegung(geom, axial_mm)
    ro, ri, n_sp = a["r_aussen_m"], a["r_innen_m"], a["n_spalte"]
    dr = (ro - ri) / k_schnitte
    radien = [ri + (i + 0.5) * dr for i in range(k_schnitte)]

    # Der Betriebspunkt kommt aus ``estimate_dq_currents`` -- derselben Funktion,
    # aus der der radiale Rasterer seine Nutstroeme nimmt. Sie gibt ein TUPEL
    # (i_q, i_d) heraus und nimmt das Luftspaltfeld als ``b_gap_t``; sie hat
    # kein ``axial_mm``.
    #
    # Hier stand zuerst ein stilles ``except: iq = id_ = 0``. Das hat den
    # Signaturfehler verschluckt und einen Lastlauf mit **Strom null** gerechnet
    # -- heraus kam das Leerlaufmoment (-0,18 Nm statt 100 Nm Soll), und nichts
    # widersprach. Ein Fehlschlag hier ist deshalb KEIN Nullstrom, sondern ein
    # benannter Grund im Ergebnis.
    iq = id_ = 0.0
    strom_grund = ""
    if last_nm > 0:
        try:
            iq, id_ = EA.estimate_dq_currents(
                geom, rpm, last_nm, b_gap_t=eichung_magnet(geom))
            iq, id_ = float(iq), float(id_)
        except Exception as e:                                       # noqa: BLE001
            strom_grund = f"{type(e).__name__}: {e}"

    # **Die AUFLOESUNG wird ueber die Schnitte konstant gehalten, nicht N.**
    # Das Fenster waechst mit dem Radius (und springt, wo mehr Polteilungen
    # noetig sind): bei festem N hat damit jeder Schnitt eine andere Maschen-
    # weite, und der Diskretisierungsfehler wandert mit dem Radius. Gemessen war
    # die Schnittreihe dadurch NICHT monoton -- k=2 lag 2,88 % neben k=8, k=4
    # aber 5,56 %. Das sah nach einem Verfahren aus, das nicht konvergiert, und
    # war die Netzfeinheit. ``N`` meint jetzt das BREITESTE Fenster; jeder
    # schmalere bekommt entsprechend weniger Punkte bei gleicher mm/px.
    # **ALLE Schnitte bekommen DIESELBE Fensterbreite in Polteilungen** -- die
    # des Innenrands, wo die Polteilung am kleinsten und die Forderung am
    # schaerfsten ist. Gerechnet wird sie aus Ri und nicht aus den Schnittradien,
    # damit sie nicht von k abhaengt.
    #
    # Der Grund ist gemessen: mit Eisenpolsterung haengt das Ergebnis noch zu
    # 1,3 % an der Fensterbreite (ueber einen Faktor 4). Das waere fuer sich
    # ertraeglich -- schaedlich war der SPRUNG. Die noetige Breite waechst
    # stufig mit dem Radius, also sprang das Ergebnis mitten im Ringraum, und
    # die Schnittreihe war dadurch nicht monoton: k = 4 lag weiter von k = 8
    # entfernt als k = 2, was wie ein nicht konvergierendes Verfahren aussah und
    # keines war. Eine einheitliche Breite nimmt den Sprung heraus; die
    # verbleibende Abhaengigkeit steht als Grenze im Ergebnis.
    n_pol = polteilungen(geom, ri)
    seiten = [n_pol * 2.0 * math.pi * r / a["poles"] * 1000.0 for r in radien]
    px_je_mm = N / max(seiten)
    n_je_schnitt = [max(160, int(round(se * px_je_mm))) for se in seiten]

    s_fluss = s_moment = 0.0
    schnitte = []
    for r, n_i in zip(radien, n_je_schnitt):
        sn = schnitt(geom, r, n_i, iq, id_, n_pol=n_pol)
        sn.pop("raster", None)
        bn, bt = sn.pop("bn"), sn.pop("bt")
        sn["bn_min_T"], sn["bt_min_T"] = float(bn.min()), float(bt.min())
        s_fluss += sn["b_n_grundwelle_T"] * r * dr
        s_moment += sn["sigma_t_pa"] * r * r * dr
        schnitte.append(sn)

    p = max(1, a["poles"] // 2)
    psi = n_sp * p * (2.0 / math.pi) * s_fluss
    t_nm = n_sp * 2.0 * math.pi * s_moment
    fl = ema_fluss.flaechen(geom, axial_mm)
    b_mittel = (sum(s["b_n_grundwelle_T"] * s["r_m"] for s in schnitte)
                / max(sum(s["r_m"] for s in schnitte), 1e-30))
    return {
        "flussweg": "axial", "bauform": a["bauform"], "n_spalte": n_sp,
        "k_schnitte": k_schnitte, "N": N, "N_je_schnitt": n_je_schnitt,
        "fenster_einheitlich": n_pol,
        "mm_je_px": 1.0 / px_je_mm, "radien_m": radien, "dr_m": dr,
        "i_q_A": iq, "i_d_A": id_, "rpm": rpm, "last_nm": last_nm,
        "strom_fehlschlag": strom_grund,
        "last_gerechnet": bool(last_nm <= 0 or (abs(iq) + abs(id_)) > 0.1),
        "psi_Wb": psi, "Kt_Nm_per_A": 1.5 * p * psi,
        "T_maxwell_Nm": t_nm,
        "B_gap_grundwelle_mittel_T": b_mittel,
        "B_gap_ueber_r_T": [s["b_n_grundwelle_T"] for s in schnitte],
        "a_fluss_m2": fl["a_fluss_m2"], "a_moment_m3": fl["a_moment_m3"],
        "T_aus_Kt_Nm": 1.5 * p * psi * iq if iq else 0.0,
        "T_verhaeltnis": (abs(t_nm) / abs(1.5 * p * psi * iq)
                          if iq and abs(psi) > 1e-30 else None),
        "widerspruch": _WIDERSPRUCH if iq else "",
        "alle_spalte_aufgeloest": all(s["spalt_aufgeloest"] for s in schnitte),
        "fenster_polteilungen": [s["n_polteilungen"] for s in schnitte],
        "schnitte": schnitte,
        "grenzen": [
            "Mehrschnitt: jeder Schnitt rechnet, als setze sich seine Geometrie "
            "radial unendlich fort -- die radiale Streuung an Ri und Ro und die "
            "radialen Stromkomponenten im Wickelkopf fehlen. Nachzumessen an "
            "Stufe 3 (Elmer-Ringsektor), nicht anzunehmen.",
            "Eisen linear (MU_R_IRON), keine Saettigung -- wie im radialen FDM.",
            "BELASTBAR sind psi und B_gap(r); das MOMENT ist es nicht. Es ist "
            "das Produkt zweier unabhaengig geeichter Felder (B_n am "
            "Magnetanker, B_t ueberwiegend am Ankeranker), konvergiert ueber "
            "der Schnittzahl nicht und steht ausserdem im Normierungs"
            "widerspruch zu 1,5*p*psi*i_q (Faktor ~3). Beides in BEFUNDE.md.",
            "Das Gebiet ist quadratisch (Gitterzwang) und wird mit EISEN "
            "gepolstert. Die verbleibende Abhaengigkeit von der Fensterbreite "
            "ist gemessen 1,3 % auf B1 ueber einen Faktor 4; alle Schnitte "
            "benutzen deshalb DIESELBE Breite, damit sie nicht als Sprung in "
            "die Schnittreihe geht.",
        ],
    }


def konvergenz(geom: dict, ks=(3, 5, 9), N: int = 400, rpm: float = 1000.0,
               last_nm: float = 0.0) -> dict:
    """Schnittkonvergenz als ZAHL, nicht als Annahme.

    Wieviele Schnitte es braucht, haengt an lambda: je enger der Ringraum, desto
    weniger aendert sich ueber ihm. Das auszurechnen ist billig (ein FDM-Lauf je
    Schnitt) und es zu behaupten waere die Art Konstante, gegen die
    ``AXIALFLUSS.md`` ausdruecklich gebaut ist.
    """
    reihe = []
    for k in ks:
        f = felder(geom, k_schnitte=k, N=N, rpm=rpm, last_nm=last_nm)
        reihe.append({"k": k, "psi_Wb": f["psi_Wb"], "T_Nm": f["T_maxwell_Nm"],
                      "B_mittel_T": f["B_gap_grundwelle_mittel_T"]})
    letzte = reihe[-1]
    for e in reihe:
        e["psi_abw_pct"] = (abs(e["psi_Wb"] - letzte["psi_Wb"])
                            / max(abs(letzte["psi_Wb"]), 1e-30) * 100.0)
        e["T_abw_pct"] = (abs(e["T_Nm"] - letzte["T_Nm"])
                          / max(abs(letzte["T_Nm"]), 1e-30) * 100.0)
    return {"reihe": reihe, "bezug_k": letzte["k"]}


# ── Bilder ───────────────────────────────────────────────────────────────────

def bilder(geom: dict, ordner: str, k_schnitte: int = 5, N: int = 360,
           rpm: float = 1000.0, last_nm: float = 0.0,
           r_bild_m: float | None = None) -> list:
    """Zwei Bilder nach ``<ordner>`` -- Schnitt und ``B_gap(r)``.

    Sie liegen in ``charts/``, weil die rechte Spalte **beider** Agentenkoepfe
    dort ueber die Aenderungszeit nachsieht (``ema_agent.bilder_im_projekt``) --
    kein zweiter Meldeweg, dieselbe Entscheidung wie bei ``ema_feldbild``.

    ``B_gap(r)`` ist die Kurve, die es radial nicht gibt: dort ist sie eine
    Konstante, axial entscheidet sie die Auslegung. Und in BEIDEN Bildern steht,
    dass sie aus einem Mehrschnitt kommen und nicht aus einer 3-D-Loesung -- ein
    Bild, das wie ein Feldbild aussieht und keines ist, waere die schlimmste
    Variante (dieselbe Regel wie bei den Saettigungsbildern).
    """
    import os

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import ema_axial

    os.makedirs(ordner, exist_ok=True)
    a = ema_axial.auslegung(geom)
    r_b = r_bild_m or 0.5 * (a["r_innen_m"] + a["r_aussen_m"])
    raus = []

    iq = id_ = 0.0
    if last_nm > 0:
        try:
            iq, id_ = EA.estimate_dq_currents(
                geom, rpm, last_nm, b_gap_t=eichung_magnet(geom))
        except Exception:                                            # noqa: BLE001
            iq = id_ = 0.0

    # ── 1. der abgewickelte Schnitt ──────────────────────────────────────────
    sch = rastere_scheibe(geom, r_b, N, iq, id_)
    lbl = EA._material_labels(sch["mu"])
    A = EA._solve_fdm(sch["mu"], sch["j_magnet"] + sch["j_anker"], cache=True)
    bx, by = EA._curl_a(A, lbl)
    bmag = np.hypot(bx, by)
    ex = [0.0, sch["seite_mm"], 0.0, sch["seite_mm"]]

    fig, ax = plt.subplots(figsize=(7.2, 7.2), dpi=130)
    ax.imshow(bmag / max(bmag.max(), 1e-30), origin="lower", extent=ex,
              cmap="magma", vmin=0.0, vmax=1.0, interpolation="bilinear")
    ax.contour(np.linspace(0, sch["seite_mm"], N),
               np.linspace(0, sch["seite_mm"], N), A,
               levels=26, colors="#7fd4ff", linewidths=0.6, alpha=0.85)
    for lg in sch["lagen"]:
        ax.axhline(lg["y0"], color="#39506b", lw=0.6, ls=":")
        ax.text(0.4, (lg["y0"] + lg["y1"]) / 2.0, lg["art"], color="#cfe8ff",
                fontsize=6.5, va="center")
    ax.axhline(sch["lagen"][-1]["y1"], color="#39506b", lw=0.6, ls=":")
    ax.set_xlabel("Umfang abgewickelt [mm]")
    ax.set_ylabel("axial [mm]")
    ax.set_title(f"Axialfluss, abgewickelter Schnitt bei r = {r_b*1000:.1f} mm\n"
                 f"{sch['bauform']}, {sch['n_polteilungen']} Polteilungen, "
                 f"{'Last' if (abs(iq)+abs(id_)) > 0.1 else 'Leerlauf'}",
                 fontsize=9)
    ax.text(0.01, -0.105, "Mehrschnitt (ema_axial_fdm) — KEINE 3-D-Loesung; "
            "radiale Streuung an Ri/Ro nicht enthalten, Eisen linear.",
            transform=ax.transAxes, fontsize=6.5, color="#888")
    f1 = os.path.join(ordner, "feld_axial_schnitt.png")
    fig.savefig(f1, bbox_inches="tight", transparent=True)
    plt.close(fig)
    raus.append(f1)

    # ── 2. B_gap ueber dem Radius ────────────────────────────────────────────
    f = felder(geom, k_schnitte=k_schnitte, N=N, rpm=rpm, last_nm=last_nm)
    rr = [r * 1000.0 for r in f["radien_m"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=130)
    ax.plot(rr, f["B_gap_ueber_r_T"], "o-", color="#e8a33d", lw=1.6,
            label="Grundwelle, geloest (Mehrschnitt)")
    ax.axhline(eichung_magnet(geom), color="#7fd4ff", ls="--", lw=1.2,
               label="analytisch (Stufe 1), konstant")
    ax.axvspan(a["r_innen_m"] * 1000, a["r_aussen_m"] * 1000, color="#2b3a4a",
               alpha=0.25, zorder=0)
    ax.set_xlabel("Radius [mm]")
    ax.set_ylabel("$B_{gap}$ Grundwelle [T]")
    ax.set_title(f"Luftspaltfeld ueber dem Ringraum — die Kurve, die es radial "
                 f"nicht gibt\nlambda = {a['lambda']:.4f}, "
                 f"Spalt/Polteilung aendert sich um "
                 f"{a['spaltverhaeltnis_spanne']:.2f}x", fontsize=9)
    ax.legend(fontsize=7.5)
    ax.grid(alpha=0.25)
    # **Der Warnsatz gehoert INS Bild.** Beim ersten Gesamtdurchlauf zeigte diese
    # Kurve eine Delle von 20 % mitten im Ringraum, und sie liest sich wie ein
    # Befund ueber die Maschine. Sie ist keiner: dieselben Radien bei anderer
    # Aufloesung gerechnet wandert sie mit N, und B1 oszilliert ueber
    # N = 320...1280 zwischen 0,874 und 0,973 T, weil der 1-mm-Spalt und der
    # 6-mm-Magnet auf das Gitter schnappen (BEFUNDE.md, 05.10.2026). Ein Bild,
    # das wie ein Messergebnis aussieht und keines ist, ist die schlimmste
    # Variante -- dieselbe Regel wie bei den Saettigungsbildern.
    ax.text(0.0, -0.30,
            "⚠ Die AMPLITUDE ist nicht konvergiert: B1 oszilliert ueber "
            "N = 320…1280 um ±5 % (duenne Schichten schnappen aufs Gitter). "
            "Strukturen in dieser Kurve sind Rasterartefakte, keine Befunde ueber "
            "die Maschine. Belastbar sind Formfaktor, Linearitaet und Carterzahl "
            "— s. BEFUNDE.md, 05.10.2026.",
            transform=ax.transAxes, fontsize=6.4, color="#c98b2e", wrap=True,
            va="top")
    f2 = os.path.join(ordner, "feld_axial_bgap_r.png")
    fig.savefig(f2, bbox_inches="tight", transparent=True)
    plt.close(fig)
    raus.append(f2)
    return raus


def uebersicht(geom: dict, k_schnitte: int = 5, N: int = 360,
               rpm: float = 1000.0, last_nm: float = 0.0) -> str:
    f = felder(geom, k_schnitte=k_schnitte, N=N, rpm=rpm, last_nm=last_nm)
    z = [f"Axialfluss-Feldstufe: {f['k_schnitte']} abgewickelte Schnitte, N = {f['N']}",
         f"  Bauform {f['bauform']}, {f['n_spalte']} Luftspalt"
         f"{'e' if f['n_spalte'] != 1 else ''}, Fenster "
         f"{f['fenster_polteilungen']} Polteilungen",
         f"  B_gap Grundwelle ueber r: "
         + "  ".join(f"{b:.4f}" for b in f["B_gap_ueber_r_T"]) + " T",
         f"  Mittel (r-gewichtet)      {f['B_gap_grundwelle_mittel_T']:.4f} T  "
         f"gegen analytisch {eichung_magnet(geom):.4f} T",
         f"  psi                       {f['psi_Wb']:.6f} Wb   "
         f"Kt {f['Kt_Nm_per_A']:.4f} Nm/A",
         f"  T_maxwell                 {f['T_maxwell_Nm']:.2f} Nm"]
    if f["last_nm"] > 0:
        z.append(f"  T aus Kt*i_q              {f['T_aus_Kt_Nm']:.2f} Nm "
                 f"(i_q = {f['i_q_A']:.1f} A)")
        if f["T_verhaeltnis"]:
            z.append(f"  ⚠ {f['widerspruch']}")
    if not f["alle_spalte_aufgeloest"]:
        z.append("  ⚠ nicht jeder Schnitt loest den Luftspalt auf "
                 f"(mindestens {SPALT_PX_MIN:.0f} px) — N erhoehen")
    for g in f["grenzen"]:
        z.append(f"  ℹ {g}")
    return "\n".join(z)
