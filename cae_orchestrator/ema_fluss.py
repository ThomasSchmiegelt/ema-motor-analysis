"""Flussweg: radial oder axial -- aus EINER Funktion, wie ``ema_radien``.

Warum das ein eigenes Modul ist
-------------------------------

Das Werkzeug spricht die Maschinenart aus (``ema_maschinenart``) und die
Laeuferbauform (``ema_radien``). Die **Richtung, in der der Luftspalt liegt**,
sprach es nicht aus -- sie stand als Rechenrichtung in rund neunzig Dateien:
``rotorOD < statorID``, Luftspalt ``= (statorID - rotorOD)/2``, ein Raster aus
``R = hypot(X, Y)``-Ringen, ein 3-D-Netz aus Scheiben EINES Querschnitts.

Eine Axialflussmaschine wird darin nicht abgewiesen. Sie wird als
Radialflussmaschine gerechnet und mit ihrem Namen beschriftet -- derselbe
Fehler, gegen den ``ema_maschinenart`` gebaut ist ("er bekommt PSM-Zahlen mit
einem anderen Etikett"). Gemessen und mit Fundstellen in ``BEFUNDE.md``
(05.10.2026), geplant in ``AXIALFLUSS.md``.

Was dieses Modul herausgibt -- und warum ZWEI Integrale
--------------------------------------------------------

Nicht "ist es axial", sondern die Groessen selbst, damit die Aufrufer den
Flussweg nicht kennen muessen. Der Kern sind zwei Integrale ueber dieselbe
Luftspaltflaeche, die **verschieden gewichtet** sind:

* die **Flussverkettung** wiegt mit r^1 -- jede Flaeche traegt ihren Fluss;
* das **Moment** wiegt mit r^2 -- Flaeche mal Hebelarm.

Radial fallen beide auf einen Radius zusammen, weil es nur einen gibt::

    A_fluss  = R_gap * L                 A_moment = R_rot^2 * L

Axial nicht, weil der Luftspalt ein RINGRAUM ist und jeder Radius darin
mitzaehlt::

    A_fluss  = n * (Ro^2 - Ri^2)/2       A_moment = n * (Ro^3 - Ri^3)/3

Gemessen an der Vorgabegeometrie (Stator 280/190, Rotor 188,6, L = 80) gegen
eine Axialflussmaschine gleicher Huelle (Ro = 130 mm, lambda = 0,577, zwei
Luftspalte) ist das Verhaeltnis **1,49 fuer den Fluss und 1,66 fuer das
Moment**. Wer die beiden zu einer Ersatzflaeche zusammenlegt, hat danach
entweder ``Kt`` oder das thermische Dauermoment richtig -- nie beide.

Damit rechnen beide Kennzahlen aus einer Quelle::

    psi_pm = p * (2/pi) * B_gap * A_fluss        (ema_analysis.compute_performance)
    T      = 2 * pi * sigma * A_moment          (ema_thermal.rated_torque)

``A_moment`` hat die Einheit m^3 und ist streng genommen keine Flaeche, sondern
ein Flaechenmoment; der Name ``flaechen()`` steht fuer beide, weil sie dieselbe
Luftspaltflaeche verschieden wiegen. Die Schluessel sagen die Einheit mit
(``a_fluss_m2``, ``a_moment_m3``).

Zwei Radien, wo man einen erwartet -- bewusst beibehalten
----------------------------------------------------------

``A_fluss`` benutzt den **mittleren Spaltradius** (``ema_radien`` ueber
``ema_analysis.r_gap_m``), ``A_moment`` den **Laeuferaussenradius**
(``rotorOD/2``). Das ist nicht konsequent, und es ist nicht neu: genau so
rechnen ``compute_performance`` und ``rated_torque`` seit jeher. Hier wird es
Ziffer fuer Ziffer beibehalten, weil die erste Abnahmebedingung dieses Moduls
lautet, dass **keine radiale Kennzahl eines bestehenden Projekts sich bewegt**
(``test_fluss.py``). Der Unterschied ist beim Innenlaeufer der halbe Luftspalt
(gemessen 0,4 % an der Vorgabegeometrie) und beim **Aussenlaeufer gross** --
dort ist ``rotorOD/2`` die Aussenflaeche des Laeuferrings und nicht die
Spaltflaeche. Das ist ein Befund und keine Aufgabe dieses Moduls; er gehoert in
``BEFUNDE.md``, nicht in eine stille Reparatur mitten in einem Umbau.

Das Tor, und was es NICHT tut
------------------------------

``pruefe_flussweg(quelle, stufe)`` weist ab, was nicht gebaut ist -- dasselbe
Tor wie ``ema_radien.pruefe_bauform``, aus demselben Grund. ``STUFEN_AXIAL``
traegt seit dem 06.10.2026 ``analytisch``, ``feld``, ``thermik`` und ``zyklus``,
seit dem 07.10.2026 auch ``cad`` und ``em3d`` -- **jedes ueber einen eigenen
Erzeuger** (``cad_weg``/``em3d_weg``), nicht ueber den Vollmotorweg. Allein
``struktur`` steht weiter aussen vor, und das ist die Aussage: die Scheibe
traegt zwei Lasten, die die radiale Struktur-FEM nicht kennt (axialer Anzug,
Fliehkraft IN der Scheibenebene), und sie werden in ``ema_axial.ruecken`` bzw.
``ema_axial.bandage`` gerechnet.

``flaechen()`` rechnet trotzdem fuer beide Wege. Das ist kein Widerspruch,
sondern die Trennung von Tor und Formel: das Tor sagt, was das Werkzeug
VERANTWORTET, die Formel ist die Grundlage, auf der Stufe 1 gebaut wird
(``AXIALFLUSS.md`` §2/§3). Ohne sie waere die erste Abnahme -- die
Invarianzprobe fuer den Radialfall -- nicht pruefbar.
"""

from __future__ import annotations

import math

FLUSSWEGE = ("radial", "axial")
LABEL = {
    "radial": "Radialfluss (Luftspalt zylindrisch, Fluss radial)",
    "axial":  "Axialfluss (Luftspalt als Ringflaeche, Fluss axial)",
}
VORGABE = "radial"

