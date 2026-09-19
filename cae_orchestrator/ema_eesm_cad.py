"""Schenkelpollaeufer der fremderregten Synchronmaschine — als reine Zahlen.

Warum ein eigenes Modul und nicht direkt in ``ema_freecad``
------------------------------------------------------------

``ema_freecad`` schreibt Python-TEXT fuer einen fremden Prozess und kann darin
nichts importieren. Steht die Geometrie nur dort, gibt es sie genau einmal — im
erzeugten Skript — und weder ``render_cross_section`` noch ein Test kommen an
sie heran. Genau dieser Fall ist bei den Wickelkopf-Radien schon einmal
eingetreten (``ema_wicklung.hairpin_radien``): die Zwillingsfassung musste
nachtraeglich herausgeloest werden, weil das Tor „Wickelkopf unter dem
Stator-Aussendurchmesser" sonst gegen eine Zeichnung prueft, die es nicht
kennt.

Also: die Masse entstehen HIER, in Millimetern, aus ``ema_eesm.polgeometrie``
und ``ema_eesm.erregung`` — und Zeichner, Querschnittsbild und Test lesen
dieselbe Funktion.

Wie der Pol gebaut ist
----------------------

Von aussen nach innen, je Pol:

    Polschuh    Kreisbogensegment am Laeuferrand, Breite ``b_pol`` aus der
                Polbedeckung. Er fuehrt den Fluss in den Luftspalt UND haelt die
                Erregerspule radial fest.
    Polkern     Rechteck darunter, SCHMALER als der Schuh — der Ueberstand ist
                genau der Platz, auf dem die Spule sitzt.
    Spule       zwei Querschnitte links und rechts des Kerns, radial ueber die
                Kernhoehe. Ihre Dicke folgt dem KUPFERQUERSCHNITT aus
                ``erregung`` (der aus der Stromdichte kommt), geteilt durch den
                Fuellfaktor — nicht dem verfuegbaren Platz. Das ist dieselbe
                Entscheidung wie bei der Laeuferwicklung der ASM und aus
                demselben Grund: eine Wicklung, die das Fenster fuellt, kam
                gemessen auf 0,7 A/mm^2 und 15,7 kg Kupfer — eine Maschine, die
                niemand baut.
    Joch        Ring zwischen Welle und Polfuss, Hoehe aus dem Fluss je Pol.

Was hier GEPRUEFT wird und was nicht
-------------------------------------

Geprueft wird, ob Kern und Spule auf die Polteilung passen (``passt``) und ob
zwischen zwei benachbarten Spulen Luft bleibt. **Nicht** geprueft wird die
Fliehkraft am Polfuss: ein Schenkelpol haengt am Schwalbenschwanz oder an
Bolzen, und dafuer gibt es hier kein Modell — es steht als ``ungeprueft`` im
Ergebnis statt als stilles Nichts.
"""

from __future__ import annotations

import math

# ── Wie hoch der Pol ueberhaupt ist ─────────────────────────────────────────
#
# Das war bis zum 19.09.2026 KEINE Entscheidung, sondern ein Rest: die
# Jochhoehe kam aus dem Fluss, und alles, was darueber noch bis zum Rand
# uebrig war, wurde Pol. Auf einem 188,6-mm-Laeufer sind das 47,5 mm Pol auf
# 16,8 mm Joch -- der Pol ist damit HALB so hoch wie der Laeuferradius.
#
# Ausgemessen an zwei Vorbildern ist er das nicht:
#
#     Schnittbild eines gebauten Schenkelpollaeufers   Polhoehe/r = 0,382
#     Energies 2025, 18, 3673, Tab. 5 (h_se+h_bd=19,1 auf r=38)   0,503
#
# Der Unterschied zwischen den beiden ist selbst eine Aussage: die zweite ist
# eine HOCHDREHZAHL-Maschine mit kleinem Laeufer, die erste eine gewoehnliche.
# Genommen wird die gemessene 0,38 -- und zwar als WUNSCH, nicht als Gesetz:
# das Joch muss den Fluss weiterhin fuehren, und wo es dafuer dicker sein
# muss, gewinnt der Fluss. Welche der beiden bindet, steht im Ergebnis.
POLHOEHE_ANTEIL = 0.38
POLHOEHE_SPANNE = (0.15, 0.65)

# Anteil der Polhoehe, den der Polschuh einnimmt. Der Rest ist Kern.
# Einstellbar ueber ``geom.polSchuhAnteil``; in der Bezeichnung der Literatur
# ist das ``h_s2 / (h_s2 + h_bd)``.
# Gemessen: 0,294 am Schnittbild, 0,236 in Tab. 5 der Veroeffentlichung --
# genommen wird die Mitte, und beide Belege stehen daneben.
SCHUH_ANTEIL = 0.26
SCHUH_ANTEIL_SPANNE = (0.08, 0.50)
SCHUH_MIN_MM = 3.0

# ── Die Bezeichnungen der Literatur ─────────────────────────────────────────
#
# Der Schenkelpol wird in der Fachliteratur mit vier Massen beschrieben, und
# dieses Modul rechnete sie unter eigenen Namen. Das ist keine Kosmetik: wer
# eine Auslegung gegen eine Veroeffentlichung haelt, vergleicht sonst Zahlen,
# von denen er erst herausfinden muss, ob sie dasselbe meinen.
#
#     h_s2  Hoehe des Polschuhs          (hier ``h_schuh_mm``)
#     w_s2  Breite des Polschuhs         (hier ``b_schuh_mm``)
#     h_bd  Hoehe des Polkoerpers        (hier ``h_kern_mm``)
#     w_bd  Breite des Polkoerpers       (hier ``b_kern_mm``)
#
# Sie stehen ZUSAETZLICH im Ergebnis, nicht anstelle der bisherigen -- ein
# Umbenennen haette jeden Aufrufer angefasst, und die deutschen Namen sagen an
# Ort und Stelle mehr. Die Quelle der Bezeichnung ist die Strukturskizze einer
# EESM-Arbeit (MDPI Energies 18(14):3673); der Text selbst war nicht abrufbar
# (HTTP 403), es ist also NUR die Benennung uebernommen und keine Zahl.
LITERATUR_NAMEN = {"h_s2_mm": "h_schuh_mm", "w_s2_mm": "b_schuh_mm",
                   "h_bd_mm": "h_kern_mm", "w_bd_mm": "b_kern_mm"}

# Kernbreite als Anteil der Polschuhbreite -- nur noch als OBERE Schranke.
# Bestimmt wird sie jetzt aus der Deckung (s. `koerper`).
#
# 0,72 und auch 0,62 waren VIEL zu breit, und das ist jetzt belegt statt
# geschaetzt: eine gerechnete und gebaute EESM (Energies 2025, 18, 3673,
# Tab. 5: w_se/h_se = 31,5/4,5 mm, w_bd/h_bd = 11,5/14,6 mm) hat
#
#     w_bd / w_se = 11,5 / 31,5 = 0,365
#
# Der Kern ist dort also gut ein Drittel so breit wie sein Schuh, nicht zwei
# Drittel. Was er zuviel nimmt, fehlt der Erregerwicklung -- gemeldet als
# „die Wicklung passt immer noch nicht", und sie passte wirklich nicht: bei
# 0,62 blieben 2 x 3,8 mm Spule, mit dem belegten Verhaeltnis sind es 2 x 10 mm.
# Der Ueberstand des Schuhs betraegt dort (31,5-11,5)/2 = 10 mm je Seite; die
# Spule sitzt also wirklich UNTER dem Schuh, wofuer er da ist.
#
# Einstellbar ueber ``geom.polKernAnteil``. Der Preis steht als Zahl daneben:
# ein schmaler Kern fuehrt denselben Polfluss durch weniger Eisen, und
# ``b_kern_T`` sagt, wie weit das traegt.
KERN_ZU_SCHUH = 0.38
KERN_ANTEIL_SPANNE = (0.25, 0.85)

