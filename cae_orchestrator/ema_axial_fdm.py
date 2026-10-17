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

Das Fenster ist **genau ganzzahlig (und geradzahlig) viele Polteilungen** breit.
In x ist es damit **wirklich periodisch**: die linke und die rechte Spalte sind
Nachbarn derselben Maschine, und genau so wird seit dem 16.10.2026 geloest
(``_solve_fdm(..., periodisch_x=True)``, eine Maskenzeile im hauseigenen
Matrixbauer -- kein zweiter Loeser).

**Vorher stand hier Dirichlet ``A = 0`` am Seitenrand** mit der Begruendung,
``A ~ sin(pi*x/tau)`` habe dort Nullen. Das war falsch herum: bei Polgrenze auf
x = 0 ist A dort EXTREM und nicht null -- die Nullen von A liegen in den
Polmitten. ``A = const`` auf einer senkrechten Linie heisst ``B_x = 0``, also
kein Umfangsfluss; erzwungen wurde das ausgerechnet an der Polgrenze, wo der
Umfangsfluss im Joch sein Maximum hat. Gemessen (mit dichtem Rand, s.
``POLSTER_MU_R``): 11,8 % Schwankung der Grundwelle ueber eine Laeuferdrehung
und 7,4 % ueber die Fensterbreite. Mit Periodizitaet bleibt davon die Nutung
uebrig. Solange die Polsterung Eisen war, war der Fehler weich -- der Fluss wich
ins Polstereisen aus; beides gehoerte deshalb zusammen repariert
(``BEFUNDE.md``, 16.10.2026).

Zwei Dinge, die der quadratische Gitterzwang erzwingt
-----------------------------------------------------

``_build_fv_matrix`` legt ``cid`` als ``(N, N)`` an und rechnet mit EINER
Maschenweite; das Gebiet muss also quadratisch sein und gleich feiner Teilung in
beiden Richtungen folgen. Daraus folgt zweierlei, und beides ist Modellwahl, die
hier ausgesprochen wird statt stillschweigend zu wirken:

