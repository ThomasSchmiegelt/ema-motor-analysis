"""Rastmoment: was ohne Strom am Umfang zerrt -- und warum es hier gerechnet wird.

Warum es das gibt
-----------------

Der Auftraggeber wollte einen Roboterarm-Antrieb, "sehr praezise auch von der
Drehgenauigkeit". Genau diese Groesse kannte das Werkzeug nicht. Es gab eine Zeile
in ``ema_analysis.compute_performance``::

    T_cogging_est = Br_NdFeB * R_gap * L_ax * 0.05 / lcm * 1000

Br des WERKSTOFFS statt des Luftspaltfelds, ein Beiwert 0,05 ohne Herkunft, und vor
allem: **die Nutoeffnung kommt darin nicht vor**. Sie ist der staerkste Hebel
ueberhaupt. Zwei Auslegungen mit gleicher Pol- und Nutzahl bekamen dieselbe Zahl,
egal wie breit die Nut zum Luftspalt hin aufging.

Warum nicht gemessen
--------------------

Der naheliegende Weg waere, den Laeufer im FDM ueber eine Rastperiode zu drehen und
das Maxwell-Moment stromlos aufzunehmen. **Das geht hier nicht**, und zwar
nachgemessen am 06.09.2026 an einer 24N/10P-Maschine (Rastperiode 3,0 Grad mech):

    N=500   T(0 Grad) = 8,70 Nm   T(3 Grad) = 0,30 Nm   Differenz -8,40
    N=700   T(0 Grad) = 0,90 Nm   T(3 Grad) = 4,10 Nm   Differenz +3,20
    N=900   T(0 Grad) = 5,50 Nm   T(3 Grad) = 3,70 Nm   Differenz -1,80

Nach einer vollen Periode MUSS derselbe Wert stehen. Es steht ein voellig anderer,
und er konvergiert mit der Aufloesung nicht. Ursache ist die Treppung: der Laeufer
liegt auf einem festen kartesischen Raster, beim Drehen springen Bildpunkte zwischen
Eisen, Magnet und Luft, und das erzeugt ein Scheinmoment, das um ein Vielfaches
groesser ist als das gesuchte. Ein Rastmoment braucht ein koerperangepasstes Netz
(Elmer/Gmsh mit Luftspaltband und Neuvernetzung je Winkel) -- eine eigene Sache.

Was hier steht, ist deshalb ein **analytisches** Modell nach Zhu/Howe. Und es ist
sauber getrennt in zwei Teile, weil die beiden verschieden belastbar sind:

**Exakt** (reine Zaehlerei, kein Modell):
  * ``n_c = kgV(Nutzahl, Polzahl)`` -- Rastperioden je Umdrehung. Je hoeher, desto
    feiner verteilt und desto kleiner die Amplitude.
  * ``C_T = Polzahl * Nutzahl / n_c`` -- der Rastfaktor nach Gieras. Kleiner ist
    besser; 1 ist das Beste, was eine Kombination erreichen kann.
  * Der Schraegungsfaktor. Eine Schraegung um genau eine Nutteilung loescht die
    Grundwelle des Rastmoments **exakt** aus -- das ist keine Naeherung, sondern
    das Integral ueber eine volle Periode.

**Geschaetzt** (Groessenordnung, Faktor ~2):
  * Die Amplitude selbst. Sie ruht auf der harmonischen Zerlegung von Nutleitwert
    und Magnetfeld und nicht auf einer Rechnung an dieser Maschine. Fuer den
    VERGLEICH zweier Auslegungen -- wofuer der Paarvergleich sie braucht -- ist das
    tragfaehig, weil beide Seiten denselben Fehler tragen. Als absolute Zusage an
    einen Kunden ist es das nicht, und so steht es auch in jeder Ausgabe.

Der wichtigste Befund vorweg
----------------------------

**Dieses Werkzeug zeichnet OFFENE Nuten.** Es gibt keinen Nutverschluss, keinen
Schlitzsteg, keine Nutschlitzbreite -- ``nut_breite`` am Bohrungsrand IST die
Oeffnung, hier gemessen 4,03 mm ueber einem Luftspalt von 0,70 mm. Das ist die
denkbar ungünstigste Anordnung fuer das Rastmoment. Wer Drehgenauigkeit braucht,
kommt an einer der drei Massnahmen nicht vorbei: Schraegung, andere Nut-/Polzahl
(hoeheres kgV) oder ein halbgeschlossener Nutschlitz, den dieses Werkzeug
zeichnerisch noch gar nicht kennt. Das steht in jeder Bewertung dabei.
"""