# Wieviel Flussdichte der Polkern tragen darf, bezogen auf die Saettigung des
# Blechs. 0,92 laesst dem Blech etwas Luft -- die oertliche Ueberhoehung an der
# Schuhkante ist hier nicht gerechnet.
KERN_B_ANTEIL = 0.92
KERN_FUELLFAKTOR = 0.96          # Blechfuellfaktor des Polkerns

# ── Der Polfuss reicht IN das Joch, er sitzt nicht darauf ──────────────────
#
# Er war zuvor eine Verbreiterung OBERHALB des Jochrings: der Kern lief von
# ``b_kern`` auf die halbe Polteilung auf und stand damit als Keil im
# Zwischenpolraum. Gemeldet als „unten muss der Polschuh tiefer in den Rotor
# reichen, zur Zeit ist dort eine Art Keil" -- und gemessen war es genau das:
# ueber die unteren 5,8 mm der Kernhoehe verdoppelte sich die Kernbreite von
# 21,7 auf 43,9 mm, und die Spule konnte deshalb nur 19,4 der 26,5 mm
# Kernhoehe nutzen.
#
# Zwei Dinge sprachen dagegen, und beide sind Messungen und keine Ansicht:
#
#  * Der Keil war der Rest einer aelteren Zeichnung. Er entstand, als der
#    Kern noch ein TRAPEZ war (nach innen schmaler, ``KERN_B_ANTEIL``) und
#    zwischen zwei Polen nach innen ein Dreieck klaffte. Seit der Kern ein
#    Rechteck ist (``b_kern_innen == b_kern_aussen``), gibt es dieses Dreieck
#    nicht mehr -- der Fuss schloss eine Luecke, die es nicht mehr gab.
#  * Er widersprach der Befestigung, die daneben gerechnet wird: ein
#    Schwalbenschwanz ist am HALS SCHMALER als der Kern
#    (``ema_schenkelpol.HALS_ZU_KERN`` = 0,70), nicht doppelt so breit, und er
#    sitzt in einer Nut IM Joch statt als Kragen darauf.
#
# Jetzt laeuft der Polkoerper mit ``b_kern`` durch bis auf den Jochring, und
# der Fuss ist das Stueck DARUNTER: Hals (``b_hals``), der sich nach innen auf
# ``b_fuss`` oeffnet, ``h_fuss`` tief im Joch. Gezeichnet wird er nicht --
# Joch und Pol werden zu EINEM Festkoerper verschmolzen, eine Nut darin waere
# im Schnitt unsichtbar; gerechnet wird er in ``ema_schenkelpol.befestigung``.
POLFUSS_ANTEIL = 0.22          # Anteil der Kernhoehe, den der Fuss tief ins Joch reicht
POLFUSS_LUFT_MM = 2.0          # Restjoch unter dem Fuss, ueber der Flusshoehe

# Wie weit der Polschuh die Spule ueberragt [mm je Seite].
#
# Das ist keine Kosmetik, sondern die mechanische Aufgabe des Polschuhs:
# „salient pole tips overhang the pole body to secure the field coil in place
# against the action of centrifugal force" (US3089049A, US3728566). Ohne
# Ueberstand haelt die Spule nichts -- sie sitzt auf einem drehenden Koerper.
SCHUH_UEBERSTAND_MM = 2.0

# Wie schmal der Kern hoechstens werden darf, bezogen auf die Schuhbreite am
# Kernradius. Darunter traegt der Pol den Fluss nicht mehr, und dann ist die
# Spule zu dick fuer diesen Pol -- das wird GESAGT statt gezeichnet.
KERN_MIN_ANTEIL = 0.35

# Kegeliger Pol: zur JOCHseite SCHMALER, und die Wicklung folgt dieser Neigung.
#
# Die Richtung war verkehrt, und der Grund ist messbar: die Polteilung
# schrumpft nach innen. Am Joch (r = 46,8 mm, 6 Pole) sind es 48,97 mm, unter
# dem Schuh (r = 83,8) schon 87,80 mm. Ein Kern, der nach innen BREITER wird,
# frisst also genau dort, wo der Platz am knappsten ist: gemessen blieben am
# Joch 7,03 mm fuer zwei Spulenseiten samt Luft, waehrend unter dem Schuh
# 54,25 mm frei standen -- und die Schranke ``joch`` band deshalb immer. Genau
# umgekehrt herum folgt der Kern der Teilung und die Spule bekommt dort Raum,
# wo sie ihn braucht. Gemeldet als „der Kegel ist in die falsche Richtung".
#
# Der Wert ist das Verhaeltnis INNEN zu AUSSEN: 0,80 heisst, der Kern ist am
# Joch vier Fuenftel so breit wie unter dem Schuh.
KEGEL_VERJUENGUNG = 0.80
SPULENFORMEN = ("rechteck", "kegel")

# Luft zwischen den Spulen zweier benachbarter Pole [mm].
SPULENLUFT_MM = 2.0

# Mindestdicke einer gezeichneten Spulenseite [mm].
SPULE_MIN_MM = 2.0

# Wie SCHLANK eine Spulenseite hoechstens sein darf (Hoehe zu Dicke).
#
# Das war der eigentliche Grund fuer „die Wicklung passt immer noch nicht":
# der Wickelraum wurde ueber die GANZE Kernhoehe ausgestrichen, und heraus kam
# ein Film -- gemessen 2 x 3,8 mm dick auf 28,9 mm Hoehe, also h/d = 7,6. Eine
# gewickelte Erregerspule ist aber ein BUENDEL: sie hat so viele Lagen wie
# Windungen je Lage, und im Bild einer gebauten Maschine sitzt sie als
# kompakter Block unter dem Polschuh (h/d ~ 1...3), nicht als Haut am Kern.
#
# Die Kupfermenge aendert sich dadurch NICHT -- nur ihre Form. Gerechnet wird
# weiter aus dem Kupferquerschnitt; was sich aendert, ist das Seitenverhaeltnis,
# unter dem er untergebracht wird.
SPULE_SCHLANKHEIT_MAX = 3.0

# Wo die Spule sitzt: dicht unter dem Polschuh, der sie gegen die Fliehkraft
# haelt. Sie am Fuss beginnen zu lassen waere die Stelle, an der nichts sie
# haelt -- der Schuh ist genau dafuer da (US3089049A).
SPULE_UNTER_SCHUH_MM = 0.5

# Wie weit die Spule ueber dem Jochring endet [mm] -- eine Lage Isolierung.
#
# Sie darf jetzt bis dorthin hinunter, weil der Polkoerper mit voller Breite
# bis auf das Joch durchlaeuft. Frueher stand der Polfuss im Weg und nahm die
# unteren 5,8 von 26,5 mm Kernhoehe weg; der Wickelraum musste deshalb in
# 19,4 mm untergebracht werden und die Spule wurde entsprechend dick.
SPULE_UEBER_JOCH_MM = 1.0

# Wie weit Kern und Spule vom Laeuferrand wegbleiben muessen [mm].
#
# Das ist die Wand, die gefehlt hat. Kern und Spule sind RECHTECKE, der Laeufer
# ist ein KREIS: ein Rechteck der halben Breite ``y``, dessen Oberkante bei
# ``r`` liegt, hat seine Ecken bei ``sqrt(r^2 + y^2)`` -- also WEITER aussen als
# seine Oberkante. Geprueft wurde bisher nur die Oberkante, und deshalb stand
# die Erregerspule einer 170-mm-Maschine gemessen mit ihren Ecken bei
# r = 88,63 mm, waehrend die Statorbohrung bei 85,8 mm anfaengt: die Spule lag
# IM Staender. Gemeldet als „in der fremderregten Maschine kollidieren Rotor
# und Stator", und genau so war es.
RAND_LUFT_MM = 1.0