#: Welche Stufen den Axialfluss heute wirklich tragen. Wie in
#: ``ema_maschinenart`` und ``ema_radien``: die zweite Spalte ist der Sinn der
#: Tabelle.
#:
#: ``analytisch`` traegt seit dem 05.10.2026 (``ema_axial``): Ringraum, die
#: beiden Flaechenintegrale, Rueckenblech (magnetisch UND Durchbiegung, mit der
#: Kreisringplatte statt einer Schranke), axialer Anzug samt negativer
#: Steifigkeit, Magnethaltung in der Scheibenebene, Zahnform.
#:
#: ``feld``/``cad``/``em3d`` ausdruecklich NICHT -- das Raster baut Ringe aus
#: ``hypot(X, Y)``, das 3-D-Netz Scheiben EINES Querschnitts, und einen solchen
#: Querschnitt gibt es axial nicht. Der Weg dorthin ist der abgewickelte
#: Mehrschnitt (``AXIALFLUSS.md`` §4, Geruest in
#: ``axialfluss_scheibenprobe.py``).
#: Seit dem 07.10.2026 traegt die Scheibe auch **em3d** -- aber ueber einen
#: anderen Loeser, genau wie bei "feld". `ema_axial_em3d` vernetzt EINE
#: Polteilung als echten Ringsektor und loest sie anti-periodisch in Elmer; der
#: magnetostatische Pipelineweg `ema_em3d` dagegen baut konzentrische Zylinder
#: und Magnete aus `magnet_legs` -- fuer eine Scheibe eine andere Maschine.
#: Dieselbe Trennung wie `FELDWEG_AXIAL`, und aus demselben Grund.
#: **`cad` traegt seit dem 07.10.2026** -- ueber `ema_axial_cad`, nicht ueber
#: `ema_freecad.build_full_motor_script` (das zeichnet einen Zylinder mit Nuten
#: im Mantel). Dritte Stufe mit eigenem Weg, dritte Begruendung derselben Art:
#: „traegt die Stufe" ist nicht „geht DIESEN Weg".
STUFEN_AXIAL: tuple = ("analytisch", "feld", "em3d", "cad", "thermik", "zyklus")

#: Welcher CAD-Erzeuger den Flussweg traegt.
CAD_WEG_AXIAL = "scheibe"
CAD_WERKZEUG = {
    "vollmotor": "ema_freecad.build_full_motor_script (Zylinder, Nuten im Mantel)",
    "scheibe": "ema_axial_cad.baue_skript (Scheibe, radiale Nuten)",
}


def cad_weg(geom: dict) -> str:
    """Welcher CAD-Erzeuger fuer diesen Flussweg gilt -- EINE Stelle."""
    return CAD_WEG_AXIAL if flussweg(geom) == "axial" else "vollmotor"


def pruefe_cad_weg(geom: dict, weg: str) -> None:
    """Abweisen, wenn der falsche Erzeuger gerufen wird.

    Ohne das hiesse ``STUFEN_AXIAL`` mit "cad" darin, der Vollmotorerzeuger
    duerfe eine Scheibe zeichnen -- und der haette klaglos einen Zylinder
    gebaut und „Axialfluss" darueber geschrieben.
    """
    soll = cad_weg(geom)
    if soll != weg:
        raise FlusswegNichtUnterstuetzt(
            f"{LABEL[flussweg(geom)]}: das CAD entsteht hier ueber "
            f"{CAD_WERKZEUG.get(soll, soll)}, nicht ueber "
            f"{CAD_WERKZEUG.get(weg, weg)}.")

#: Welcher 3-D-Loeser die Scheibe traegt. Muster `ema_maschinenart.EM3D_WEG`.
EM3D_WEG_AXIAL = "sektor_axial"
EM3D_WERKZEUG_FLUSS = {
    "elmer3d_stat": "der magnetostatische Vollmotor (ema_em3d)",
    "sektor_axial": ("der anti-periodische Ringsektor EINER Polteilung "
                     "(ema_axial_em3d)"),
}


def em3d_weg(geom: dict) -> str:
    """Welcher 3-D-Weg fuer diesen Flussweg gilt -- EINE Stelle."""
    return (EM3D_WEG_AXIAL if flussweg(geom) == "axial"
            else "elmer3d_stat")


def pruefe_em3d_weg(geom: dict, weg: str) -> None:
    """Abweisen, wenn der falsche 3-D-Loeser gerufen wird.

    Ohne das hiesse ``STUFEN_AXIAL`` mit "em3d" darin, der magnetostatische
    Vollmotorweg duerfe eine Scheibe vernetzen -- und der haette klaglos
    konzentrische Zylinder gebaut und „Axialfluss" darueber geschrieben.
    """
    soll = em3d_weg(geom)
    if soll != weg:
        raise FlusswegNichtUnterstuetzt(
            f"{LABEL[flussweg(geom)]}: die 3-D-Stufe geht hier ueber "
            f"{EM3D_WERKZEUG_FLUSS.get(soll, soll)}, nicht ueber "
            f"{EM3D_WERKZEUG_FLUSS.get(weg, weg)}.")

#: Wie die Stufennamen der Pipeline heissen. ``run_pipeline`` kennt
#: ``geometry/field/structural/thermal/drivecycle``, dieses Modul kennt
#: ``cad/feld/struktur/thermik/zyklus`` -- und eine Zuordnung im Kopf des
#: Lesers ist keine. Was hier NICHT steht, traegt der Axialfluss nicht.
STUFE_AUS_PIPELINE = {
    "geometry": "cad", "field": "feld", "structural": "struktur",
    "thermal": "thermik", "drivecycle": "zyklus",
}


def stufen_aufteilen(geom: dict, stufen) -> tuple:
    """Einen Stufensatz AUFTEILEN statt ihn abzuweisen: (traegt, uebersprungen).

    ``stufen_pruefen`` ist das Tor fuer einen AUSDRUECKLICH verlangten Schritt
    ("rechne mir das CAD") -- dort ist ein Nein richtig, und es nennt den Weg,
    der stattdessen geht. Fuer den ganzen LAUF ist es die falsche Antwort, und
    zwar nach der Regel, die in ``_gate_maschinenart`` schon ausgeschrieben
    steht: dort wurden vier von fuenf Maschinenarten bei 4 % abgewiesen, weil
    EINE Stufe woanders liegt, und das war ein Fehler. Beim Axialfluss war es
    bis zum 07.10.2026 genauso -- aus dem Browser lief **kein** Axiallauf, weil
    ``stages`` dort ``None`` ist und das Tor dann den vollen Satz prueft und an
    ``geometry``/``structural`` haengenbleibt. Gerechnet wurde dadurch nichts,
    obwohl Feld, Thermik und Fahrzyklus laengst tragen.

    Zurueck kommen zwei Listen. Die zweite ist nicht Abfall, sondern die
    Auskunft: der Aufrufer schreibt sie ins Protokoll, samt dem Weg, der es
    rechnet. Eine stillschweigend uebersprungene Stufe waere schlimmer als eine
    abgewiesene.
    """
    if flussweg(geom) != "axial":
        return (list(stufen or ()), [])
    traegt, offen = [], []
    for p in (stufen or ()):
        (traegt if STUFE_AUS_PIPELINE.get(p, p) in STUFEN_AXIAL
         else offen).append(p)
    return (traegt, offen)