from __future__ import annotations

import math
from math import gcd

MU0 = 4e-7 * math.pi

# Polbedeckung: welcher Anteil der Polteilung traegt Magnetfluss. Fuer vergrabene
# Magnete (IPM) ist das keine gezeichnete Groesse -- der Polschuh fuehrt den Fluss
# und die Bedeckung ist praktisch die volle Polteilung abzueglich der Streustege.
# 0,80 ist der uebliche Ansatz und steht hier als benannte ANNAHME statt als Zahl
# mitten in einer Formel.
POLBEDECKUNG = 0.80

# Ab wann eine Auslegung "praezise" heisst. Die Baender sind Erfahrungswerte aus der
# Antriebstechnik und ausdruecklich Baender, keine Normwerte:
#   bis 1 %   Direktantriebe, Robotergelenke, Werkzeugmaschinenachsen
#   bis 3 %   allgemeiner Servoantrieb
#   bis 8 %   Traktion, Pumpen, Luefter -- dort stoert Rasten kaum
BAND_PRAEZISE = 1.0
BAND_SERVO    = 3.0
BAND_TRAKTION = 8.0


def ordnung(geom: dict) -> dict:
    """Die EXAKTEN Kennzahlen einer Nut-/Polzahl-Kombination -- reine Zaehlerei.

    Nichts hiervon ist geschaetzt: ``n_c`` ist das kleinste gemeinsame Vielfache,
    ``C_T`` der daraus gebildete Rastfaktor nach Gieras. Beide sagen mehr ueber die
    Drehgenauigkeit einer Auslegung als jede geschaetzte Amplitude, weil sie
    unabhaengig von Feld, Werkstoff und Nutform gelten.
    """
    q = max(int(geom.get("slots", 0) or 0), 1)
    poles = max(2 * int(geom.get("p", 0) or 0), 2)
    n_c = q * poles // gcd(q, poles)
    return {
        "nuten": q, "pole": poles,
        "n_c": n_c,                                   # Rastperioden je Umdrehung
        "periode_grad": 360.0 / n_c,                  # mechanisch
        "rastfaktor": round(poles * q / n_c, 3),      # Gieras C_T, kleiner ist besser
        "nuten_je_pol_und_strang": round(q / (poles * 3.0), 4),
    }


def schraegungsfaktor(geom: dict, n_c: int | None = None) -> dict:
    """Wieviel vom Rastmoment eine Schraegung uebrig laesst -- exakt, nicht geschaetzt.

    ``skew_deg`` ist die Schraegung ueber die ganze Paketlaenge in **mechanischen
    Grad** -- derselbe Schluessel, den der 3-D-Zweig (``ema_em3d``) schon benutzt,
    ausdruecklich kein zweiter. Kontinuierlich geschraegt gilt der Spaltfaktor
    ``sin(x)/x`` mit ``x = n_c*gamma/2``; in ``skew_segments`` Stufen gestaffelt
    gilt der Zonenfaktor ``sin(n*d/2)/(n*sin(d/2))``.

    Die Nullstelle liegt bei einer Schraegung um genau **eine Nutteilung**
    (``360/Nutzahl`` Grad): dann integriert sich die Grundwelle ueber eine volle
    Periode weg. Das ist der Grund, aus dem geschraegt wird, und es ist ein
    Integral, keine Naeherung.
    """
    o = ordnung(geom)
    n_c = int(n_c or o["n_c"])
    gamma = math.radians(float(geom.get("skew_deg", 0.0) or 0.0))
    stufen = max(1, int(geom.get("skew_segments", 1) or 1))
    if gamma <= 0:
        return {"faktor": 1.0, "art": "keine", "skew_grad": 0.0, "stufen": 1,
                "nutteilung_grad": round(360.0 / o["nuten"], 3)}
    if stufen >= 2:
        d = n_c * gamma / stufen
        nenner = stufen * math.sin(d / 2.0)
        f = abs(math.sin(stufen * d / 2.0) / nenner) if abs(nenner) > 1e-12 else 1.0
        art = f"gestaffelt ({stufen} Stufen)"
    else:
        x = n_c * gamma / 2.0
        f = abs(math.sin(x) / x) if x > 1e-12 else 1.0
        art = "kontinuierlich"
    return {"faktor": round(min(1.0, f), 5), "art": art,
            "skew_grad": round(math.degrees(gamma), 3), "stufen": stufen,
            "nutteilung_grad": round(360.0 / o["nuten"], 3)}