def _spule_einpassen(a_wick_mm2: float, r_joch: float, y_kern: float,
                     r_max: float, r_deckel: float = 0.0) -> tuple:
    """Dicke und Aussenradius der Erregerspule, so dass ihre ECKEN drinbleiben.

    Gesucht ist das Paar ``(d, r_top)`` mit

        d * (r_top - r_joch) = a_wick/2            (Wickelraum je Spulenseite)
        sqrt(r_top^2 + (y_kern + d)^2) = r_max     (die Ecke liegt auf dem Rand)

    Eingesetzt bleibt EINE Gleichung in ``d``; sie ist nicht monoton (eine
    dickere Spule muss tiefer sitzen und wird dadurch kuerzer), hat also ein
    Maximum. Genommen wird die KLEINERE Wurzel -- die duennere, hoehere Spule:
    sie sitzt naeher am Polschuh und wird von ihm gehalten.

    Gibt es keine Wurzel, passt die Wicklung nicht unter den Rand. Dann kommt
    ``ok=False`` heraus und das beste erreichbare Paar dazu -- gezeichnet wird
    etwas, das im Laeufer bleibt, und der Befund steht daneben.
    """
    ziel = max(a_wick_mm2, 0.0) / 2.0
    d_max = math.sqrt(max(r_max ** 2 - r_joch ** 2, 0.0)) - y_kern
    # Mit dem Kerndeckel ist die Hoehe nach oben begrenzt, die Dicke also
    # nicht mehr durch die Ecke allein: ohne diese Reserve findet die Suche
    # eine Wurzel nicht, die es gibt.
    if r_deckel > 0.0 and r_deckel > r_joch:
        d_max = max(d_max, ziel / (r_deckel - r_joch) * 1.2)
    if d_max <= SPULE_MIN_MM:
        return SPULE_MIN_MM, max(r_joch + 1.0, 0.0), False

    def hoehe(d: float) -> float:
        # Zwei Deckel, und der KLEINERE gilt: die Ecke darf nicht aus dem
        # Laeufer treten (r_max), und die Spule sitzt NEBEN dem Kern, kann also
        # nicht hoeher werden als er (r_deckel). Ohne den zweiten kam eine
        # Loesung heraus, die der Aufrufer anschliessend abschnitt -- und dann
        # fasste die gezeichnete Spule weniger als den geforderten Wickelraum
        # (gemessen 186 gegen 219 mm²), ohne dass irgendwo etwas widersprach.
        r_top = math.sqrt(max(r_max ** 2 - (y_kern + d) ** 2, 0.0))
        if r_deckel > 0.0:
            r_top = min(r_top, r_deckel)
        return r_top - r_joch

    n = 400
    bestes = (SPULE_MIN_MM, hoehe(SPULE_MIN_MM))
    vorher = SPULE_MIN_MM * hoehe(SPULE_MIN_MM) - ziel
    if vorher >= 0.0:
        return SPULE_MIN_MM, r_joch + hoehe(SPULE_MIN_MM), True
    for i in range(1, n + 1):
        d = SPULE_MIN_MM + (d_max - SPULE_MIN_MM) * i / n
        f = d * hoehe(d) - ziel
        if d * hoehe(d) > bestes[0] * bestes[1]:
            bestes = (d, hoehe(d))
        if f >= 0.0:                      # Vorzeichenwechsel -> einschachteln
            lo, hi = d - (d_max - SPULE_MIN_MM) / n, d
            for _ in range(60):
                m = 0.5 * (lo + hi)
                if m * hoehe(m) - ziel < 0.0:
                    lo = m
                else:
                    hi = m
            return hi, r_joch + hoehe(hi), True
        vorher = f
    # Keine Wurzel: der Wickelraum passt nicht unter den Rand. Gezeichnet wird
    # die groesstmoegliche Spule, damit das Bild nicht leer bleibt.
    return bestes[0], r_joch + bestes[1], False


SPULENFUELLUNGEN = ("vorgabe", "max")

# Wie weit die Polbedeckung mitwachsen darf, wenn die Spule den Bauraum
# ausfuellen soll [-]. Obergrenze wie im Schema (`polbedeckung`).
BEDECKUNG_MAX = 0.85


