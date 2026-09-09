"""Getriebeauslegung -- gerechnet, nicht angenommen.

Warum es dieses Modul gibt
--------------------------

Das Getriebe war in dieser Kette **zwei Konstanten**::

    DEFAULT_VEHICLE = { …, "gear_ratio": 9.5, "eta_drive": 0.95, … }

``ema_drivecycle.compute_drivetrain`` rechnet damit ``rpm_motor = rpm_wheel * i``
und ``T_motor = T_wheel / (i * eta)`` -- mehr nicht. Keine Stufenteilung, keine
Zaehnezahlen, kein Modul, keine Tragfaehigkeit, keine Masse, keine Traegheit, und
ein Wirkungsgrad, der bei Volllast dasselbe sagt wie im Schub. Ein
Fahrrad-Nabenmotor und ein Traktionsantrieb bekamen dieselben 9,5 und 0,95,
sofern niemand sie von Hand setzte.

Was hier gerechnet wird -- und was NICHT
-----------------------------------------

**Gerechnet aus der Geometrie** (kein Tabellenwert, keine Faustzahl):

* Zahnformfaktor ``Y_Fa`` und Kerbfaktor ``Y_Sa`` nach dem Verfahren der
  30-Grad-Tangente (ISO 6336-3 / DIN 3990-3, Verfahren B) -- die Hilfsgroessen
  E, G, H und der Waelzwinkel ``theta`` werden aus Zaehnezahl, Profilverschiebung
  und Werkzeugform bestimmt, ``theta`` iterativ. Eine Tabelle waere hier das
  Naheliegende und das Falsche gewesen: sie gilt nur fuer x = 0 und genau eine
  Werkzeugform.
* Profil- und Sprungueberdeckung, daraus ``Y_eps`` und ``Z_eps``.
* Zonenfaktor ``Z_H`` und Elastizitaetsfaktor ``Z_E`` -- beide aus ihren Formeln,
  ``Z_E`` aus E-Modul und Querzahl der Paarung.
* Zahnverlustgrad ``H_V`` nach Ohlendorf, daraus der lastabhaengige
  Verzahnungswirkungsgrad.
* Massen und Traegheiten der Radkoerper, die Traegheit **auf die Motorwelle
  bezogen** (``J/i^2``) -- denn genau so wirkt sie im Fahrzyklus.

**Angenommen und als Annahme gekennzeichnet** (sie sind keine Geometrie, sondern
Betriebs- und Werkstoffwissen):

* ``K_A`` (Anwendungsfaktor), ``K_V`` (Dynamik), ``K_Hbeta``/``K_Fbeta``
  (Breitenlast) -- Beiwerte aus der Norm, hier als Eingang mit begruendeter
  Vorgabe. Wer sie nicht setzt, bekommt die Vorgabe UND den Hinweis darauf.
* ``mu_m`` (mittlere Zahnreibzahl) und die Leerlaufverluste je Stufe.
* ``sigma_Flim`` / ``sigma_Hlim`` der Werkstoffe. Sie stehen in
  ``ema_referenz.GETRIEBE_WERKSTOFF`` und sind dort ausdruecklich als **Annahme**
  gefuehrt, nicht als Zitat -- solange sie keine Fundstelle haben, traegt jede
  Sicherheit den Vermerk ``werkstoff_beleg: "annahme"``. Eine erfundene
  Festigkeitszahl waere die gefaehrlichste Zahl in diesem Werkzeug.

**Gar nicht gerechnet**, und das steht auch in der Ausgabe: Lagerlebensdauer,
Waermehaushalt, Geraeusch, Gehaeuse. Beim **Kegelrad** laeuft die Tragfaehigkeit
ueber das Ersatz-Stirnrad (Tredgold) -- eine Naeherung. Bei der **Schnecke** gibt
es keine Zahnfussrechnung; dort zaehlen Wirkungsgrad, Selbsthemmung und
Erwaermung, und der Wirkungsgrad haengt so stark am Reibwert, dass eine Spanne
ausgegeben wird und keine Zahl.

Der Einbauort
-------------

``einbau`` entscheidet, WO das Getriebe sitzt, und nicht jede Bauart kann jeden
Ort:

* ``achsparallel`` -- Stirnradstufen neben der Maschine.
* ``koaxial`` -- Planetensatz vor der Stirnseite, auf derselben Achse.
* ``in_welle`` -- Planetensatz **in der Hohlwelle des Laeufers**. Das ist der
  integrierte Antrieb, und er hat eine harte Bedingung: das Hohlrad samt Wand
  muss in die Bohrung passen -- und die Bohrung muss magnetisch ueberhaupt
  zulaessig sein. Genau das rechnet ``ema_welle.pruefen`` bereits aus dem Feld
  (``bohrung.hoechstens_mm``); ``in_welle_pruefen`` stellt beide Zahlen
  nebeneinander und sagt, welche bindet. Ein Stirnradsatz in der Welle wird
  abgewiesen und nicht naeherungsweise gerechnet.
"""

from __future__ import annotations

import math

# ── Normen und Werkzeugform ─────────────────────────────────────────────────
# Bezugsprofil nach DIN 867 (Normal): Eingriffswinkel 20 Grad, Kopfhoehe 1*m,
# Fusshoehe 1,25*m, Kopfrundung des Werkzeugs 0,38*m.
ALPHA_N_GRAD = 20.0
HA_STERN     = 1.00        # Kopfhoehenfaktor des Rades
HF_STERN     = 1.25        # Fusshoehenfaktor (= Kopfhoehe des Werkzeugs)
RHO_FP_STERN = 0.38        # Kopfrundung des Werkzeugs, bezogen auf m
Y_ST         = 2.0         # Spannungskorrekturfaktor des Normpruefrades

# Modulreihe DIN 780, Reihe 1. AUFGERUNDET wird, nie ab: ein Modul unter dem
# gerechneten waere ein Zahn, der die Last nicht traegt.
MODUL_REIHE1 = (0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0,
                8.0, 10.0, 12.0, 16.0, 20.0, 25.0, 32.0, 40.0, 50.0, 60.0)

# Kleinste Zaehnezahl ohne Unterschnitt bei 20 Grad und x = 0. Darunter geht es
# nur mit Profilverschiebung -- und dann steht sie auch in der Ausgabe.
Z_MIN_OHNE_X = 17
Z_MIN_MIT_X  = 14

# Groesste Uebersetzung je STUFE. Darueber wird geteilt, statt eine Stufe zu
# ueberdehnen: das Rad wuerde gross, die Umfangsgeschwindigkeit hoch und der
# Achsabstand unbrauchbar.
I_MAX_STUFE = {"stirnrad": 6.3, "planeten": 10.0, "kegelrad": 5.0, "schnecke": 60.0}
I_MIN_PLANET = 3.0         # unter 1+z_h/z_s = 3 wird der Satz unbaubar

# Zielsicherheiten. DIN 3990/ISO 6336 nennen fuer den allgemeinen Maschinenbau
# etwa diese Groessenordnung; sie sind hier EINGANG mit Vorgabe, keine Konstante
# der Physik.
S_F_ZIEL = 1.4             # Zahnfuss
S_H_ZIEL = 1.0             # Flanke (Gruebchen)

# Wandstaerke des Hohlradkoerpers, in Modulen. Faustwert -- er entscheidet beim
# Einbau in der Welle darueber, wie gross die Bohrung sein muss, und steht
# deshalb als Zahl da und nicht in einer Formel versteckt.
WAND_HOHLRAD_M = 3.0

# Betriebsbeiwerte -- ANNAHMEN mit Vorgabe (s. Modulkopf).
BEIWERTE_VORGABE = {
    "K_A":     1.25,   # Anwendungsfaktor: E-Antrieb, maessige Stoesse
    "K_V":     1.10,   # Dynamikfaktor
    "K_Hbeta": 1.20,   # Breitenlastfaktor Flanke
    "K_Fbeta": 1.15,   # Breitenlastfaktor Fuss
    "K_Halpha": 1.0, "K_Falpha": 1.0,
    "mu_m":    0.05,   # mittlere Zahnreibzahl, oelgeschmiert
}

# Leerlaufverlust je Stufe (Lager + Planschen), bezogen auf die Nennleistung.
# Annahme; sie ist der Grund, warum der Wirkungsgrad mit der Last STEIGT.
LEERLAUF_ANTEIL = 0.005

EINBAU_ARTEN = {
    "achsparallel": "Stirnradstufen neben der Maschine",
    "koaxial":      "Planetensatz vor der Stirnseite, auf derselben Achse",
    "in_welle":     "Planetensatz in der Hohlwelle des Laeufers",
}

# Welche Bauart welchen Einbauort traegt. ``in_welle`` ist der Grund fuer diese
# Tabelle: ein Stirnradsatz sitzt neben der Achse, nicht auf ihr, und laesst sich
# nicht in eine Bohrung legen -- das wird abgewiesen und nicht genaehert.
EINBAU_ERLAUBT = {
    "stirnrad": ("achsparallel",),
    "planeten": ("koaxial", "in_welle"),
    "kegelrad": ("achsparallel",),
    "schnecke": ("achsparallel",),
}


def _grad(x: float) -> float:
    return math.degrees(x)


def _bog(x: float) -> float:
    return math.radians(x)


def inv(alpha: float) -> float:
    """Evolventenfunktion: inv(a) = tan(a) - a. Winkel im Bogenmass."""
    return math.tan(alpha) - alpha


def modul_normen(m: float, reihe=MODUL_REIHE1) -> float:
    """Auf die naechste Normgroesse AUFRUNDEN. Nie ab -- s. MODUL_REIHE1."""
    for r in reihe:
        if r >= m - 1e-9:
            return r
    return reihe[-1]


# ── Zahnform: Y_Fa und Y_Sa aus der GEOMETRIE ───────────────────────────────
#
# Verfahren der 30-Grad-Tangente (ISO 6336-3 / DIN 3990-3). Der gefaehrdete
# Querschnitt ist dort, wo eine unter 30 Grad geneigte Gerade die Fussrundung
# beruehrt; seine Dicke ``s_Fn`` und der Hebelarm ``h_Fa`` folgen aus der
# Erzeugung durch das Werkzeug.
#
# Warum das gerechnet und nicht nachgeschlagen wird: eine Y_Fa-Tabelle gilt fuer
# x = 0 und genau EINE Werkzeugform. Sobald die Auslegung eine Profilverschiebung
# waehlt -- und das tut sie, sobald z unter 17 faellt -- ist der Tabellenwert
# falsch, ohne dass es jemandem auffiele.