def _fourier_rechteck(m: int, anteil: float) -> float:
    """Fourierkoeffizient m-ter Ordnung eines Rechtecks der relativen Breite ``anteil``."""
    if m <= 0:
        return 0.0
    return (2.0 / (m * math.pi)) * math.sin(m * math.pi * max(0.0, min(1.0, anteil)))


def _abklingen(m: int, teilung_m: float, weg_m: float) -> float:
    """Wieviel von der m-ten Oberwelle nach ``weg_m`` Luftspalt noch ankommt.

    Ohne das taugt das Modell nicht. Reine Rechteck-Fourierkoeffizienten fallen nur
    wie ``1/m`` und schwingen dabei -- nachgerechnet lag eine 27-Nut-Auslegung mit
    kgV 270 dann kaum besser als eine 24-Nut-Auslegung mit kgV 120, was der
    Erfahrung widerspricht: ein hohes kgV ist DER Hebel gegen das Rasten.

    Physikalisch ist der Grund einfach und exakt: im stromfreien Luftspalt ist das
    Feld harmonisch (Laplace). Eine Stoerung mit der Wellenlaenge ``teilung/m``
    klingt ueber den Weg ``x`` wie ``exp(-2*pi*m*x/teilung)`` ab. Kurzwellige
    Stoerungen -- und genau das sind hohe Ordnungen -- kommen auf der Gegenseite gar
    nicht mehr an. Das ist derselbe Grund, aus dem ein weiter Luftspalt glaettet.

    Als Weg wird der **halbe** Luftspalt angesetzt: das Moment entsteht nicht an
    einer der beiden Oberflaechen, sondern im Spalt dazwischen. Das ist die eine
    Modellannahme in dieser Funktion und mit dem ganzen Spalt waere das Ergebnis
    etwa halb so gross.
    """
    if m <= 0 or teilung_m <= 0 or weg_m <= 0:
        return 1.0
    return math.exp(-2.0 * math.pi * m * weg_m / teilung_m)