#: Was statt der uebersprungenen Stufe geht -- je Stufe EIN Satz, damit das
#: Protokoll nicht nur sagt, was NICHT laeuft.
STUFE_STATTDESSEN = {
    "geometry": ("Das CAD der Scheibe baut `ema_axial_cad` (radiale Nuten, "
                 "Sektormagnete), nicht `ema_freecad.build_full_motor_script` "
                 "(Zylinder, Nuten im Mantel) \u2014 derselbe Knopf, der richtige "
                 "Erzeuger."),
    "structural": ("Die Struktur-FEM rechnet Fliehkraft an einem Blechschnitt; "
                   "die Hauptlast der Scheibe ist der axiale ANZUG (gemessen "
                   "8,6 : 1 zum Schub) und steht in keiner der drei Loeser. "
                   "`ema_axial.ruecken`/`bandage` rechnen ihn, erreichbar "
                   "ueber `cae_cli.py axial`."),
}


def stufen_pruefen(geom: dict, stufen) -> None:
    """Einen STUFENSATZ gegen den Flussweg pruefen.

    Der Lauf als Ganzes (``stufe = "lauf"``) ist fuer die Scheibe die falsche
    Frage: sie traegt Feld, Thermik und Fahrzyklus, aber weder CAD noch
    Struktur-FEM noch 3-D. Wer den ganzen Satz abweist, weist damit auch das ab,
    was laengst geht; wer ihn durchlaesst, rechnet CAD auf einer Scheibe. Also
    einzeln, und die Meldung NENNT die Stufe, die bindet, samt dem, was bleibt.
    """
    if flussweg(geom) != "axial":
        return
    offen = [p for p in (stufen or ())
             if STUFE_AUS_PIPELINE.get(p, p) not in STUFEN_AXIAL]
    if not offen:
        return
    traegt = [p for p in (stufen or ()) if p not in offen]
    raise FlusswegNichtUnterstuetzt(
        f"{LABEL['axial']}: die Stufe(n) {', '.join(sorted(offen))} tragen ihn "
        f"nicht."
        + (f" Getragen waeren hier: {', '.join(sorted(traegt))}."
           if traegt else "")
        + f" Insgesamt getragen: {', '.join(STUFEN_AXIAL)}. "
        f"Waehle im Reiter ⑤ Berechnung nur die tragenden Stufen, oder nimm "
        f"`cae_cli.py axial`. Ein Radialfluss-Ergebnis unter diesem Namen waere "
        f"schlimmer als keines -- gemessen laege allein die Flussflaeche um den "
        f"Faktor 1,49 daneben, das Moment um 1,66.")

#: **Welcher LOESER die axiale Feldstufe traegt.** Dieselbe Unterscheidung wie
#: ``ema_maschinenart.Art.feldweg``, und aus demselben Grund: „traegt die Stufe"
#: und „geht DIESEN Weg" sind zwei Fragen. Die Pipeline rechnet ihr Feld mit der
#: 2-D-FDM auf einem ``R = hypot(X, Y)``-Raster; eine Scheibe ist darin nicht
#: abbildbar. Ohne diese Trennung haette ``STUFEN_AXIAL`` mit "feld" darin
#: bedeutet, die Pipeline duerfe eine Axialflussmaschine durch die radiale FDM
#: schicken -- und die haette klaglos ein Ringfeld ausgegeben und „Axialfluss"
#: darueber geschrieben. Genau diese stille Ersatzrechnung ist der Anlass des
#: ganzen Moduls.
FELDWEG_AXIAL = "fdm_scheibe"
FELDWEG_WERKZEUG = {
    "fdm": "die 2-D-FDM der Pipeline (ema_analysis._rasterise)",
    "fdm_scheibe": "der abgewickelte Mehrschnitt (ema_axial_fdm.felder)",
}

#: Welche MASCHINENART axial ueberhaupt eine Bauform hat. Die Matrix ist nicht
#: voll besetzt, und das ist die Aussage -- eine Reluktanzmaschine braucht
#: orientiertes Blech in einer Scheibe, und das ist nicht blechbar.
#:
#: Bemerkenswert: die GSM hat axial die aelteste Bauform von allen (der
#: Scheibenlaeufer mit gedrucktem oder eisenlosem Anker), ist aber die einzige
#: Art ohne Feldstufe -- ``feldweg="keiner"``, weil ein kommutierter Anker nicht
#: magnetostatisch ist. Daran aendert die Scheibe nichts.
#: **Korrigiert am 05.10.2026.** Die erste Fassung schrieb hier Urteile ueber
#: die MASCHINE, wo nur Aussagen ueber dieses WERKZEUG zulaessig sind -- und zwei
#: davon waren schlicht falsch. Sie lauteten:
#:
#:   asm:   "ein Scheibenkaefig ist schwer herstellbar [...] Nicht getragen"
#:   synrm: "die Anisotropie braucht orientiertes Blech IN einer Scheibe --
#:           nicht blechbar. Nicht getragen"
#:
#: Die Axialfluss-Asynchronmaschine mit Kaefiglaeufer ist ein eigenes
#: Forschungsfeld; Igelspacher (TU Muenchen, 2018/2020) widmet ihr eine ganze
#: Dissertation samt den drei Bauformen (ein Stator/ein Rotor, zwei Statoren/ein
#: Rotor, ein Stator/zwei Rotoren), der Stapelbauweise und einer Beispielmaschine
#: mit reduziertem Rotorjoch. "Schwer herstellbar" war kein Befund, sondern eine
#: Vermutung in der Form eines Befunds -- genau das, was ``BEFUNDE.md`` als
#: Gegenteil seiner selbst benennt.
#:
#: ``nicht gebaut`` ist deshalb jetzt von ``gibt es nicht`` getrennt. Das
#: Werkzeug darf sagen, was ES traegt; ueber die Maschinenwelt sagt es nichts.
#:
#: Quellen, die der Mensch am 05.10.2026 dagegengehalten hat:
#:   * Igelspacher, "Zur Theorie der Axialfluss-Asynchronmaschine als
#:     ausfallsicherer Antrieb", Diss. TU Muenchen 2018/2020 -- Kap. 2
#:   * HAW Hamburg, Forschungsgruppe Elektrische Mobilitaet: Pancake-Design,
#:     Single-Rotor-Single-Stator / DRSS / DSSR, Halbacharrays, kernlose
#:     Luftspulenwicklungen
#:   * Wikipedia "Scheibenlaeufermotor": eisenloser bzw. gedruckter Scheibenanker,
#:     Fluss parallel zur Drehachse, Durchmesser groesser als Baulaenge
ART_AXIAL = {
    "pmsm":  (True,  "gebaut. Die verbreitetste Bauform (YASA, TORUS, AFIR): "
                     "Sektormagnete flach auf der Scheibe"),
    "gsm":   (True,  "gebaut (analytisch). Der Scheibenlaeufer mit gedrucktem "
                     "oder eisenlosem Anker ist die aelteste axiale Bauform -- "
                     "kein Rastmoment, kleinste Traegheit. Weiterhin ohne "
                     "Feldstufe, aus dem alten Grund (kommutierter Anker)"),
    "eesm":  (True,  "gebaut (analytisch): Ringerregerspule axial, Schleifringe "
                     "wie bisher"),
    "asm":   (False, "NICHT GEBAUT -- und das ist eine Aussage ueber dieses "
                     "Werkzeug, nicht ueber die Maschine. Die "
                     "Axialfluss-Asynchronmaschine mit Kaefiglaeufer existiert "
                     "und ist erforscht (Igelspacher, Diss. TU Muenchen 2020, "
                     "drei Bauformen + Stapelbauweise). Was hier fehlt, ist der "
                     "Scheibenkaefig in ema_asm und ein harmonischer Loeser auf "
                     "dem abgewickelten Schnitt"),
    "synrm": (False, "NICHT GEBAUT. Der Reluktanzlaeufer als Scheibe ist "
                     "ungewoehnlich und fertigungstechnisch anspruchsvoll "
                     "(Anisotropie in der Scheibenebene), aber die frueher hier "
                     "stehende Behauptung 'nicht blechbar' ist nicht belegt und "
                     "zurueckgenommen"),
}

