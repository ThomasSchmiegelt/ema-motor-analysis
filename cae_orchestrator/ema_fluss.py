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
ist heute **leer**, und das ist die Aussage: keine Stufe traegt den Axialfluss.

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
STUFEN_AXIAL: tuple = ("analytisch", "feld")

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
    n = int(g.get("axialSpalte", 0) or 0) or AXIAL_BAUFORMEN[bauform]["spalte"]
    if n < 1:
        raise ValueError(f"'axialSpalte' = {n}: eine Maschine ohne Luftspalt "
                         f"hat kein Luftspaltfeld.")
    ro = d_a / 2.0 / 1000.0
    return {"r_aussen_m": ro, "r_innen_m": lam * ro, "lambda": lam,
            "n_spalte": n, "bauform": bauform,
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