def rastmoment(geom: dict, b_gap_t: float, axial_mm: float,
               nut_breite_mm: float | None = None) -> dict:
    """Rastmoment-Amplitude nach Zhu/Howe -- GESCHAETZT, mit benannten Annahmen.

    Die geschlossene Form (Zhu & Howe, IEEE Trans. Energy Conversion 2000):

        T_rast = (pi*Q*L*(R_si^2 - R_ro^2))/(4*mu0) * n_c * G_k * B_j

    mit ``k = n_c/Q`` (Ordnung der Nutleitwertwelle, die traegt) und ``j = n_c/2p``
    (Ordnung der Feldwelle, die dazu passt). Nur wo beide ganzzahlig sind, bleibt
    nach der Integration ueber den Umfang etwas stehen -- das ist derselbe
    kgV-Zusammenhang wie in ``ordnung``, nur hergeleitet statt behauptet.

    Was hier eingeht und in der alten Zeile fehlte:

    * die **Nutoeffnung** ``b_o`` (hier: die Nutbreite am Bohrungsrand, denn dieses
      Werkzeug zeichnet offene Nuten) -- ueber das Oeffnungsverhaeltnis ``b_o/Nutteilung``
      und ueber die Leitwertabsenkung ``b_o/(2*Luftspalt)``,
    * das **Luftspaltfeld** statt der Remanenz des Werkstoffs,
    * die **Schraegung**,
    * die **Polbedeckung**.

    ``guete`` sagt bei jedem Ergebnis, woran man ist.
    """
    import ema_analysis
    import ema_radien
    import ema_wicklung

    o = ordnung(geom)
    q, poles, n_c = o["nuten"], o["pole"], o["n_c"]
    r = ema_radien.radien(geom)
    r_si = r["r_stator_innen_mm"] / 1000.0
    r_ro = r["r_rotor_aussen_mm"] / 1000.0
    g_m = max(ema_analysis.luftspalt_mm(geom) / 1000.0, 1e-6)
    l_ax = max(float(axial_mm or 0.0), 1.0) / 1000.0
    b_gap = abs(float(b_gap_t))

    if nut_breite_mm is None:
        nut_breite_mm = float(ema_wicklung.nutgeometrie(geom)["nut_breite_mm"])
    b_o = max(float(nut_breite_mm), 0.0) / 1000.0
    tau_s = 2.0 * math.pi * r_si / q                       # Nutteilung am Bohrungsrand
    anteil = min(b_o / tau_s, 0.95) if tau_s > 0 else 0.0

    # Leitwertabsenkung unter der Oeffnung (Zhu): eine schmale Nut ueber einem
    # weiten Spalt stoert kaum, eine weite ueber einem engen unterbricht fast ganz.
    beta = 1.0 - 1.0 / math.sqrt(1.0 + (b_o / (2.0 * g_m)) ** 2)

    k = n_c // q                                            # Nutleitwertordnung
    j = n_c // poles                                        # Feldordnung
    tau_p = 2.0 * math.pi * r_si / poles                    # Polteilung am Bohrungsrand
    weg = g_m / 2.0                                         # halber Spalt, s. _abklingen
    d_k = _abklingen(k, tau_s, weg)                         # Nutwelle zum Laeufer hin
    d_j = _abklingen(j, tau_p, weg)                         # Feldwelle zum Stator hin
    g_k = beta * _fourier_rechteck(k, anteil) * d_k
    b_j = (b_gap ** 2) * _fourier_rechteck(j, POLBEDECKUNG) * d_j

    vor = (math.pi * q * l_ax * max(r_si ** 2 - r_ro ** 2, 0.0)) / (4.0 * MU0)
    t_roh = abs(vor * n_c * g_k * b_j)

    sk = schraegungsfaktor(geom, n_c)
    t_rast = t_roh * sk["faktor"]

    return {
        "T_rast_Nm": round(t_rast, 4),
        "T_rast_ungeschraegt_Nm": round(t_roh, 4),
        "guete": "schaetzung",
        "ordnung": o,
        "schraegung": sk,
        "nutoeffnung_mm": round(b_o * 1000.0, 3),
        "nutteilung_mm": round(tau_s * 1000.0, 3),
        "oeffnungsverhaeltnis": round(anteil, 3),
        "leitwertabsenkung": round(beta, 3),
        "b_gap_T": round(b_gap, 4),
        "offene_nut": anteil > 0.25,
        "ordnung_nutwelle": k, "ordnung_feldwelle": j,
        "abklingen_nutwelle": round(d_k, 5), "abklingen_feldwelle": round(d_j, 5),
    }