def wickelraum(geom: dict, axial_mm: float, bedeckung: float = 0.0) -> dict:
    """Der Wickelraum, den die ZEICHNUNG wirklich hergibt -- je Pol, in mm.

    Reine Geometrie: diese Funktion ruft ``erregung`` ausdruecklich NICHT auf,
    damit ``erregung`` sie umgekehrt benutzen kann. Sonst haette der
    Kupferquerschnitt zwei Quellen -- die analytische Fensterformel in
    ``ema_eesm._pol_fenster`` und die gezeichnete Spule -- und die beiden
    liefen auseinander, ohne dass es jemand merkt.

    Und sie laufen auseinander: ``_pol_fenster`` rechnet ein RECHTECK
    (Fensterbreite mal Fensterhoehe) und kennt weder den Polschuh, der die
    Spule halten muss, noch dass die Polteilung nach innen schrumpft.
    Gemessen an der Beispielmaschine (2p = 8, Rotor 188,6, Welle 38,
    Polbedeckung 0,55): 2024 mm^2 analytisch gegen 672 mm^2 zeichenbar.

    Drei Schranken, und es gilt die engste:

    * **Polteilung.** Neben dem Kern bleibt bei Radius r die halbe Breite
      ``(2*pi*r/2p - SPULENLUFT)/2 - b_kern/2``. Die waechst nach aussen und
      wird nach innen NEGATIV -- unterhalb von r = 30,2 mm ueberdecken sich
      die Polkoerper (das ist die Nabe), dort ist ueberhaupt kein Platz.
    * **Polschuh.** Er muss die Spule gegen die Fliehkraft halten, also darf
      sie nicht breiter sein als sein Ueberstand: ``(b_schuh_k - b_kern)/2 -
      SCHUH_UEBERSTAND_MM``.
    * **Laeuferrand.** Die Spule ist ein Rechteck im Kreis; ihre AUSSERE Ecke
      muss drin bleiben.

    Weil beide ersten Schranken in r linear bzw. konstant sind, ist ihr
    Minimum konkav -- ein TRAPEZ zwischen den beiden Endpunkten liegt deshalb
    ueberall darunter und kann nicht kollidieren. Genau das wird gezeichnet,
    und genau deshalb ist die kegelige Spule hier nicht Zierat, sondern die
    Form, die der Bauraum vorgibt.
    """
    import ema_eesm as _EE
    pg = _EE.polgeometrie(geom, axial_mm)
    poles = int(pg["poles"])
    r_rot = float(geom["rotorOD"]) / 2.0
    r_wel = max(float(geom["shaftD"]) / 2.0, 1.0)
    tau_pol = float(pg["tau_pol_mm"])
    alpha = float(bedeckung) if bedeckung > 0 else _EE.polbedeckung(geom)
    b_schuh = alpha * tau_pol

    anteil_pol = float(geom.get("polHoeheAnteil") or 0.0) or POLHOEHE_ANTEIL
    anteil_pol = min(max(anteil_pol, POLHOEHE_SPANNE[0]), POLHOEHE_SPANNE[1])
    r_schuh_bezug = min(max(r_rot * (1.0 - anteil_pol), r_wel + 2.0), r_rot - 2.0)
    h_pol = max(r_rot - r_schuh_bezug, 2.0)
    schuh_anteil = float(geom.get("polSchuhAnteil") or 0.0) or SCHUH_ANTEIL
    schuh_anteil = min(max(schuh_anteil, SCHUH_ANTEIL_SPANNE[0]),
                       SCHUH_ANTEIL_SPANNE[1])
    h_schuh = max(SCHUH_MIN_MM, min(schuh_anteil * h_pol, 0.6 * h_pol))
    r_kern_aussen = r_rot - h_schuh
    # Die Schuhbreite am KERNradius -- derselbe Bogenwinkel, kleinerer Radius.
    # Und dort als SEHNE gedeckelt: `b_pol` ist eine Bogenlaenge, und bei
    # sehr breiten Polen (2p = 2, alpha 0,85: Bogen 251,8 mm bei einem Laeufer
    # von 188,6 mm Durchmesser) ist sie als kartesische Breite sinnlos. Ohne
    # den Deckel wuchs der Kern aus dem Laeufer heraus (gemessen r bis
    # 95,43 gegen 94,30 mm Rand).
    _halb_w = min((b_schuh / 2.0) / max(r_rot, 1e-9), 0.5 * math.pi - 1e-3)
    b_schuh_k = min(b_schuh * (r_kern_aussen / max(r_rot, 1e-9)),
                    2.0 * r_kern_aussen * math.sin(_halb_w))

    # Die Kernbreite aus dem FLUSS -- in dieser Betriebsart die einzige
    # Schranke, die ihn nach unten haelt: je schmaler der Kern, desto groesser
    # der Wickelraum, und schmaler als der Fluss erlaubt geht er nicht.
    import ema_pipeline as _PL
    lam = _PL.LAMINATES.get(
        str(geom.get("rotor_lam") or geom.get("rotorLam") or "m270_35a"),
        _PL.LAMINATES["m270_35a"])
    b_sat = float(lam.get("B_sat_T") or 2.0)
    b_m = _EE.ziel_feld(geom)
    b_kern = (b_m * b_schuh
              / max(KERN_B_ANTEIL * b_sat * KERN_FUELLFAKTOR, 1e-9))
    b_kern = max(b_kern, KERN_MIN_ANTEIL * b_schuh_k)
    r_max = max(r_rot - RAND_LUFT_MM, r_wel + 1.0)
    b_kern = min(b_kern, 2.0 * math.sqrt(max(r_max ** 2 - r_kern_aussen ** 2, 0.0)))

    d_schuh = (b_schuh_k - b_kern) / 2.0 - SCHUH_UEBERSTAND_MM

    def _d_teilung(r):
        return (2.0 * math.pi * r / poles - SPULENLUFT_MM) / 2.0 - b_kern / 2.0

    # Wo die Spule anfangen KANN: dort, wo neben dem Kern gerade SPULE_MIN_MM
    # Platz ist. Weiter innen ueberdecken sich die Polkoerper.
    r_innen = (poles * (2.0 * (SPULE_MIN_MM + b_kern / 2.0) + SPULENLUFT_MM)
               / (2.0 * math.pi))
    r_min = max(r_innen, r_wel + SPULE_UEBER_JOCH_MM)
    r_aussen = r_kern_aussen - SPULE_UNTER_SCHUH_MM
    d_ecke = math.sqrt(max(r_max ** 2 - r_aussen ** 2, 0.0)) - b_kern / 2.0
    d_aussen = min(_d_teilung(r_aussen), d_schuh, d_ecke)

    # Wo die Spule ANFAENGT, wird gesucht statt gesetzt.
    #
    # Die Huellkurve ist konkav (Teilung linear, Schuh konstant), die Sehne
    # zwischen zwei Punkten auf ihr liegt also ueberall darunter -- das Trapez
    # kann nicht kollidieren. Es laesst aber je nach Anfangspunkt verschieden
    # viel Flaeche liegen: ganz unten angesetzt ist es lang und spitz, am Knick
    # angesetzt kurz und voll. Gemessen an der Beispielmaschine 369 gegen
    # 444 mm^2 -- also wird der Anfang durchgefahren und der beste genommen.
    r_innen, d_innen, a_wick = r_min, min(SPULE_MIN_MM, max(d_aussen, 0.0)), -1.0
    if d_aussen > 0.0 and r_aussen > r_min:
        for _i in range(101):
            _r = r_min + (r_aussen - r_min) * _i / 100.0
            _d = min(_d_teilung(_r), d_schuh, d_ecke)
            if _d < SPULE_MIN_MM:
                continue
            _a = 2.0 * 0.5 * (_d + d_aussen) * (r_aussen - _r)
            if _a > a_wick:
                r_innen, d_innen, a_wick = _r, _d, _a
    a_wick = max(a_wick, 0.0)
    # Und der Kern selbst muss im Laeufer bleiben: er ist ein Rechteck im
    # Kreis, seine ECKE liegt weiter aussen als seine Oberkante.
    passt = (d_aussen >= SPULE_MIN_MM
             and r_aussen - r_innen >= SPULE_MIN_MM
             and math.hypot(r_kern_aussen, b_kern / 2.0) <= r_max + 1e-6)
    h = max(r_aussen - r_innen, 0.0)
    return {
        "bedeckung": round(alpha, 4),
        "b_schuh_mm": round(b_schuh, 3),
        "b_kern_mm": round(b_kern, 3),
        "r_innen_mm": round(r_innen, 3),
        "r_aussen_mm": round(r_aussen, 3),
        "d_innen_mm": round(d_innen, 3),
        "d_aussen_mm": round(d_aussen, 3),
        "h_mm": round(h, 3),
        "A_wickelraum_mm2": round(max(a_wick, 0.0), 1),
        "bindet": ("schuh" if d_schuh <= min(_d_teilung(r_aussen), d_ecke)
                   else ("rotorrand" if d_ecke <= _d_teilung(r_aussen)
                         else "teilung")),
        "passt": bool(passt),
    }


def wickelraum_max(geom: dict, axial_mm: float) -> dict:
    """Die beste Polbedeckung fuer den Wickelraum -- gemessen, nicht geraten.

    Das „Dach" darf mitwachsen: ein breiterer Polschuh ueberdeckt eine dickere
    Spule. Er zwingt aber zugleich einen BREITEREN Kern (der Schuh nimmt mehr
    Fluss auf), und der frisst den Platz schneller, als der Ueberstand ihn
    gewinnt. Ob es sich lohnt, entscheidet deshalb eine Messung ueber die
    erlaubte Spanne und keine Regel. Nach unten wird nicht gesucht: die
    Polbedeckung ist eine magnetische Entscheidung des Menschen, hier darf sie
    nur FOLGEN.
    """
    import ema_eesm as _EE
    a0 = _EE.polbedeckung(geom)
    beste = wickelraum(geom, axial_mm, a0)
    beste["bedeckung_vorgabe"] = round(a0, 4)
    schritt = 0.01
    a = a0
    while a < BEDECKUNG_MAX - 1e-9:
        a = min(a + schritt, BEDECKUNG_MAX)
        kand = wickelraum(geom, axial_mm, a)
        if (kand["passt"] and
                kand["A_wickelraum_mm2"] > beste["A_wickelraum_mm2"] + 1e-6):
            kand["bedeckung_vorgabe"] = round(a0, 4)
            beste = kand
    beste["bedeckung_gewachsen"] = bool(
        beste["bedeckung"] > beste["bedeckung_vorgabe"] + 1e-9)
    return beste


def fuellung(geom: dict) -> str:
    """``vorgabe`` (Stromdichte entscheidet) oder ``max`` (Bauraum entscheidet)."""
    f = str(geom.get("erregerSpuleFuellung") or "vorgabe")
    return f if f in SPULENFUELLUNGEN else "vorgabe"