#: Bauformen des Axialflusses und wieviele Luftspalte sie haben. Der Name
#: allein entscheidet nichts; er sagt, wo sich die Anzugskraft aufhebt.
AXIAL_BAUFORMEN = {
    "einseitig": {"spalte": 1, "label": "einseitig (1 Laeufer, 1 Staender)",
                  "anzug": "unausgeglichen -- die ganze Kraft liegt am Lager"},
    "afir":      {"spalte": 2, "label": "AFIR (2 Staender, 1 Laeufer)",
                  "anzug": "hebt sich am LAEUFER auf"},
    "torus_nn":  {"spalte": 2, "label": "TORUS-NN (2 Laeufer, 1 Staender, Umfangsjoch)",
                  "anzug": "hebt sich am STAENDER auf"},
    "yasa":      {"spalte": 2, "label": "YASA / TORUS-NS (2 Laeufer, jochloser Staender)",
                  "anzug": "hebt sich am STAENDER auf"},
}
AXIAL_BAUFORM_VORGABE = "yasa"


class FlusswegNichtUnterstuetzt(ValueError):
    """Diese Stufe traegt diesen Flussweg (noch) nicht."""


def flussweg(quelle) -> str:
    """Flussweg aus Payload **oder** ``geom``. Unbekannt -> radial.

    Der Schluessel sitzt in ``geom``, aus demselben Grund wie ``machineType``
    (s. ``ema_maschinenart.art_code``): die analytischen Funktionen bekommen
    nur ``geom``, und laege er oben im Payload, waere er genau dort unsichtbar,
    wo er entscheidet.
    """
    if not isinstance(quelle, dict):
        return VORGABE
    g = quelle.get("geom") if isinstance(quelle.get("geom"), dict) else quelle
    w = str(g.get("fluxPath", "") or quelle.get("fluxPath", "") or "").strip().lower()
    if w in ("axial", "axialfluss", "axial_flux", "afpm", "scheibe", "scheibenlaeufer"):
        return "axial"
    return VORGABE


def traegt(stufe: str) -> bool:
    return stufe in STUFEN_AXIAL


def pruefe_flussweg(quelle, stufe: str) -> str:
    """Traegt diese Stufe den Flussweg? Sonst klarer Fehler, keine Ersatzrechnung."""
    w = flussweg(quelle)
    if w == "radial" or stufe in STUFEN_AXIAL:
        return w
    getragen = ", ".join(STUFEN_AXIAL) if STUFEN_AXIAL else "keine"
    raise FlusswegNichtUnterstuetzt(
        f"{LABEL[w]}: die Stufe '{stufe}' traegt ihn nicht. Getragen: "
        f"{getragen}. Der Umbauplan steht in AXIALFLUSS.md, die zwoelf Stellen, "
        f"die heute eine Zahl statt eines Neins geben, in BEFUNDE.md "
        f"(05.10.2026). Ein Radialfluss-Ergebnis unter diesem Namen waere "
        f"schlimmer als keines -- gemessen laege allein die Flussflaeche um "
        f"den Faktor 1,49 daneben, das Moment um 1,66.")


def pruefe_art_flussweg(quelle) -> str:
    """Hat DIESE Maschinenart axial ueberhaupt eine Bauform?

    Zwei Tore, die wie eines aussehen und es nicht sind: ``pruefe_flussweg``
    fragt, ob die STUFE den Flussweg traegt, dieses hier, ob die ART ihn hat.
    Eine Reluktanzmaschine als Scheibe abzuweisen ist keine Luecke im Werkzeug,
    sondern eine Aussage ueber die Maschine.
    """
    import ema_maschinenart

    w = flussweg(quelle)
    if w == "radial":
        return w
    code = ema_maschinenart.art_code(quelle)
    traegt_art, hinweis = ART_AXIAL.get(code, (False, "unbekannte Art"))
    if traegt_art:
        return w
    raise FlusswegNichtUnterstuetzt(
        f"{ema_maschinenart.ARTEN[code].label} als Axialflussmaschine: "
        f"{hinweis}. Axial getragen: "
        f"{', '.join(k for k, (t, _) in ART_AXIAL.items() if t)}.")


def pruefe_feldweg(quelle, weg: str) -> str:
    """Traegt der Flussweg die Feldstufe **auf diesem Loeser**?

    ``pruefe_flussweg(quelle, "feld")`` sagt nur, dass es fuer den Axialfluss
    ueberhaupt eine Feldstufe gibt. Welcher Loeser sie traegt, sagt
    ``FELDWEG_AXIAL`` -- und wer die Scheibe in die radiale FDM schickt, bekommt
    hier einen Fehler mit der Adresse des richtigen Werkzeugs statt ein Ringfeld
    unter fremdem Namen. Wortgleich zu ``ema_maschinenart.pruefe_feldweg``.
    """
    w = pruefe_flussweg(quelle, "feld")
    if w == "radial" or weg == FELDWEG_AXIAL:
        return w
    raise FlusswegNichtUnterstuetzt(
        f"{LABEL[w]}: die Feldstufe laeuft nicht ueber "
        f"'{FELDWEG_WERKZEUG.get(weg, weg)}', sondern ueber "
        f"'{FELDWEG_WERKZEUG[FELDWEG_AXIAL]}'. Das Raster der Pipeline baut "
        f"Ringe aus hypot(X, Y); eine Scheibe ist darin nicht abbildbar.")


def axial_bauform(geom: dict) -> str:
    b = str((geom or {}).get("axialBauform", "") or "").strip().lower()
    return b if b in AXIAL_BAUFORMEN else AXIAL_BAUFORM_VORGABE