def bewerte(geom: dict, b_gap_t: float, axial_mm: float, t_nenn_nm: float,
            nut_breite_mm: float | None = None) -> dict:
    """Rastmoment im Verhaeltnis zum Nennmoment -- die Zahl, die eine Wahl entscheidet.

    Ein absolutes Rastmoment sagt fuer sich wenig: 0,2 Nm sind an einem
    200-Nm-Traktionsmotor nichts und an einem 2-Nm-Robotergelenk sehr viel. Der
    Anteil am Nennmoment ist die vergleichbare Groesse, und die Baender daneben
    sagen, wofuer das reicht.
    """
    r = rastmoment(geom, b_gap_t, axial_mm, nut_breite_mm)
    t_n = max(float(t_nenn_nm or 0.0), 1e-9)
    anteil = 100.0 * r["T_rast_Nm"] / t_n
    if anteil <= BAND_PRAEZISE:
        stufe, text = "praezise", "Direktantrieb, Robotergelenk, Werkzeugmaschinenachse"
    elif anteil <= BAND_SERVO:
        stufe, text = "servo", "allgemeiner Servoantrieb"
    elif anteil <= BAND_TRAKTION:
        stufe, text = "traktion", "Traktion, Pumpe, Luefter — dort stoert Rasten kaum"
    else:
        stufe, text = "grob", "fuer einen geregelten Antrieb zu grob"

    hinweise = []
    if anteil > 50.0:
        # Jenseits davon ist die Aussage nur noch "unbrauchbar", nicht mehr "so
        # viel". Das Modell ist an Auslegungen geeicht, die man baut; eine
        # Kombination, die ein Rastmoment in der Groesse des Nennmoments erzeugt,
        # rechnet man nicht genauer aus, man verwirft sie.
        hinweise.append(
            f"Die Schaetzung liegt bei {anteil:.0f} % des Nennmoments und damit "
            f"AUSSERHALB des Bereichs, in dem dieses Modell noch etwas aussagt. Die "
            f"Aussage lautet: diese Nut-/Polzahl-Kombination ist so nicht brauchbar — "
            f"nicht, dass es genau {anteil:.0f} % sind.")
    if r["offene_nut"]:
        hinweise.append(
            f"Die Nut ist zum Luftspalt hin OFFEN ({r['nutoeffnung_mm']:.2f} mm auf "
            f"{r['nutteilung_mm']:.2f} mm Nutteilung) — dieses Werkzeug zeichnet keinen "
            f"Nutverschluss. Das ist der staerkste einzelne Beitrag; ein "
            f"halbgeschlossener Schlitz wuerde ihn vielfach senken, laesst sich hier "
            f"aber weder zeichnen noch rechnen.")
    if r["schraegung"]["faktor"] >= 0.999:
        hinweise.append(
            f"Nicht geschraegt. Eine Schraegung um eine Nutteilung "
            f"({r['schraegung']['nutteilung_grad']:.2f} Grad, --set skew_deg=…) loescht "
            f"die Grundwelle exakt aus; das ist der wirksamste Hebel, den dieses "
            f"Werkzeug wirklich rechnen kann.")
    if r["ordnung"]["rastfaktor"] > 2.0:
        hinweise.append(
            f"Rastfaktor {r['ordnung']['rastfaktor']:.1f} (kgV {r['ordnung']['n_c']} aus "
            f"{r['ordnung']['nuten']} Nuten und {r['ordnung']['pole']} Polen) — eine "
            f"Kombination mit hoeherem kgV rastet von sich aus feiner.")

    return {**r, "T_nenn_Nm": round(t_n, 3), "anteil_pct": round(anteil, 2),
            "stufe": stufe, "stufe_text": text, "hinweise": hinweise,
            "baender_pct": {"praezise": BAND_PRAEZISE, "servo": BAND_SERVO,
                            "traktion": BAND_TRAKTION}}


def als_text(b: dict) -> list:
    """Der Befund in Zeilen -- fuer CLI, Bericht und Paarvergleich dieselbe Fassung."""
    z = [f"Rastmoment {b['T_rast_Nm']:.3f} Nm = {b['anteil_pct']:.2f} % von "
         f"{b['T_nenn_Nm']:.2f} Nm  [{b['stufe']}: {b['stufe_text']}]",
         f"  {b['ordnung']['n_c']} Rastperioden je Umdrehung "
         f"(alle {b['ordnung']['periode_grad']:.3f} Grad), Rastfaktor "
         f"{b['ordnung']['rastfaktor']:.2f}",
         f"  Nutoeffnung {b['nutoeffnung_mm']:.2f} mm auf {b['nutteilung_mm']:.2f} mm "
         f"Nutteilung, Leitwertabsenkung {b['leitwertabsenkung']:.2f}"]
    s = b["schraegung"]
    if s["faktor"] < 0.999:
        z.append(f"  Schraegung {s['skew_grad']:.2f} Grad {s['art']}: laesst "
                 f"{s['faktor']*100:.1f} % stehen "
                 f"(ungeschraegt {b['T_rast_ungeschraegt_Nm']:.3f} Nm)")
    for h in b["hinweise"]:
        z.append(f"  ⚠ {h}")
    z.append("  GESCHAETZT: analytisch nach Zhu/Howe, Amplitude auf etwa Faktor 2 genau. "
             "Der VERGLEICH zweier Auslegungen traegt, die absolute Zusage nicht — "
             "ein Rastmoment misst man an einem koerperangepassten Netz, nicht am FDM "
             "(dessen gedrehte Rastergeometrie erzeugt ein groesseres Scheinmoment).")
    return z