def koerper(geom: dict, axial_mm: float) -> dict:
    """Alle Masse des Schenkelpollaeufers in Millimetern.

    Radien sind absolut (von der Wellenachse), Breiten in Millimetern **am
    jeweiligen Radius** — der Zeichner setzt daraus Rechtecke und Kreisbogen-
    segmente, das Querschnittsbild dieselben.
    """
    import ema_eesm

    # Bei `max` darf das „Dach" mitwachsen: ein breiterer Polschuh ueberdeckt
    # eine dickere Spule, zwingt aber zugleich einen breiteren Kern. Was von
    # beidem ueberwiegt, ENTSCHEIDET EINE MESSUNG (`wickelraum_max`) -- und
    # ihr Ergebnis muss dann durch die ganze Rechnung gehen, sonst haetten
    # Zeichnung und Magnetkreis verschiedene Polschuhe.
    alpha_eff = ema_eesm.polbedeckung(geom)
    if fuellung(geom) == "max":
        alpha_eff = wickelraum_max(geom, axial_mm)["bedeckung"]
        if abs(alpha_eff - ema_eesm.polbedeckung(geom)) > 1e-9:
            geom = dict(geom, polbedeckung=alpha_eff)

    pg = ema_eesm.polgeometrie(geom, axial_mm)
    er = ema_eesm.erregung(geom, axial_mm)

    poles = int(pg["poles"])
    r_rot = float(geom["rotorOD"]) / 2.0
    r_wel = max(float(geom["shaftD"]) / 2.0, 1.0)
    # ── Der Polkoerper laeuft bis an die WELLE, es gibt keinen Jochring ──
    #
    # Frueher sass der Pol auf einem vollen Jochring (Vorgabe: 38 % des
    # Laeuferhalbmessers Pol, der Rest Joch), und der Wickelraum war damit auf
    # die oberen 26,5 von 75,3 mm beschraenkt. Jetzt laeuft der Kern, auf den
    # die Spule gewickelt ist, mit seiner Breite bis auf die Wellenbohrung
    # durch; die Welle wird zuletzt abgezogen. Das Joch ist damit kein eigener
    # Ring mehr, sondern das, was die Polkoerper nahe der Bohrung MITEINANDER
    # bilden -- sie ueberdecken sich dort (s. `nabe_r_mm`).
    #
    # `h_joch_fluss` bleibt die Bedingung, die der Fluss stellt, und wird
    # gegen diese NABE gehalten statt gegen einen Ring: reicht sie nicht, ist
    # das ein Befund (`nabe_reicht`, `B_nabe_T`) und keine stille Korrektur.
    h_joch_fluss = float(pg["h_joch_mm"])
    # Der Bezugsradius fuer die Schuhhoehe -- die einzige Groesse, die noch an
    # der frueheren Polhoehe haengt. Ohne ihn waere der Schuh auf einmal
    # `schuh_anteil * (r_rot - r_wel)` hoch, also mehr als doppelt so dick,
    # obwohl an ihm niemand etwas geaendert hat.
    anteil_pol = float(geom.get("polHoeheAnteil") or 0.0) or POLHOEHE_ANTEIL
    anteil_pol = min(max(anteil_pol, POLHOEHE_SPANNE[0]), POLHOEHE_SPANNE[1])
    r_schuh_bezug = min(max(r_rot * (1.0 - anteil_pol), r_wel + 2.0),
                        r_rot - 2.0)
    r_joch = r_wel                       # kein Ring: der Kern beginnt an der Welle
    joch_bindet = False
    h_joch = 0.0

    h_pol = max(r_rot - r_schuh_bezug, 2.0)             # Bezug fuer die Schuhhoehe
    schuh_anteil = float(geom.get("polSchuhAnteil") or 0.0) or SCHUH_ANTEIL
    schuh_anteil = min(max(schuh_anteil, SCHUH_ANTEIL_SPANNE[0]),
                       SCHUH_ANTEIL_SPANNE[1])
    h_schuh = max(SCHUH_MIN_MM, min(schuh_anteil * h_pol, 0.6 * h_pol))
    r_kern_aussen = r_rot - h_schuh
    # Die Kernhoehe ist jetzt die GANZE Strecke von der Welle bis unter den
    # Schuh -- das ist der Wickelraum, den der Umbau bringt.
    h_kern = max(r_kern_aussen - r_wel, 1.0)

    b_schuh = float(pg["b_pol_mm"])                     # Bogenlaenge am Rand
    tau_pol = float(pg["tau_pol_mm"])
    # Die Kernbreite wird am KERNradius gemessen, die Polbedeckung aber am
    # Rand. Ohne die Umrechnung waere der Kern bei kleinem Laeufer breiter als
    # die Teilung, die ihm dort zusteht.
    tau_kern = 2.0 * math.pi * r_kern_aussen / poles
    # Die Schuhbreite AM KERNRADIUS -- derselbe Bogenwinkel, kleinerer Radius.
    # Die Schuhbreite am KERNradius -- derselbe Bogenwinkel, kleinerer Radius.
    # Und dort als SEHNE gedeckelt: `b_pol` ist eine Bogenlaenge, und bei
    # sehr breiten Polen (2p = 2, alpha 0,85: Bogen 251,8 mm bei einem Laeufer
    # von 188,6 mm Durchmesser) ist sie als kartesische Breite sinnlos. Ohne
    # den Deckel wuchs der Kern aus dem Laeufer heraus (gemessen r bis
    # 95,43 gegen 94,30 mm Rand).
    _halb_w = min((b_schuh / 2.0) / max(r_rot, 1e-9), 0.5 * math.pi - 1e-3)
    b_schuh_k = min(b_schuh * (r_kern_aussen / max(r_rot, 1e-9)),
                    2.0 * r_kern_aussen * math.sin(_halb_w))

    # Spulendicke aus dem KUPFERquerschnitt, nicht aus dem Platz.
    kf = ema_eesm._fuellfaktor()
    a_cu = float(er["A_cu_mm2"])
    a_wick = a_cu / max(kf, 1e-6)                       # mm^2, Wickelraum je Pol

    form = str(geom.get("erregerSpuleForm") or "rechteck")
    if form not in SPULENFORMEN:
        form = "rechteck"
    # Verhaeltnis innen:aussen des Kerns -- beim Rechteck 1,0, beim Kegel
    # kleiner als 1 (am Joch schmaler, s. KEGEL_VERJUENGUNG).
    kegel = KEGEL_VERJUENGUNG if form == "kegel" else 1.0

    r_max = max(r_rot - RAND_LUFT_MM, r_joch + 1.0)
    # Die Blechsorte aus der EINEN Tabelle -- vor der Schleife, weil die
    # Fluss-Schranke sie braucht.
    import ema_pipeline as _PLv
    _lam_v = _PLv.LAMINATES.get(
        str(geom.get("rotor_lam") or geom.get("rotorLam") or "m270_35a"),
        _PLv.LAMINATES["m270_35a"])
    b_sat_vorab = float(_lam_v.get("B_sat_T") or 2.0)
    import ema_eesm as _EEv
    b_m_vorab = _EEv.ziel_feld(geom)

    kern_anteil = float(geom.get("polKernAnteil") or 0.0) or KERN_ZU_SCHUH
    kern_anteil = min(max(kern_anteil, KERN_ANTEIL_SPANNE[0]),
                      KERN_ANTEIL_SPANNE[1])

    # Der Polkoerper beginnt AM JOCH -- der Fuss liegt darunter, im Joch.
    #
    # `r_fuss` ist damit die Unterkante des Koerpers und zugleich die
    # Oberkante des Jochrings; die Spule darf bis dorthin hinunter. Die Tiefe
    # des Fusses ist nach unten durch den Fluss begrenzt: unter ihm muss das
    # Joch noch die Hoehe behalten, die `ema_eesm.polgeometrie` verlangt.
    r_fuss = r_joch
    _joch_frei = max(h_joch - h_joch_fluss - POLFUSS_LUFT_MM, 0.0)
    h_fuss = max(min(POLFUSS_ANTEIL * h_kern, _joch_frei), 0.0)
    # Die Spule steht auf dem Joch, nicht IM Joch: eine Lage Isolierung.
    r_wickel_boden = min(r_fuss + SPULE_UEBER_JOCH_MM, r_kern_aussen - 1.0)

    # ── Kern und Spule haengen voneinander ab, also wird gekoppelt geloest ──
    #
    # Die Kernbreite folgt der Spulendicke (Deckung, Platz am Joch), die
    # Spulendicke aber der verbleibenden Hoehe -- und die haengt wieder an der
    # Kernbreite, weil die Spulenecke auf dem Laeuferrand landen muss. Vier
    # Durchgaenge genuegen (gemessen: der zweite bewegt noch 0,3 mm, der
    # vierte 1e-4 mm); der Startwert ist der alte, aus der vollen Kernhoehe
    # gerechnete -- damit bleibt eine Auslegung, bei der die Ecke nie stoerte,
    # Ziffer fuer Ziffer dieselbe.
    d_spule = max(SPULE_MIN_MM, a_wick / (2.0 * max(h_kern, 1e-9)))
    r_spule = r_kern_aussen
    spule_passt = True
    for _durchgang in range(4):
        # ── Vier Schranken, und es gilt die engste ────────────────────────
        # (1) DECKUNG: der Polschuh muss die Spule ueberragen, sonst haelt sie
        #     nichts gegen die Fliehkraft (US3089049A).
        # (2) PLATZ AM SPULENFUSS: die Polteilung schrumpft nach innen, der
        #     Kern ist beim Rechteck aber ueber die ganze Hoehe gleich breit.
        #     Geprueft wurde bisher nur am KERNradius, wo reichlich Platz ist --
        #     gemessen durchdringen sich dadurch ab acht Polen die Spulen
        #     benachbarter Pole um 3,9 mm. Massgeblich ist der Radius, an dem
        #     die SPULE endet, nicht die Welle: die Polkoerper duerfen sich
        #     nahe der Bohrung ueberdecken -- dort bilden sie die Nabe --, die
        #     Spulen duerfen es nicht. Der Kegel entschaerft die Schranke, weil
        #     er dem Schrumpfen der Teilung folgt.
        # (3) LAEUFERRAND: der Kern ist ein Rechteck im Kreis, seine ECKEN
        #     liegen weiter aussen als seine Oberkante (s. RAND_LUFT_MM).
        # (4) die alte obere Schranke: ein Kern fast so breit wie sein Schuh
        #     liesse keinen Platz fuer die Wicklung.
        # Die Spule ist ein Buendel (h/d <= SPULE_SCHLANKHEIT_MAX), ihr Fuss
        # liegt also hoechstens so tief unter dem Schuh.
        r_eng = max(r_wickel_boden,
                    r_kern_aussen - SPULE_UNTER_SCHUH_MM
                    - SPULE_SCHLANKHEIT_MAX * d_spule)
        tau_eng = 2.0 * math.pi * r_eng / poles
        schranken = {
            "deckung": b_schuh_k - 2.0 * (d_spule + SCHUH_UEBERSTAND_MM),
            "teilung": (tau_eng - SPULENLUFT_MM - 2.0 * d_spule) / kegel,
            "rotorrand": 2.0 * math.sqrt(
                max(r_max ** 2 - r_kern_aussen ** 2, 0.0)),
            "kernanteil": kern_anteil * b_schuh_k,
        }
        bindend = min(schranken, key=lambda k: schranken[k])
        b_kern_aussen = schranken[bindend]
        # ── Die FLUSS-Schranke, und sie zieht nach UNTEN ──────────────────
        #
        # Der Kern fuehrt den ganzen Polfluss, den der Schuh aus dem Luftspalt
        # aufnimmt. Aus der Flusserhaltung folgt unmittelbar
        #
        #     B_kern = B_m * w_s2 / (w_bd * k_fe)
        #
        # -- die Laenge kuerzt sich heraus, es ist ein reines
        # BREITENverhaeltnis. Ein schmaler Kern ist also nicht umsonst zu
        # haben, und deshalb ist die aus der Literatur uebernommene Schlankheit
        # (w_bd/w_s2 = 0,365) keine Vorgabe, sondern eine OBERE Schranke: ob
        # sie erreichbar ist, entscheidet das Luftspaltfeld. Bei B_m = 0,80 T
        # und M270-35A sind es gemessen 0,49, bei 0,60 T dagegen 0,37.
        b_kern_fluss = (b_m_vorab * b_schuh
                        / max(KERN_B_ANTEIL * b_sat_vorab * KERN_FUELLFAKTOR, 1e-9))
        if b_kern_fluss > b_kern_aussen:
            bindend = "kernfluss"
            b_kern_aussen = b_kern_fluss
        b_kern_min = KERN_MIN_ANTEIL * b_schuh_k
        passt = b_kern_aussen >= b_kern_min
        b_kern_aussen = max(b_kern_aussen, b_kern_min)
        # Der Laeuferrand ist die EINE Schranke, die das Mindestmass nicht
        # ueberstimmen darf: ein zu schmaler Kern ist ein Befund, ein Kern
        # ausserhalb des Laeufers ist eine falsche Zeichnung. Passt es nicht,
        # steht `passt=False` schon oben -- gezeichnet wird trotzdem etwas,
        # das im Blech bleibt.
        # Geteilt wird nur, wenn der Kegel nach INNEN breiter wird (kegel > 1)
        # -- dann ist die Innenbreite die groessere. `KEGEL_VERJUENGUNG` ist
        # aber 0,80, der Kern also aussen breiter, und dann klemmte die
        # Division die falsche Seite: gemessen bei 2p = 2 stand die Kernecke
        # bei 95,43 mm gegen einen Rand von 94,30 mm.
        b_kern_aussen = min(b_kern_aussen,
                            schranken["rotorrand"] / max(kegel, 1.0))
        b_kern_innen = b_kern_aussen * kegel
        # Die Spule sitzt NEBEN dem Kern: massgeblich ist die breiteste Stelle
        # (beim Kegel die Jochseite), sonst waere gerade dort die Ecke draussen.
        y_kern = max(b_kern_aussen, b_kern_innen) / 2.0
        d_neu, r_spule, spule_passt = _spule_einpassen(
            a_wick, r_wickel_boden, y_kern, r_max, r_kern_aussen)
        if abs(d_neu - d_spule) < 1e-4:
            d_spule = d_neu
            break
        d_spule = d_neu
    d_spule = max(d_spule, SPULE_MIN_MM)
    r_spule = min(max(r_spule, r_wickel_boden + 1.0), r_kern_aussen)

    # ── Aus dem Film wird ein Buendel ────────────────────────────────────
    #
    # Bis hierher ist `d_spule` die Dicke, die den Wickelraum ueber die ganze
    # verfuegbare Hoehe ausstreicht. Das ist die duennste moegliche Loesung und
    # sieht auch so aus. Jetzt wird derselbe Querschnitt auf ein Verhaeltnis
    # gebracht, das eine Wicklung wirklich hat -- die FLAECHE bleibt gleich,
    # nur ihre Form aendert sich.
    _hoehe_frei = max(r_spule - r_wickel_boden, 0.5)
    _a_seite = max(a_wick / 2.0, 1e-9)                 # mm^2 je Spulenseite
    _d_kompakt = math.sqrt(_a_seite / max(SPULE_SCHLANKHEIT_MAX, 0.1))
    d_spule = max(d_spule, min(_d_kompakt, 0.5 * max(schranken["deckung"], 0.0)
                               if schranken.get("deckung", 0) > 0 else _d_kompakt))
    d_spule = max(d_spule, SPULE_MIN_MM)
    h_spule_soll = min(_a_seite / d_spule, _hoehe_frei)
    # Reicht die Hoehe fuer diese Dicke nicht, wird sie wieder duenner --
    # sonst waere die gezeichnete Flaeche kleiner als der Wickelraum.
    if h_spule_soll < _a_seite / d_spule - 1e-6:
        d_spule = _a_seite / _hoehe_frei
        h_spule_soll = _hoehe_frei
    # Die Spule haengt UNTER dem Polschuh, der sie haelt.
    r_spule_aussen = r_spule - SPULE_UNTER_SCHUH_MM
    r_spule_innen = max(r_spule_aussen - h_spule_soll, r_wickel_boden)
    r_spule = r_spule_aussen
    # Letzter Riegel: auch im Fehlerfall bleibt die gezeichnete Ecke drin.
    _y_aussen = max(b_kern_aussen, b_kern_innen) / 2.0 + d_spule
    r_spule = min(r_spule, math.sqrt(max(r_max ** 2 - _y_aussen ** 2, 1.0)))
    h_spule = r_spule_aussen - r_spule_innen
    d_spule_innen = d_spule                  # Rechteckspule: beide Enden gleich

    # ── Bauraum statt Stromdichte: die Spule fuellt den Zwischenpolraum ──
    #
    # Dann bemisst nicht `A_cu` die Spule, sondern die Zeichnung -- und
    # `ema_eesm.erregung` liest DIESELBE Funktion, damit Kupfermasse,
    # Stromdichte und Erregerverlust zu dem gehoeren, was gebaut wird.
    # Die Spule wird dabei KEGELIG: die Polteilung waechst nach aussen, also
    # der Platz neben dem Kern auch.
    fuellung_hinweis = ""
    if fuellung(geom) == "max":
        _w = wickelraum(geom, axial_mm, alpha_eff)
        if _w["passt"]:
            b_kern_aussen = _w["b_kern_mm"]
            b_kern_innen = b_kern_aussen * kegel
            d_spule = _w["d_aussen_mm"]
            d_spule_innen = _w["d_innen_mm"]
            r_spule_innen = _w["r_innen_mm"]
            r_spule_aussen = _w["r_aussen_mm"]
            r_spule = r_spule_aussen
            h_spule = max(r_spule_aussen - r_spule_innen, 0.1)
            a_wick = _w["A_wickelraum_mm2"]
            spule_passt = True
            fuellung_hinweis = ""
        else:
            # Kein Nein, sondern ein Rueckfall: bleibt vom Zwischenpolraum
            # nichts Wickelbares uebrig (sehr wenige, sehr breite Pole), wird
            # weiter ueber die Stromdichte bemessen -- und das steht dann da,
            # statt dass der ganze Laeufer als unzeichenbar abgewiesen wird.
            fuellung_hinweis = (
                "Fuellung 'max' nicht moeglich: zwischen den Polen bleibt "
                "kein wickelbarer Raum (d_aussen %.2f mm, r %.1f…%.1f mm) -- "
                "bemessen wurde ueber die Stromdichte."
                % (_w["d_aussen_mm"], _w["r_innen_mm"], _w["r_aussen_mm"]))
    b_kern = b_kern_aussen                   # was ein Zeichner liest, der nur EINE Breite kennt

    # Der Fuss: der Pol sitzt nicht mehr auf einem Ring, er IST bis zur
    # Bohrung durchgezogen. `ema_schenkelpol.befestigung` rechnet weiter einen
    # Schwalbenschwanz (Hals schmaler als der Kern) -- das ist jetzt die
    # Nachrechnung fuer einen aufgesetzten Pol und steht als solche daneben.
    import ema_schenkelpol as _SPv
    b_hals = _SPv.HALS_ZU_KERN * b_kern_innen
    b_fuss = b_kern_innen

    # ── Die NABE: was die Polkoerper nahe der Bohrung miteinander bilden ──
    #
    # Zwei benachbarte Koerper der halben Breite w, deren Achsen 2*pi/poles
    # auseinanderliegen, ueberdecken sich bis zum Radius w/sin(pi/poles): dort
    # schneiden sich ihre Flanken. Unterhalb davon ist der Laeufer voll, und
    # genau dieser Ring ist das Joch -- es gibt keinen anderen mehr.
    # Gemessen wird deshalb, ob er traegt: `h_nabe` gegen `h_joch_fluss`, und
    # daraus die Flussdichte, die wirklich darin steht.
    r_nabe = (b_kern_innen / 2.0) / max(math.sin(math.pi / poles), 1e-9)
    h_nabe = max(r_nabe - r_wel, 0.0)
    zusammen = r_nabe > r_wel + 1e-6
    b_nabe_T = (b_m_vorab * b_schuh / max(2.0 * h_nabe * KERN_FUELLFAKTOR, 1e-9)
                if h_nabe > 1e-9 else float("inf"))
    nabe_reicht = h_nabe >= h_joch_fluss - 1e-6

    # Nachgerechnet statt angenommen: alles drei sind ERGEBNISSE, keine Vorgaben.
    ueberstand = (b_schuh_k - (b_kern_aussen + 2.0 * d_spule)) / 2.0
    deckt = ueberstand >= 0.0
    belegt = b_kern_innen + 2.0 * d_spule
    # Der engste Punkt zwischen zwei Wicklungen liegt am Spulenfuss.
    tau_spule = 2.0 * math.pi * r_spule_innen / poles
    frei = tau_spule - belegt
    # Die Kernbreite AM SPULENENDE -- eine Zahl, drei Zeichner.
    #
    # Die Spule liegt am Kern an, endet aber weiter innen als er. Beim Kegel
    # ist der Kern dort schmaler als an seiner Oberkante; ohne diesen Wert
    # muesste jeder Zeichner die Verjuengung selbst ausmultiplizieren, und beim
    # dritten stuende eine andere Spule im Bild als im CAD.
    def _b_bei(r):
        # Die Kernbreite an einem beliebigen Radius -- der Kegel verjuengt
        # linear zwischen Fuss und Schuh.
        u = (r - r_fuss) / max(r_kern_aussen - r_fuss, 1e-9)
        return b_kern_innen + (b_kern_aussen - b_kern_innen) * min(max(u, 0.0), 1.0)

    b_kern_spulenende = _b_bei(r_spule_aussen)
    b_kern_spuleanfang = _b_bei(r_spule_innen)

    # Die Flussdichte IM POLKERN -- aus der Flusserhaltung, nicht aus einem
    # Feldlauf (dasselbe Verfahren wie `ema_saettigung`: der Kern fuehrt den
    # Fluss, den der Schuh aus dem Luftspalt aufnimmt).
    #
    #     Phi_pol = B_m * w_s2 * L        (Schuhflaeche am Luftspalt)
    #     B_kern  = Phi_pol / (w_bd * L * k_fe) = B_m * w_s2/(w_bd * k_fe)
    #
    # Die Laenge kuerzt sich heraus -- es ist ein reines BREITENverhaeltnis,
    # und genau deshalb ist ein schmaler Kern nicht umsonst zu haben.
    b_m, k_fe, _lam, b_sat = b_m_vorab, KERN_FUELLFAKTOR, _lam_v, b_sat_vorab
    b_kern_T = b_m * b_schuh / max(b_kern_aussen * k_fe, 1e-9)
    kern_saettigt = b_kern_T > b_sat

    # Die Ecke, an der es frueher hinauslief -- jetzt gemessen statt angenommen.
    r_ecke_kern = math.hypot(r_kern_aussen, max(b_kern_aussen, b_kern_innen) / 2.0)
    r_ecke_spule = math.hypot(r_spule, max(b_kern_aussen, b_kern_innen) / 2.0
                              + d_spule)
    im_laeufer = max(r_ecke_kern, r_ecke_spule) <= r_rot + 1e-6
    if not spule_passt:
        passt = False

    if passt:
        grund = ""
    elif not spule_passt:
        grund = (f"Der Wickelraum ({a_wick:.0f} mm² je Pol) passt nicht unter "
                 f"den Laeuferrand: mehr als {d_spule * h_spule * 2:.0f} mm² "
                 f"sind zwischen Joch (r = {r_joch:.1f} mm) und Rand "
                 f"(r = {r_max:.1f} mm) nicht unterzubringen, ohne dass die "
                 f"Spulenecke aus dem Laeufer tritt. Groesserer Laeufer, "
                 f"hoehere Stromdichte oder weniger Pole")
    elif bindend == "rotorrand":
        grund = (f"Der Polkern bleibt mit seinen Ecken nicht im Laeufer: bei "
                 f"r = {r_kern_aussen:.1f} mm duerfte er hoechstens "
                 f"{schranken['rotorrand']:.1f} mm breit sein, das Mindestmass "
                 f"sind aber {b_kern_min:.1f} mm. Ein dickerer Polschuh "
                 f"(kleinerer Kernradius) oder weniger Polbedeckung")
    elif not deckt:
        grund = (f"Der Polschuh ueberdeckt die Spule NICHT: er ist am "
                 f"Kernradius {b_schuh_k:.1f} mm breit, Kern ({b_kern:.1f}) "
                 f"und Spule (2 x {d_spule:.1f} mm) brauchen aber "
                 f"{b_kern + 2 * d_spule:.1f} mm. Die Spule haengt dann ueber "
                 f"und wird von nichts gegen die Fliehkraft gehalten — mehr "
                 f"Polbedeckung oder eine duennere Spule (hoehere Stromdichte)")
    elif frei < SPULENLUFT_MM:
        grund = (f"Kern ({b_kern_innen:.1f} mm an der engsten Stelle) und "
                 f"Spule (2 x {d_spule:.1f} mm) belegen {belegt:.1f} mm — es "
                 f"bleiben {frei:.1f} mm statt der geforderten "
                 f"{SPULENLUFT_MM:.1f} mm Luft zum Nachbarpol")
    else:
        grund = (f"Die Spule ist zu dick fuer diesen Pol: die engste Schranke "
                 f"ist '{bindend}' und liesse nur {schranken[bindend]:.1f} mm "
                 f"Kern, unter dem Mindestmass von {b_kern_min:.1f} mm. "
                 f"Mehr Polbedeckung, weniger Pole oder eine hoehere "
                 f"Stromdichte")

    return {
        "poles": poles,
        "r_welle_mm": round(r_wel, 3),
        "r_joch_aussen_mm": round(r_joch, 3),
        "h_joch_mm": round(h_joch, 3),
        "h_joch_fluss_mm": round(h_joch_fluss, 3),
        "polhoehe_anteil": round((r_rot - r_joch) / max(r_rot, 1e-9), 3),
        "joch_bindet": bool(joch_bindet),
        "r_kern_aussen_mm": round(r_kern_aussen, 3),
        "r_rotor_mm": round(r_rot, 3),
        "h_pol_mm": round(h_pol, 3),
        "h_schuh_mm": round(h_schuh, 3),
        "h_kern_mm": round(h_kern, 3),
        "b_schuh_mm": round(b_schuh, 3),
        "b_kern_mm": round(b_kern, 3),
        # Kegel: zwei Breiten statt einer. Bei `rechteck` sind sie gleich, und
        # jeder Zeichner, der nur `b_kern_mm` liest, bleibt richtig.
        "spulenform": form,
        "b_kern_aussen_mm": round(b_kern_aussen, 3),
        "b_kern_innen_mm": round(b_kern_innen, 3),
        "schuh_ueberstand_mm": round(ueberstand, 3),
        "deckt_spule": bool(deckt),
        "d_spule_mm": round(d_spule, 3),
        # Zwei Dicken: bei der Rechteckspule gleich, bei der ausgefuellten
        # (kegeligen) innen duenner -- die Polteilung schrumpft nach innen.
        "d_spule_innen_mm": round(d_spule_innen, 3),
        "d_spule_aussen_mm": round(d_spule, 3),
        "fuellung": fuellung(geom),
        "fuellung_hinweis": fuellung_hinweis,
        "bedeckung_eff": round(alpha_eff, 4),
        # Der Aussenradius der SPULE ist nicht der des Kerns: die Spule sitzt
        # neben ihm und muesste mit ihrer Ecke sonst aus dem Laeufer treten.
        "r_spule_aussen_mm": round(r_spule, 3),
        # Der Polfuss liegt UNTER `r_fuss_mm` -- im Joch, nicht darauf:
        # `h_fuss_mm` tief, am Hals `b_hals_mm` schmal, unten `b_fuss_mm`.
        # Gezeichnet wird er nicht (Joch und Pol sind EIN Festkoerper),
        # gerechnet in `ema_schenkelpol.befestigung`.
        "r_spule_innen_mm": round(r_spule_innen, 3),
        "spule_schlankheit": round(h_spule / max(d_spule, 1e-9), 2),
        "b_kern_spuleanfang_mm": round(b_kern_spuleanfang, 3),
        "r_fuss_mm": round(r_fuss, 3),
        "h_fuss_mm": round(h_fuss, 3),
        "b_fuss_mm": round(b_fuss, 3),
        "b_hals_mm": round(b_hals, 3),
        # Die Nabe: was die Polkoerper an der Bohrung MITEINANDER bilden --
        # es gibt keinen Jochring mehr, der sie traegt.
        "r_nabe_mm": round(r_nabe, 3),
        "h_nabe_mm": round(h_nabe, 3),
        "B_nabe_T": (round(b_nabe_T, 3) if b_nabe_T != float("inf") else None),
        "nabe_reicht": bool(nabe_reicht),
        "nabe_zusammen": bool(zusammen),
        "kern_anteil": round(kern_anteil, 3),
        "schuh_anteil": round(schuh_anteil, 3),
        "B_kern_T": round(b_kern_T, 3),
        "B_kern_grenze_T": round(b_sat, 3),
        "kern_saettigt": bool(kern_saettigt),
        "blech": str(_lam.get("label") or ""),
        "b_kern_spulenende_mm": round(b_kern_spulenende, 3),
        "h_spule_mm": round(h_spule, 3),
        "r_ecke_kern_mm": round(r_ecke_kern, 3),
        "r_ecke_spule_mm": round(r_ecke_spule, 3),
        "im_laeufer": bool(im_laeufer),
        "tau_pol_mm": round(tau_pol, 3),
        "tau_kern_mm": round(tau_kern, 3),
        "belegt_mm": round(belegt, 3),
        "frei_mm": round(frei, 3),
        "passt": bool(passt),
        "bindend": bindend,
        "grund": grund,
        "A_cu_mm2": round(a_cu, 2),
        "A_wickelraum_mm2": round(a_wick, 2),
        "fuellfaktor": round(kf, 3),
        "I_f_A": float(er["I_f_A"]),
        "F_pol_A": float(er["F_pol_A"]),
        "fenster_reicht": bool(er["fenster_reicht"]),
        # Was dieses Modul NICHT weiss. Ein Schenkelpol haengt am
        # Schwalbenschwanz oder an Bolzen; die Fliehkraft daran rechnet hier
        # niemand, und ein Schweigen darueber laese sich als „geprueft" lesen.
        "h_s2_mm": round(h_schuh, 3),      # Literatur: Polschuhhoehe
        "w_s2_mm": round(b_schuh, 3),      # Literatur: Polschuhbreite
        "h_bd_mm": round(h_kern, 3),       # Literatur: Polkoerperhoehe
        "w_bd_mm": round(b_kern, 3),       # Literatur: Polkoerperbreite
        "ungeprueft": ("Die Kernflussdichte kommt aus der FLUSSERHALTUNG "
                       "(Breitenverhaeltnis Schuh zu Kern), nicht aus einem "
                       "Feldlauf: oertliche Ueberhoehung an der Schuhkante und "
                       "die Streuung zwischen den Polen sind darin nicht "
                       "enthalten. Fuer die Fliehkraft am Polfuss gibt es "
                       "ema_schenkelpol.befestigung"),
    }