* **Nach oben und unten wird mit einer FLUSS-SPERRE aufgefuellt**, bis das
  Gebiet quadratisch ist (``POLSTER_MU_R``, s. dort) -- weder mit Luft noch mit
  Eisen. Beide waren einmal da, und beide waren messbar falsch:

  *Luft* (erster Entwurf) laesst den Fluss hinausstreuen, und weil mit dem
  Quadrat auch das Luftvolumen waechst, haengt das Ergebnis an der
  FENSTERBREITE -- gemessen bei r = 102,5 mm 0,86410 / 0,84730 / 0,83494 /
  0,82445 T ueber 2 / 4 / 6 / 8 Polteilungen, fallend ohne zu konvergieren.
  Die noetige Fensterbreite springt mit dem Radius, also sprang das Ergebnis
  mitten im Ringraum mit.

  *Eisen* (bis 16.10.2026) hat den Fehler ins Gegenteil verkehrt: der Rueckweg
  lag dann DRAUSSEN. Gemessen liefen bei der gezeichneten Rueckendicke 71,9 %
  des Rueckflusses durch die Polsterung, und das gezeichnete Rueckenblech
  bewegte deshalb **keine einzige Stelle** -- 4 bis 40 mm, Ziffer fuer Ziffer
  dasselbe Ergebnis. Der Satz, der hier stand ("das zusaetzliche Eisen fuehrt
  keinen Fluss"), war genau falsch herum.

  Die *Sperre* sagt aus, was ein Joch TUT: der Rueckfluss schliesst sich im
  gezeichneten Eisen. Damit faellt die Fensterbreite wirklich heraus (gemessen
  0,37 % ueber Faktor 4 statt 7,4 %), und das Rueckenblech wirkt wieder
  (+4,1 % von 4 auf 40 mm an der Vorgabemaschine). **Was der lineare FDM
  weiterhin nicht zeigt, ist die Saettigung**: ein zu duennes Rueckenblech wird
  hier reluktanzwirksam, nicht gesaettigt -- ob es dick genug ist, sagt
  ``ema_axial.ruecken``.

  Dass beides zusammen repariert werden musste, ist der Kern: die Eisen-
  polsterung hat den Fehler der Seitenbedingung (s. oben) WEICH gemacht. Allein
  umgestellt, stieg die Schwankung ueber die Laeuferstellung von 2,0 auf
  11,8 %. Nachgemessen in ``test_axial_fdm.py``.
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

#: **Was ausserhalb des Stapels steht -- eine FLUSS-SPERRE, kein Eisen.**
#:
#: Das Gebiet muss quadratisch sein (``_build_fv_matrix`` legt ``cid`` als
#: ``(N, N)`` an), der Stapel ist aber flach: bei der Vorgabemaschine 65 mm in
#: einem 215-mm-Fenster. Die drei Fuellungen, alle an derselben Maschine
#: gemessen (YASA, r = 102,5 mm, nutlos, rohe Spaltgrundwelle):
#:
#: ========================  ==================  ================
#: Polsterung                Rueckenblech 4->40  Fluss ausserhalb
#: ========================  ==================  ================
#: Eisen (bis 16.10.2026)       **+0,0 %**          **59,1 %**
#: Luft                           +4,0 %               2,3 %
#: Sperre (hier)                  +4,1 %               1,9 %
#: ========================  ==================  ================
#:
#: (N = 400, Vorgabemaschine, MIT der periodischen Seitenbedingung. Ohne sie
#: standen hier +22,5 / +23,2 % -- das war der Randfehler und nicht das
#: Rueckenblech. Die beiden Reparaturen gehoeren zusammen.)
#:
#: **Luft und Sperre liegen jetzt auf 0,1 % zusammen** -- nachdem die
#: Seitenbedingung stimmt, ist die Wahl fast gleichgueltig geworden. Die Sperre
#: bleibt, weil sie die Annahme AUSSPRICHT (der Rueckfluss schliesst sich im
#: gezeichneten Eisen) und den Reststreuweg nach aussen ganz schliesst; dass es
#: nur noch 0,1 % sind, steht hier, damit niemand ihr mehr zuschreibt.
#:
#: Mit EISEN lag der Rueckweg draussen: bei der gezeichneten Dicke liefen 59,1 %
#: des Rueckflusses durch die Polsterung (mit der alten Seitenbedingung 71,9 %,
#: bei 4 mm Ruecken 89,5 %), und das gezeichnete
#: Rueckenblech bewegte deshalb **keine einzige Stelle** -- zehnfache Dicke,
#: Ziffer fuer Ziffer dasselbe Ergebnis. Der Modulkopf behauptete das Gegenteil
#: ("das zusaetzliche Eisen fuehrt keinen Fluss"); siehe ``BEFUNDE.md``,
#: 16.10.2026.
#:
#: Die Sperre sagt stattdessen aus, was ein Joch TUT: der Rueckfluss schliesst
#: sich **im gezeichneten Eisen**, nach aussen tritt nichts. Das ist eine
#: Annahme -- in Wirklichkeit streut ein wenig --, aber eine bezifferte: mit
#: Luft statt Sperre treten 0,7 % aus und B1 aendert sich um 0,06 %.
#:
#: **Der Wert ist ein GRENZFALL und kein gedrehter Knopf.** Gemessen ueber
#: 1e-2 / 1e-3 / 1e-4 / 1e-5 stimmt das Ergebnis auf sieben Stellen ueberein
#: (1,121225 T viermal) -- unterhalb von ~1e-2 ist die Sperre dicht und es
#: passiert nichts mehr. 1e-3 liegt in der Mitte dieses Plateaus, weit weg von
#: der Kante UND weit weg von schlechter Kondition. ``test_axial_fdm.py`` misst
#: genau diese Unempfindlichkeit, damit aus dem Grenzfall nicht unbemerkt eine
#: Stellschraube wird.
POLSTER_MU_R = 1e-3

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
def _widerspruch_text(verhaeltnis: float) -> str:
    """Der Normierungswiderspruch -- mit der GEMESSENEN Zahl, nicht mit einer alten.

    Hier stand eine Konstante, und darin „Faktor ~3, ueber den Strom nahezu
    konstant". Beides war am 16.10.2026 nicht mehr wahr: gemessen 42,9 / 26,2 /
    14,8 / 14,8 ueber 25 / 50 / 100 / 200 Nm. Die Zahl ist seit den
    Feldreparaturen desselben Tages gewandert (die Grundwelle stieg stark), und
    oberhalb von ~100 Nm steht sie nur deshalb still, weil der Strom dann an
    der Umrichtergrenze klemmt -- die Konstanz ist dort ein Anschlag und kein
    Befund.

    Eine Warnung, die eine falsche Zahl nennt, ist schlechter als eine ohne
    Zahl: wer sie liest, glaubt, den Abstand zu kennen. Das Verhaeltnis steht
    ohnehin als ``T_verhaeltnis`` im Ergebnis; es wird jetzt eingesetzt.
    """
    return (f"WIDERSPRUCH im Werkzeug: T_maxwell (geloeste Schubspannung) und "
            f"T_aus_Kt (1,5*p*psi*i_q) liegen um den Faktor {verhaeltnis:.1f} "
            f"auseinander -- ein Normierungsunterschied (psi auf 1 Windung/Nut, "
            f"_analytical_Barm auf N_ph = slots/3; vgl. ema_asm.k_norm). "
            f"Welcher Bezug gilt, entscheidet Stufe 3 und nicht ein "
            f"Korrekturfaktor. Klemmt der Strom an der Umrichtergrenze, steht "
            f"die Zahl still, ohne dass sich etwas geklaert haette.")


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
#: Bildhintergrund -- dieselbe Farbe wie `ema_feldbild.GRUND`, von dort geholt
#: statt danebengeschrieben: zwei Schwarztoene in einem Projektordner faellt
#: beim ersten Nebeneinander auf.
try:
    from ema_feldbild import GRUND
except Exception:                                            # noqa: BLE001
    GRUND = "#0d1014"

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


def lagen(geom: dict) -> list:
    """**Die axiale Schichtung -- die EINE Quelle.** Liste von Lagen, in mm.

    Je Lage ``{art, kenn, z0, z1, d}``: ``art`` aus ``_BAUFORMEN[...]["stapel"]``
    (``ruecken``/``magnet``/``spalt``/``stator``), ``kenn`` das MAGNETVORZEICHEN
    der Lage -- der ganze Unterschied zwischen YASA (NS: beide gleichsinnig, der
    Fluss geht axial durch den Zahn) und TORUS (NN: gegensinnig, der Fluss laeuft
    im Staender umfangs). Wer es verliert, baut die falsche Bauform.

    Sie stand bis zum 07.10.2026 **zweimal**: als Schleife in ``stapelhoehe``
    (die nur die Summe brauchte) und als ``ema_axial_em3d._lagen`` (die die
    Lagen selbst brauchte). Mit dem CAD waere es die dritte Fassung geworden --
    und die Schichtung ist genau die Groesse, bei der eine Abschrift bedeutet,
    dass Netz, Zeichnung und Hoehenangabe drei verschiedene Maschinen meinen
    (gemessen: der erste Entwurf des Elmer-Sektors legte beim YASA zwei
    Zahnbaender uebereinander und kam auf 90 mm, wo Mehrschnitt und Thermik
    65 mm rechnen).

    Lagen der Dicke 0 fallen heraus -- ein jochloser Staender hat kein Joch, und
    eine Lage ohne Dicke ist keine.
    """
    import ema_axial

    a = ema_axial.auslegung(geom)
    bf = _BAUFORMEN[a["bauform"]]
    dicke = {"ruecken": _rueckenhoehe(geom),
             "magnet": a["magnet_dicke_m"] * 1000.0,
             "spalt": a["luftspalt_m"] * 1000.0,
             "stator": statorhoehe(geom)}
    z, aus = 0.0, []
    for art, kenn in bf["stapel"]:
        d = dicke[art]
        if d <= 1e-6:
            continue
        aus.append({"art": art, "kenn": kenn, "z0": z, "z1": z + d, "d": d})
        z += d
    return aus


def stapelhoehe(geom: dict) -> float:
    """Axiale Hoehe des aktiven Stapels in **Millimetern** (ohne Luftpolster)."""
    lg = lagen(geom)
    return float(lg[-1]["z1"]) if lg else 0.0


def zahnlaenge(geom: dict) -> float:
    """Laenge EINES Zahns in Millimetern -- und damit die Tiefe EINER Nut.

    **Zwei Schluessel fuer dieselbe Groesse**, und das ist ein Befund: hier
    stand ``slotDepth`` (die radiale Nuttiefe), waehrend der axiale
    Parametersatz seit dem 06.10.2026 ``axialZahnLaengeMm`` fuehrt. Beide
    haben die Vorgabe 25, sie fielen also nur ZUFAELLIG zusammen. Vorrang hat
    jetzt der axiale Schluessel; ``slotDepth`` bleibt der Rueckfall fuer
    Payloads, die ihn noch nicht tragen.

    **Eigene Funktion seit dem 16.10.2026**, und der Grund ist ein Befund:
    ``rastere_scheibe`` reichte ``statorhoehe`` als Schnitttiefe an ``_nuten``
    weiter -- und ``statorhoehe`` traegt seit dem 06.10.2026 das Joch mit. Die
    Nut schnitt damit durch das Joch hindurch; jede Bauform mit Joch hatte im
    Feldmodell keines (gemessen: torus_nn 0,0 mm von 12,0, afir 0,5 von 12,0,
    einseitig 0,0 von 12,0). Siehe ``BEFUNDE.md``, 16.10.2026.
    """
    g = geom or {}
    return float(g.get("axialZahnLaengeMm") or g.get("slotDepth", 25.0) or 25.0)


def _zahnlagen(bauform: str) -> int:
    """Wieviele ZAHNBAENDER der Staender dieser Bauform traegt: 1 oder 2.

    Abgelesen am ``kenn`` der Staenderlage und nicht danebengeschrieben --
    ``"beide"`` heisst beidseitig genutet (TORUS-NN: Zaehne auf beiden
    Stirnflaechen, Joch dazwischen), alles andere einseitig. ``"durch"`` ist
    der jochlose YASA-Staender: EIN Zahnband ueber die volle Hoehe.
    """
    for art, kenn in _BAUFORMEN[bauform]["stapel"]:
        if art == "stator":
            return 2 if kenn == "beide" else 1
    return 1


def statorhoehe(geom: dict) -> float:
    """Axiale Hoehe des STAENDERS (Zaehne + ggf. Joch), in Millimetern.

    Sie stand inline an zwei Stellen (`stapelhoehe`, `rastere_scheibe`) und
    jetzt an einer -- der 3-D-Sektor braucht genau dieselbe Zahl, sonst
    vernetzt er eine andere Maschine als die, gegen die er gemessen wird.

    **Beidseitig genutet heisst ZWEI Zahnbaender** (16.10.2026): ein TORUS-NN
    traegt Zaehne auf beiden Stirnflaechen und das Joch dazwischen, ist also
    ``2*Zahn + Joch`` hoch. Vorher stand hier ``Zahn + Joch``, und die Nut
    wurde von beiden Seiten ueber die volle Bandhoehe geschnitten -- uebrig
    blieben Zahnsaeulen ohne Joch, und die Luftspalt-Grundwelle brach um
    Faktor 10 ein. Fuer die uebrigen Bauformen aendert sich nichts.
    """
    import ema_axial
    bf = ema_axial.auslegung(geom or {})["bauform"]
    h = _zahnlagen(bf) * zahnlaenge(geom)
    if _BAUFORMEN[bf]["joch"]:
        h += _jochhoehe(geom)
    return h


def _rueckenhoehe(geom: dict) -> float:
    """Rueckenblech [mm] -- das GEZEICHNETE, sonst das gerechnete.

    **Befund vom 06.10.2026.** Hier stand nur ``axialRueckenMm`` als Vorgabe,
    und den Schluessel gibt es im Schema gar nicht; gerechnet wurde deshalb
    immer ``ema_axial.ruecken`` -- die ANFORDERUNG. Der axiale Parametersatz
    fuehrt seit dem 06.10.2026 aber ``axialJochLaeuferMm``, also das, was
    wirklich gezeichnet ist. Gemessen fielen die beiden auseinander: 11,10 mm
    gerechnet gegen 13,00 mm gezeichnet, und damit meldeten Mehrschnitt
    (61,2 mm) und Thermik (65,0 mm) zwei verschiedene Bauhoehen fuer dieselbe
    Maschine.

    Gezeichnet gewinnt -- das Feld soll die gebaute Maschine rechnen. Ob die
    gezeichnete Dicke REICHT, sagt weiterhin ``ema_axial.ruecken``, und das ist
    die richtige Arbeitsteilung: hier die Geometrie, dort das Urteil.
    """
    import ema_axial
    g = geom or {}
    vor = float(g.get("axialJochLaeuferMm", 0) or g.get("axialRueckenMm", 0) or 0.0)
    if vor > 0:
        return vor
    try:
        return ema_axial.ruecken(geom, eichung_magnet(geom))["t_soll_m"] * 1000.0
    except Exception:                                                # noqa: BLE001
        return 12.0


def _jochhoehe(geom: dict) -> float:
    """Staenderjoch [mm], wo die Bauform eines braucht (NN, AFIR, einseitig).

    Bemessen wie das Rueckenblech: es fuehrt die Haelfte des Polflusses umfangs
    -- und wie dort gewinnt das GEZEICHNETE (``axialJochStaenderMm``), wo es
    gesetzt ist.
    """
    import ema_axial
    _vor = float((geom or {}).get("axialJochStaenderMm", 0) or 0.0)
    if _vor > 0:
        return _vor
    a = ema_axial.auslegung(geom)
    ro, ri = a["r_aussen_m"], a["r_innen_m"]
    # ``eichung_magnet`` TRAEGT die Polbedeckung schon (es ist der
    # Flussmittelwert). Sie hier noch einmal zu multiplizieren rechnete das Joch
    # auf alpha^2 = 0,72 des Flusses, den es fuehren muss -- also 28 % zu duenn;
    # ein zu duennes Staenderjoch saettigt (s. ``BEFUNDE.md``, 06.10.2026).
    phi = (eichung_magnet(geom)
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

    Gemessen in ``axialfluss_scheibenprobe.py``: Permeanz 0,8325 -> 0,9573 T.

    **Diese Zahl ist ein MITTELWERT, keine Spitze und keine Grundwelle** -- das
    ``alpha_i`` am Ende ist die Polbedeckung, also der Flussmittelwert ueber die
    Polteilung. Sie heisst nur historisch ``eichung_magnet``; wer eine Spitze
    oder eine Grundwelle braucht, nimmt ``eichung_magnet_spitze`` bzw.
    ``eichung_magnet_grundwelle``. Die drei liegen um Faktor 1,00 : 1,18 : 1,46
    auseinander, und sie zu verwechseln war der Fund vom 06.10.2026: ``schnitt``
    pinnte die geloeste SPITZE auf diesen MITTELWERT und meldete die
    Luftspaltgrundwelle dadurch um 45 % zu klein (s. ``BEFUNDE.md``).

    Verwendet wird sie dort, wo wirklich ein Fluss gemeint ist -- Rueckenblech
    und Staenderjoch --, und als die zu ``psi = p*(2/pi)*B*A`` passende
    Amplitude.
    """
    return float(np.clip(eichung_magnet_spitze(geom) * _polbedeckung(geom),
                         0.01, 2.0))


def _polbedeckung(geom: dict) -> float:
    import ema_axial
    return float(ema_axial.auslegung(geom)["polbedeckung"])


def eichung_magnet_spitze(geom: dict) -> float:
    """Die SPITZE der Arbeitsgeraden [T]: ``Br * hm/(hm + mu_r*kc*g)``.

    Der Flachdachwert unter dem Magneten, **ohne** Polbedeckung -- und damit der
    einzige der drei Anker, den Modell und Loeser gleich definieren: beide
    meinen dieselbe Stelle, die Mitte eines Magneten. Deshalb eicht ``schnitt``
    hieran und nicht an einem Mittelwert (s. ``BEFUNDE.md``, 06.10.2026).
    """
    import ema_axial
    a = ema_axial.auslegung(geom)
    hm = a["magnet_dicke_m"] * 1000.0
    g = a["luftspalt_m"] * 1000.0
    perm = hm / (hm + EA.MU_R_MAG * KC * g)
    return float(np.clip(EA.Br_NdFeB * perm, 0.01, 2.0))


def eichung_magnet_grundwelle(geom: dict) -> float:
    """Die GRUNDWELLE der Arbeitsgeraden [T]: ``4/pi * Spitze * sin(alpha*pi/2)``.

    Die Fourier-Grundwelle der Rechteckwelle, die ein flach liegender Magnet
    ueber die Polbedeckung ``alpha`` erzeugt. Sie ist GROESSER als die Spitze
    (Faktor 1,24 bei alpha = 0,85) -- wer sie mit dem Mittelwert verwechselt,
    liegt um 1,46 daneben, und genau das war der Fund vom 06.10.2026.

    Nachgemessen am nutlosen Schnitt: der Loeser trifft sie auf **1,0 %**.
    """
    al = _polbedeckung(geom)
    return float(4.0 / math.pi * eichung_magnet_spitze(geom)
                 * math.sin(al * math.pi / 2.0))


def formfaktor_grundwelle(geom: dict) -> float:
    """Grundwellenamplitude / Flussmittelwert der Polwelle: ``(4/pi)*sin(a*pi/2)/a``.

    **Wofuer es den Faktor gibt.** Die Flussverkettung dieses Werkzeugs steht in
    der Form ``psi = p*(2/pi)*B*A_fluss`` (``ema_analysis.compute_performance``,
    ``betriebspunkt``). Der Term ``(2/pi)`` ist der Mittelwert einer halben
    Sinuswelle ueber ihre AMPLITUDE -- er setzt also voraus, dass ``B`` eine
    **Grundwellenamplitude** ist. Eingesetzt wurde axial ``eichung_magnet``, und
    das ist ausdruecklich der **Flussmittelwert** (``Spitze * alpha``). Damit
    stand dort ``(2/pi) * Mittelwert``, und das ist weder der Gesamtfluss je Pol
    noch der Grundwellenfluss -- s. ``BEFUNDE.md``, 16.10.2026.

    Der Faktor ist reine Fourier-Arithmetik und keine Modellwahl: fuer die
    Rechteckwelle der Breite ``alpha*tau_p`` ist die Grundwellenamplitude
    ``(4/pi)*Spitze*sin(alpha*pi/2)`` und der Mittelwert ``Spitze*alpha``.

    **Er wird MULTIPLIZIERT und ersetzt nichts.** So wirkt er auch auf ein
    gemessenes ``B`` -- er ist eine Formeigenschaft der Polwelle, keine
    Eichgroesse. Bei ``alpha = 1`` sind es ``4/pi = 1,2732``, bei
    ``alpha = 0,85`` **1,4565**.
    """
    al = max(1e-6, min(1.0, _polbedeckung(geom)))
    return float(4.0 / math.pi * math.sin(al * math.pi / 2.0) / al)


def eichung_anker(geom: dict, i_pk: float) -> float:
    """Analytisches Ankerfeld [T] -- ueber ``ema_analysis._analytical_Barm``.

    Die Formel braucht Wicklung und Spalt, aber **keinen Radius**: sie gilt
    unveraendert, seit ``luftspalt_mm`` einen axialen Zweig hat. Hier wird sie
    deshalb nur weitergereicht, statt eine zweite daneben zu stellen -- das waere
    genau die Stelle, an der die Eichung der beiden Flusswege auseinanderlaeuft.
    """
    return EA._analytical_Barm(geom, i_pk)


def betriebspunkt(geom: dict, rpm: float, last_nm: float,
                  axial_mm: float | None = None) -> dict:
    """i_q und i_d der Scheibenmaschine -- OHNE den Laeufer, den sie nicht hat.

    Hier stand ``ema_analysis.estimate_dq_currents``, und das war falsch. Die
    Funktion rechnet MTPA ueber ``estimate_saliency(geom)``, die ihrerseits auf
    ``magnet_legs`` steht -- und der Payload traegt dort weiterhin die
    Schemavorgabe ``magShape = "v"``. Gemessen am 05.10.2026: zwei V-Schenkel je
    Pol mit tilt +-60 Grad, Salienz **2,589**, daraus ``i_d = -9,9 A``. Der
    Betriebspunkt der axialen Feldstufe kam damit aus einem IPM-Laeufer, den
    eine Scheibe nicht hat; ueber das Ankerfeld ging er in das Moment ein.
    Gemeldet als „deine maschine sieht aus wie eine psm mit magneten in
    v-anordnung".

    Was statt dessen gilt, ist der einfachste Fall, den es gibt: die
    Axialfluss-PM-Maschine traegt **Oberflaechenmagnete flach auf der Scheibe**
    -- keine Tasche, kein Steg, keine Vorzugsrichtung im Blech. Damit ist
    ``Ld = Lq``, es gibt **kein Reluktanzmoment**, und MTPA ist ``i_d = 0``.
    Das ist keine Vereinfachung, sondern die Bauart (vgl. HAW Hamburg: Rotoren
    mit Permanentmagneten, Halbacharrays, kernlose Luftspulenwicklungen).

    ``Kt`` kommt aus ``ema_fluss.flaechen`` -- derselben Quelle wie psi und das
    Dauermoment --, nicht aus ``compute_performance``, die ueber
    ``_analytical_Bgap`` wieder am Radiallaeufer haengt.

    Wo eine Scheibenmaschine **doch** salient ist -- ein vergrabener
    Scheibenmagnet, ein Reluktanzlaeufer --, ist das hier NICHT gerechnet und
    steht als Grenze im Ergebnis, statt mit einer fremden Salienz gefuellt zu
    werden.
    """
    import ema_fluss

    f = ema_fluss.flaechen(geom, axial_mm)
    a_fluss = f["a_fluss_m2"]
    p = max(1, int((geom or {}).get("p", 3) or 3))
    b_gap = eichung_magnet(geom)
    # **Die Groesse im (2/pi)-Term ist eine GRUNDWELLENAMPLITUDE.** Hier stand
    # `b_gap` -- der Flussmittelwert aus `eichung_magnet` --, und damit war
    # dieses psi weder der Gesamtfluss je Pol noch der Grundwellenfluss.
    # Gemessen am Vorgabe-Payload (alpha = 0,85, mittlerer Schnitt): direkt
    # integriert 81,27 mWb/m, Grundwellenfluss 75,00, gerechnet wurden 51,74 --
    # also genau 2/pi des Gesamtflusses. Der eigene Loeser desselben Moduls
    # (`felder`) rechnet psi seit jeher aus `b_n_grundwelle_T`: die beiden
    # Stufen gaben damit zwei verschiedene Kt fuer dieselbe Maschine.
    # Siehe `BEFUNDE.md`, 16.10.2026.
    b1 = b_gap * formfaktor_grundwelle(geom)
    psi = p * (2.0 / math.pi) * b1 * a_fluss
    kt = max(1.5 * p * psi, 1e-9)
    i_lim = float(EA.umrichter(geom).get("i_max_1t", 800.0))
    i_q = max(min(float(last_nm) / kt, i_lim), 0.0)
    return {
        "i_q_A": i_q, "i_d_A": 0.0,
        "Kt_Nm_per_A": kt, "psi_Wb": psi, "B_gap_T": b_gap, "B1_T": b1,
        "formfaktor_grundwelle": formfaktor_grundwelle(geom),
        "i_grenze_A": i_lim, "am_anschlag": i_q >= i_lim - 1e-9,
        "salienz": 1.0,
        "hinweis": ("Oberflaechenmagnete flach auf der Scheibe: Ld = Lq, kein "
                    "Reluktanzmoment, MTPA ist i_d = 0. Ein vergrabener "
                    "Scheibenmagnet oder ein Reluktanzlaeufer WAERE salient und "
                    "ist hier nicht gerechnet."),
    }


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
    # Die Bandhoehe kommt aus ``statorhoehe`` (der EINEN Quelle, aus der auch
    # ``lagen``/CAD/3-D lesen); die Nut schneidet dagegen nur EINEN Zahn tief.
    # Dass das zwei verschiedene Zahlen sind, ist der Befund vom 16.10.2026.
    t_zahn = zahnlaenge(geom)
    t_ruecken = _rueckenhoehe(geom)

    lagen, y = [], y0
    for art, kenn in bf["stapel"]:
        d = {"ruecken": t_ruecken, "magnet": t_mag, "spalt": t_spalt,
             "stator": statorhoehe(geom)}[art]
        lagen.append({"art": art, "kenn": kenn, "y0": y, "y1": y + d})
        y += d

    Y, X = np.meshgrid(np.arange(N) / sc, np.arange(N) / sc, indexing="ij")

    # Die Polsterung ist eine FLUSS-SPERRE (s. ``POLSTER_MU_R``): sie laesst den
    # Rueckfluss im gezeichneten Eisen und nicht daneben. Bis zum 16.10.2026
    # stand hier ``EA.MU_R_IRON``, und dann lief der groessere Teil des
    # Rueckflusses durch die Polsterung statt durch das Rueckenblech.
    mu = np.full((N, N), POLSTER_MU_R)
    mu[(Y >= lagen[0]["y0"]) & (Y < lagen[-1]["y1"])] = 1.0
    My = np.zeros((N, N))
    j_ank = np.zeros((N, N))
    swr = min(0.8, max(0.2, float((geom or {}).get("slotWidthRatio", 0.5) or 0.5)))
    amp = EA.Br_NdFeB / (MU0 * EA.MU_R_MAG)
    # **Der LAEUFER dreht sich mit ``rotor_winkel``.**
    #
    # Bis zum 06.10.2026 tat er das nicht: der Parameter erreichte nur die
    # Staenderstroeme in ``_nuten`` (``el - rotor_winkel*p_pairs``), waehrend
    # die Magnete an ``X % tau_p`` klebten. Gemessen stand der Schwerpunkt von
    # ``j_magnet`` ueber eine ganze elektrische Periode auf **40,170 mm** --
    # jeder Winkel gab dasselbe Raster. Aufgefallen ist es erst an einer
    # Bildreihe: zwei Frames 180 Grad elektrisch auseinander sahen gleich aus.
    #
    # Beides zusammen ist die richtige Drehung: Laeufer UND Stromwelle wandern,
    # der Lastwinkel bleibt stehen -- genau wie im radialen Rasterer, wo
    # ``_rasterise`` die Pole mit ``rotor_angle`` dreht und ``_nuten``s
    # Gegenstueck den Strom nachzieht.
    x_rot = X - rotor_winkel * r_m * 1000.0                # mm, mitgedreht
    pol = np.floor(x_rot / tau_p).astype(int) % 2
    vz = np.where(pol == 0, 1.0, -1.0)

    for lg in lagen:
        band = (Y >= lg["y0"]) & (Y < lg["y1"])
        if lg["art"] == "ruecken":
            mu[band] = EA.MU_R_IRON
        elif lg["art"] == "magnet":
            mu[band] = EA.MU_R_MAG
            # Polbedeckung < 1: der Magnet fuellt die Polteilung nicht ganz aus.
            mitte = (x_rot % tau_p) / tau_p
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
                _nuten(mu, j_ank, band, X, Y, lg, tau_s, swr, t_zahn, seite,
                       r_m, iq, id_, rotor_winkel, N, a)

    # J = curl M = dMy/dx  (Mx = 0) -- derselbe Ansatz wie im radialen Rasterer,
    # aber **umlaufend**: das Fenster ist in x periodisch (s. Modulkopf), die
    # erste und die letzte Spalte sind Nachbarn.
    #
    # Mit ``j_mag[:, 1:-1] = (My[:, 2:] - My[:, :-2])/2`` blieben die beiden
    # Randspalten auf null -- und genau dorthin faellt der Polwechsel, wenn der
    # Laeufer gerade so steht (Laeuferwinkel 0 ist der Normalfall: jedes
    # Standbild, jeder erste Frame). Der halbe Ersatz-Flaechenstrom fehlte
    # dann, gemessen B1 0,6102 statt 1,1356 T -- ein Einbruch um 46 %, der NUR
    # bei dieser einen Stellung auftrat und sich damit wie Physik las.
    j_mag = (np.roll(My, -1, axis=1) - np.roll(My, 1, axis=1)) / 2.0
    return {"mu": mu, "j_magnet": j_mag, "j_anker": j_ank, "lagen": lagen,
            "sc": sc, "seite_mm": seite, "n_polteilungen": n_pol,
            "tau_p_mm": tau_p, "tau_s_mm": tau_s,
            "spalt_px": t_spalt * sc, "N": N, "r_m": r_m,
            "bauform": a["bauform"], "n_spalte": a["n_spalte"]}


def _nuten(mu, j_ank, band, X, Y, lg, tau_s, swr, t_zahn, seite_mm,
           r_m, iq, id_, rotor_winkel, N, a):
    """Nuten als Luft, dazu der dreiphasige Nutstrom.

    ``t_zahn`` ist die Laenge EINES Zahns, also die Tiefe EINER Nut -- NICHT
    die Hoehe des Staenderbandes. Der Unterschied ist das Joch, und wer hier
    die Bandhoehe uebergibt, schneidet es weg (``BEFUNDE.md``, 16.10.2026).

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
            tiefe |= (Y >= lg["y1"] - t_zahn)
        if von_unten:
            tiefe |= (Y <= lg["y0"] + t_zahn)
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
            nuten: bool = True, n_pol: int | None = None,
            bilddaten: bool = False) -> dict:
    """EINE Scheibe: rastern, mit dem HAUS-Loeser loesen, getrennt eichen.

    Zwei Loesungen auf DEMSELBEN ``mu`` -- Magnet und Anker --, also eine
    Faktorisierung und eine Ruecksubstitution: der LU-Cache des Hauses greift
    hier genauso wie radial, weil er nach ``(N, hash(mu))`` schluesselt und
    ``mu`` nicht am Strom haengt.

    ``bilddaten=True`` gibt zusaetzlich die GEEICHTEN Flaechen ``A``/``bx``/
    ``by`` heraus -- dieselbe Summe, aus der die Kennwerte entstehen, nur nicht
    auf die Spaltlinie reduziert. Sie ist die eine Quelle fuer jedes Bild
    dieses Moduls (``schnitt_figur``, ``frames``); ohne sie rechnete jedes
    Bild seine eigene Loesung, und genau dabei ist die Eichung verloren
    gegangen (s. ``BEFUNDE.md``, 17.10.2026). Opt-in, weil ``felder`` den
    Schnitt k-mal aufsammelt und drei ``(N, N)``-Felder je Schnitt in
    ``results.json`` landen wuerden.
    """
    sch = rastere_scheibe(geom, r_m, N, iq, id_, rotor_winkel, nuten, n_pol)
    lbl = EA._material_labels(sch["mu"])

    a_mag = EA._solve_fdm(sch["mu"], sch["j_magnet"], cache=True, periodisch_x=True)
    bx_m, by_m = EA._curl_a(a_mag, lbl)
    jy, _ = _spaltlinie(sch)
    pk_m = float(np.abs(by_m[jy, :]).max())

    # Geeicht wird an der SPITZE DES NUTLOSEN Laufs gegen die Spitze der
    # Arbeitsgeraden -- die eine Stelle, die Modell und Loeser gleich
    # definieren. Die genutete Spitze taugt dafuer NICHT: ueber einem Zahn ist
    # der Fluss gebuendelt, sie steigt um gemessene 23 %, waehrend der Fluss je
    # Pol faellt (derselbe Befund, aus dem ``carter`` an der Grundwelle und
    # nicht an der Spitze rechnet). Der Nutungsverlust wird damit GEMESSEN
    # statt aus ``KC`` angenommen. Kosten: ein zweiter Loeserlauf je Schnitt.
    b_an = eichung_magnet_spitze(geom)
    if nuten:
        _o = rastere_scheibe(geom, r_m, N, 0.0, 0.0, rotor_winkel, False, n_pol)
        _ao = EA._solve_fdm(_o["mu"], _o["j_magnet"], cache=True, periodisch_x=True)
        _, _byo = EA._curl_a(_ao, EA._material_labels(_o["mu"]))
        _jo, _ = _spaltlinie(_o)
        pk_ref = float(np.abs(_byo[_jo, :]).max())
    else:
        pk_ref = pk_m
    sf_m = b_an / max(pk_ref, 1e-30)

    i_pk = math.hypot(iq, id_)
    if i_pk > 1e-6:
        a_ank = EA._solve_fdm(sch["mu"], sch["j_anker"], cache=True, periodisch_x=True)
        bx_a, by_a = EA._curl_a(a_ank, lbl)
        pk_a = float(np.abs(by_a[jy, :]).max())
        # ``eichung_anker`` ist eine GRUNDWELLENamplitude
        # (``_analytical_Barm``: "peak fundamental MMF"), also wird die
        # Grundwelle darauf gepinnt und nicht die Spitze.
        _ba = np.fft.rfft(by_a[jy, :]) / len(by_a[jy, :])
        _h1a = sch["n_polteilungen"] // 2
        h1_a = float(2 * abs(_ba[_h1a]))
        sf_a = eichung_anker(geom, i_pk) / max(h1_a, 1e-30)
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
        "eichung_art": "spitze_nutlos",
        "b_an_magnet_grundwelle_T": eichung_magnet_grundwelle(geom),
        "spitze_roh_genutet": pk_m, "spitze_roh_nutlos": pk_ref,
        "b_an_anker_T": eichung_anker(geom, i_pk) if i_pk > 1e-6 else 0.0,
        "nuten": nuten,
        "bn": bn, "bt": bt, "raster": sch,
        # **Die geeichte Summe, nicht die rohe.** Die beiden Anteile brauchen
        # Eichfaktoren, die um Faktor ~1340 auseinanderliegen (gemessen
        # 1,19e-6 gegen 1,60e-3); roh addiert traegt der Anker ein
        # Tausendstel seines Gewichts, und das Bild zeigt den Leerlauf, auch
        # wenn Volllast darueber steht.
        **({"A": a_mag * sf_m + (a_ank * sf_a if i_pk > 1e-6 else 0.0),
            "bx": bx_m * sf_m + bx_a * sf_a,
            "by": by_m * sf_m + by_a * sf_a} if bilddaten else {}),
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
    bp = {}
    if last_nm > 0:
        try:
            bp = betriebspunkt(geom, rpm, last_nm, axial_mm)
            iq, id_ = bp["i_q_A"], bp["i_d_A"]
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
        "betriebspunkt": bp,
        "last_gerechnet": bool(last_nm <= 0 or (abs(iq) + abs(id_)) > 0.1),
        "psi_Wb": psi, "Kt_Nm_per_A": 1.5 * p * psi,
        "T_maxwell_Nm": t_nm,
        "B_gap_grundwelle_mittel_T": b_mittel,
        "B_gap_ueber_r_T": [s["b_n_grundwelle_T"] for s in schnitte],
        "a_fluss_m2": fl["a_fluss_m2"], "a_moment_m3": fl["a_moment_m3"],
        "T_aus_Kt_Nm": 1.5 * p * psi * iq if iq else 0.0,
        "T_verhaeltnis": (abs(t_nm) / abs(1.5 * p * psi * iq)
                          if iq and abs(psi) > 1e-30 else None),
        "widerspruch": (_widerspruch_text(abs(t_nm) / abs(1.5 * p * psi * iq))
                        if iq and abs(1.5 * p * psi * iq) > 1e-12 else ""),
        "alle_spalte_aufgeloest": all(s["spalt_aufgeloest"] for s in schnitte),
        "fenster_polteilungen": [s["n_polteilungen"] for s in schnitte],
        "schnitte": schnitte,
        "grenzen": [
            "Mehrschnitt: jeder Schnitt rechnet, als setze sich seine Geometrie "
            "radial unendlich fort -- die radiale Streuung an Ri und Ro und die "
            "radialen Stromkomponenten im Wickelkopf fehlen. Nachzumessen an "
            "Stufe 3 (Elmer-Ringsektor), nicht anzunehmen.",
            "Eisen linear (MU_R_IRON), keine Saettigung -- wie im radialen FDM.",
            "Der Betriebspunkt setzt OBERFLAECHENmagnete voraus (Ld = Lq, kein "
            "Reluktanzmoment, i_d = 0). Ein vergrabener Scheibenmagnet oder ein "
            "Reluktanzlaeufer waere salient und ist nicht gerechnet.",
            # Gemessen am 06.10.2026, als beide Feldstufen zum ersten Mal
            # nebeneinander erreichbar waren. Dieser Satz MUSS in die Grenzen,
            # weil der Zahlenwert sonst wie eine Messung aussieht.
            # Diese Zeile hat am 06.10.2026 das Gegenteil behauptet, und die
            # Begruendung war falsch. Sie sagte "B_gap(r) ist ueber N NICHT
            # konvergiert (-12,6 / -9,5 / -6,7 / -9,7 %), Ursache ist das
            # gleichmaessige Gitter". Die Streuung war echt, das Gitter aber
            # nicht ihr Grund: geeicht wurde an der Spitze des GENUTETEN Feldes,
            # und die sitzt auf einer getreppten Zahnkante, deren Lage mit N
            # wandert -- also wanderte der Eichfaktor. Seit die Eichung am
            # nutlosen Lauf haengt, steht die Zahl ueber N = 300/450/700 auf
            # 1,0656 / 1,0655 / 1,0643 T, also 0,1 %. Siehe BEFUNDE.md.
            "B_gap(r) konvergiert ueber N (gemessen 0,1 % ueber N = "
            "300...700). Die -10 % gegen die analytische Grundwelle der "
            "Arbeitsgeraden sind der gemessene NUTUNGSverlust, nicht ein "
            "Netzfehler: `carter` misst an derselben Scheibe 1,096, das sind "
            "-8,8 %. Gegengerechnet gegen die beiden unabhaengigen Wege: der "
            "JS-Mehrschnitt (axialfluss/schnitt.js) kommt auf 1,0819 T, der "
            "Elmer-Ringsektor (ema_axial_em3d) auf ~1,10 T -- drei Loeser "
            "innerhalb von 3 %.",
            "BELASTBAR sind psi und B_gap(r); das MOMENT ist es nicht. Es ist "
            "das Produkt zweier unabhaengig geeichter Felder (B_n am "
            "Magnetanker, B_t ueberwiegend am Ankeranker), konvergiert ueber "
            "der Schnittzahl nicht und steht ausserdem im Normierungs"
            "widerspruch zu 1,5*p*psi*i_q (die gemessene Zahl steht als "
            "T_verhaeltnis im Ergebnis). Beides in BEFUNDE.md.",
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

#: **Die drei Darstellungsarten der Animation -- dieselben Namen wie radial.**
#: ``ema_pipeline`` fuehrt sie seit jeher als ``field_modes``, und die Maske
#: hat dafuer zwei Haekchen. Die Scheibe kannte bis zum 17.10.2026 nur
#: ``rotate``, und die beiden anderen wurden STILL uebersprungen: angehakt,
#: nicht gerechnet, kein Wort darueber. Gemeldet als „auch wird das
#: Feld-Darstellung Ankerrueckwirkung / Last-Rampe nicht gerechnet".
#:
#: Darstellbar sind sie, weil ``rastere_scheibe`` den Strombelag aus ``iq``
#: UND ``id_`` aufbaut (eine Zeile: ``id_*cos(el) - iq*sin(el)``) -- der
#: Stromwinkel ist dort also schon enthalten, es hat ihn nur niemand
#: durchgefahren.
#: Die Beschriftungen tragen Umlaute, obwohl der Rest dieses Moduls
#: umschrieben ist: sie stehen in der Auswahlliste des Ergebnis-Reiters NEBEN
#: den radialen ("Rotor-Rotation", "Stromwinkel (Ankerrueckwirkung)") und im
#: Bildtitel.
ARTEN_BILD = {
    "rotate": "Läuferdrehung",
    "current_angle": "Ankerrückwirkung (Läufer steht, Stromwinkel β)",
    "load_ramp": "Last-Rampe (Läufer steht, Last 0→Volllast)",
}


def _bildpunkte(geom: dict, art: str, n_frames: int, periode: float,
                iq: float, id_: float) -> list:
    """Die Punktliste EINER Darstellungsart: (iq, id_, Winkel, Beschriftung).

    Hier und nicht im Zeichner, damit alle drei Arten dieselbe Loesung,
    dieselbe Eichung und dieselbe festgehaltene Farbskala benutzen. Was sie
    unterscheidet, sind drei Zahlen je Bild -- und nur die stehen hier.
    """
    n = max(2, int(n_frames))
    i_s = math.hypot(iq, id_)
    punkte = []
    if art == "current_angle":
        # beta von 0 (rein momentbildend) bis 90 Grad (rein feldschwaechend),
        # BETRAG konstant: nur so ist das Bild eine Aussage ueber den Winkel
        # und nicht ueber die Stromhoehe.
        for k in range(n):
            b = (math.pi / 2.0) * k / (n - 1)
            punkte.append((i_s * math.cos(b), -i_s * math.sin(b), 0.0,
                           f"Stromwinkel beta {math.degrees(b):.1f}\u00b0",
                           round(math.degrees(b), 1)))
    elif art == "load_ramp":
        for k in range(n):
            fr = k / (n - 1)
            punkte.append((fr * iq, fr * id_, 0.0,
                           f"Last {fr*100:.0f} %", round(fr * 100)))
    else:
        for k in range(n):
            w = periode * k / n
            punkte.append((iq, id_, w,
                           f"Laeuferwinkel {math.degrees(w):.1f}\u00b0 mech",
                           round(math.degrees(w), 1)))
    return punkte


def frames(geom: dict, ordner: str, n_frames: int = 12, N: int = 300,
           rpm: float = 1000.0, last_nm: float = 0.0,
           r_bild_m: float | None = None, melde=None,
           art: str = "rotate") -> dict:
    """Eine Bildreihe der Scheibe -- Laeuferwinkel, Stromwinkel oder Last.

    Der radiale Weg hat das seit jeher (`ema_pipeline` dreht den Laeufer durch
    das FDM-Raster und schreibt `frames/frame_XXXX.png` plus `anim.mp4`); die
    Scheibe hatte es nicht, obwohl `rastere_scheibe` Rotorwinkel UND
    Stromwinkel laengst kennt. Gezeichnet wird EIN abgewickelter Schnitt beim
    mittleren Radius -- nicht alle, denn eine Animation ueber Winkel UND
    Radius waere ein Bild, das zwei Dinge gleichzeitig bewegt und keines davon
    zeigt.

    **Eine elektrische Periode sind zwei Polteilungen**, mechanisch also
    ``2*(2*pi/2p)``. Ueber eine volle mechanische Umdrehung zu laufen hiesse,
    ``p`` mal dasselbe zu zeichnen. Bei den beiden Stillstandsarten steht der
    Laeufer, dort faehrt statt dessen der Strom.

    **Gezeichnet wird die GEEICHTE Loesung** (`schnitt(..., bilddaten=True)`),
    und das ist seit dem 17.10.2026 der eigentliche Unterschied: hier stand
    ein eigener Loeserlauf auf ``j_magnet + j_anker``, also die ROHE Summe.
    Die beiden Anteile brauchen aber Eichfaktoren, die um Faktor ~1340
    auseinanderliegen (gemessen 1,19e-6 gegen 1,60e-3) -- derselbe Befund, aus
    dem `run_em_analysis` radial getrennt eicht. Roh addiert trug der Anker
    ein Tausendstel seines Gewichts: das Bild bewegte sich von Leerlauf auf
    Volllast um **0,006 %**, war also ein Leerlaufbild mit „Last" darueber,
    und eine Last-Rampe darauf waere eine Reihe gleicher Bilder gewesen.
    Richtig geeicht steigt die Spaltspitze 1,384 -> 2,486 T (+80 %).

    **Es kostet Faktor 2,0** (gemessen 166 -> 331 ms je Bild bei N = 200,
    507 -> 1007 ms bei N = 300, ohne das Zeichnen): die Eichung braucht den
    NUTLOSEN Begleitlauf, und dessen ``mu`` ist ein anderes -- dort hilft der
    LU-Cache nicht, waehrend der Ankerlauf sich die Faktorisierung des
    Magnetlaufs teilt.

    Die Farbskala wird am ERSTEN Bild festgehalten und fuer alle weiteren
    behalten. Ohne das setzt jedes Bild seine eigene Skala, und dann sieht ein
    Feld, das sich nicht aendert, nach einem aus, das pulsiert -- derselbe
    Grund, aus dem der 3-D-Betrachter ein „Skala fixieren" hat. Bei der
    Last-Rampe ist das doppelt wichtig: ihr erstes Bild IST der Leerlauf.
    """
    import os

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import ema_axial

    os.makedirs(ordner, exist_ok=True)
    a = ema_axial.auslegung(geom)
    r_b = r_bild_m or 0.5 * (a["r_innen_m"] + a["r_aussen_m"])
    p_paare = max(1, int(a["poles"]) // 2)
    periode = 2.0 * (2.0 * math.pi / max(int(a["poles"]), 2))
    art = art if art in ARTEN_BILD else "rotate"

    iq = id_ = 0.0
    if last_nm > 0:
        try:
            _bp = betriebspunkt(geom, rpm, last_nm)
            iq, id_ = _bp["i_q_A"], _bp["i_d_A"]
        except Exception:                                            # noqa: BLE001
            iq = id_ = 0.0
    # **Die beiden Stillstandsarten ohne Strom sind keine Bildreihe.** Ohne
    # Last ist der Stromwinkel an einem Strom von 0 A gemessen und die Rampe
    # faehrt von 0 auf 0 -- n gleiche Bilder. Das wird GESAGT, nicht
    # stillschweigend gezeichnet.
    if art in ("current_angle", "load_ramp") and (abs(iq) + abs(id_)) < 0.1:
        return {"ordner": ordner, "dateien": [], "n": 0, "video": "",
                "r_bild_m": r_b, "art": art, "periode_grad": 0.0,
                "grund": (f"{ARTEN_BILD[art]}: ohne Last gibt es keinen "
                          f"Statorstrom, den man durchfahren koennte "
                          f"(last_nm = {last_nm:g} Nm, i_q = {iq:.1f} A). "
                          f"Die Reihe waere {max(2, int(n_frames))} gleiche "
                          f"Bilder.")}

    punkte = _bildpunkte(geom, art, n_frames, periode, iq, id_)
    dateien, deckel, werte = [], None, []
    for k, (f_iq, f_id, w, lbl_txt, wert) in enumerate(punkte):
        sn = schnitt(geom, r_b, N, f_iq, f_id, rotor_winkel=w, bilddaten=True)
        sch = sn["raster"]
        A, bmag = sn["A"], np.hypot(sn["bx"], sn["by"])
        if deckel is None:
            deckel = float(np.percentile(bmag, 99.0)) or 1.0
        ex = [0.0, sch["seite_mm"], 0.0, sch["seite_mm"]]
        fig, ax = plt.subplots(figsize=(7.2, 7.2), dpi=110)
        ax.imshow(np.clip(bmag / deckel, 0, 1), origin="lower", extent=ex,
                  cmap="magma", vmin=0.0, vmax=1.0, interpolation="bilinear")
        ax.contour(np.linspace(0, sch["seite_mm"], sch["N"]),
                   np.linspace(0, sch["seite_mm"], sch["N"]), A, 26,
                   colors="#8fe3ff", linewidths=0.5, alpha=0.75)
        for lg in sch["lagen"]:
            ax.axhline(lg["y0"], color="#39506b", lw=0.6, ls=":")
        ax.set_xlabel("Umfang abgewickelt [mm]")
        ax.set_ylabel("axial [mm]")
        _zus = (f" ({math.degrees(w)*p_paare:.0f}\u00b0 el)"
                if art == "rotate" else
                f" bei {math.hypot(f_iq, f_id):.0f} A")
        ax.set_title(f"Axialfluss, abgewickelt bei r = {r_b*1000:.1f} mm \u2014 "
                     f"{lbl_txt}{_zus}")
        ax.text(0.01, -0.105, f"{ARTEN_BILD[art]} \u00b7 Mehrschnitt "
                f"(ema_axial_fdm) \u2014 KEINE 3-D-Loesung; getrennt geeichtes "
                f"Magnet- und Ankerfeld, Skala am ersten Bild festgehalten",
                transform=ax.transAxes, fontsize=6.5, color="#888")
        f = os.path.join(ordner, f"frame_{k:04d}.png")
        fig.savefig(f, bbox_inches="tight", facecolor="#0d1014")
        plt.close(fig)
        dateien.append(f)
        werte.append(wert)
        if melde:
            melde(k + 1, len(punkte))

    video = ""
    try:
        import ema_em3d
        if ema_em3d._encode_video(ordner):
            video = os.path.join(ordner, "anim.mp4")
    except Exception:                                                # noqa: BLE001
        video = ""
    return {"ordner": ordner, "dateien": dateien, "n": len(dateien),
            "video": video, "r_bild_m": r_b, "deckel_T_roh": deckel,
            "art": art, "werte": werte, "i_q_A": iq, "i_d_A": id_,
            "periode_grad": math.degrees(periode) if art == "rotate" else 0.0}


def schnitt_figur(geom: dict, r_b_m: float, N: int = 360,
                  iq: float = 0.0, id_: float = 0.0):
    """Der abgewickelte Schnitt als matplotlib-Figur — |B| und die FELDLINIEN.

    Herausgeloest aus ``bilder``, weil ausser dem Lauf auch die **Einzelbild-
    Vorschau** (`/preview_field`) ihn braucht. Die zeichnete bis zum 11.10.2026
    fuer eine Scheibe den radialen Querschnitt samt RADIALER Magnete -- ein Bild
    der falschen Maschine, und zwar an der Stelle, an der man schnell nachsieht,
    ob die Geometrie stimmt. Eine zweite Zeichenfassung dafuer waere die
    naechste `magnetLegs`-Drift; also gibt es diese eine.

    Die Hoehenlinien von A SIND hier die Feldlinien: der Schnitt loest
    ``B = rot(A e_r)`` in dieser Ebene (dieselbe Begruendung wie in
    ``axialfluss/live.js``).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # **Dieselbe geeichte Loesung wie die Kennwerte** (`bilddaten=True`).
    # Hier stand ein eigener Lauf auf der ROHEN Summe `j_magnet + j_anker`;
    # der Ankeranteil braucht aber einen ~1340-fachen Eichfaktor, trug also
    # ein Tausendstel seines Gewichts, und das „Last"-Bild war eines vom
    # Leerlauf (s. `frames` und `BEFUNDE.md`, 17.10.2026).
    sn = schnitt(geom, r_b_m, N, iq, id_, bilddaten=True)
    sch = sn["raster"]
    A, bx, by = sn["A"], sn["bx"], sn["by"]
    N = sch["N"]
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
    ax.set_title(f"Axialfluss, abgewickelter Schnitt bei r = {r_b_m*1000:.1f} mm\n"
                 f"{sch['bauform']}, {sch['n_polteilungen']} Polteilungen, "
                 f"{'Last' if (abs(iq)+abs(id_)) > 0.1 else 'Leerlauf'}",
                 fontsize=9)
    ax.text(0.01, -0.105, "Mehrschnitt (ema_axial_fdm) — KEINE 3-D-Loesung; "
            "radiale Streuung an Ri/Ro nicht enthalten, Eisen linear. "
            "Die hellen Linien sind Hoehenlinien von A, also die Feldlinien.",
            transform=ax.transAxes, fontsize=6.5, color="#888")
    return fig, sch


def bgap_figur(f: dict, geom: dict):
    """``B_gap(r)`` als Figur — die Kurve, die es radial nicht gibt.

    **Es gab diese Zeichnung ZWEIMAL**, und das ist der Grund, aus dem sie im
    Browser nie ankam: `ema_pipeline._axial_bgap_chart` war eine zweite,
    eigenstaendige Fassung, die den Schluessel ``r_schnitte_m`` las -- den
    ``felder`` nicht liefert (dort heisst er ``radien_m``). Sie gab deshalb
    IMMER ``None`` zurueck, seit es sie gibt, und ``charts/airgap.png`` wurde
    beim Axiallauf nie geschrieben. Gemessen am Lauf vom 11.10.2026.

    Zugleich war die hiesige Fassung diejenige mit der **falschen Bezugslinie**:
    sie stellte die gemessene GRUNDWELLE gegen ``eichung_magnet``, also gegen
    einen flussgewichteten MITTELWERT -- genau die Verwechslung, die am
    06.10.2026 als Befund aufgeschrieben wurde. Die Bezugslinie ist jetzt
    ``eichung_magnet_grundwelle``; beides zusammengelegt kann nur noch EINE
    Fassung falsch sein.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import ema_axial

    r = f.get("radien_m")
    b = f.get("B_gap_ueber_r_T")
    if not r or not b or len(r) != len(b):
        # **Kein stilles `None`.** Genau das hat den Schluesselfehler oben
        # monatelang verdeckt: eine Zeichenfunktion, die bei fehlenden Daten
        # nichts sagt, sieht von aussen wie eine aus, die nichts zu zeichnen
        # hatte.
        raise ValueError(
            f"B_gap(r) nicht zeichenbar: radien_m={len(r or [])}, "
            f"B_gap_ueber_r_T={len(b or [])} — erwartet gleich lang und nicht leer.")
    a = ema_axial.auslegung(geom)
    rr = [x * 1000.0 for x in r]
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=130)
    ax.plot(rr, b, "o-", color="#e8a33d", lw=1.6, ms=5,
            label="Grundwelle, geloest (Mehrschnitt)")
    try:
        h1 = float(eichung_magnet_grundwelle(geom))
        ax.axhline(h1, color="#7fd4ff", ls="--", lw=1.2,
                   label=f"analytische Grundwelle {h1:.3f} T (ohne Nut)")
    except Exception:                                            # noqa: BLE001
        h1 = None
    m = f.get("B_gap_grundwelle_mittel_T")
    if m:
        ax.axhline(float(m), color="#8bc34a", ls=":", lw=1.2,
                   label=f"Mittel r-gewichtet {float(m):.3f} T")
    ax.axvspan(a["r_innen_m"] * 1000, a["r_aussen_m"] * 1000, color="#2b3a4a",
               alpha=0.25, zorder=0)
    ax.set_xlabel("Radius [mm]")
    ax.set_ylabel("$\\hat{B}_{n,1}$ im Luftspalt [T]")
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
    return fig


def bilder(geom: dict, ordner: str, k_schnitte: int = 5, N: int = 360,
           rpm: float = 1000.0, last_nm: float = 0.0,
           r_bild_m: float | None = None) -> list:
    """Zwei Bilder nach ``<ordner>`` -- Schnitt und ``B_gap(r)``.

    Sie liegen in ``charts/``, weil die rechte Spalte **beider** Agentenkoepfe
    dort ueber die Aenderungszeit nachsieht (``ema_agent.bilder_im_projekt``) --
    kein zweiter Meldeweg, dieselbe Entscheidung wie bei ``ema_feldbild``.

    Gezeichnet wird in ``schnitt_figur`` / ``bgap_figur``; hier wird nur
    gespeichert. Der Lauf, die Vorschau und der Bericht sollen dasselbe Bild
    bekommen und nicht drei aehnliche.
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
            _bp = betriebspunkt(geom, rpm, last_nm)
            iq, id_ = _bp["i_q_A"], _bp["i_d_A"]
        except Exception:                                            # noqa: BLE001
            iq = id_ = 0.0

    fig, _ = schnitt_figur(geom, r_b, N, iq, id_)
    f1 = os.path.join(ordner, "feld_axial_schnitt.png")
    fig.savefig(f1, bbox_inches="tight", facecolor=GRUND)
    plt.close(fig)
    raus.append(f1)

    f = felder(geom, k_schnitte=k_schnitte, N=N, rpm=rpm, last_nm=last_nm)
    fig = bgap_figur(f, geom)
    f2 = os.path.join(ordner, "feld_axial_bgap_r.png")
    fig.savefig(f2, bbox_inches="tight", facecolor=GRUND)
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