def masse_axial(geom: dict) -> dict:
    """Die Masse des Ringraums in **Metern** -- Ro, Ri, lambda, Spaltzahl.

    ``axialAktivOD`` ist der **aktive** Aussendurchmesser und ausdruecklich
    nicht ``statorOD``: zwischen aktivem Rand und Huelle sitzen Bandage,
    Gehaeuse und Fuegespalt. Ihn aus ``statorOD`` abzuleiten hiesse, eine
    Auslegungsregel zu erfinden und das Ergebnis dann als gerechnet zu
    beschriften; er wird deshalb verlangt. Welche Regel dort richtig ist,
    entscheidet Stufe 1 (``AXIALFLUSS.md`` §3).
    """
    g = geom or {}
    d_a = float(g.get("axialAktivOD", 0) or 0.0)
    if d_a <= 0.0:
        raise ValueError(
            "'axialAktivOD' fehlt -- fuer Axialfluss wird der AKTIVE "
            "Aussendurchmesser gebraucht. Er ist nicht 'statorOD': dazwischen "
            "liegen Bandage, Gehaeuse und Fuegespalt, und eine erfundene "
            "Ableitung waere eine Auslegungsregel mit dem Anschein einer "
            "Messung.")
    lam = float(g.get("axialLambda", 0) or 0.0) or 0.5774
    if not 0.05 < lam < 0.98:
        raise ValueError(
            f"'axialLambda' = {lam:.4f} liegt ausserhalb 0,05..0,98. lambda ist "
            f"Ri/Ro; bei lambda -> 1 verschwindet der Ringraum, bei lambda -> 0 "
            f"wird das Wickelfenster am Innenrand null.")
    bauform = axial_bauform(g)
    # **Die Spaltzahl FOLGT der Bauform, sie wird nicht daneben eingestellt.**
    #
    # Hier stand `int(g.get("axialSpalte")) or AXIAL_BAUFORMEN[...]["spalte"]`:
    # der gespeicherte Schluessel gewann gegen die Bauform. Abgeleitet wurde er
    # aber nur in `aus_seite` (der Zeichenseite) -- wer `axialBauform` direkt
    # setzt, also `cae_cli --set`, der Agent und jeder Payload aus
    # `axial_vorgabe`, bekam die Spaltzahl des VORIGEN Standes.
    #
    # Gemessen am 16.10.2026: `--set axialBauform=einseitig` ergab **2**
    # Luftspalte statt einem -- also die doppelte Ringflaeche, das doppelte
    # Moment und einen Anzug, der sich laut Modell aufhebt, obwohl eine
    # einseitige Maschine ihn gerade NICHT aufhebt (`hebt_sich_auf` liest
    # `n_spalte > 1`). Ueber die Zeichenseite war dieselbe Maschine richtig.
    # Siehe `BEFUNDE.md`, 16.10.2026.
    stapel = max(1, int(g.get("axialStapel", 1) or 1))
    n = AXIAL_BAUFORMEN[bauform]["spalte"] * stapel
    n_key = int(g.get("axialSpalte", 0) or 0)
    # Ein widersprechender gespeicherter Wert wird UEBERSTIMMT und GEMELDET --
    # nicht abgewiesen. Abweisen traefe jeden Altpayload, der die Zahl noch
    # traegt (das Werkzeug hat sie selbst hineingeschrieben), und stilles
    # Uebergehen waere der Fehler von vorhin mit umgekehrtem Vorzeichen.
    korrigiert = (n_key, n) if (n_key and n_key != n) else None
    if n < 1:
        raise ValueError(f"'axialSpalte' = {n}: eine Maschine ohne Luftspalt "
                         f"hat kein Luftspaltfeld.")
    ro = d_a / 2.0 / 1000.0
    return {"r_aussen_m": ro, "r_innen_m": lam * ro, "lambda": lam,
            "n_spalte": n, "bauform": bauform,
            "spalte_korrigiert": korrigiert,
            "label": AXIAL_BAUFORMEN[bauform]["label"],
            "anzug": AXIAL_BAUFORMEN[bauform]["anzug"],
            "ringflaeche_m2": n * math.pi * (ro ** 2 - (lam * ro) ** 2)}


def flaechen(geom: dict, axial_mm: float | None = None) -> dict:
    """Die zwei Integrale der Luftspaltflaeche -- fuer BEIDE Flusswege.

    ``a_fluss_m2``  [m^2]  r^1-gewichtet, fuer ``psi_pm``
    ``a_moment_m3`` [m^3]  r^2-gewichtet, fuer ``T = 2*pi*sigma*A_moment``

    Der radiale Zweig gibt **genau** zurueck, womit ``compute_performance``
    (``r_gap_m(geom) * stapellaenge_m(geom, axial_mm)``) und ``rated_torque``
    (``(rotorOD/2/1000)^2 * L``) heute rechnen -- einschliesslich der beiden
    verschiedenen Radien, s. Modulkopf. Das ist die Invarianzbedingung, nicht
    ein uebernommener Fehler.
    """
    import ema_analysis

    w = flussweg(geom)
    L = ema_analysis.stapellaenge_m(geom, axial_mm)
    if w == "radial":
        r_gap = ema_analysis.r_gap_m(geom)
        r_rot = float(geom["rotorOD"]) / 2.0 / 1000.0
        return {
            "flussweg": w, "label": LABEL[w],
            "a_fluss_m2":  r_gap * L,
            "a_moment_m3": r_rot ** 2 * L,
            "r_fluss_m": r_gap, "r_moment_m": r_rot, "laenge_m": L,
            "hinweis": ("Ein Radius fuer beide Integrale -- radial fallen sie "
                        "zusammen. a_fluss nimmt den mittleren Spaltradius, "
                        "a_moment den Laeuferaussenradius (so rechnet das "
                        "Werkzeug seit jeher, s. ema_fluss-Modulkopf)."),
        }

    m = masse_axial(geom)
    ro, ri, n = m["r_aussen_m"], m["r_innen_m"], m["n_spalte"]
    return {
        "flussweg": w, "label": LABEL[w],
        "a_fluss_m2":  n * (ro ** 2 - ri ** 2) / 2.0,
        "a_moment_m3": n * (ro ** 3 - ri ** 3) / 3.0,
        "r_aussen_m": ro, "r_innen_m": ri, "lambda": m["lambda"],
        "n_spalte": n, "bauform": m["bauform"], "baulaenge_m": L,
        "spalte_korrigiert": m["spalte_korrigiert"],
        "hinweis": ("Zwei verschiedene Integrale ueber denselben Ringraum: "
                    "der Fluss waechst mit r^1, das Moment mit r^2. Ein "
                    "Ersatzradius kann nur eines von beiden treffen."),
    }