def mit_literaturnamen(k: dict) -> dict:
    """Dieselben Masse zusaetzlich unter den Symbolen der Literatur.

    Kein zweiter Satz Zahlen -- eine Zuordnung. Wer ``h_bd`` liest, bekommt
    denselben Wert wie ``h_kern_mm``, und zwar denselben, nicht einen neu
    gerechneten.
    """
    aus = dict(k)
    for sym, eigen in LITERATUR_NAMEN.items():
        if eigen in k:
            aus[sym] = k[eigen]
    return aus


def zeichenmasse(k: dict) -> dict:
    """Nur die Zahlen, die ein erzeugtes Skript braucht.

    Urteile (``passt``, ``grund``, ``ungeprueft``) bleiben draussen: sie
    gehoeren ins Protokoll, und ein ``true``/``null`` aus JSON waere im
    erzeugten **Python**-Skript ein NameError — gemessen genau daran
    gescheitert (s. ``ema_schleifring.zeichenmasse``).
    """
    k = mit_literaturnamen(k)
    return {n: float(k[n]) for n in (
        "r_welle_mm", "r_joch_aussen_mm", "r_kern_aussen_mm", "r_rotor_mm",
        "h_schuh_mm", "h_kern_mm", "b_schuh_mm", "b_kern_mm", "d_spule_mm",
        "b_kern_aussen_mm", "b_kern_innen_mm", "r_spule_aussen_mm",
        "b_kern_spulenende_mm", "r_fuss_mm", "h_fuss_mm", "b_fuss_mm",
        "d_spule_innen_mm", "d_spule_aussen_mm",
        "r_spule_innen_mm", "b_kern_spuleanfang_mm",
    )} | {"poles": int(k["poles"])}
