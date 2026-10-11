"""Der Laeufer der Reluktanzmaschine -- als reine Zahlen, nach Auslegungsregeln.

**Warum es dieses Modul gibt.** Bis zum 20.09.2026 zeichnete das Werkzeug den
SynRM-Laeufer als *IPM-Laeufer ohne Magnete*: `ema_laeuferbild._synrm` nahm die
Taschenlage aus `ema_topology.magnet_legs` und liess sie leer. Gemeldet als „in
der reluktanzmaschine sind nur die magnete entfernt. das ist doch nicht
richtig." -- und das ist richtig. Eine Magnettasche sitzt dort, wo ein Magnet
Platz braucht; eine **Flussbarriere** sitzt dort, wo der q-Fluss durch muss. Das
sind zwei verschiedene Geometrien, und die zweite hat eigene, seit den 1990ern
ausgearbeitete Regeln.

Gerechnet wird hier nichts Elektrisches -- das bleibt bei `ema_synrm`. Hier
entsteht die GEOMETRIE, wie in `ema_eesm_cad` fuer den Schenkelpol, und zwar an
EINER Stelle, damit Leinwand, FDM-Raster, Querschnittsbild und CAD dieselben
Zahlen sehen.

Quellen (abgerufen 20.09.2026, Volltext):

* R. R. Moghaddam, *Synchronous Reluctance Machine (SynRM) Design*, MSc-Arbeit,
  KTH / ABB Corporate Research, 2007 — diva2:753114. Kapitel 5.1.3/5.1.4 und
  6.2. Daraus die vier tragenden Regeln unten.
* T. J. E. Miller, *Some essential features of the synchronous reluctance
  motor*, JMAG Engineer's Diary Nr. 34 — die Begruendung der Barrierenform:
  „the flux-guides follow, more or less, the pattern of flux lines that would
  be obtained without the rotor".

## Die vier Regeln

**(1) Zahl der Barrieren je Pol `k`.** Die Laeufer-„Nutteilung" `alpha_m` soll
gleich der Staendernutteilung sein oder ein Vielfaches davon (Moghaddam 5.1.3,
Fig. 5.8). Mit `alpha_m = pi/(p*(2k+1))` und der Staendernutteilung
`2*pi/slots` heisst das

    slots = 2*p*(2k+1)   <=>   k = (slots/(2*p) - 1)/2

Fuer den im Bericht durchgerechneten Staender (36 Nuten, 4 Pole) kommt damit
k = 4 heraus -- genau die Zahl, die dort als geeignet benannt wird. Geht die
Rechnung nicht auf, gilt die zweite Regel: `k` etwas groesser als die Lochzahl
`q = slots/(6p)`. Ueber **5 Barrieren** bringt es nichts mehr („increasing the
number of barriers more than 5 ... will not have any significant gain",
Moghaddam 8.1.3), darunter wird es schnell schlecht (gemessenes Moment 105 ->
150 -> 157 N·m bei 1 -> 3 -> 5 Barrieren).

**(2) Wo die Barrieren an den Luftspalt stossen.** Konstante Laeufernutteilung
(Moghaddam 6.2.1, Fig. 6.3): die Endpunkte liegen bei

    theta_h = (2h-1) * alpha_m/2,   h = 1..k,   von der d-Achse aus gemessen

mit einem gedachten (k+1)-ten Punkt bei `(2k+1)*alpha_m/2`. Der Rest bis zur
q-Achse ist der Freiwinkel `beta` -- ein ausdruecklicher Freiheitsgrad zur
Beeinflussung der Momentwelligkeit, hier als Vorgabe 0.

**(3) Welche FORM eine Barriere hat.** Sie folgt einer **Feldlinie** des
Feldes, das ohne Laeufer im Luftspalt stuende. Fuer ein 2p-poliges Feld ist die
Stromfunktion im Zylinder `Psi ~ r^p * sin(p*theta)`; eine Feldlinie ist also

    r^p * sin(p*theta) = const

In der q-Achse (`phi` von dort gemessen) wird daraus `r(phi) =
(C/cos(p*phi))^(1/p)` -- symmetrisch zur q-Achse, mit dem kleinsten Radius
GENAU dort, und beide Enden am Luftspalt. Das ist keine Naeherung an ein Bild,
sondern die geschlossene Loesung, an der sich die Bauform orientiert; beide
Raender einer Barriere sind solche Linien, die Barriere ist also ueberall
feldlinienparallel.

**(4) Wie DICK sie sind.** Ueber den Isolationsgrad
`k_w = Summe(Luft) / Summe(Eisen)` entlang der q-Achse (Moghaddam 5.1.4,
Fig. 5.12): fuer das Moment (~ Ld-Lq) liegt der Bestwert des **Mittelwerts im
Laeufer zwischen 0,2 und 0,6**; in der q-Achse allein liegt er hoeher (im
Bericht 0,96). Vorgabe hier 0,5.

## Was NICHT drin ist, und das steht auch in der Ausgabe

* Kein **Cut-off** (die zusaetzliche Barriere unmittelbar an der q-Achse,
  Moghaddam Fig. 6.1b). Sie bringt im Bericht bei kleiner Barrierenzahl mehr
  Moment und bei k >= 4 fast nichts mehr.
* Keine **Radialstege** in der Barrierenmitte. Der Tangentialsteg am Rand wird
  gezeichnet und begrenzt; ob er die Fliehkraft traegt, rechnet er NICHT --
  dafuer gibt es `ema_rotorcheck`/die Struktur-FEM, und der Steg eines
  Reluktanzlaeufers ist ein eigener Fall (mehrere duenne Bruecken in Reihe).
* Keine **Schraegung** und keine Optimierung der Momentwelligkeit ueber
  ungleiche Endwinkel (Moghaddam nennt beides als den wirksamen Hebel).
"""