def zahnform(z: int, x: float = 0.0, beta_grad: float = 0.0,
             ha_stern: float = HA_STERN, hf_stern: float = HF_STERN,
             rho_fp_stern: float = RHO_FP_STERN,
             alpha_n_grad: float = ALPHA_N_GRAD) -> dict:
    """``Y_Fa``, ``Y_Sa``, Fussdicke und Kerbradius -- alles in Modulen.

    Rueckgabe traegt die Zwischengroessen mit (``theta``, ``s_Fn_m``, ``h_Fa_m``,
    ``rho_F_m``, ``q_s``), damit sich nachrechnen laesst, woher die beiden
    Faktoren kommen.
    """
    alpha_n = _bog(alpha_n_grad)
    beta = _bog(beta_grad)
    # Ersatzzahnzahl der Schraegverzahnung: der Zahn wird im Normalschnitt
    # gerechnet, und dort sitzt er auf einem groesseren gedachten Rad.
    beta_b = math.asin(math.sin(beta) * math.cos(alpha_n))
    z_n = z / (math.cos(beta_b) ** 2 * math.cos(beta)) if z else 0.0
    if z_n < 1.0:
        return {"ok": False, "grund": "Zaehnezahl zu klein"}

    # Hilfsgroessen (alles in Modulen; s_pr = 0, kein Protuberanzwerkzeug)
    E = (math.pi / 4.0) - hf_stern * math.tan(alpha_n) \
        - (1.0 - math.sin(alpha_n)) * rho_fp_stern / math.cos(alpha_n)
    G = rho_fp_stern - hf_stern + x
    H = (2.0 / z_n) * (math.pi / 2.0 - E) - math.pi / 3.0

    # theta = (2G/z_n)*tan(theta) - H  -- Fixpunkt, Start bei 30 Grad. Er
    # konvergiert hier zuverlaessig (die rechte Seite ist im Bereich flach);
    # nach 40 Schritten wird abgebrochen, damit eine unsinnige Geometrie nicht
    # haengt, sondern sich meldet.
    theta = math.pi / 6.0
    for _ in range(40):
        neu = (2.0 * G / z_n) * math.tan(theta) - H
        if abs(neu - theta) < 1e-12:
            theta = neu
            break
        theta = neu
        if not (-1.5 < theta < 1.5):
            return {"ok": False, "grund": "Zahnform konvergiert nicht (z/x unstimmig)"}

    s_Fn_m = z_n * math.sin(math.pi / 3.0 - theta) \
        + math.sqrt(3.0) * (G / math.cos(theta) - rho_fp_stern)
    nenner = math.cos(theta) * (z_n * math.cos(theta) ** 2 - 2.0 * G)
    if abs(nenner) < 1e-12:
        return {"ok": False, "grund": "Kerbradius nicht bestimmbar"}
    rho_F_m = rho_fp_stern + 2.0 * G * G / nenner

    # Lastangriff am Zahnkopf (Y_Fa): der Fall, gegen den ausgelegt wird.
    d_n_m  = z_n
    d_bn_m = d_n_m * math.cos(alpha_n)
    d_an_m = d_n_m + 2.0 * (ha_stern + x)
    if d_an_m <= d_bn_m:
        return {"ok": False, "grund": "Kopfkreis unter dem Grundkreis"}
    alpha_an = math.acos(d_bn_m / d_an_m)
    gamma_a = (0.5 * math.pi + 2.0 * x * math.tan(alpha_n)) / z_n \
        + inv(alpha_n) - inv(alpha_an)
    alpha_Fan = alpha_an - gamma_a
    h_Fa_m = 0.5 * ((math.cos(gamma_a) - math.sin(gamma_a) * math.tan(alpha_Fan)) * d_an_m
                    - z_n * math.cos(math.pi / 3.0 - theta)
                    - G / math.cos(theta) + rho_fp_stern)
    if s_Fn_m <= 0 or h_Fa_m <= 0 or rho_F_m <= 0:
        return {"ok": False, "grund": "Zahnfussgeometrie unstimmig"}

    Y_Fa = 6.0 * h_Fa_m * math.cos(alpha_Fan) / (s_Fn_m ** 2 * math.cos(alpha_n))

    L = s_Fn_m / h_Fa_m
    q_s = s_Fn_m / (2.0 * rho_F_m)
    Y_Sa = (1.2 + 0.13 * L) * q_s ** (1.0 / (1.21 + 2.3 / L))

    return {"ok": True, "Y_Fa": Y_Fa, "Y_Sa": Y_Sa, "z_n": z_n,
            "theta": theta, "s_Fn_m": s_Fn_m, "h_Fa_m": h_Fa_m,
            "rho_F_m": rho_F_m, "q_s": q_s, "L": L}


# ── Ueberdeckung ────────────────────────────────────────────────────────────

def ueberdeckung(z1: int, z2: int, m: float, b: float, x1: float = 0.0,
                 x2: float = 0.0, beta_grad: float = 0.0,
                 alpha_n_grad: float = ALPHA_N_GRAD,
                 ha_stern: float = HA_STERN, innen: bool = False) -> dict:
    """Profil- (``eps_alpha``) und Sprungueberdeckung (``eps_beta``).

    ``innen=True`` fuer die Paarung Planet/Hohlrad -- dort zaehlt z2 negativ,
    und der Betriebseingriffswinkel folgt der Innenverzahnung.
    """
    alpha_n = _bog(alpha_n_grad)
    beta = _bog(beta_grad)
    z2s = -abs(z2) if innen else abs(z2)
    alpha_t = math.atan(math.tan(alpha_n) / math.cos(beta)) if beta else alpha_n
    # Betriebseingriffswinkel aus der Profilverschiebungssumme
    summe = (x1 + x2) if not innen else (x2 - x1)
    z_sum = z1 + z2s
    if abs(z_sum) < 1e-9:
        return {"ok": False, "grund": "Zaehnezahlsumme null"}
    inv_wt = inv(alpha_t) + 2.0 * math.tan(alpha_n) * summe / z_sum
    # inv umkehren -- Newton, Start beim Eingriffswinkel selbst
    a_wt = alpha_t
    for _ in range(60):
        f = inv(a_wt) - inv_wt
        fs = math.tan(a_wt) ** 2
        if abs(fs) < 1e-12:
            break
        schritt = f / fs
        a_wt -= schritt
        if abs(schritt) < 1e-12:
            break
    a_wt = min(max(a_wt, 1e-4), 1.5)

    def _kopf(z, x):
        d  = m * abs(z) / math.cos(beta) if beta else m * abs(z)
        db = d * math.cos(alpha_t)
        da = d + 2.0 * m * (ha_stern + x) * (1.0 if z > 0 else -1.0)
        return d, db, abs(da)

    d1, db1, da1 = _kopf(z1, x1)
    d2, db2, da2 = _kopf(z2s, x2)
    a_w = (db1 + db2) / (2.0 * math.cos(a_wt)) if not innen \
        else abs(db2 - db1) / (2.0 * math.cos(a_wt))
    try:
        g1 = math.sqrt(max(da1 ** 2 - db1 ** 2, 0.0)) / 2.0
        g2 = math.sqrt(max(da2 ** 2 - db2 ** 2, 0.0)) / 2.0
        laenge = (g1 + g2 - a_w * math.sin(a_wt)) if not innen \
            else (g1 - g2 + a_w * math.sin(a_wt))
        p_bt = math.pi * m * math.cos(alpha_t) / math.cos(beta) if beta \
            else math.pi * m * math.cos(alpha_t)
        eps_a = abs(laenge) / p_bt if p_bt > 0 else 0.0
    except (ValueError, ZeroDivisionError):
        eps_a = 0.0
    eps_b = b * math.sin(beta) / (math.pi * m) if beta else 0.0
    # Die TEILueberdeckungen (Vor- und Nacheingriff). Sie werden fuer den
    # Zahnverlustgrad gebraucht: die Reibung haengt davon ab, wie weit der
    # Eingriff vor und hinter dem Waelzpunkt reicht, nicht nur von der Summe.
    def _eps_teil(z, da, db):
        if da <= db:
            return 0.0
        return abs(z) / (2.0 * math.pi) * (math.sqrt((da / db) ** 2 - 1.0)
                                           - math.tan(a_wt))
    eps_1 = _eps_teil(z1, da1, db1)
    eps_2 = _eps_teil(z2s, da2, db2)
    return {"ok": True, "eps_alpha": eps_a, "eps_beta": eps_b,
            "eps_1": eps_1, "eps_2": eps_2,
            "alpha_wt": a_wt, "alpha_t": alpha_t, "a_w_mm": a_w,
            "d1_mm": d1, "d2_mm": abs(d2), "da1_mm": da1, "da2_mm": da2,
            "db1_mm": db1, "db2_mm": abs(db2)}


# ── Faktoren aus ihren Formeln, nicht aus Tabellen ──────────────────────────

def zonenfaktor(alpha_wt: float, alpha_t: float, beta_grad: float = 0.0) -> float:
    """``Z_H`` -- die Kruemmung im Waelzpunkt. Fuer Normverzahnung 20 Grad,
    x = 0, beta = 0 kommt daraus die bekannte 2,5."""
    beta = _bog(beta_grad)
    beta_b = math.asin(math.sin(beta) * math.cos(_bog(ALPHA_N_GRAD))) if beta else 0.0
    return math.sqrt(2.0 * math.cos(beta_b) * math.cos(alpha_wt)
                     / (math.cos(alpha_t) ** 2 * math.sin(alpha_wt)))


def elastizitaetsfaktor(E1: float = 206000.0, E2: float = 206000.0,
                        nu1: float = 0.3, nu2: float = 0.3) -> float:
    """``Z_E`` aus E-Modul und Querzahl. Stahl/Stahl ergibt daraus 189,8."""
    return math.sqrt(1.0 / (math.pi * ((1.0 - nu1 ** 2) / E1 + (1.0 - nu2 ** 2) / E2)))


def _y_eps(eps_alpha: float) -> float:
    return 0.25 + 0.75 / eps_alpha if eps_alpha > 0.1 else 1.0