def traeger(geom: dict) -> dict:
    """Welches Bauteil die Luftspaltkraft traegt -- als Aussage, nicht als Formel.

    Das Gegenstueck zu ``ema_radien.magnethaltung``, und aus demselben Grund in
    Worten: der Unterschied ist keine Vorzeichenaenderung.

    Radial hebt sich die Normalkraft auf dem Umfang auf und heisst bei Unwucht
    "unbalanced magnetic pull" -- eine Stoergroesse. Axial ist sie die
    **Hauptlast**: gemessen 345,8 kPa Normalspannung gegen 40 kPa
    momentbildenden Schub, also 8,6 : 1 (``axialfluss_scheibenprobe.py``). Bei
    zwei Luftspalten hebt sie sich nur bei MITTIGEM Staender auf, und der
    Restschub bei Versatz wirkt IN Richtung des Versatzes: der Staender muss
    ihn als **Steifigkeit** aufbringen, nicht nur tragen.
    """
    w = flussweg(geom)
    if w == "radial":
        return {"flussweg": w,
                "traeger": "Laeufer- und Staenderjoch, umfangs geschlossen",
                "kraft_hebt_sich_auf": True,
                "lastart_vorhanden": True,
                "aussage": ("Die Normalkraft hebt sich auf dem Umfang auf; was "
                            "uebrigbleibt, ist der unausgeglichene Magnetzug "
                            "aus Unwucht. Fliehkraft ist die bemessende Last, "
                            "und sie ist gerechnet (ema_rotorcheck).")}
    m = masse_axial(geom)
    einseitig = m["n_spalte"] == 1
    return {"flussweg": w, "bauform": m["bauform"], "label": m["label"],
            "traeger": ("das Lager" if einseitig else
                        "der Staender als Steifigkeit, nicht nur als Festigkeit"),
            "kraft_hebt_sich_auf": not einseitig,
            "lastart_vorhanden": False,
            "aussage": (f"{m['anzug']}. Der axiale Anzug ist die Hauptlast "
                        f"(gemessen 8,6 : 1 zum momentbildenden Schub), und er "
                        f"ist in KEINER Strukturstufe vorhanden: ema_deck, "
                        f"ema_z88 und ema_aster rechnen Fliehkraft. Dazu haelt "
                        f"den Sektormagneten kein Blechsteg -- die Fliehkraft "
                        f"zieht ihn in der SCHEIBENEBENE nach aussen, dort ist "
                        f"nur Klebung oder eine Bandage am Rand.")}


def uebersicht(geom: dict, axial_mm: float | None = None) -> str:
    f = flaechen(geom, axial_mm)
    t = traeger(geom)
    z = [f["label"]]
    if f["flussweg"] == "radial":
        z.append(f"  Spaltradius (Fluss)   r = {f['r_fluss_m'] * 1000:8.2f} mm")
        z.append(f"  Laeuferradius (Moment) r = {f['r_moment_m'] * 1000:8.2f} mm")
        z.append(f"  Blechpaket             L = {f['laenge_m'] * 1000:8.2f} mm")
    else:
        z.append(f"  Bauform               {f['bauform']} ({f['n_spalte']} Luftspalt"
                 f"{'e' if f['n_spalte'] != 1 else ''})")
        z.append(f"  Ringraum              Ri = {f['r_innen_m'] * 1000:.2f} .. "
                 f"Ro = {f['r_aussen_m'] * 1000:.2f} mm  (lambda = {f['lambda']:.4f})")
        z.append(f"  Baulaenge             {f['baulaenge_m'] * 1000:.2f} mm")
    z.append(f"  A_fluss               {f['a_fluss_m2'] * 1e4:10.2f} cm^2   (r^1)")
    z.append(f"  A_moment              {f['a_moment_m3'] * 1e6:10.2f} cm^3   (r^2)")
    z.append(f"  Luftspaltkraft traegt: {t['traeger']}")
    z.append(f"  {t['aussage']}")
    return "\n".join(z)


# ---------------------------------------------------------------------------
# Die Zeichenseite und das Schema -- EINE Zuordnung
# ---------------------------------------------------------------------------
#
# ``axialfluss/ansicht.html`` ist als eigenstaendige Seite gebaut worden, damit
# sie geprueft werden konnte, bevor etwas davon in ``ema.html`` wandert. Sie
# hat dabei einen VOLLSTAENDIGEN axialen Parametersatz bekommen -- aus der
# Bauart heraus, nicht aus dem radialen abgeleitet -- und der ist jetzt der
# axiale Parametersatz des Werkzeugs.
#
# Diese Tabelle ist die einzige Stelle, an der Feldname und Schemaschluessel
# verbunden sind. Die Seite HOLT sie sich (``GET /axialfluss/felder``) und
# schreibt sie nicht ab: eine zweite Zuordnung waere dieselbe Falle wie die
# handgespiegelte ``magnetLegs`` -- beide Seiten saehen richtig aus und
# meinten verschiedene Maschinen.
#
# Drei Umrechnungen stehen darin, und jede ist eine, die man genau einmal
# falsch macht:
#   * die Seite fuehrt den AUSSENRADIUS, das Schema den DURCHMESSER
#   * die Seite fuehrt die POLZAHL 2p, das Schema die POLPAARE p
#   * ``topo`` und ``axialBauform`` sind DASSELBE in zwei Vokabularen
#     (Dissertation gegen Industrie), nicht zwei Einstellungen

#: Seitenname -> (Schemaschluessel, Faktor Seite->Schema).
#: Faktor ``None`` heisst: keine Zahl, s. ``_UMSCHRIFT``.
SEITE_FELDER: dict[str, tuple[str, float | None]] = {
    "ro":      ("axialAktivOD", 2.0),      # Radius -> Durchmesser
    "lam":     ("axialLambda", 1.0),
    "poles":   ("p", 0.5),                 # Polzahl 2p -> Polpaare p
    "q":       ("slots", 1.0),
    "bnut":    ("axialNutBreiteMm", 1.0),
    "spalt":   ("axialSpaltMm", 1.0),
    "zahn":    ("axialZahnLaengeMm", 1.0),
    "jochS":   ("axialJochStaenderMm", 1.0),
    "jochR":   ("axialJochLaeuferMm", 1.0),
    "magd":    ("axialMagnetDicke", 1.0),
    "alpha":   ("axialPolbedeckung", 1.0),
    "welle":   ("shaftD", 1.0),            # beides Durchmesser
    "wkI":     ("axialWickelkopfMm", 1.0),
    "stapel":  ("axialStapel", 1.0),
    "magSegU": ("axialMagSegUmfang", 1.0),
    "magSegR": ("axialMagSegRadial", 1.0),
    "magFuge": ("axialMagFugeMm", 1.0),
    "qr":      ("axialLaeuferStaebe", 1.0),
    "topo":    ("axialBauform", None),
    "laeufer": ("axialLaeuferart", None),
}