from __future__ import annotations

import math

# Ueber 5 Barrieren bringt es nichts mehr (Moghaddam 8.1.3); unter 2 ist es
# kein Reluktanzlaeufer, sondern eine angeschnittene Scheibe.
K_MIN, K_MAX = 2, 5

# Bestwert des mittleren Isolationsgrads im Laeufer (Moghaddam Fig. 5.12).
KW_BAND = (0.2, 0.6)
KW_VORGABE = 0.5

# Tangentialsteg zwischen Barrierenende und Laeuferrand. Dieselbe
# Groessenordnung wie der Steg ueber der Magnettasche (`ema_topology.BRIDGE_MM`)
# und aus demselben Grund: er haelt das Segment gegen die Fliehkraft.
STEG_RAND_MM = 1.0
# Was zwischen zwei Barrieren und zur Welle mindestens an Eisen stehen bleibt.
STEG_MIN_MM = 1.5
BARRIERE_MIN_MM = 1.0

# Stuetzstellen je Barrierenrand. 28 sind bei den hier vorkommenden Winkeln
# unter einem Promille Flaechenfehler und halten die Teileliste klein.
N_STUETZ = 28


def _kw(geom: dict) -> float:
    w = float((geom or {}).get("synrmIsolationsgrad") or 0.0)
    return w if w > 0.0 else KW_VORGABE


def barrierenzahl(geom: dict) -> dict:
    """Wieviele Barrieren je Pol -- und woher die Zahl kommt.

    Regel (1) im Modulkopf. Gibt die Zahl UND ihre Begruendung zurueck, weil
    eine Zahl ohne Herkunft hier nichts wert ist: sie entscheidet die Bauform.
    """
    vor = int(float((geom or {}).get("synrmBarrieren") or 0))
    slots = max(int((geom or {}).get("slots") or 0), 1)
    p = max(int((geom or {}).get("p") or 1), 1)
    q = slots / (6.0 * p)
    # Die Nutteilungsregel: slots = 2p(2k+1)
    k_roh = (slots / (2.0 * p) - 1.0) / 2.0
    passt = abs(k_roh - round(k_roh)) < 1e-6 and K_MIN <= round(k_roh) <= K_MAX
    if vor > 0:
        k, grund = vor, "vorgegeben"
    elif passt:
        k = int(round(k_roh))
        grund = (f"Laeufernutteilung = Staendernutteilung: "
                 f"slots = 2p(2k+1) = {2 * p * (2 * k + 1)} = {slots}")
    else:
        k = int(min(max(round(q) + 1, K_MIN), K_MAX))
        grund = (f"Nutteilungsregel geht nicht auf (slots/(2p) = "
                 f"{slots / (2.0 * p):.2f}); statt dessen k > q = {q:.2f}")
    geklemmt = ""
    if k < K_MIN or k > K_MAX:
        geklemmt = (f"{k} Barrieren: ausserhalb von {K_MIN}…{K_MAX} — unter "
                    f"{K_MIN} ist die Reluktanzwirkung schwach, ueber {K_MAX} "
                    f"bringt sie nichts mehr (Moghaddam 8.1.3)")
    return {"k": int(min(max(k, K_MIN), K_MAX)), "grund": grund, "q": round(q, 3),
            "nutteilung_passt": bool(passt), "befund": geklemmt}