def _z_eps(eps_alpha: float, eps_beta: float) -> float:
    if eps_beta <= 0:                       # Geradverzahnung
        return math.sqrt(max((4.0 - eps_alpha) / 3.0, 0.05))
    if eps_beta >= 1.0:
        return math.sqrt(1.0 / eps_alpha) if eps_alpha > 0 else 1.0
    return math.sqrt((4.0 - eps_alpha) / 3.0 * (1.0 - eps_beta) + eps_beta / eps_alpha)


def _y_beta(eps_beta: float, beta_grad: float) -> float:
    y = 1.0 - min(eps_beta, 1.0) * min(abs(beta_grad), 30.0) / 120.0
    return max(y, 0.75)


# ── Zaehnezahlen und Modul ──────────────────────────────────────────────────

def _ggt(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def zaehnezahlen(i_soll: float, z_min: int = Z_MIN_OHNE_X, z_max: int = 200,
                 z1_fenster: int = 10, toleranz: float = 0.03) -> dict:
    """``z1``/``z2`` zu einer Sollübersetzung.

    Das Ritzel bleibt in einem SCHMALEN Fenster ueber der Unterschnittgrenze
    (``z_min`` … ``z_min + z1_fenster``). Ohne diese Schranke gewinnt immer das
    groesste Ritzel: mit z1 = 41 laesst sich jede Uebersetzung auf ein Promille
    treffen -- und das Rad wird bei gleichem Modul doppelt so gross. Die
    Uebersetzung genauer zu treffen, als der Bauraum es bezahlt, ist kein Gewinn.

    Teilerfremd („hunting ratio") ist erwuenscht, aber nicht um jeden Preis: bei
    ggT > 1 laeuft ein Ritzelzahn nur gegen z2/ggT Partner, ein Fertigungsfehler
    frisst sich in genau die ein. Der Zuschlag entspricht 0,5 % Uebersetzungs-
    fehler -- wo eine schoene Paarung mehr kostet, wird sie nicht genommen und
    das steht als Hinweis dabei.

    ``i_ist`` steht IMMER daneben: eine Uebersetzung aus ganzen Zaehnezahlen
    trifft den Sollwert fast nie genau, und die Abweichung ist eine Aussage --
    keine Nachkommastelle, die man wegrundet.
    """
    i_soll = abs(float(i_soll))
    if i_soll < 1.0:
        return {"ok": False, "grund": f"Uebersetzung {i_soll:g} < 1 (ins Schnelle "
                                      f"uebersetzen ist hier nicht vorgesehen)"}
    beste = None
    for z1 in range(z_min, z_min + max(1, z1_fenster) + 1):
        z2_ideal = z1 * i_soll
        for z2 in {int(math.floor(z2_ideal)), int(math.ceil(z2_ideal)),
                   int(round(z2_ideal)) + 1, int(round(z2_ideal)) - 1}:
            if z2 < z1 or z2 > z_max:
                continue
            i_ist = z2 / z1
            fehler = abs(i_ist - i_soll) / i_soll
            if fehler > toleranz:
                continue
            teilerfremd = _ggt(z1, z2) == 1
            note = fehler + (0.0 if teilerfremd else 0.005)
            if beste is None or note < beste["note"]:
                beste = {"z1": z1, "z2": z2, "i_ist": i_ist, "fehler": fehler,
                         "teilerfremd": teilerfremd, "note": note}
    if beste is None:
        return {"ok": False,
                "grund": (f"keine Zaehnezahlpaarung fuer i = {i_soll:g} mit "
                          f"z1 = {z_min}…{z_min + z1_fenster} innerhalb "
                          f"{100 * toleranz:.0f} % Abweichung")}
    beste.pop("note")
    beste["ok"] = True
    beste["z_min"] = z_min
    beste["hinweis"] = ("" if beste["teilerfremd"] else
                        f"z1 und z2 haben den gemeinsamen Teiler "
                        f"{_ggt(beste['z1'], beste['z2'])}: jeder Ritzelzahn "
                        f"trifft nur {beste['z2'] // _ggt(beste['z1'], beste['z2'])} "
                        f"Radzaehne. Teilerfremd waere gleichmaessiger, kostete "
                        f"hier aber mehr Uebersetzungsfehler.")
    return beste


def modul_aus_moment(T1_Nm: float, z1: int, psi_m: float, sigma_FP: float,
                     Y_Fa: float, Y_Sa: float, Y_eps: float, Y_beta: float,
                     K_ges: float) -> float:
    """Kleinstes Modul, das den Zahnfuss traegt -- vor dem Aufrunden.

        sigma_F = (2*T1 / (z1 * psi_m * m^3)) * Y_Fa*Y_Sa*Y_eps*Y_beta * K_ges
        m >= ( 2*T1*Y*K / (z1 * psi_m * sigma_FP) )^(1/3)

    ``T1`` in Nm wird hier auf Nmm gebracht; ``sigma_FP`` in N/mm^2.
    """
    if min(z1, psi_m, sigma_FP) <= 0:
        return 0.0
    zaehler = 2.0 * (T1_Nm * 1000.0) * Y_Fa * Y_Sa * Y_eps * Y_beta * K_ges
    return (zaehler / (z1 * psi_m * sigma_FP)) ** (1.0 / 3.0)


# ── Eine Stirnradstufe, vollstaendig ────────────────────────────────────────

def stufe_auslegen(T1_Nm: float, i_soll: float, werkstoff: dict, *,
                   psi_m: float = 20.0, beta_grad: float = 0.0,
                   n1_1pmin: float = 0.0, beiwerte: dict | None = None,
                   z_min: int = Z_MIN_OHNE_X, s_F_ziel: float = S_F_ZIEL,
                   s_H_ziel: float = S_H_ZIEL, name: str = "Stufe") -> dict:
    """Zaehnezahlen -> Modul -> Geometrie -> Tragfaehigkeit fuer EINE Stufe.

    ``psi_m = b/m`` ist das Breitenverhaeltnis (15…25 im Getriebebau; breiter
    braucht eine steifere Lagerung, sonst traegt der Zahn nur an einem Ende --
    genau dafuer steht ``K_Fbeta``).
    """
    K = dict(BEIWERTE_VORGABE)
    K.update(beiwerte or {})
    zz = zaehnezahlen(i_soll, z_min=z_min)
    if not zz.get("ok"):
        return {"ok": False, "grund": zz["grund"], "name": name}
    z1, z2, i_ist = zz["z1"], zz["z2"], zz["i_ist"]

    form1 = zahnform(z1, beta_grad=beta_grad)
    form2 = zahnform(z2, beta_grad=beta_grad)
    if not form1.get("ok") or not form2.get("ok"):
        return {"ok": False, "name": name,
                "grund": form1.get("grund") or form2.get("grund")}

    belegt = bool(werkstoff.get("sigma_Flim_Nmm2")) and bool(werkstoff.get("sigma_Hlim_Nmm2"))
    if not belegt:
        return {"ok": False, "name": name,
                "grund": (f"Werkstoff '{werkstoff.get('label', '?')}' hat keine "
                          f"Festigkeitskennwerte — ohne sigma_Flim und sigma_Hlim "
                          f"gibt es keine Tragfaehigkeit und damit kein Modul.")}
    sigma_FP = werkstoff["sigma_Flim_Nmm2"] * Y_ST / s_F_ziel

    K_F = K["K_A"] * K["K_V"] * K["K_Fbeta"] * K["K_Falpha"]
    K_H = K["K_A"] * K["K_V"] * K["K_Hbeta"] * K["K_Halpha"]
    Z_E = elastizitaetsfaktor(werkstoff.get("E_Nmm2", 206000.0),
                              werkstoff.get("E_Nmm2", 206000.0),
                              werkstoff.get("nu", 0.3), werkstoff.get("nu", 0.3))

    def _bei(m_try):
        """Alle Spannungen und Sicherheiten bei EINEM Modul."""
        b_ = psi_m * m_try
        ue_ = ueberdeckung(z1, z2, m_try, b_, beta_grad=beta_grad)
        Y_e_ = _y_eps(ue_["eps_alpha"])
        Y_b_ = _y_beta(ue_["eps_beta"], beta_grad)
        Z_e_ = _z_eps(ue_["eps_alpha"], ue_["eps_beta"])
        Z_b_ = math.sqrt(math.cos(_bog(beta_grad)))
        Z_H_ = zonenfaktor(ue_["alpha_wt"], ue_["alpha_t"], beta_grad)
        d1_ = ue_["d1_mm"]
        F_t_ = 2.0 * T1_Nm * 1000.0 / d1_
        sF1 = (F_t_ / (b_ * m_try)) * form1["Y_Fa"] * form1["Y_Sa"] * Y_e_ * Y_b_ * K_F
        sF2 = (F_t_ / (b_ * m_try)) * form2["Y_Fa"] * form2["Y_Sa"] * Y_e_ * Y_b_ * K_F
        u_ = z2 / z1
        sH = (Z_H_ * Z_E * Z_e_ * Z_b_
              * math.sqrt(F_t_ / (d1_ * b_) * (u_ + 1.0) / u_) * math.sqrt(K_H))
        return {"m": m_try, "b": b_, "ue": ue_, "Y_e": Y_e_, "Y_b": Y_b_,
                "Z_e": Z_e_, "Z_b": Z_b_, "Z_H": Z_H_, "F_t": F_t_,
                "sF1": sF1, "sF2": sF2, "sH": sH,
                "S_F": werkstoff["sigma_Flim_Nmm2"] * Y_ST / max(sF1, sF2),
                "S_H": werkstoff["sigma_Hlim_Nmm2"] / sH}

    # 1) Das Modul, das der ZAHNFUSS braucht. Die Ueberdeckung steckt selbst im
    # Modul (Y_eps haengt an eps_alpha, das an m), also einmal schaetzen und
    # nachziehen -- der Einfluss auf m^3 ist schwach, zwei Durchgaenge reichen.
    m_roh = modul_aus_moment(T1_Nm, z1, psi_m, sigma_FP,
                             form1["Y_Fa"], form1["Y_Sa"], 1.0, 1.0, K_F)
    m_fuss = modul_normen(m_roh)
    for _ in range(3):
        st = _bei(m_fuss)
        m_roh = modul_aus_moment(T1_Nm, z1, psi_m, sigma_FP,
                                 form1["Y_Fa"], form1["Y_Sa"], st["Y_e"], st["Y_b"], K_F)
        m_neu = modul_normen(m_roh)
        if m_neu == m_fuss:
            break
        m_fuss = m_neu

    # 2) Und dann die FLANKE, die meistens entscheidet. Das ist kein Nebensatz:
    # die Fussformel liefert m aus T^(1/3), die Flanke traegt mit m^1,5 --
    # gemessen an einer 191-Nm-Stufe haelt der Fuss bei m = 2,0 mit S_F = 1,41,
    # waehrend die Flanke dort bei S_H = 0,91 steht. Wer nach der Fussformel
    # aufhoert, legt eine Verzahnung aus, die im Betrieb Gruebchen bekommt.
    # Also die Normreihe hoch, bis BEIDE Sicherheiten stehen, und ausgeben,
    # welche gebunden hat.
    reihe = [r for r in MODUL_REIHE1 if r >= m_fuss - 1e-9]
    stand, bindend = None, "zahnfuss"
    for m_try in (reihe or [m_fuss]):
        stand = _bei(m_try)
        if stand["S_F"] >= s_F_ziel and stand["S_H"] >= s_H_ziel:
            bindend = "flanke" if m_try > m_fuss else "zahnfuss"
            break
    m = stand["m"]

    b = stand["b"]
    ue, Y_e, Y_b = stand["ue"], stand["Y_e"], stand["Y_b"]
    Z_e, Z_b, Z_H = stand["Z_e"], stand["Z_b"], stand["Z_H"]
    d1, d2 = ue["d1_mm"], ue["d2_mm"]
    F_t = stand["F_t"]
    sigma_F1, sigma_F2, sigma_H = stand["sF1"], stand["sF2"], stand["sH"]
    S_F1 = werkstoff["sigma_Flim_Nmm2"] * Y_ST / sigma_F1
    S_F2 = werkstoff["sigma_Flim_Nmm2"] * Y_ST / sigma_F2
    S_H = stand["S_H"]
    u = z2 / z1

    v_umfang = math.pi * d1 * 1e-3 * n1_1pmin / 60.0 if n1_1pmin else 0.0

    return {
        "ok": True, "name": name, "art": "stirnrad",
        "z1": z1, "z2": z2, "i_ist": i_ist, "i_soll": i_soll,
        "i_fehler_pct": round(100.0 * zz["fehler"], 2),
        "teilerfremd": zz["teilerfremd"], "hinweis_zaehne": zz["hinweis"],
        "m_mm": m, "m_roh_mm": round(m_roh, 3), "m_zahnfuss_mm": m_fuss,
        "bindend": bindend, "b_mm": round(b, 1),
        "psi_m": psi_m, "beta_grad": beta_grad,
        "d1_mm": round(d1, 2), "d2_mm": round(d2, 2),
        "da1_mm": round(ue["da1_mm"], 2), "da2_mm": round(ue["da2_mm"], 2),
        "a_mm": round(ue["a_w_mm"], 2),
        "eps_alpha": round(ue["eps_alpha"], 3), "eps_beta": round(ue["eps_beta"], 3),
        "F_t_N": round(F_t, 1), "v_umfang_ms": round(v_umfang, 2),
        "Y_Fa1": round(form1["Y_Fa"], 3), "Y_Sa1": round(form1["Y_Sa"], 3),
        "Y_Fa2": round(form2["Y_Fa"], 3), "Y_Sa2": round(form2["Y_Sa"], 3),
        "Y_eps": round(Y_e, 3), "Y_beta": round(Y_b, 3),
        "Z_H": round(Z_H, 3), "Z_E": round(Z_E, 1), "Z_eps": round(Z_e, 3),
        "sigma_F1_Nmm2": round(sigma_F1, 1), "sigma_F2_Nmm2": round(sigma_F2, 1),
        "sigma_H_Nmm2": round(sigma_H, 1),
        "S_F": round(min(S_F1, S_F2), 2), "S_H": round(S_H, 2),
        "S_F_ziel": s_F_ziel, "S_H_ziel": s_H_ziel,
        "haelt": bool(min(S_F1, S_F2) >= s_F_ziel and S_H >= s_H_ziel),
        "werkstoff": werkstoff.get("label", "?"),
        "werkstoff_beleg": werkstoff.get("beleg", "unbekannt"),
        "beiwerte": K,
        "T1_Nm": T1_Nm, "n1_1pmin": n1_1pmin,
    }


# ── Planetensatz ────────────────────────────────────────────────────────────
#
# Standardbauform: Hohlrad steht, Sonne treibt, Steg treibt ab. Dann ist
#
#     i = 1 + z_h / z_s        und      z_p = (z_h - z_s) / 2
#
# Der Satz ist der KOAXIALE Fall -- Ab- und Antrieb auf einer Achse -- und damit
# der einzige, der in eine Hohlwelle passt (s. ``in_welle_pruefen``).

def _montage_ok(z_s: int, z_h: int, n_p: int) -> bool:
    """(z_s + z_h) muss durch die Planetenzahl teilbar sein.

    Sonst lassen sich die Planeten nicht gleichmaessig ueber den Umfang
    einbauen -- der letzte passt schlicht nicht in seine Luecke. Keine
    Feinheit: es ist die Bedingung, an der ein sonst fertiger Satz scheitert.
    """
    return n_p > 0 and (z_s + z_h) % n_p == 0


def planetensatz(T_sonne_Nm: float, i_soll: float, werkstoff: dict, *,
                 n_planeten: int = 3, psi_m: float = 18.0,
                 n_sonne_1pmin: float = 0.0, beiwerte: dict | None = None,
                 k_gamma: float = 1.15, s_F_ziel: float = S_F_ZIEL,
                 s_H_ziel: float = S_H_ZIEL, name: str = "Planetensatz") -> dict:
    """Sonne/Planet/Hohlrad, beide Eingriffe geprueft.

    ``k_gamma`` ist die Lastaufteilung auf die Planeten: drei Planeten tragen
    nicht je genau ein Drittel, weil Fertigungsabweichungen einen bevorzugen.
    1,15 ist eine ANNAHME (drei Planeten, ohne Lastausgleich); sie steht in der
    Ausgabe, damit niemand sie fuer gerechnet haelt.
    """
    K = dict(BEIWERTE_VORGABE)
    K.update(beiwerte or {})
    i_soll = float(i_soll)
    if not (I_MIN_PLANET <= i_soll <= I_MAX_STUFE["planeten"]):
        return {"ok": False, "name": name,
                "grund": (f"Ein einfacher Planetensatz traegt i = "
                          f"{I_MIN_PLANET:g}…{I_MAX_STUFE['planeten']:g}; "
                          f"gefordert sind {i_soll:g}. Darunter wird das Hohlrad "
                          f"kleiner als die Sonne, darueber der Planet zu klein.")}

    # Sonne so waehlen, dass Uebersetzung, Ganzzahligkeit und Montage stimmen.
    beste = None
    for z_s in range(Z_MIN_OHNE_X, Z_MIN_OHNE_X + 30):
        z_h_ideal = z_s * (i_soll - 1.0)
        for z_h in (int(math.floor(z_h_ideal)), int(math.ceil(z_h_ideal))):
            if (z_h - z_s) % 2 != 0:            # z_p muss ganzzahlig werden
                continue
            z_p = (z_h - z_s) // 2
            if z_p < Z_MIN_MIT_X or z_h < z_s + 2 * Z_MIN_MIT_X:
                continue
            if not _montage_ok(z_s, z_h, n_planeten):
                continue
            i_ist = 1.0 + z_h / z_s
            fehler = abs(i_ist - i_soll) / i_soll
            if fehler > 0.05:
                continue
            if beste is None or fehler < beste["fehler"]:
                beste = {"z_s": z_s, "z_p": z_p, "z_h": z_h,
                         "i_ist": i_ist, "fehler": fehler}
    if beste is None:
        return {"ok": False, "name": name,
                "grund": (f"keine Zaehnezahlen fuer i = {i_soll:g} mit "
                          f"{n_planeten} Planeten: Uebersetzung, ganzzahliger "
                          f"Planet und Montagebedingung sind nicht zugleich "
                          f"erfuellbar")}
    z_s, z_p, z_h = beste["z_s"], beste["z_p"], beste["z_h"]

    # Der Eingriff Sonne/Planet traegt das kleinste Rad und damit die Auslegung.
    # Moment je Planet, mit dem Lastaufteilungsfaktor.
    T_eingriff = T_sonne_Nm * k_gamma / max(n_planeten, 1)
    sp = stufe_auslegen(T_eingriff, z_p / z_s, werkstoff, psi_m=psi_m,
                        n1_1pmin=n_sonne_1pmin, beiwerte=K,
                        z_min=min(z_s, Z_MIN_OHNE_X), s_F_ziel=s_F_ziel,
                        s_H_ziel=s_H_ziel, name=f"{name}: Sonne/Planet")
    # ``stufe_auslegen`` waehlt eigene Zaehnezahlen -- hier zaehlen die des
    # Satzes. Uebernommen wird nur das MODUL; damit wird der Satz sauber
    # nachgerechnet.
    if not sp.get("ok"):
        return {"ok": False, "name": name, "grund": sp.get("grund")}
    m = sp["m_mm"]

    d_s, d_p, d_h = m * z_s, m * z_p, m * z_h
    b = psi_m * m
    a_sp = m * (z_s + z_p) / 2.0

    # Nachbarbedingung: die Planeten duerfen sich nicht beruehren.
    d_a_p = d_p + 2.0 * m * HA_STERN
    platz = 2.0 * a_sp * math.sin(math.pi / max(n_planeten, 1))
    nachbar_ok = platz > d_a_p + 1.0

    # Beide Eingriffe nachrechnen: aussen Sonne/Planet, INNEN Planet/Hohlrad.
    # Der Innen-Eingriff ist der freundlichere (grosse Kruemmungsradien, die
    # Flanken schmiegen sich) -- ihn zu ueberspringen waere trotzdem falsch,
    # weil der Planet dort mit derselben Kraft arbeitet.
    ue_sp = ueberdeckung(z_s, z_p, m, b)
    ue_ph = ueberdeckung(z_p, z_h, m, b, innen=True)
    F_t = 2.0 * T_eingriff * 1000.0 / d_s
    K_F = K["K_A"] * K["K_V"] * K["K_Fbeta"] * K["K_Falpha"]
    K_H = K["K_A"] * K["K_V"] * K["K_Hbeta"] * K["K_Halpha"]
    Z_E = elastizitaetsfaktor(werkstoff.get("E_Nmm2", 206000.0),
                              werkstoff.get("E_Nmm2", 206000.0),
                              werkstoff.get("nu", 0.3), werkstoff.get("nu", 0.3))

    eingriffe = []
    for lab, za, zb, ue, innen in (("Sonne/Planet", z_s, z_p, ue_sp, False),
                                   ("Planet/Hohlrad", z_p, z_h, ue_ph, True)):
        fa, fb = zahnform(za), zahnform(zb)
        if not fa.get("ok"):
            continue
        Y_e = _y_eps(ue["eps_alpha"])
        Z_e = _z_eps(ue["eps_alpha"], 0.0)
        Z_H = zonenfaktor(ue["alpha_wt"], ue["alpha_t"])
        sF = (F_t / (b * m)) * fa["Y_Fa"] * fa["Y_Sa"] * Y_e * K_F
        if fb.get("ok"):
            sF = max(sF, (F_t / (b * m)) * fb["Y_Fa"] * fb["Y_Sa"] * Y_e * K_F)
        u = zb / za
        # Innenverzahnung: (u-1)/u statt (u+1)/u -- die Kruemmungen wirken
        # gegeneinander, die Pressung faellt.
        faktor = (u - 1.0) / u if innen else (u + 1.0) / u
        sH = Z_H * Z_E * Z_e * math.sqrt(abs(F_t / (m * za * b) * faktor)) * math.sqrt(K_H)
        eingriffe.append({
            "eingriff": lab, "innen": innen,
            "eps_alpha": round(ue["eps_alpha"], 3),
            "sigma_F_Nmm2": round(sF, 1), "sigma_H_Nmm2": round(sH, 1),
            "S_F": round(werkstoff["sigma_Flim_Nmm2"] * Y_ST / sF, 2),
            "S_H": round(werkstoff["sigma_Hlim_Nmm2"] / sH, 2) if sH > 0 else None,
        })

    S_F = min((e["S_F"] for e in eingriffe), default=0.0)
    S_H = min((e["S_H"] for e in eingriffe if e["S_H"]), default=0.0)

    # Der Koerper des Hohlrads: Fusskreis der INNENverzahnung liegt AUSSEN vom
    # Teilkreis, dazu die Wand. Das ist die Zahl, die ueber „passt in die Welle"
    # entscheidet.
    d_f_hohlrad = d_h + 2.0 * m * HF_STERN
    d_aussen = d_f_hohlrad + 2.0 * WAND_HOHLRAD_M * m

    return {
        "ok": True, "name": name, "art": "planeten",
        "z_sonne": z_s, "z_planet": z_p, "z_hohlrad": z_h,
        "n_planeten": n_planeten, "k_gamma": k_gamma,
        "i_ist": round(beste["i_ist"], 4), "i_soll": i_soll,
        "i_fehler_pct": round(100.0 * beste["fehler"], 2),
        "m_mm": m, "b_mm": round(b, 1), "psi_m": psi_m,
        "d_sonne_mm": round(d_s, 2), "d_planet_mm": round(d_p, 2),
        "d_hohlrad_mm": round(d_h, 2),
        "d_hohlrad_fuss_mm": round(d_f_hohlrad, 2),
        "d_aussen_mm": round(d_aussen, 2),
        "wand_hohlrad_mm": round(WAND_HOHLRAD_M * m, 2),
        "a_sonne_planet_mm": round(a_sp, 2),
        "montage_ok": True, "nachbar_ok": bool(nachbar_ok),
        "nachbar_platz_mm": round(platz, 2), "d_kopf_planet_mm": round(d_a_p, 2),
        "T_eingriff_Nm": round(T_eingriff, 1),
        "eingriffe": eingriffe,
        "S_F": S_F, "S_H": S_H, "S_F_ziel": s_F_ziel, "S_H_ziel": s_H_ziel,
        "haelt": bool(S_F >= s_F_ziel and S_H >= s_H_ziel and nachbar_ok),
        "werkstoff": werkstoff.get("label", "?"),
        "werkstoff_beleg": werkstoff.get("beleg", "unbekannt"),
        "beiwerte": K, "T1_Nm": T_sonne_Nm, "n1_1pmin": n_sonne_1pmin,
    }


# ── Der Einbauort: passt der Satz in die Welle? ─────────────────────────────
#
# Der integrierte Antrieb legt den Planetensatz in die HOHLWELLE des Laeufers.
# Zwei Zahlen entscheiden, und beide gibt es schon:
#
#   1. Was der Satz BRAUCHT -- Hohlrad-Fusskreis plus Wand (``d_aussen_mm``).
#   2. Was die Welle HERGIBT -- und das ist nicht der Wunsch des Konstrukteurs,
#      sondern eine gerechnete Groesse: ``ema_welle.pruefen`` misst am Feld,
#      wie gross die Bohrung sein darf, ohne in den magnetischen Pfad zu
#      geraten (``bohrung.hoechstens_mm``).
#
# Beides nebeneinander, und dazu welche der beiden bindet. Ein Stirnradsatz
# wird hier ABGEWIESEN und nicht genaehert: er sitzt neben der Achse, nicht auf
# ihr, und laesst sich nicht in eine Bohrung legen.

def in_welle_pruefen(satz: dict, geom: dict, *, welle_befund: dict | None = None,
                     laenge_verfuegbar_mm: float = 0.0,
                     lager_je_seite_mm: float = 12.0) -> dict:
    """Passt ein Planetensatz in die Wellenbohrung? Radial UND axial.

    ``welle_befund`` ist das Ergebnis von ``ema_welle.pruefen``. Fehlt es, wird
    nur gegen die im Payload stehende Bohrung geprueft — und ausdruecklich
    gesagt, dass die magnetische Grenze dann NICHT geprueft wurde. Das ist der
    Unterschied zwischen „passt in die gezeichnete Bohrung" und „diese Bohrung
    ist ueberhaupt zulaessig".
    """
    if satz.get("art") != "planeten":
        return {"ok": False, "passt": False,
                "grund": (f"Nur ein Planetensatz kann in der Welle sitzen — "
                          f"'{satz.get('art', '?')}' arbeitet achsparallel und "
                          f"braucht einen eigenen Achsabstand ({satz.get('a_mm', '?')} mm). "
                          f"Einbau 'in_welle' ist dafuer nicht darstellbar.")}

    d_noetig = float(satz["d_aussen_mm"])
    d_gezeichnet = float(geom.get("shaftBoreD", 0) or 0)
    d_welle = float(geom.get("shaftD", 0) or 0)

    d_magnetisch = None
    if welle_befund and welle_befund.get("ok"):
        d_magnetisch = float((welle_befund.get("bohrung") or {}).get("hoechstens_mm", 0))

    grenzen = [("gezeichnete Bohrung (shaftBoreD)", d_gezeichnet)]
    if d_magnetisch is not None:
        grenzen.append(("magnetisch zulaessig (ema_welle)", d_magnetisch))
    # Die Welle selbst ist die harte Schranke: mehr als ihr Aussendurchmesser
    # abzueglich einer Restwand geht nie.
    if d_welle > 0:
        grenzen.append(("Wellendurchmesser minus Restwand", max(0.0, d_welle - 2.0)))

    bindend, d_verfuegbar = min(((n, v) for n, v in grenzen if v > 0),
                                key=lambda nv: nv[1], default=("keine Angabe", 0.0))
    passt_radial = d_verfuegbar > 0 and d_noetig <= d_verfuegbar

    # Axial: der Satz braucht seine Zahnbreite plus die Lager auf beiden Seiten.
    l_noetig = float(satz["b_mm"]) + 2.0 * lager_je_seite_mm
    passt_axial = (laenge_verfuegbar_mm <= 0) or (l_noetig <= laenge_verfuegbar_mm)

    saetze = []
    if passt_radial:
        saetze.append(f"Radial passt es: der Satz braucht {d_noetig:.1f} mm "
                      f"Bohrung, verfuegbar sind {d_verfuegbar:.1f} mm "
                      f"({bindend}).")
    else:
        fehlt = d_noetig - d_verfuegbar
        saetze.append(f"Radial passt es NICHT: der Satz braucht {d_noetig:.1f} mm "
                      f"Bohrung, verfuegbar sind {d_verfuegbar:.1f} mm "
                      f"({bindend}) — es fehlen {fehlt:.1f} mm.")
    if d_magnetisch is None:
        saetze.append("Die MAGNETISCHE Grenze wurde nicht geprueft: ohne Befund "
                      "aus 'welle' steht hier nur, was gezeichnet ist, nicht was "
                      "zulaessig ist.")
    elif d_magnetisch < d_gezeichnet:
        saetze.append(f"Achtung: die gezeichnete Bohrung ({d_gezeichnet:.1f} mm) "
                      f"ist bereits groesser als magnetisch zulaessig "
                      f"({d_magnetisch:.1f} mm) — das ist unabhaengig vom Getriebe "
                      f"ein Befund fuer sich.")
    if laenge_verfuegbar_mm > 0:
        saetze.append(f"Axial {'passt' if passt_axial else 'passt NICHT'}: "
                      f"{l_noetig:.1f} mm noetig (Zahnbreite {satz['b_mm']:.1f} + "
                      f"2 x {lager_je_seite_mm:.0f} mm Lager), "
                      f"{laenge_verfuegbar_mm:.1f} mm vorhanden.")

    return {
        "ok": True, "passt": bool(passt_radial and passt_axial),
        "passt_radial": bool(passt_radial), "passt_axial": bool(passt_axial),
        "d_noetig_mm": round(d_noetig, 1),
        "d_verfuegbar_mm": round(d_verfuegbar, 1),
        "bindend": bindend,
        "grenzen": [{"was": n, "d_mm": round(v, 1)} for n, v in grenzen],
        "d_magnetisch_mm": (None if d_magnetisch is None else round(d_magnetisch, 1)),
        "magnetisch_geprueft": d_magnetisch is not None,
        "l_noetig_mm": round(l_noetig, 1),
        "l_verfuegbar_mm": round(laenge_verfuegbar_mm, 1),
        "satz": " ".join(saetze),
        "vorbehalt": ("Geprueft ist PLATZ. Ob die verbleibende Wellenwand das "
                      "Moment und die Fliehkraft traegt, sagt die Festigkeit "
                      "('struktur', 'sicherheit') — eine Bohrung, in die das "
                      "Getriebe passt, kann mechanisch unzulaessig sein."),
    }


# ── Verluste: lastabhaengig, nicht als Konstante ────────────────────────────
#
# ``eta_drive: 0.95`` sagt bei Volllast dasselbe wie im Schub, und das ist der
# Punkt, an dem die alte Vorgabe am deutlichsten falsch war: die Reibung in der
# Verzahnung waechst mit der Last, die Lager- und Planschverluste aber NICHT --
# sie haengen an der Drehzahl. Bei kleiner Last frisst der drehzahlabhaengige
# Anteil einen viel groesseren Bruchteil, der Wirkungsgrad bricht ein. Genau
# diese Form fehlte dem Fahrzyklus.

RHO_STAHL = 7850.0          # kg/m^3


def zahnverlustgrad(z1: int, z2: int, eps_alpha: float, eps_1: float,
                    eps_2: float, beta_grad: float = 0.0) -> float:
    """``H_V`` nach Ohlendorf -- aus der Geometrie, nicht aus einer Faustzahl."""
    u = abs(z2) / max(abs(z1), 1)
    beta = _bog(beta_grad)
    beta_b = math.asin(math.sin(beta) * math.cos(_bog(ALPHA_N_GRAD))) if beta else 0.0
    if z1 <= 0 or u <= 0:
        return 0.0
    return (math.pi * (u + 1.0) / (abs(z1) * u * math.cos(beta_b))
            * (1.0 - eps_alpha + eps_1 ** 2 + eps_2 ** 2))


def verluste(stufen: list, P_ab_W: float, n_ein_1pmin: float,
             P_nenn_W: float, n_nenn_1pmin: float,
             mu_m: float = 0.05,
             leerlauf_anteil: float = LEERLAUF_ANTEIL) -> dict:
    """Wirkungsgrad bei DIESEM Betriebspunkt.

    Zwei Anteile, und sie verhalten sich gegenlaeufig:

    * **Verzahnung** -- ``P_z = P_ab * H_V * mu_m`` je Eingriff. Waechst mit der
      Last, der Wirkungsgrad bleibt dabei annaehernd konstant.
    * **Leerlauf** (Lager, Planschen, Dichtungen) -- haengt an der DREHZAHL,
      nicht an der Last. Bei kleiner Last ist er der ganze Verlust.

    Deshalb steigt der Wirkungsgrad mit der Last und faellt mit der Drehzahl.
    ``mu_m`` und ``leerlauf_anteil`` sind Annahmen (s. Modulkopf).
    """
    P_ab_W = abs(float(P_ab_W))
    n_ein = abs(float(n_ein_1pmin))
    h_v_summe = 0.0
    for st in stufen:
        h_v_summe += float(st.get("H_V", 0.0))
    P_zahn = P_ab_W * h_v_summe * mu_m
    P_leer = (leerlauf_anteil * abs(P_nenn_W) * len(stufen)
              * (n_ein / n_nenn_1pmin if n_nenn_1pmin else 1.0))
    P_verlust = P_zahn + P_leer
    eta = P_ab_W / (P_ab_W + P_verlust) if (P_ab_W + P_verlust) > 0 else 0.0
    return {"eta": eta, "P_verlust_W": P_verlust,
            "P_zahn_W": P_zahn, "P_leerlauf_W": P_leer,
            "H_V_summe": h_v_summe, "mu_m": mu_m,
            "leerlauf_anteil": leerlauf_anteil}


def _scheibe_J(d_a_mm: float, d_i_mm: float, b_mm: float,
               rho: float = RHO_STAHL) -> tuple:
    """Masse [kg] und Traegheit [kg m^2] eines Rades als Ring/Scheibe."""
    ra, ri, b = d_a_mm / 2000.0, max(d_i_mm, 0.0) / 2000.0, b_mm / 1000.0
    v = math.pi * (ra ** 2 - ri ** 2) * b
    m = rho * v
    J = 0.5 * m * (ra ** 2 + ri ** 2)
    return m, J


def massen_traegheit(stufen: list, art: str = "stirnrad") -> dict:
    """Masse und die auf die EINTRITTSWELLE bezogene Traegheit.

    ``J_red = J_1 + J_2/i_1^2 + J_3/(i_1 i_2)^2 …`` -- genau so wirkt sie beim
    Beschleunigen, und genau so gehoert sie in den Fahrzyklus. Die Traegheit der
    zweiten Stufe zaehlt nur mit ``1/i^2``; wer sie ungeteilt addiert, rechnet
    sie um den Faktor i^2 zu gross.
    """
    m_ges, J_red = 0.0, 0.0
    i_kum = 1.0
    einzeln = []
    for st in stufen:
        if st.get("art") == "planeten":
            m1, J1 = _scheibe_J(st["d_sonne_mm"] + 2 * st["m_mm"], 0.0, st["b_mm"])
            mp, Jp = _scheibe_J(st["d_planet_mm"] + 2 * st["m_mm"], 0.0, st["b_mm"])
            mh, Jh = _scheibe_J(st["d_aussen_mm"], st["d_hohlrad_mm"], st["b_mm"])
            m_st = m1 + st["n_planeten"] * mp + mh
            # Das Hohlrad steht -- es traegt Masse, aber keine Traegheit.
            J_ein = J1
            J_aus = st["n_planeten"] * Jp
            i_st = st["i_ist"]
        else:
            m1, J1 = _scheibe_J(st["da1_mm"], 0.0, st["b_mm"])
            m2, J2 = _scheibe_J(st["da2_mm"], 0.0, st["b_mm"])
            m_st = m1 + m2
            J_ein, J_aus = J1, J2
            i_st = st["i_ist"]
        m_ges += m_st
        J_red += J_ein / (i_kum ** 2) + J_aus / ((i_kum * i_st) ** 2)
        einzeln.append({"stufe": st.get("name", "?"), "masse_kg": round(m_st, 2),
                        "J_ein_kgm2": round(J_ein, 6), "J_aus_kgm2": round(J_aus, 6),
                        "i": i_st})
        i_kum *= i_st
    return {"masse_kg": round(m_ges, 2), "J_red_kgm2": round(J_red, 6),
            "je_stufe": einzeln,
            "hinweis": ("Radkoerper als volle Scheiben gerechnet — ein "
                        "ausgedrehtes Rad ist leichter. Die Zahl ist damit die "
                        "obere Schranke, nicht die gebaute Masse.")}


# ── Die Stufenteilung ───────────────────────────────────────────────────────

def uebersetzung_aufteilen(i_ges: float, stufen: int, art: str = "stirnrad") -> dict:
    """Gesamtuebersetzung auf die Stufen verteilen.

    Fuer zwei Stufen ``i1 ~ sqrt(1,2 * i_ges)``: die SCHNELLE Stufe bekommt
    etwas weniger. Grund ist das Bauvolumen -- das langsame Rad ist das grosse,
    und wer ihm die kleinere Uebersetzung gibt, macht es unnoetig gross. Beide
    werden auf die Stufengrenze der Bauart geklemmt; passt die Gesamtuebersetzung
    dann nicht mehr, ist das eine Antwort und keine Panne.
    """
    i_ges = abs(float(i_ges))
    i_max = I_MAX_STUFE.get(art, 6.3)
    stufen = max(1, int(stufen))
    if stufen == 1:
        if i_ges > i_max:
            return {"ok": False,
                    "grund": (f"i = {i_ges:.2f} ueberschreitet die Grenze einer "
                              f"{art}-Stufe ({i_max:g}). Zwei Stufen oder eine "
                              f"andere Bauart.")}
        return {"ok": True, "i_stufen": [i_ges], "i_ges": i_ges}
    if stufen > 2:
        return {"ok": False, "grund": "mehr als zwei Stufen sind hier nicht vorgesehen"}
    i1 = math.sqrt(1.2 * i_ges)
    i1 = min(max(i1, 1.0), i_max)
    i2 = i_ges / i1
    if i2 > i_max:
        i2 = i_max
        i1 = i_ges / i2
    if i1 > i_max:
        return {"ok": False,
                "grund": (f"i = {i_ges:.2f} passt nicht in zwei {art}-Stufen zu "
                          f"je hoechstens {i_max:g} (das waeren {i_max*i_max:.1f}).")}
    return {"ok": True, "i_stufen": [i1, i2], "i_ges": i_ges}


# ── Die ganze Kette ─────────────────────────────────────────────────────────

def auslegen(spec: dict) -> dict:
    """Von der geforderten Uebersetzung bis zu Wirkungsgrad, Masse und Traegheit.

    ``spec``:
      ``art``            stirnrad | planeten | kegelrad | schnecke
      ``einbau``         achsparallel | koaxial | in_welle
      ``stufen``         1 oder 2 (nur stirnrad)
      ``i`` ODER ``n_motor_1pmin`` + ``n_ab_1pmin``
      ``T_motor_Nm``     Moment an der Getriebe-EINGANGswelle
      ``n_motor_1pmin``  Drehzahl dort
      ``werkstoff``      Schluessel in ``ema_referenz.GETRIEBE_WERKSTOFF``
      ``geom``           Payload-Geometrie (nur fuer ``einbau='in_welle'``)
      ``welle_befund``   Ergebnis von ``ema_welle.pruefen`` (optional, s. dort)
    """
    art = str(spec.get("art", "stirnrad")).lower()
    einbau = str(spec.get("einbau", "")).lower() or (
        "koaxial" if art == "planeten" else "achsparallel")
    if art not in EINBAU_ERLAUBT:
        return {"ok": False, "grund": f"Bauart '{art}' gibt es nicht. Bekannt: "
                                      + ", ".join(sorted(EINBAU_ERLAUBT))}
    if einbau not in EINBAU_ARTEN:
        return {"ok": False, "grund": f"Einbau '{einbau}' gibt es nicht. Bekannt: "
                                      + ", ".join(EINBAU_ARTEN)}
    if einbau not in EINBAU_ERLAUBT[art]:
        return {"ok": False,
                "grund": (f"'{art}' laesst sich nicht '{einbau}' einbauen. "
                          f"Moeglich waere: "
                          + ", ".join(EINBAU_ERLAUBT[art])
                          + ". " + ("Nur ein Planetensatz sitzt koaxial und "
                                    "kann damit in der Welle liegen."
                                    if einbau == "in_welle" else ""))}

    werkstoff = spec.get("werkstoff_dict") or _werkstoff_holen(spec.get("werkstoff"))
    if not werkstoff.get("ok", True):
        return {"ok": False, "grund": werkstoff.get("grund", "Werkstoff unbekannt")}

    n_mot = float(spec.get("n_motor_1pmin", 0) or 0)
    n_ab = float(spec.get("n_ab_1pmin", 0) or 0)
    i_ges = float(spec.get("i", 0) or 0)
    if i_ges <= 0:
        if n_mot > 0 and n_ab > 0:
            i_ges = n_mot / n_ab
        else:
            return {"ok": False, "grund": "Weder 'i' noch 'n_motor_1pmin' + "
                                          "'n_ab_1pmin' gegeben."}
    T_mot = float(spec.get("T_motor_Nm", 0) or 0)
    if T_mot <= 0:
        return {"ok": False, "grund": "'T_motor_Nm' fehlt — ohne Moment kein Modul."}

    if art in ("kegelrad", "schnecke"):
        return _sonderbauart(art, i_ges, T_mot, n_mot, werkstoff, spec)

    stufen_n = int(spec.get("stufen", 1) or 1)
    if art == "planeten":
        stufen_n = 1
    teil = uebersetzung_aufteilen(i_ges, stufen_n, art)
    if not teil.get("ok"):
        return {"ok": False, "grund": teil["grund"]}

    beiwerte = spec.get("beiwerte") or {}
    psi_m = float(spec.get("psi_m", 20.0 if art == "stirnrad" else 18.0))
    beta = float(spec.get("beta_grad", 0.0))

    stufen, T_i, n_i, i_kum = [], T_mot, n_mot, 1.0
    for k, i_st in enumerate(teil["i_stufen"], start=1):
        if art == "planeten":
            st = planetensatz(T_i, i_st, werkstoff, psi_m=psi_m,
                              n_planeten=int(spec.get("n_planeten", 3)),
                              n_sonne_1pmin=n_i, beiwerte=beiwerte,
                              k_gamma=float(spec.get("k_gamma", 1.15)),
                              name="Planetensatz")
        else:
            st = stufe_auslegen(T_i, i_st, werkstoff, psi_m=psi_m,
                                beta_grad=beta, n1_1pmin=n_i,
                                beiwerte=beiwerte, name=f"Stufe {k}")
        if not st.get("ok"):
            return {"ok": False, "grund": st.get("grund"), "stufe": k}
        # Zahnverlustgrad je Stufe -- er geht in den Wirkungsgrad ein.
        if art == "planeten":
            ue = ueberdeckung(st["z_sonne"], st["z_planet"], st["m_mm"], st["b_mm"])
            st["H_V"] = zahnverlustgrad(st["z_sonne"], st["z_planet"],
                                        ue["eps_alpha"], ue["eps_1"], ue["eps_2"])
        else:
            ue = ueberdeckung(st["z1"], st["z2"], st["m_mm"], st["b_mm"],
                              beta_grad=beta)
            st["H_V"] = zahnverlustgrad(st["z1"], st["z2"], ue["eps_alpha"],
                                        ue["eps_1"], ue["eps_2"], beta)
        stufen.append(st)
        # Moment und Drehzahl fuer die naechste Stufe -- das Moment waechst.
        T_i = T_i * st["i_ist"]
        n_i = n_i / st["i_ist"] if st["i_ist"] else n_i
        i_kum *= st["i_ist"]

    P_nenn = T_mot * 2.0 * math.pi * n_mot / 60.0 if n_mot else 0.0
    verl = verluste(stufen, P_nenn, n_mot, P_nenn, n_mot,
                    mu_m=float((spec.get("beiwerte") or {}).get(
                        "mu_m", BEIWERTE_VORGABE["mu_m"])))
    mt = massen_traegheit(stufen, art)

    erg = {
        "ok": True, "art": art, "einbau": einbau,
        "einbau_text": EINBAU_ARTEN[einbau],
        "i_soll": round(i_ges, 4), "i_ist": round(i_kum, 4),
        "i_fehler_pct": round(100.0 * abs(i_kum - i_ges) / i_ges, 2),
        "stufen": stufen, "n_stufen": len(stufen),
        "T_motor_Nm": T_mot, "n_motor_1pmin": n_mot,
        "T_ab_Nm": round(T_mot * i_kum * verl["eta"], 1),
        "n_ab_1pmin": round(n_mot / i_kum, 1) if i_kum else None,
        "P_nenn_W": round(P_nenn, 1),
        "wirkungsgrad": {"eta_nenn": round(verl["eta"], 4), **{
            k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in verl.items() if k != "eta"}},
        "masse_kg": mt["masse_kg"], "J_red_kgm2": mt["J_red_kgm2"],
        "massen": mt,
        "werkstoff": werkstoff.get("label"),
        "werkstoff_beleg": werkstoff.get("beleg"),
        "haelt": all(st.get("haelt") for st in stufen),
    }

    if einbau == "in_welle":
        erg["in_welle"] = in_welle_pruefen(
            stufen[0], spec.get("geom") or {},
            welle_befund=spec.get("welle_befund"),
            laenge_verfuegbar_mm=float(spec.get("laenge_verfuegbar_mm", 0) or 0))
        erg["passt"] = bool(erg["in_welle"].get("passt"))
        # ``haelt`` bleibt die Aussage ueber die VERZAHNUNG und wird hier NICHT
        # mit ``passt`` verrechnet. Zusammengeworfen las sich ein Satz, der
        # traegt und nur nicht in die Bohrung geht, als „traegt nicht" — und
        # schickte die Suche zu mehr Modul statt zu mehr Platz. Wer beides
        # zugleich braucht, fragt ``haelt and passt`` (so macht es das Verb).
    return erg


def _werkstoff_holen(schluessel) -> dict:
    """Werkstoff aus ``ema_referenz`` -- die eine Quelle fuer Fremdwerte."""
    try:
        import ema_referenz
        tabelle = getattr(ema_referenz, "GETRIEBE_WERKSTOFF", {})
    except Exception:                                        # noqa: BLE001
        return {"ok": False, "grund": "ema_referenz nicht ladbar"}
    if not tabelle:
        return {"ok": False, "grund": "ema_referenz.GETRIEBE_WERKSTOFF ist leer"}
    key = str(schluessel or "").strip() or next(iter(tabelle))
    w = tabelle.get(key)
    if w is None:
        return {"ok": False, "grund": (f"Werkstoff '{key}' unbekannt. Bekannt: "
                                       + ", ".join(sorted(tabelle)))}
    return dict(w, ok=True, schluessel=key)


def _sonderbauart(art: str, i_ges: float, T_mot: float, n_mot: float,
                  werkstoff: dict, spec: dict) -> dict:
    """Kegelrad und Schnecke -- Geometrie ja, Tragfaehigkeit nur so weit sie traegt.

    Beides sind eigene Formelwelten. Sie hier auf dieselbe Stufe wie das
    Stirnrad zu stellen waere eine Behauptung, deshalb steht an jeder Zahl das
    Verfahren:

    * **Kegelrad** -- Geometrie voll, Tragfaehigkeit ueber das ERSATZ-Stirnrad
      (Tredgold): der Kegelzahn wird auf einen gedachten Stirnradzahn mit der
      Ersatzzaehnezahl ``z_v = z / cos(delta)`` abgebildet. Eine Naeherung.
    * **Schnecke** -- KEINE Zahnfussrechnung. Was dort zaehlt, ist der
      Wirkungsgrad (und mit ihm die Erwaermung) und die Selbsthemmung; beide
      haengen so stark am Reibwert, dass eine Spanne ausgegeben wird und keine
      Zahl.
    """
    i_max = I_MAX_STUFE[art]
    if i_ges > i_max:
        return {"ok": False, "grund": f"i = {i_ges:.2f} ueber der Grenze einer "
                                      f"{art}-Stufe ({i_max:g})."}
    if art == "kegelrad":
        zz = zaehnezahlen(i_ges, z_min=Z_MIN_OHNE_X)
        if not zz.get("ok"):
            return {"ok": False, "grund": zz["grund"]}
        z1, z2 = zz["z1"], zz["z2"]
        delta1 = math.atan(z1 / z2)                    # Teilkegelwinkel, Achswinkel 90
        delta2 = math.pi / 2.0 - delta1
        z_v1 = z1 / math.cos(delta1)
        z_v2 = z2 / math.cos(delta2)
        # Ersatz-Stirnradpaar; die Breite eines Kegelrads ist kleiner (b <= R_e/3).
        st = stufe_auslegen(T_mot, z_v2 / z_v1, werkstoff,
                            psi_m=float(spec.get("psi_m", 12.0)),
                            n1_1pmin=n_mot, beiwerte=spec.get("beiwerte") or {},
                            name="Kegelrad (Ersatz-Stirnrad)")
        if not st.get("ok"):
            return {"ok": False, "grund": st["grund"]}
        m = st["m_mm"]
        d1, d2 = m * z1, m * z2
        R_e = math.sqrt(d1 ** 2 + d2 ** 2) / 2.0
        b = min(st["b_mm"], R_e / 3.0)
        st["H_V"] = 0.20                       # Annahme: Kegelrad reibt mehr
        P_nenn = T_mot * 2.0 * math.pi * n_mot / 60.0 if n_mot else 0.0
        verl = verluste([st], P_nenn, n_mot, P_nenn, n_mot)
        return {"ok": True, "art": art, "einbau": "achsparallel",
                "einbau_text": EINBAU_ARTEN["achsparallel"] + " (Achswinkel 90 Grad)",
                "i_soll": round(i_ges, 4), "i_ist": round(z2 / z1, 4),
                "i_fehler_pct": round(100.0 * zz["fehler"], 2),
                "z1": z1, "z2": z2, "m_mm": m, "b_mm": round(b, 1),
                "d1_mm": round(d1, 2), "d2_mm": round(d2, 2),
                "delta1_grad": round(_grad(delta1), 2),
                "delta2_grad": round(_grad(delta2), 2),
                "z_ersatz1": round(z_v1, 1), "z_ersatz2": round(z_v2, 1),
                "aussenkegellaenge_mm": round(R_e, 2),
                "S_F": st["S_F"], "S_H": st["S_H"], "haelt": st["haelt"],
                "stufen": [st], "n_stufen": 1,
                "T_motor_Nm": T_mot, "n_motor_1pmin": n_mot,
                "wirkungsgrad": {"eta_nenn": round(verl["eta"], 4), **verl},
                "verfahren": ("Tragfaehigkeit ueber das ERSATZ-Stirnrad "
                              "(Tredgold, z_v = z/cos(delta)) — eine Naeherung. "
                              "Eine Kegelradnorm (ISO 10300) rechnet anders."),
                "werkstoff": werkstoff.get("label"),
                "werkstoff_beleg": werkstoff.get("beleg")}

    # Schnecke
    z1 = int(spec.get("z_schnecke", 2) or 2)               # Gaengezahl
    z2 = max(int(round(i_ges * z1)), 20)
    m = float(spec.get("m_mm", 0) or 0) or modul_normen(
        (T_mot * 1000.0 / (0.08 * z2 * z2)) ** (1.0 / 3.0))
    q = float(spec.get("formzahl_q", 10.0))                # Durchmesserkennzahl
    d1, d2 = q * m, m * z2
    gamma = math.atan(z1 / q)                              # Steigungswinkel
    spanne = []
    for mu in (0.03, 0.05, 0.08):
        rho = math.atan(mu)
        eta = math.tan(gamma) / math.tan(gamma + rho)
        spanne.append({"mu": mu, "eta": round(eta, 4)})
    selbsthemmend = _grad(gamma) < _grad(math.atan(0.05))
    return {"ok": True, "art": art, "einbau": "achsparallel",
            "einbau_text": EINBAU_ARTEN["achsparallel"] + " (Achswinkel 90 Grad)",
            "i_soll": round(i_ges, 4), "i_ist": round(z2 / z1, 4),
            "z_schnecke": z1, "z_rad": z2, "m_mm": m,
            "d_schnecke_mm": round(d1, 2), "d_rad_mm": round(d2, 2),
            "steigungswinkel_grad": round(_grad(gamma), 2),
            "formzahl_q": q,
            "wirkungsgrad_spanne": spanne,
            "selbsthemmend": bool(selbsthemmend),
            "haelt": None,
            "verfahren": ("KEINE Zahnfussrechnung. Bei der Schnecke entscheiden "
                          "Wirkungsgrad, Erwaermung und Selbsthemmung, und der "
                          "Wirkungsgrad haengt so stark am Reibwert, dass hier "
                          "eine SPANNE steht (mu = 0,03…0,08) und keine Zahl. "
                          "Eine Tragfaehigkeit nach DIN 3996 ist nicht gerechnet."),
            "werkstoff": werkstoff.get("label"),
            "werkstoff_beleg": werkstoff.get("beleg"),
            "T_motor_Nm": T_mot, "n_motor_1pmin": n_mot, "stufen": [], "n_stufen": 1}


# ── Ausgabe ─────────────────────────────────────────────────────────────────

def als_text(e: dict) -> str:
    """Der Befund als Text. Fuer einen Agenten ist das die eigentliche Ausgabe:
    ein Bild kann er nicht lesen, und Base64 wird ohnehin herausgefiltert."""
    if not e.get("ok"):
        return f"GETRIEBE: nicht auslegbar — {e.get('grund', 'kein Grund genannt')}"

    art = e["art"]
    z = [f"GETRIEBE  {art}, {e['einbau']} ({e['einbau_text']})",
         f"  Uebersetzung : {e['i_ist']} (gefordert {e['i_soll']}, "
         f"Abweichung {e['i_fehler_pct']} %)"]
    if e.get("n_stufen"):
        z.append(f"  Stufen       : {e['n_stufen']}")
    z.append(f"  Eingang      : {e.get('T_motor_Nm', 0):.1f} Nm bei "
             f"{e.get('n_motor_1pmin', 0):.0f} 1/min")
    if e.get("T_ab_Nm"):
        z.append(f"  Abtrieb      : {e['T_ab_Nm']:.1f} Nm bei "
                 f"{e.get('n_ab_1pmin', 0):.0f} 1/min")
    z.append(f"  Werkstoff    : {e.get('werkstoff', '?')}  "
             f"[{e.get('werkstoff_beleg', '?')}]")
    z.append("")

    for st in e.get("stufen", []):
        if st.get("art") == "planeten":
            z.append(f"  {st['name']}: Sonne {st['z_sonne']} / Planet "
                     f"{st['z_planet']} x{st['n_planeten']} / Hohlrad {st['z_hohlrad']}")
            z.append(f"    Modul {st['m_mm']} mm, Breite {st['b_mm']} mm, "
                     f"i = {st['i_ist']}")
            z.append(f"    Sonne {st['d_sonne_mm']} / Planet {st['d_planet_mm']} / "
                     f"Hohlrad {st['d_hohlrad_mm']} mm, aussen {st['d_aussen_mm']} mm")
            for ei in st.get("eingriffe", []):
                z.append(f"    {ei['eingriff']:16s} eps_a {ei['eps_alpha']:5.3f}  "
                         f"S_F {ei['S_F']:5.2f}  S_H "
                         + ("—" if ei["S_H"] is None else f"{ei['S_H']:5.2f}"))
            if not st.get("nachbar_ok"):
                z.append(f"    ⚠ Die Planeten beruehren sich: Kopfkreis "
                         f"{st['d_kopf_planet_mm']} mm, Platz "
                         f"{st['nachbar_platz_mm']} mm.")
        else:
            z.append(f"  {st.get('name', 'Stufe')}: z {st['z1']}/{st['z2']}, "
                     f"i = {st['i_ist']:.4f} ({st['i_fehler_pct']} %)")
            z.append(f"    Modul {st['m_mm']} mm  (Zahnfuss allein braeuchte "
                     f"{st['m_zahnfuss_mm']} mm — bindend: {st['bindend']})")
            z.append(f"    Breite {st['b_mm']} mm, Achsabstand {st['a_mm']} mm, "
                     f"d {st['d1_mm']}/{st['d2_mm']} mm")
            z.append(f"    eps_alpha {st['eps_alpha']}, F_t {st['F_t_N']:.0f} N, "
                     f"v {st['v_umfang_ms']} m/s")
            z.append(f"    sigma_F {st['sigma_F1_Nmm2']:.0f} N/mm^2 -> S_F "
                     f"{st['S_F']} (Ziel {st['S_F_ziel']})")
            z.append(f"    sigma_H {st['sigma_H_Nmm2']:.0f} N/mm^2 -> S_H "
                     f"{st['S_H']} (Ziel {st['S_H_ziel']})")
            if st.get("hinweis_zaehne"):
                z.append(f"    Hinweis: {st['hinweis_zaehne']}")
        z.append("")

    if art == "kegelrad":
        z += [f"  Teilkegelwinkel {e['delta1_grad']}° / {e['delta2_grad']}°, "
              f"Ersatzzaehnezahlen {e['z_ersatz1']}/{e['z_ersatz2']}",
              f"  Aussenkegellaenge {e['aussenkegellaenge_mm']} mm", ""]
    if art == "schnecke":
        z += [f"  Schnecke {e['z_schnecke']}-gaengig, Rad {e['z_rad']} Zaehne, "
              f"Modul {e['m_mm']} mm",
              f"  Steigungswinkel {e['steigungswinkel_grad']}°, "
              f"selbsthemmend: {'ja' if e['selbsthemmend'] else 'nein'}",
              "  Wirkungsgrad je nach Reibwert:"]
        for s in e["wirkungsgrad_spanne"]:
            z.append(f"    mu = {s['mu']:.2f}  ->  eta = {s['eta']:.3f}")
        z.append("")

    w = e.get("wirkungsgrad") or {}
    if w:
        z += [f"  Wirkungsgrad (Nennpunkt): {w.get('eta_nenn', 0):.4f}",
              f"    Verzahnung {w.get('P_zahn_W', 0):.0f} W + Leerlauf "
              f"{w.get('P_leerlauf_W', 0):.0f} W = {w.get('P_verlust_W', 0):.0f} W",
              f"    Der Leerlaufanteil haengt an der DREHZAHL, nicht an der Last —",
              f"    darum steigt der Wirkungsgrad mit der Last und faellt mit n.", ""]
    if e.get("masse_kg") is not None:
        z += [f"  Masse   : {e['masse_kg']} kg  (Radkoerper als volle Scheiben — "
              f"obere Schranke)",
              f"  Traegheit: {e['J_red_kgm2']} kg m^2, auf die EINGANGSwelle "
              f"bezogen (J/i^2)", ""]

    iw = e.get("in_welle")
    if iw:
        z += ["  EINBAU IN DER WELLE:", "    " + iw["satz"], ""]
        for g in iw.get("grenzen", []):
            z.append(f"      {g['was']:38s} {g['d_mm']:8.1f} mm")
        z.append(f"      {'gebraucht':38s} {iw['d_noetig_mm']:8.1f} mm")
        z.append("")
        z.append("    " + iw["vorbehalt"])
        z.append("")

    if e.get("verfahren"):
        z += ["  VERFAHREN: " + e["verfahren"], ""]
    if e.get("werkstoff_beleg") == "annahme":
        z.append("  ACHTUNG: die Festigkeitskennwerte sind eine ANNAHME "
                 "(Groessenordnung der")
        z.append("  Werkstoffklasse), keine zitierte Messung. Damit ist jede "
                 "Sicherheit oben")
        z.append("  eine Groessenordnung. Belegen: cae_cli.py recherche.")
    # „Haelt nicht" und „passt nicht" sind zweierlei, und sie zusammenzuwerfen
    # schickt die Suche in die falsche Richtung: eine Verzahnung, die traegt und
    # nur nicht in die Bohrung geht, braucht mehr Platz — nicht mehr Modul.
    verzahnung_haelt = e.get("haelt")
    if verzahnung_haelt is False:
        z.append("  ⚠ Die VERZAHNUNG traegt nicht — s. die Sicherheiten oben. "
                 "Mehr Modul, mehr Breite oder ein besserer Werkstoff.")
    elif verzahnung_haelt is None:
        z.append("  Eine Tragfaehigkeit wurde fuer diese Bauart nicht gerechnet.")
    if iw and not iw.get("passt"):
        z.append("  ⚠ Der Satz PASST NICHT an den gewaehlten Einbauort. Die "
                 "Verzahnung ist davon unberuehrt —")
        z.append("  was fehlt, ist Platz: groessere Bohrung, kleinere "
                 "Uebersetzung oder ein anderer Einbau.")
    return "\n".join(z)