#: ``topo`` der Seite <-> ``axialBauform`` des Schemas. Dasselbe Merkmal, zwei
#: Vokabulare: die Seite zaehlt Staender und Laeufer (Igelspacher Kap. 2), die
#: Industrie benennt die Bauform. Wer beides als zwei Einstellungen fuehrte,
#: haette zwei Zahlen fuer die Zahl der Luftspalte.
#:
#: Die Unterscheidung YASA / TORUS innerhalb von ESDR steht NICHT hier, sondern
#: folgt aus ``axialJochStaenderMm``: yokeless heisst ohne Staenderjoch. Sie
#: hier zu fuehren hiesse, sie zweimal einstellbar zu machen.
TOPO_BAUFORM = {"eser": "einseitig", "dser": "afir", "esdr": "yasa"}
BAUFORM_TOPO = {"einseitig": "eser", "afir": "dser",
                "yasa": "esdr", "torus_nn": "esdr"}

#: Zahl der magnetisch wirksamen Luftspalte je Teilmaschine, AUS der Bauform.
#: ``masse_axial`` rechnet sie seit dem 16.10.2026 **immer** hieraus; der
#: Schluessel ``axialSpalte`` wird von ``aus_seite`` nur noch MITgeschrieben
#: (damit ein abgelegter Payload sie lesbar traegt) und gewinnt nirgends mehr.
#: Vorher gewann er, und genau dann standen Bauform und Spaltzahl nebeneinander
#: und widersprachen sich -- s. ``BEFUNDE.md``, 16.10.2026.
BAUFORM_SPALTE = {"einseitig": 1, "afir": 2, "yasa": 2, "torus_nn": 2}