def _bogen(r_q: float, r_e: float, phi_e: float, n: int):
    """Ein Kreisbogen, symmetrisch zur q-Achse, durch ZWEI vorgegebene Punkte.

    Die Barriere muss beides treffen: ihren q-Achsen-Radius (aus der
    Flussregel, 6.2.2) und ihren Endpunkt am Luftspalt (aus der
    Nutteilungsregel, 6.2.1). Aus Symmetriegruenden liegt der Mittelpunkt auf
    der q-Achse, damit sind drei Bedingungen erfuellt und der Kreis eindeutig:

        c = (r_q^2 - r_e^2) / (2*(r_q - r_e*cos(phi_e))),   rho = r_q - c

    Warum ein Bogen und nicht die Feldlinie selbst: die Feldlinie
    ``r^p cos(p*phi) = const`` hat nur EINEN freien Wert und kann deshalb nur
    einen der beiden Punkte treffen. Der Bogen ist die uebliche praktische
    Naeherung an sie (und die Bauform, die als „circular flux barrier" in der
    Literatur steht).
    """
    nenner = 2.0 * (r_q - r_e * math.cos(phi_e))
    if abs(nenner) < 1e-9:
        c = 0.0
    else:
        c = (r_q * r_q - r_e * r_e) / nenner
    rho = abs(r_q - c)
    # WELCHE der beiden Schnittstellen. Bei phi = 0 sind die Wurzeln c +- rho;
    # gemeint ist die, auf der `r_q` liegt. Ohne diese Fallunterscheidung kam
    # bei p = 2 durchgehend die aeussere heraus, und alle vier Barrieren lagen
    # als Strich auf dem Laeuferrand (gemessen, bevor es jemand sehen konnte).
    vz = 1.0 if r_q >= c else -1.0
    aus = []
    for i in range(n + 1):
        phi = -phi_e + 2.0 * phi_e * i / n
        # Schnittpunkt des Strahls phi mit dem Kreis um (c, 0) mit Radius rho.
        b_ = c * math.cos(phi)
        d = b_ * b_ - (c * c - rho * rho)
        r = (b_ + vz * math.sqrt(d)) if d > 0 else r_q
        aus.append((phi, min(max(r, 0.1), r_e)))
    return aus


def mittellinien(geom: dict, axial_mm: float | None = None) -> list:
    """Jede Barriere als **dicke Polylinie**: Mittellinie plus Dicke.

    Fuer Verbraucher, die keine Polygone bauen koennen -- namentlich den
    3-D-Netzbauer, der Barrieren seit jeher als Kette von Kastenprismen
    zusammensetzt (`ema_em3d.barrier_rects`). Die Punkte kommen aus DEMSELBEN
    Bogen wie die beiden Raender des Polygons, es ist also keine zweite
    Geometrie -- nur eine andere Sicht auf dieselben Zahlen.

    Der Rahmen ist der der q-Achse; wer sie im Laeufer haben will, dreht sie um
    die Zwischenpolachse (wie `ema_laeuferbild._synrm`).
    """
    b = barrieren(geom, axial_mm)
    return [{"punkte": x["mittellinie"], "dicke_mm": x["dicke_mm"]}
            for x in b.get("barrieren") or []]


def barrieren(geom: dict, axial_mm: float | None = None) -> dict:
    """Die Flussbarrieren EINER Polteilung, im Rahmen der q-Achse.

    Gibt je Barriere den geschlossenen Polygonzug in Millimetern zurueck (x
    entlang der q-Achse nach aussen, y quer dazu), dazu die Kennzahlen, mit
    denen man die Auslegung beurteilt: q-Achsen-Radius, Dicke, Endwinkel am
    Luftspalt und den ERREICHTEN Isolationsgrad -- der weicht vom gewuenschten
    ab, sobald ein Mindeststeg bindet, und das soll dastehen statt geraten zu
    werden.
    """
    p = max(int((geom or {}).get("p") or 1), 1)
    r_rot = float(geom["rotorOD"]) / 2.0
    r_wel = float(geom.get("shaftD") or 0.0) / 2.0
    bz = barrierenzahl(geom)
    k = bz["k"]
    befund = [bz["befund"]] if bz["befund"] else []

    steg_rand = float(geom.get("synrmStegMm") or 0.0) or STEG_RAND_MM
    r_e = r_rot - steg_rand                      # dort enden die Barrieren
    r_in = r_wel + STEG_MIN_MM
    if r_e <= r_in + (k + 1) * (BARRIERE_MIN_MM + STEG_MIN_MM):
        return {"k": k, "barrieren": [], "grund": (
            f"Zwischen Welle ({2 * r_wel:.1f} mm) und Laeuferrand "
            f"({2 * r_rot:.1f} mm) ist kein Platz fuer {k} Barrieren"),
            "passt": False, "befund": befund, "kw_soll": _kw(geom)}

    beta = math.radians(float(geom.get("synrmBetaGrad") or 0.0))
    # Regel (2): konstante Laeufernutteilung.
    alpha_m = (math.pi / p - 2.0 * beta) / (2.0 * k + 1.0)
    # Endwinkel von der d-Achse, umgerechnet auf den Abstand zur q-Achse.
    phi_e = [math.pi / (2.0 * p) - (2 * h - 1) * alpha_m / 2.0
             for h in range(1, k + 1)]
    # Regel (3): die Feldlinie durch den Endpunkt. Ihr q-Achsen-Radius:
    r_q = [r_e * (math.cos(p * pe) ** (1.0 / p)) for pe in phi_e]

    # Regel (4) + die Segmentregel aus 6.2.2 -- und sie legen die LAGE fest.
    #
    # Ein erster Entwurf hat die Barrieren auf die Feldlinie durch ihren
    # Endpunkt gesetzt und die Dicke daraus abgeleitet. Das ist ueberbestimmt:
    # gemessen kam Barriere 1 auf 26,8 mm und die Barrieren 3 und 4 fielen ganz
    # aus. Richtig herum ist es umgekehrt -- die Lage folgt aus dem FLUSS, den
    # das Eisen darunter tragen muss, und die Form verbindet sie dann mit dem
    # Endpunkt:
    #
    #   * Eisensegment h traegt den Fluss, den es ueber seinen Bogen des
    #     Luftspalts aufnimmt, also ~ sin(p*theta_h) - sin(p*theta_(h-1))
    #     (Moghaddam 6.2.2, bei konstanter Nutteilung gleichbedeutend mit
    #     „Segmentbreite ~ speisende MMK");
    #   * der Isolationsgrad teilt die Strecke in Eisen und Luft;
    #   * die Barrieren bekommen gleiche Dicke (die im Bericht untersuchte
    #     „constant barrier width"-Bauform).
    #
    # Damit steht der Stapel von innen nach aussen exakt, ohne Rest.
    kw_soll = _kw(geom)
    t_gesamt = r_e - r_in
    t_eisen = t_gesamt / (1.0 + kw_soll)
    t_luft = t_gesamt - t_eisen
    th = [0.0] + [math.pi / (2.0 * p) - pe for pe in phi_e] + [math.pi / (2.0 * p)]
    d_sin = [max(math.sin(p * th[h + 1]) - math.sin(p * th[h]), 0.0)
             for h in range(k + 1)]
    summe = sum(d_sin) or 1.0
    s_soll = [max(t_eisen * d / summe, STEG_MIN_MM) for d in d_sin]
    w_soll = max(t_luft / k, BARRIERE_MIN_MM)
    # Nach dem Anheben auf die Mindestmasse passt der Stapel vielleicht nicht
    # mehr; dann wird gleichmaessig gestaucht und das GESAGT.
    stapel = sum(s_soll) + k * w_soll
    if stapel > t_gesamt:
        f = t_gesamt / stapel
        s_soll = [x * f for x in s_soll]
        w_soll *= f
        befund.append(f"Stapel um {100.0 * (1.0 - f):.0f} % gestaucht — "
                      f"Mindeststege und Isolationsgrad passen nicht beide")

    aus, luft_summe, unten = [], 0.0, r_in
    for h in range(k):
        lo = unten + s_soll[h]
        hi = lo + w_soll
        unten = hi
        luft_summe += w_soll
        r_q_h = (lo + hi) / 2.0
        # Die Muendung ist so breit wie die Barriere dick ist.
        d_phi = (w_soll / 2.0) / max(r_e, 1e-9)
        pa = max(phi_e[h] - d_phi, 1e-3)          # naeher an der q-Achse
        pi_ = min(phi_e[h] + d_phi, math.pi / (2.0 * p) - 1e-3)
        rand_a = _bogen(hi, r_e, pa, N_STUETZ)    # naeher am Luftspalt
        rand_i = _bogen(lo, r_e, pi_, N_STUETZ)
        pts = [(r * math.cos(f), r * math.sin(f)) for f, r in rand_i]
        n_b = 3
        for i in range(1, n_b):
            f = pi_ + (pa - pi_) * i / n_b
            pts.append((r_e * math.cos(f), r_e * math.sin(f)))
        pts += [(r * math.cos(f), r * math.sin(f)) for f, r in reversed(rand_a)]
        for i in range(1, n_b):
            f = -pa + (-pi_ + pa) * i / n_b
            pts.append((r_e * math.cos(f), r_e * math.sin(f)))
        # Die MITTELLINIE derselben Barriere -- fuer Verbraucher, die keine
        # Polygone koennen. Der 3-D-Netzbauer (`ema_em3d`) baut Barrieren als
        # dicke Polylinien (Kastenprismen je Abschnitt, wie die Designer-
        # Barrieren); er bekommt hier **denselben Bogen und dieselbe Dicke**,
        # aus denen auch die beiden Raender des Polygons entstehen -- also
        # keine zweite Ableitung, nur eine andere Sicht. Der Unterschied ist
        # die Sehne statt des Bogens; bei `N_STUETZ` Abschnitten liegt er
        # gemessen bei 0,02…0,31 mm, also 0,4…6,1 % der Barrierendicke
        # (`test_synrm_eesm.py` misst es nach und nagelt die Schranke fest).
        mitte = _bogen(r_q_h, r_e, min(pa, pi_), N_STUETZ)

        aus.append({
            "punkte": [(round(x, 4), round(y, 4)) for x, y in pts],
            "mittellinie": [(round(r * math.cos(f), 4), round(r * math.sin(f), 4))
                            for f, r in mitte],
            "r_q_mm": round(r_q_h, 3),
            "dicke_mm": round(w_soll, 3),
            "eisen_darunter_mm": round(s_soll[h], 3),
            "endwinkel_grad": round(math.degrees(math.pi / (2.0 * p)
                                                 - phi_e[h]), 3),
            "muendung_grad": round(math.degrees(2.0 * d_phi), 3)})

    # Das letzte Segment traegt den Rest -- und sagt, wieviel das ist.
    s_letzt = r_e - unten
    if s_soll and s_soll[-1] > 1e-9:
        _ab = 100.0 * (s_letzt - s_soll[-1]) / s_soll[-1]
        if abs(_ab) > 25.0:
            befund.append(
                f"Aeusserstes Eisensegment {s_letzt:.2f} mm statt "
                f"{s_soll[-1]:.2f} mm nach der Flussregel ({_ab:+.0f} %) — "
                f"Lage (Feldlinie) und Segmentbreite sind zusammen "
                f"ueberbestimmt, der Rest landet hier")
    eisen = (r_e - r_in) - luft_summe
    kw_ist = luft_summe / max(eisen, 1e-9)
    if abs(kw_ist - kw_soll) > 0.05 * max(kw_soll, 1e-9):
        befund.append(f"Isolationsgrad {kw_ist:.2f} statt {kw_soll:.2f} — ein "
                      f"Mindeststeg ({STEG_MIN_MM:.1f} mm) bindet")
    if not (KW_BAND[0] <= kw_ist <= KW_BAND[1]):
        befund.append(f"Isolationsgrad {kw_ist:.2f} liegt ausserhalb des "
                      f"Bestbereichs {KW_BAND[0]}…{KW_BAND[1]} (Moghaddam "
                      f"Fig. 5.12) — das kostet Moment")
    return {"k": k, "barrieren": aus, "grund": bz["grund"],
            "passt": bool(aus), "befund": befund,
            "alpha_m_grad": round(math.degrees(alpha_m), 4),
            "kw_soll": round(kw_soll, 3), "kw_ist": round(kw_ist, 3),
            "luft_mm": round(luft_summe, 2), "eisen_mm": round(eisen, 2),
            "steg_rand_mm": round(steg_rand, 2),
            "r_e_mm": round(r_e, 3), "r_in_mm": round(r_in, 3),
            "q": bz["q"], "nutteilung_passt": bz["nutteilung_passt"],
            "ungeprueft": (
                "Gerechnet ist die GEOMETRIE nach den Auslegungsregeln "
                "(Moghaddam 2007, Kap. 5/6). NICHT gerechnet sind: die "
                "Fliehkraft an den Tangentialstegen (dafuer Struktur-FEM), "
                "die Momentwelligkeit (dafuer braeuchte es die Endwinkel als "
                "Freiheitsgrad und einen Feldlauf) und die Saettigung der "
                "Segmente. `ema_synrm.induktivitaeten` kennt von alledem "
                "weiterhin nur eine Ersatz-Barrierenhoehe.")}