def _zahl(x, vorgabe=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return vorgabe


def aus_seite(werte: dict) -> dict:
    """Felder der Zeichenseite -> Geometrie-Teilmenge fuer den Payload.

    Setzt ``fluxPath="axial"`` mit: wer diese Seite uebernimmt, meint eine
    Axialflussmaschine, und die Stufen fragen genau diesen Schluessel.
    """
    g: dict = {"fluxPath": "axial"}
    for seite, (schl, fak) in SEITE_FELDER.items():
        if seite not in werte:
            continue
        roh = werte[seite]
        if fak is None:
            if seite == "topo":
                g[schl] = TOPO_BAUFORM.get(str(roh), "yasa")
            else:
                g[schl] = str(roh)
            continue
        w = _zahl(roh) * fak
        g[schl] = int(round(w)) if schl in ("p", "slots", "axialStapel",
                                            "axialMagSegUmfang",
                                            "axialMagSegRadial",
                                            "axialLaeuferStaebe") else w
    # Abgeleitet, nicht eingestellt -- s. BAUFORM_SPALTE.
    bf = g.get("axialBauform", "yasa")
    g["axialSpalte"] = BAUFORM_SPALTE.get(bf, 2) * max(1, int(g.get("axialStapel", 1)))
    # YASA gegen TORUS folgt aus dem Staenderjoch, nicht aus einem zweiten Feld.
    if bf in ("yasa", "torus_nn"):
        g["axialBauform"] = "yasa" if _zahl(g.get("axialJochStaenderMm"), 0) <= 0.5 \
                            else "torus_nn"
    # Die Zahnform folgt aus der Zeichnung: die Seite zeichnet durchweg
    # PARALLELFLANKIGE Nuten, das ist ihre Aussage (Igelspacher Kap. 2.1).
    g["axialZahnform"] = "parallel"
    return g


def zur_seite(geom: dict) -> dict:
    """Die Gegenrichtung: Geometrie -> Felder der Zeichenseite.

    Fehlt ein Schluessel, fehlt er auch im Ergebnis -- die Seite behaelt dann
    ihren eigenen Wert. Ihn hier mit einer Vorgabe zu fuellen hiesse, einen
    Wert zu erfinden, der im Projekt nicht steht.
    """
    w: dict = {}
    for seite, (schl, fak) in SEITE_FELDER.items():
        if schl not in geom or geom[schl] is None:
            continue
        if fak is None:
            w[seite] = (BAUFORM_TOPO.get(str(geom[schl]), "esdr")
                        if seite == "topo" else str(geom[schl]))
        else:
            w[seite] = _zahl(geom[schl]) / fak
    return w


#: **Ein tragfaehiger Axialfluss-Startpunkt -- die EINE Quelle.**
#:
#: ``ema_text2ema.SCHEMA`` traegt fuer jeden axialen Schluessel ``def: None``:
#: die Felder sind beschrieben, aber nicht VORBELEGT, weil die Zeichenseite sie
#: ohnehin alle setzt. Fuer den Agenten war das eine Sackgasse -- ``--frisch``
#: plus ``--set fluxPath=axial`` ergab einen Payload aus Nullen, und der erste
#: Zugriff darauf starb (gemessen: ``TypeError: float() argument ... not
#: 'NoneType'`` in der Thermik, ``'axialAktivOD' fehlt`` in ``flaechen``).
#:
#: Die Zahlen hier sind die Maschine aus ``AXIALFLUSS.md`` §1, also derselbe
#: Fall, gegen den Stufe 1, der Mehrschnitt, der Elmer-Sektor und die Thermik
#: gemessen sind. Sie sind ein **Ausgangspunkt und keine Auslegung**: nichts
#: daran ist optimiert, und genau deshalb muss danach ``paarvergleich`` laufen.
AXIAL_VORGABE = {
    "axialAktivOD": 260.0,        # aktiver Aussendurchmesser (NICHT statorOD)
    "axialLambda": 0.577,         # Ri/Ro -- nahe am Momentoptimum des freien Rings
    "axialBauform": "yasa",       # zwei Spalte, jochloser Staender
    # `axialSpalte` steht hier mit Absicht NICHT: sie folgt der Bauform
    # (BAUFORM_SPALTE x axialStapel) und wird in `masse_axial` abgeleitet. Als
    # Vorgabewert waere sie ein gespeicherter Stand, der der naechsten
    # Bauformwahl widerspricht -- genau der Befund vom 16.10.2026.
    "axialSpaltMm": 1.0,
    "axialMagnetDicke": 6.0,
    "axialPolbedeckung": 0.85,
    "axialZahnform": "keil",      # b ~ r: B_zahn ueber dem Radius konstant
    "axialNabeD": 0.0,            # 0 = shaftD
    "axialBminMm": 2.0,
    "axialNutBreiteMm": 0.0,      # 0 = aus slotWidthRatio (s. ema_axial.nutbreite_mm)
    "axialZahnLaengeMm": 25.0,
    "axialJochStaenderMm": 0.0,   # jochlos (YASA); > 0 nur wo die Bauform es braucht
    "axialJochLaeuferMm": 13.0,
    "axialWickelkopfMm": 14.0,
    "axialStapel": 1,
    "axialLaeuferart": "sektor",
    "axialMagSegUmfang": 1,
    "axialMagSegRadial": 1,
    "axialMagFugeMm": 1.0,
    "axialLaeuferStaebe": 0,
}


#: **Welche axialen Schluessel eine ECHTE Zahl brauchen** -- und welche nicht.
#:
#: Bei den uebrigen ist 0 eine gueltige Wahl und bedeutet „ableiten":
#: ``axialJochStaenderMm`` 0 = jochlos, ``axialNabeD`` 0 = ``shaftD``,
#: ``axialNutBreiteMm`` 0 = aus ``slotWidthRatio``. Diese fuenf dagegen sind
#: ohne Zahl keine Maschine -- und genau daran scheiterte der erste Anlauf:
#: ``axialAktivOD`` stand als **0** im Schema (nicht als ``None``), die
#: Vorbelegung griff nicht, und der Lauf endete mit „'axialAktivOD' fehlt".
AXIAL_PFLICHT = ("axialAktivOD", "axialLambda", "axialSpaltMm",
                 "axialMagnetDicke", "axialPolbedeckung", "axialZahnLaengeMm",
                 "axialJochLaeuferMm", "axialWickelkopfMm")


#: Wo eine 0 keine Zahl ist, sondern "ableiten". Ohne diesen Zusatz liest das
#: Protokoll "axialNabeD = 0.0" als ergaenztes MASS -- und ein Nabendurchmesser
#: von null waere keine Maschine. Dieselbe Unterscheidung wie in
#: ``AXIAL_PFLICHT``, nur fuer die Ausgabe.
NULL_HEISST = {
    "axialNabeD": " (0 = Einspannung auf shaftD)",
    "axialJochStaenderMm": " (0 = jochlos, wie es die Bauform yasa meint)",
    "axialNutBreiteMm": " (0 = aus slotWidthRatio)",
    "axialLaeuferStaebe": " (0 = abgeleitet, Spiegel von ema_asm.stabzahl)",
}

#: Was eine ergaenzte Vorgabe IST -- ein Satz, der mit jedem Fundstueck
#: mitgeht. Er steht hier und nicht an den drei Stellen, die ihn ausgeben.
ERGAENZT_SATZ = ("Ausgangspunkt aus ema_fluss.AXIAL_VORGABE (AXIALFLUSS.md "
                 "§1), KEINE Auslegung: nichts daran ist optimiert. Gezeichnet "
                 "und eingestellt wird die Scheibe im Reiter ⊙ Axialfluss "
                 "(dort „↑ ins Projekt übernehmen“), danach paarvergleich.")


def axial_ergaenzen(geom: dict | None = None) -> tuple[dict, list[str]]:
    """Wie ``axial_vorgabe`` -- und sagt dazu, WAS sie gesetzt hat.

    Der Grund, aus dem es diese zweite Tuer gibt: ``axial_vorgabe`` fuellt
    stillschweigend, und still war genau das Problem. Der Browser schickte
    ``fluxPath="axial"`` ohne einen einzigen ``axial*``-Schluessel -- die Maske
    hat keine, die Scheibe wird im Reiter ⊙ Axialfluss gezeichnet --, und der
    Lauf starb am ersten Zugriff (``'axialAktivOD' fehlt``, gemeldet am
    09.10.2026 mit vollem Traceback im Protokollfenster). Eine Vorgabe
    einzusetzen macht den Lauf moeglich; sie **unbenannt** einzusetzen macht aus
    einer fremden Maschine eine, die aussieht wie die eigene.

    Rueckgabe: der ergaenzte Payload und je ergaenztem Schluessel eine Zeile
    ``name = wert``. Leere Liste heisst: alles kam von aussen.
    """
    g = dict(geom or {})
    vorher = {k: g.get(k) for k in AXIAL_VORGABE}
    g = axial_vorgabe(g)
    ergaenzt = [f"{k} = {g[k]}" + NULL_HEISST.get(k, "")
                for k in AXIAL_VORGABE if _geaendert(vorher[k], g[k])]
    return g, ergaenzt


def _geaendert(alt, neu) -> bool:
    """Hat ``axial_vorgabe`` diesen Schluessel wirklich angefasst?"""
    if alt is None or alt == "":
        return True
    try:
        return abs(float(alt) - float(neu)) > 1e-12
    except (TypeError, ValueError):
        return str(alt) != str(neu)


def axial_vorgabe(geom: dict | None = None) -> dict:
    """Die axialen Schluessel eines Payloads auf tragfaehige Werte setzen.

    Gesetzt wird nur, was **fehlt oder ``None`` ist** -- ein ausdruecklich
    gesetzter Wert bleibt stehen. Dazu ``fluxPath="axial"``, ``p``/``slots``
    passend (16 Pole, 48 Nuten ergibt q = 1, die klassische Konzentrierte) und
    ``magShape="spm"``: eine Scheibe traegt Oberflaechenmagnete, und die
    Schemavorgabe ``"v"`` haette eine V-Tasche bedeutet, die es dort nicht gibt
    -- genau daraus fiel am 05.10.2026 eine Salienz von 2,589 in den
    Betriebspunkt (s. ``BEFUNDE.md``).

    Wer wissen muss, WAS ergaenzt wurde, nimmt ``axial_ergaenzen`` -- diese
    Fassung fuellt still, und das ist nur dort richtig, wo der Aufrufer die
    Vorgabe ausdruecklich bestellt hat (``cae_cli.py --frisch``).
    """
    g = dict(geom or {})
    g["fluxPath"] = "axial"
    for k, v in AXIAL_VORGABE.items():
        roh = g.get(k)
        fehlt = roh is None or roh == ""
        if not fehlt and k in AXIAL_PFLICHT:
            # Hier ist 0 KEINE Wahl, sondern eine Luecke.
            fehlt = _zahl(roh, 0.0) <= 0
        if fehlt:
            g[k] = v
    # Oberflaechenmagnete flach auf der Scheibe. Der Schluessel heisst radial
    # `magShape`, und `spm` ist dort genau das: Magnete auf dem Rand, ohne Tasche.
    if str(g.get("magShape") or "") in ("", "v", "vasym", "vv", "u", "delta",
                                        "pmasynrm"):
        g["magShape"] = "spm"
    # Eine Scheibe hat keine Magnettasche, also auch keine Taschenwaende: der
    # Wandmodus ist dort gegenstandslos und sein Einpassen scheitert ehrlich
    # ("auch der kuerzeste Magnet passt nicht zwischen die Waende"), weil das
    # Layouttor fuer eine Scheibe gar nicht zustaendig ist.
    g["pocketMode"] = "position"
    if not (_zahl(g.get("p"), 0) > 0):
        g["p"] = 8
    if not (_zahl(g.get("slots"), 0) >= 3):
        g["slots"] = 48
    return g
