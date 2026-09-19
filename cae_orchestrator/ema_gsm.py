"""Fremderregte Gleichstrommaschine (GSM) -- analytisch, in der Hauskonvention.

Warum sie wirklich gerechnet wird und nicht nur gezeichnet
-----------------------------------------------------------

Ein Kommutator, der nur gezeichnet ist, liefert Zahlen unter falschem Namen --
genau der Fehler, gegen den ``ema_maschinenart`` gebaut ist. Die GSM bekommt
deshalb dieselben fuenf Funktionen wie ``ema_asm``/``ema_eesm``/``ema_synrm``
(``k_norm``, ``betriebspunkt``, ``verluste``, ``dauermoment``,
``massen_und_kosten``) und dazu das, was sie von allen anderen unterscheidet.

Was sie von den anderen vier unterscheidet
-------------------------------------------

Bei PSM, ASM, SynRM und EESM dreht ein **Feld** und der Laeufer folgt ihm. Hier
steht das Feld still (Schenkelpole am STAENDER, gleichstromerregt), und der
**Kommutator** schaltet den Ankerstrom so um, dass die Durchflutung des
drehenden Ankers im Raum stehen bleibt. Daraus folgt alles Weitere:

    E = (p*z)/(2*pi*a) * Phi * omega          [V]
    T = (p*z)/(2*pi*a) * Phi * I_a            [Nm]

mit derselben Maschinenkonstante ``k = p*z/(2*pi*a)``. Dass beide dieselbe
Konstante tragen, ist keine Schoenheit, sondern die **Leistungserhaltung**:
``E*I_a = T*omega`` gilt damit exakt, und ``test_gsm.py`` schliesst die Formel
genau darueber gegen sich selbst -- was eine Formel wirklich prueft, waehrend
ein festgenagelter Zahlenwert nur prueft, dass sich nichts geaendert hat.

``a`` ist die Zahl der **Zweigpaare**: Schleifenwicklung ``a = p`` (2p Zweige),
Wellenwicklung ``a = 1`` (2 Zweige). Beide Bauarten liefern bei gleicher
Maschine dieselbe LEISTUNG und teilen sie nur anders auf Strom und Spannung auf
-- die Wellenwicklung macht eine Hochspannungs-Kleinstrom-Maschine daraus.

Warum ``k_norm`` hier 1,0 ist
------------------------------

Die Normierungsbruecke der anderen Module (``pi*k_w*N_ph/p^2``) gibt es, weil
``compute_performance`` eine auf **eine Windung je Nut** normierte
Flussverkettung herausgibt, waehrend die Magnetkreisrechnung mit der
physikalischen Durchflutung arbeitet. Hier entsteht die Maschinenkonstante
**geometrisch exakt** aus Leiterzahl, Polpaarzahl und Zweigpaaren -- es gibt
nichts umzurechnen. ``k_norm`` gibt darum 1,0 zurueck, und dieser Absatz ist der
Grund; eine stillschweigende 1,0 saehe aus wie ein vergessener Faktor.

Das eigentliche Tor: die Kommutierung
--------------------------------------

Eine Gleichstrommaschine wird nicht vom Eisen begrenzt, sondern vom
Kommutator. Drei Groessen entscheiden ueber ihre Baugroesse, und alle drei
stehen in ``kommutierung``:

* **Mittlere Lamellenspannung** ``U_l = 2a*E/k_lam``. Ueber rund 18 V wird der
  Abstand zwischen zwei Lamellen zur Funkenstrecke.
* **Spitzenwert** derselben Groesse. Das Feld ist ueber den Umfang nicht
  gleich, unter der Polmitte steht mehr als im Pollueckenbereich; ueber rund
  35 V entsteht ein Rundfeuer, und das zerstoert den Kommutator in Sekunden.
* **Umfangsgeschwindigkeit am Kommutator**, rund 40 m/s. Darueber hebt die
  Buerste ab.

Was hier NICHT gerechnet wird -- und ausdruecklich gesagt
----------------------------------------------------------

* **Wendepole und Kompensationswicklung.** Sie sind die uebliche Antwort auf
  die Ankerrueckwirkung; ohne sie gilt hier ein Abschlag (``ANKER_ABSCHLAG``),
  der als **Schaetzung** gekennzeichnet ist und nicht als Rechnung. Eine
  Maschine mit Wendepolen ist besser als das, was hier herauskommt.
* **Der Kommutierungsvorgang selbst** (Reaktanzspannung, Buerstenbreite,
  Ueberdeckungszahl). Er entscheidet, ob die Kommutierung gelingt; hier stehen
  nur die drei Grenzen oben, die ihn eingrenzen.
* **Keine Feldstufe.** Die 2-D-FDM ist reell, linear und magnetostatisch; ein
  kommutierter Anker mit stehender Durchflutung ist darin so wenig darstellbar
  wie ein Kaefig. ``ARTEN["gsm"].stufen`` sagt das.
"""

from __future__ import annotations

import math

# ── Wicklungsarten des Ankers ─────────────────────────────────────────────────
#
# Zweigpaare a: Schleifenwicklung a = p (2p Zweige), Wellenwicklung a = 1.
WICKLUNGSARTEN = ("schleife", "welle")
WICKLUNG_VORGABE = "schleife"

# Leiter je Ankernut, wenn nichts gesetzt ist. Zwei ist das Minimum (eine Spule
# mit Hin- und Rueckleiter).
LEITER_JE_NUT_VORGABE = 4

# ── Die drei Kommutierungsgrenzen ─────────────────────────────────────────────
#
# Alle drei sind GRENZEN und keine Auslegungswerte: ueberschritten werden sie
# gemeldet, nicht stillschweigend unterschritten.
U_LAMELLE_MITTEL_V = 18.0      # mittlere Spannung zwischen zwei Lamellen
U_LAMELLE_SPITZE_V = 35.0      # Spitzenwert -- darueber Rundfeuer
V_KOMMUTATOR_MPS = 40.0        # Umfangsgeschwindigkeit an der Buerste

# Verhaeltnis Spitzen- zu Mittelwert der Lamellenspannung. Das Luftspaltfeld ist
# ueber den Umfang nicht gleich: unter der Polmitte steht mehr als in der
# Pollücke. 2,0 ist der uebliche Ansatz fuer einen Schenkelpolstaender.
U_LAMELLE_FORMFAKTOR = 2.0

# Kommutatordurchmesser als Anteil des Ankerdurchmessers (ueblich 0,6-0,75).
D_KOMM_ANTEIL = 0.65

# Wie viele Lamellen eine Buerste ueberdeckt. Klassisch 2...3: weniger, und der
# Kommutierungsvorgang wird zu kurz; mehr, und zu viele Spulen liegen
# gleichzeitig kurzgeschlossen.
BUERSTE_LAMELLEN = 2.5

# Wieviel der Kommutatorlaenge die Buerste belegen darf, und wieviel Rand an
# jedem Ende frei bleibt [mm]. Der Rest ist Anlauf und Lamellenfuss.
BUERSTE_ZU_KOMM = 0.80
KOMM_RAND_MM = 3.0

# ── Ankerrueckwirkung ─────────────────────────────────────────────────────────
#
# Die Ankerdurchflutung steht quer zum Erregerfeld und verzerrt es; unter der
# einen Polkante saettigt das Eisen, unter der anderen bleibt Luft, und in der
# Summe FAELLT der Fluss. Wendepole und Kompensationswicklung heben das
# weitgehend auf -- ohne sie bleibt ein Abschlag.
#
# Der Ansatz ist eine SCHAETZUNG und als solche gekennzeichnet: der Fluss faellt
# um ``ANKER_ABSCHLAG`` mal dem Verhaeltnis Anker- zu Erregerdurchflutung,
# gedeckelt. Eine belastbare Zahl braeuchte eine Feldrechnung mit
# Saettigungskennlinie, und die gibt es fuer diese Art nicht.
ANKER_ABSCHLAG = 0.25
ANKER_ABSCHLAG_MAX = 0.35

# Ziel-Luftspaltfeld UNTER DEM POLSCHUH (nicht die Grundwelle -- eine
# Gleichstrommaschine hat keine). Dieselbe Spanne wie bei der EESM.
B_ZIEL_T = 0.85
B_ZIEL_SPANNE = (0.55, 1.05)

# Stromdichte der Ankerwicklung [A/mm^2]. Wie beim Stator einer Drehfeld-
# maschine: gewickeltes Kupfer in einer Nut.
J_ANKER_APMM2 = 5.0

ANKER_MAT = "cu_etp"


# ── Grundgroessen ─────────────────────────────────────────────────────────────

def k_norm(geom: dict) -> float:
    """1,0 — und der Modulkopf sagt, warum das kein vergessener Faktor ist."""
    return 1.0


def klemmenstrom(geom: dict) -> float:
    """Die Stromgrenze des Stellglieds — als KLEMMENstrom, nicht normiert.

    ``ema_analysis.umrichter`` gibt zwei Zahlen heraus: ``i_max_A`` an den
    Klemmen und ``i_max_1t`` auf die Hauskonvention „eine Windung je Nut"
    umgerechnet. Jede Drehfeldmaschine hier rechnet mit der zweiten, weil ihr
    ganzes elektrisches Modell so normiert ist.

    **Die Gleichstrommaschine nicht.** Ihre Maschinenkonstante ``p*z/(2*pi*a)``
    entsteht geometrisch exakt aus der wirklichen Leiterzahl; ihr Ankerstrom
    IST der Klemmenstrom. Mit ``i_max_1t`` gerechnet stuende hier eine Grenze,
    die zur Wicklung gehoert, die es nicht gibt.
    """
    import ema_analysis
    return float(ema_analysis.umrichter(geom)["i_max_A"])


def wicklungsart(geom: dict) -> str:
    """``"schleife"`` (Vorgabe) oder ``"welle"``."""
    a = str(geom.get("armatureWinding") or WICKLUNG_VORGABE).strip().lower()
    return a if a in WICKLUNGSARTEN else WICKLUNG_VORGABE


def ziel_feld(geom: dict) -> float:
    """Luftspaltfeld unter dem Polschuh [T] — gesetzt oder Vorgabe."""
    b = float(geom.get("bZielT") or B_ZIEL_T)
    return min(max(b, B_ZIEL_SPANNE[0]), B_ZIEL_SPANNE[1])


def staenderpole(geom: dict, axial_mm: float) -> dict:
    """Die Schenkelpole am STAENDER — dieselbe Formel wie beim EESM-Laeufer.

    Gerechnet in ``ema_eesm.polmasse``; hier stehen nur die anderen Radien: die
    Polflaeche liegt an der Statorbohrung und zeigt nach innen, der Platz fuer
    Pol und Joch ist ``r_aussen - r_bohrung``.
    """
    import ema_eesm
    import ema_radien
    r = ema_radien.radien(geom)
    p = max(int(geom["p"]), 1)
    r_gap = r["r_stator_gap_mm"]
    spanne = max(r["r_stator_aussen_mm"] - r_gap, 5.0)
    return ema_eesm.polmasse(2 * p, r_gap, spanne, ziel_feld(geom), axial_mm,
                             ema_eesm.polbedeckung(geom))


def ankerwicklung(geom: dict, axial_mm: float) -> dict:
    """Leiterzahl, Zweigpaare, Lamellenzahl und Ankerwiderstand.

    **``geom["slots"]`` sind hier die ANKERnuten.** Eine Gleichstrommaschine hat
    nur EIN genutetes Teil, und das ist der Laeufer; der Staender traegt
    Schenkelpole. Wer das verwechselt, rechnet eine Maschine mit zwei Nutungen.
    """
    from ema_pipeline import HAIRPIN_MATS
    import ema_wicklung

    p = max(int(geom["p"]), 1)
    L = float(axial_mm)
    n_nut = max(int(geom["slots"]), 4)
    u = max(2, int(geom.get("conductorsPerSlot") or LEITER_JE_NUT_VORGABE))
    u = u + (u % 2)                                    # Hin- und Rueckleiter
    z = n_nut * u                                      # Ankerleiter gesamt

    art = wicklungsart(geom)
    a = p if art == "schleife" else 1                  # ZWEIGPAARE
    zweige = 2 * a

    # Lamellen: eine je Spule. Eine Nut traegt u/2 Spulenseitenpaare.
    k_lam = max(int(n_nut * u / 2), 3)

    # ── Die Nuttiefe folgt dem STROM, nicht dem Platz ──────────────────────
    # Derselbe Fehler ist in diesem Werkzeug schon zweimal gemacht worden: der
    # Kaefigstab fuellte den Laeuferraum bis zum Deckel (1,14 A/mm^2 statt 4-8,
    # Widerstand um Faktor 5 daneben), und die Erregerwicklung das Polfenster
    # (0,7 A/mm^2, 15,7 kg Kupfer). Bemessen wird ueber die Stromdichte, das
    # Blech ist die Schranke.
    #
    # Der Auslegungsstrom braucht keinen Betriebspunkt: mehr als die
    # KLEMMENgrenze des Stellglieds kann der Anker nie fuehren, und er teilt
    # sich auf ``zweige`` Zweige auf.
    r_a = float(geom["rotorOD"]) / 2.0
    r_wel = max(float(geom["shaftD"]) / 2.0, 1.0)
    h_joch = max(0.12 * (r_a - r_wel), 3.0)
    nutraum = max(r_a - r_wel - h_joch - 2.0, 2.0)

    i_klemme = klemmenstrom(geom)
    i_zweig = i_klemme / max(zweige, 1)
    j_soll = min(max(float(geom.get("armatureCurrentDensity")
                           or J_ANKER_APMM2), 1.0), 20.0)
    a_soll = i_zweig / j_soll                              # mm^2 je Leiter
    b_nut = 2.0 * math.pi * r_a / max(n_nut, 1) * 0.45
    t_strom = (u * a_soll / max(b_nut - 2 * 0.8, 0.1) + (u + 1) * 0.8 + 2.0)
    t_deckel = 3.0 * b_nut                                 # Stromverdraengung
    tiefe = max(min(t_strom, nutraum, t_deckel), 2.0)
    bemessung = ("Blechraum" if tiefe >= nutraum - 1e-9 and t_strom > nutraum
                 else "Tiefe/Breite" if tiefe >= t_deckel - 1e-9 and t_strom > t_deckel
                 else "Stromdichte")

    # Nutgeometrie ueber die EINE Nutformel, mit den Zahlen des Ankers.
    schatten = {"slots": n_nut, "statorID": 2.0 * r_a,
                "statorOD": 2.0 * r_a + 10.0, "slotDepth": tiefe,
                "slotWidthRatio": 0.45, "conductorsPerSlot": u,
                "windingType": "rundraht"}
    ng = ema_wicklung.nutgeometrie(schatten)

    mat = HAIRPIN_MATS.get(geom.get("armatureMat") or ANKER_MAT,
                           HAIRPIN_MATS[ANKER_MAT])
    # Mittlere Leiterlaenge: einmal durch das Paket und einmal ueber den
    # Wickelkopf zurueck (Spulenweite ~ Polteilung).
    tau_pol = 2.0 * math.pi * r_a / (2 * p)
    l_leiter = 2.0 * (L + 1.2 * tau_pol) * 1e-3              # m je Leiter
    a_leiter = max(ng["A_leiter_m2"], 1e-12)
    # Ankerwiderstand: z Leiter, auf 2a Zweige aufgeteilt -> je Zweig z/(2a)
    # Leiter in Reihe, die 2a Zweige parallel.
    from ema_pipeline import rho_bei, leitertemperatur
    r_zweig = (rho_bei(mat, leitertemperatur(geom))
               * (z / zweige) * l_leiter / a_leiter)
    r_anker = r_zweig / zweige

    return {
        "n_nut": n_nut, "u_je_nut": u, "z_leiter": z,
        "wicklungsart": art, "a_zweigpaare": a, "zweige": zweige,
        "k_lamellen": k_lam,
        "nut_breite_mm": round(ng["nut_breite_mm"], 3),
        "nut_tiefe_mm": round(tiefe, 2),
        "nutraum_mm": round(nutraum, 2),
        "bemessung": bemessung,
        "I_klemme_A": round(i_klemme, 1),
        "I_zweig_A": round(i_zweig, 1),
        "J_anker_Apmm2": round(i_zweig / max(ng["A_leiter_m2"] * 1e6, 1e-9), 2),
        "h_joch_mm": round(h_joch, 2),
        "A_leiter_mm2": round(a_leiter * 1e6, 3),
        "passt": bool(ng["passt"]),
        "l_leiter_m": round(l_leiter, 4),
        "R_anker_Ohm": round(r_anker, 6),
        "material": mat["label"],
    }


def maschinenkonstante(geom: dict, axial_mm: float) -> float:
    """``k = p*z/(2*pi*a)`` [Nm/(Wb*A)] bzw. [Vs/(Wb*rad)] — dieselbe fuer beide."""
    aw = ankerwicklung(geom, axial_mm)
    p = max(int(geom["p"]), 1)
    return p * aw["z_leiter"] / (2.0 * math.pi * aw["a_zweigpaare"])


def polfluss(geom: dict, axial_mm: float) -> float:
    """Nutzfluss je Pol [Wb] = B unter dem Schuh mal Polschuhflaeche.

    Ausdruecklich NICHT die Grundwelle: eine Gleichstrommaschine hat kein
    Drehfeld, ihr Anker sieht den ganzen Fluss unter dem Polschuh.
    """
    pg = staenderpole(geom, axial_mm)
    return ziel_feld(geom) * (pg["b_pol_mm"] * 1e-3) * (float(axial_mm) * 1e-3)


# ── Die Kommutierung: das Tor dieser Bauart ───────────────────────────────────

def kommutierung(geom: dict, axial_mm: float, rpm: float,
                 i_a_A: float = 0.0) -> dict:
    """Lamellenspannung (Mittel und Spitze) und Umfangsgeschwindigkeit.

    Die drei Groessen, die die Baugroesse einer Gleichstrommaschine wirklich
    begrenzen — nicht das Eisen. Jede traegt ihr eigenes Urteil; ``ok`` ist das
    UND aller drei, und welche bindet, steht in ``bindend``.
    """
    aw = ankerwicklung(geom, axial_mm)
    k = maschinenkonstante(geom, axial_mm)
    phi = polfluss(geom, axial_mm)
    omega = 2.0 * math.pi * float(rpm) / 60.0
    e = k * phi * omega                                       # V je Zweig

    u_mittel = aw["zweige"] * e / max(aw["k_lamellen"], 1)
    u_spitze = U_LAMELLE_FORMFAKTOR * u_mittel

    d_komm = max(D_KOMM_ANTEIL * float(geom["rotorOD"]),
                 float(geom["shaftD"]) + 20.0)
    v_komm = math.pi * (d_komm * 1e-3) * float(rpm) / 60.0

    befunde = []
    if u_mittel > U_LAMELLE_MITTEL_V:
        befunde.append(f"mittlere Lamellenspannung {u_mittel:.1f} V > "
                       f"{U_LAMELLE_MITTEL_V:.0f} V")
    if u_spitze > U_LAMELLE_SPITZE_V:
        befunde.append(f"Spitzenwert {u_spitze:.1f} V > "
                       f"{U_LAMELLE_SPITZE_V:.0f} V (Rundfeuergefahr)")
    if v_komm > V_KOMMUTATOR_MPS:
        befunde.append(f"Umfangsgeschwindigkeit {v_komm:.1f} m/s > "
                       f"{V_KOMMUTATOR_MPS:.0f} m/s")

    # Welche Grenze am naechsten ist -- die Ausnutzung, nicht das bestandene Ja.
    ausl = {"lamelle_mittel": u_mittel / U_LAMELLE_MITTEL_V,
            "lamelle_spitze": u_spitze / U_LAMELLE_SPITZE_V,
            "umfang": v_komm / V_KOMMUTATOR_MPS}
    bindend = max(ausl, key=ausl.get)

    return {
        "ok": not befunde, "befunde": befunde, "bindend": bindend,
        "ausnutzung": {n: round(v, 3) for n, v in ausl.items()},
        "E_V": round(e, 2),
        "k_lamellen": aw["k_lamellen"],
        "U_lamelle_mittel_V": round(u_mittel, 2),
        "U_lamelle_spitze_V": round(u_spitze, 2),
        "U_lamelle_mittel_grenze_V": U_LAMELLE_MITTEL_V,
        "U_lamelle_spitze_grenze_V": U_LAMELLE_SPITZE_V,
        "d_kommutator_mm": round(d_komm, 1),
        "v_kommutator_mps": round(v_komm, 1),
        "v_grenze_mps": V_KOMMUTATOR_MPS,
        "hinweis": ("Der Kommutierungsvorgang selbst (Reaktanzspannung, "
                    "Buerstenbreite, Ueberdeckung) ist NICHT gerechnet — diese "
                    "drei Grenzen grenzen ihn nur ein."),
    }


def kommutator(geom: dict, axial_mm: float, rpm: float,
               i_a_A: float = 0.0) -> dict:
    """Der Kommutator als BAUTEIL — Lamellen, Buersten, Grenzen in einem.

    ``kommutierung`` beantwortet die Frage „haelt er das aus"; hier steht, was
    er IST. Beides getrennt zu lassen hiesse, dass die Bauart zwar begrenzt,
    aber nie beschrieben wird — und dann taucht der Kommutator in keiner
    Stueckliste, keinem Steckbrief und keinem Paarvergleich auf.

    Die Buerstenflaeche kommt aus derselben Stromdichte wie der Schleifring
    (``ema_schleifring.J_BUERSTE_APCM2``) und derselbe Kontaktabfall aus
    ``U_BUERSTE_V``: ein Kohlekontakt ist ein Kohlekontakt, ob er auf einem Ring
    oder auf Lamellen laeuft. Zwei Tabellen daneben waeren zwei verschieden
    grosse Buersten fuer denselben Strom.
    """
    import ema_schleifring

    aw = ankerwicklung(geom, axial_mm)
    kom = kommutierung(geom, axial_mm, rpm, i_a_A)
    i_a = float(i_a_A) if i_a_A else klemmenstrom(geom)
    k_lam = int(aw["k_lamellen"])
    d_komm = float(kom["d_kommutator_mm"])

    teilung = math.pi * d_komm / max(k_lam, 1)
    b_lamelle = max(teilung - LAMELLENSPALT_MM, 0.3)

    # Buerstenarme: bei der SCHLEIFENwicklung einer je Pol, bei der
    # WELLENwicklung genuegen zwei (jeder Zweig laeuft ueber alle Pole).
    poles = 2 * max(int(geom["p"]), 1)
    arme = poles if wicklungsart(geom) == "schleife" else 2
    a_ges_cm2 = max(i_a, 1e-6) / ema_schleifring.J_BUERSTE_APCM2
    a_arm_cm2 = a_ges_cm2 / max(arme, 1)
    # Die Buerste ist in Umfangsrichtung so breit wie ein paar Lamellen; die
    # Laenge folgt aus der Flaeche und ist durch die Kommutatorlaenge begrenzt.
    b_buerste = max(BUERSTE_LAMELLEN * teilung, 4.0)
    l_buerste = a_arm_cm2 * 100.0 / max(b_buerste, 1e-9)
    lam_je_buerste = b_buerste / max(teilung, 1e-9)

    # Die BAULAENGE folgt der Buerste, nicht umgekehrt.
    #
    # `L_KOMM_ANTEIL` ist eine ZEICHENregel (ein Anteil der Paketlaenge) und
    # taugt als Boden; als Bemessung ist sie falsch. Gemessen am frischen
    # Payload braucht ein Ankerstrom von 800 A 80 cm² Buerstenflaeche — auf
    # einem 24-mm-Kommutator ist das nicht unterzubringen, und die Maschine
    # waere daran gescheitert, obwohl nur eine Zeichenregel zu klein war. Ein
    # Kommutator wird also so lang, wie seine Buersten es verlangen, und wenn
    # das die Maschine spuerbar verlaengert, steht es als BEFUND da.
    l_boden = max(L_KOMM_ANTEIL * float(axial_mm), 15.0)
    l_komm = max(l_boden, l_buerste / BUERSTE_ZU_KOMM + 2.0 * KOMM_RAND_MM)
    lang = l_komm > float(axial_mm)
    passt = l_buerste <= BUERSTE_ZU_KOMM * (l_komm - 2.0 * KOMM_RAND_MM) + 1e-6

    return {
        "k_lamellen": k_lam,
        "wicklungsart": wicklungsart(geom),
        "d_kommutator_mm": round(d_komm, 2),
        "l_kommutator_mm": round(l_komm, 2),
        "lamellenteilung_mm": round(teilung, 3),
        "b_lamelle_mm": round(b_lamelle, 3),
        "lamellenspalt_mm": LAMELLENSPALT_MM,
        "I_anker_A": round(i_a, 1),
        "n_buerstenarme": arme,
        "A_buerste_ges_cm2": round(a_ges_cm2, 2),
        "A_buerste_arm_cm2": round(a_arm_cm2, 2),
        "b_buerste_mm": round(b_buerste, 2),
        "l_buerste_mm": round(l_buerste, 2),
        "lamellen_je_buerste": round(lam_je_buerste, 2),
        # Was der Kommutator lang sein MUESSTE, damit die Buerste darauf
        # sitzt. `l_kommutator` folgt heute einem Anteil der Paketlaenge
        # (`L_KOMM_ANTEIL`) -- das ist eine Zeichenregel, und bei grossen
        # Ankerstroemen ist sie die falsche: die Buerstenflaeche bemisst den
        # Kommutator, nicht umgekehrt. Ein Vorschlag ist besser als ein Nein.
        "l_kommutator_boden_mm": round(l_boden, 2),
        "lang": bool(lang),
        "U_buerste_V": ema_schleifring.U_BUERSTE_V,
        "P_buerste_W": round(2.0 * ema_schleifring.U_BUERSTE_V * i_a, 1),
        "passt": bool(passt),
        "grund": "" if passt else (
            f"Die Buerste passt nicht auf den Kommutator: "
            f"{a_arm_cm2:.2f} cm² je Arm bei {b_buerste:.1f} mm Breite "
            f"brauchen {l_buerste:.1f} mm Laenge auf {l_komm:.1f} mm "
            f"Baulaenge. Mehr Buerstenarme (heute {arme}) oder weniger "
            f"Ankerstrom"),
        "hinweis": ("" if not lang else
                    f"Der Kommutator ist mit {l_komm:.0f} mm laenger als das "
                    f"Blechpaket ({float(axial_mm):.0f} mm): bei "
                    f"{i_a:.0f} A Ankerstrom braucht die Buerstenflaeche "
                    f"({a_ges_cm2:.0f} cm² gesamt) diese Laenge. Das ist bei "
                    f"Gleichstrommaschinen ueblich, verlaengert die Maschine "
                    f"aber um genau diesen Betrag — weniger Ankerstrom (mehr "
                    f"Windungen) oder mehr Buerstenarme verkuerzen ihn."),
        # Die Grenzen bleiben, wo sie hingehoeren -- hier stehen sie nur mit,
        # damit man den Kommutator EINMAL fragen muss und nicht zweimal.
        "grenzen": kom,
        "ungeprueft": ("Buerstenverschiebung, Wendepole und "
                       "Kompensationswicklung sind NICHT modelliert; die "
                       "Ankerrueckwirkung wird als Abschlag gerechnet "
                       "(ankerrueckwirkung) und als solcher benannt."),
    }


def ankerrueckwirkung(geom: dict, axial_mm: float, i_a_A: float) -> dict:
    """Flussabschlag durch die Ankerdurchflutung — eine SCHAETZUNG.

    Die Ankerdurchflutung je Pol ist ``F_a = z*I_a/(4*p*a)`` (der Strom teilt
    sich auf 2a Zweige, und je Pol zaehlt die halbe Leiterzahl). Ins Verhaeltnis
    zur Erregerdurchflutung gesetzt ergibt das den Abschlag — mit einem
    Beiwert, der **nicht** gerechnet, sondern angesetzt ist.
    """
    import ema_eesm
    aw = ankerwicklung(geom, axial_mm)
    p = max(int(geom["p"]), 1)
    f_anker = aw["z_leiter"] * max(float(i_a_A), 0.0) / (4.0 * p * aw["a_zweigpaare"])

    pg = staenderpole(geom, axial_mm)
    g_eff = ema_eesm.K_CARTER * (__import__("ema_analysis").luftspalt_mm(geom) / 1000.0)
    formfaktor = (4.0 / math.pi) * math.sin(
        ema_eesm.polbedeckung(geom) * math.pi / 2.0)
    f_erreger = (ziel_feld(geom) * g_eff / (4.0e-7 * math.pi)) / formfaktor

    verh = f_anker / max(f_erreger, 1e-9)
    abschlag = min(ANKER_ABSCHLAG * verh, ANKER_ABSCHLAG_MAX)
    return {
        "F_anker_A": round(f_anker, 1),
        "F_erreger_A": round(f_erreger, 1),
        "verhaeltnis": round(verh, 3),
        "flussabschlag": round(abschlag, 4),
        "k_fluss": round(1.0 - abschlag, 4),
        "geschaetzt": True,
        "hinweis": ("Wendepole und Kompensationswicklung sind NICHT modelliert. "
                    "Eine Maschine mit ihnen ist besser als diese Zahl; der "
                    "Abschlag ist ein Ansatz, keine Feldrechnung."),
        "pol": pg,
    }


# ── Hauskonvention: Betriebspunkt, Verluste, Dauermoment, Massen ──────────────

def betriebspunkt(geom: dict, axial_mm: float, rpm: float, last_nm: float,
                  u_klemme_V: float = 0.0) -> dict:
    """Stationaerer Punkt: Ankerstrom, Klemmenspannung, Moment, Kommutierung."""
    import ema_analysis
    import ema_eesm
    import ema_schleifring

    aw = ankerwicklung(geom, axial_mm)
    k0 = maschinenkonstante(geom, axial_mm)
    phi0 = polfluss(geom, axial_mm)
    omega = 2.0 * math.pi * float(rpm) / 60.0
    t_soll = float(last_nm)

    # Erster Wurf ohne Ankerrueckwirkung, dann EINMAL nachgezogen: der Abschlag
    # haengt am Strom, der Strom am Abschlag. Ein zweiter Durchgang aendert die
    # dritte Stelle; eine Iteration bis zur Konvergenz waere hier Genauigkeit,
    # die das Modell gar nicht hat.
    i_a = t_soll / max(k0 * phi0, 1e-12)
    ar = ankerrueckwirkung(geom, axial_mm, i_a)
    phi = phi0 * ar["k_fluss"]
    i_a = t_soll / max(k0 * phi, 1e-12)

    i_lim = klemmenstrom(geom)
    am_limit = i_a > i_lim
    i_a = min(i_a, i_lim)
    t_ist = k0 * phi * i_a

    e = k0 * phi * omega
    u_b = 2.0 * ema_schleifring.U_BUERSTE_V
    u_klemme = e + i_a * aw["R_anker_Ohm"] + u_b
    if u_klemme_V and u_klemme_V > 0:
        u_klemme = float(u_klemme_V)

    komm = kommutierung(geom, axial_mm, rpm, i_a)
    er = ema_eesm.erregung(geom, axial_mm)

    return {
        "ok": True, "grund": "",
        "B_gap_T": round(ziel_feld(geom), 4),
        "Phi_pol_Wb": round(phi, 6),
        "Phi_pol_leer_Wb": round(phi0, 6),
        "k_Nm_per_WbA": round(k0, 4),
        # In der Hauskonvention heisst das Moment je Ampere ``Kt`` -- hier ist
        # es k*Phi und keine Naeherung.
        "Kt_Nm_per_A": round(k0 * phi, 5),
        "I_a_A": round(i_a, 1),
        "i_lim_A": round(i_lim, 1),
        "strom_limit": bool(am_limit),
        "I_s_A": round(i_a, 1),          # Vergleichsgroesse des Paarvergleichs
        "T_ist_Nm": round(t_ist, 1),
        "E_V": round(e, 1),
        "U_klemme_V": round(u_klemme, 1),
        "U_buerste_V": round(u_b, 2),
        "R_anker_Ohm": aw["R_anker_Ohm"],
        "n_1pmin": round(float(rpm), 1),
        "anker": aw,
        "kommutierung": komm,
        "ankerrueckwirkung": ar,
        "erregung": er,
        # Kein Schlupf, keine d/q-Achse -- die Kennzahlen dazu gibt es fuer
        # diese Art nicht (``ema_maschinenart.ohne_bedeutung``).
        "schlupf": None,
    }


def verluste(geom: dict, axial_mm: float, rpm: float, last_nm: float,
             bp: dict, rot_lam: dict, st_lam: dict, hp_mat: dict,
             kuehlung: str) -> dict:
    """Ankerkupfer, Buersten, Erregerkreis, Eisen — in der Hauskonvention.

    Zwei Dinge sind hier anders als bei jeder Drehfeldmaschine:

    * Der **Buerstenverlust** ist dem Strom PROPORTIONAL, nicht seinem Quadrat
      (der Spannungsabfall am Kohlekontakt ist naeherungsweise konstant). Bei
      kleiner Last ist er deshalb der groesste Einzelposten.
    * Das **Ankereisen** ummagnetisiert mit ``f = p*n/60`` — der Anker dreht
      im stehenden Feld. Das Staenderjoch dagegen fuehrt Gleichfluss und hat
      keine Ummagnetisierungsverluste; nur die Nutungsoberwellen wirken dort,
      und die sind hier nicht gerechnet.
    """
    import ema_thermal

    if not bp.get("ok"):
        return {"ok": False, "grund": bp.get("grund", "kein Betriebspunkt")}

    aw = bp["anker"]
    i_a = float(bp["I_a_A"])
    p_cu = i_a ** 2 * float(aw["R_anker_Ohm"])
    p_buerste = float(bp["U_buerste_V"]) * i_a
    p_erreger = float(bp["erregung"]["P_erreger_W"])
    p_ring = float(bp["erregung"]["P_schleifring_W"])

    # Ankereisen ueber dieselbe Verlustziffer wie ueberall hier.
    p = max(int(geom["p"]), 1)
    f_el = p * float(rpm) / 60.0
    r_a = float(geom["rotorOD"]) / 2000.0
    r_wel = float(geom["shaftD"]) / 2000.0
    v_anker = math.pi * (r_a ** 2 - r_wel ** 2) * (float(axial_mm) / 1000.0)
    m_anker = max(0.01, v_anker * float(rot_lam["density"]))
    p_fe = (float(rot_lam["specific_loss_Wkg"]) * (f_el / 50.0)
            * (float(bp["B_gap_T"]) ** 2) * m_anker)

    ges = p_cu + p_buerste + p_erreger + p_ring + p_fe
    aw2 = ankerwicklung(geom, axial_mm)
    return {
        "ok": True,
        # ── Hauskonvention: dieselben Namen wie bei den anderen vier ────────
        # ``P_Cu`` ist hier das ANKERkupfer, ``R_phase_mOhm`` der
        # Ankerwiderstand. Eine Gleichstrommaschine hat keinen Strang -- die
        # Groesse heisst so, weil der Paarvergleich sie so liest, und der
        # Docstring sagt, was sie ist. Ein eigener Name hier hiesse, dass der
        # Vergleich sie nicht faende.
        "P_total": round(ges, 1),
        "P_Cu": round(p_cu, 1),
        "J_Apmm2": float(aw2["J_anker_Apmm2"]),
        "R_phase_mOhm": round(float(aw2["R_anker_Ohm"]) * 1000.0, 3),
        "P_Fe_stator": 0.0,          # Gleichfluss im Staenderjoch
        "P_Fe_rotor": round(p_fe, 1),
        "P_Bearing": 0.0,
        # ── Was NUR diese Bauart hat ────────────────────────────────────────
        "P_anker_Cu_W": round(p_cu, 1),
        "P_buerste_W": round(p_buerste, 1),
        "P_erreger_W": round(p_erreger, 1),
        "P_schleifring_W": round(p_ring, 1),
        "P_Fe_anker_W": round(p_fe, 1),
        "P_gesamt_W": round(ges, 1),
        "hinweis": ("Der Buerstenverlust waechst LINEAR mit dem Strom (fester "
                    "Spannungsabfall am Kohlekontakt) und ist bei kleiner Last "
                    "der groesste Einzelposten. Das Staenderjoch fuehrt "
                    "Gleichfluss und hat keine Ummagnetisierungsverluste; die "
                    "Nutungsoberwellen dort sind NICHT gerechnet. "
                    "Lager- und Luftreibungsverluste ebenfalls nicht."),
    }


def dauermoment(geom: dict, axial_mm: float, kuehlung: str, bp: dict) -> dict:
    """Dauermoment: das kleinere aus Kuehlung, Strom und KOMMUTIERUNG."""
    import ema_thermal
    if not bp.get("ok"):
        return {"T_dauer_Nm": None, "begrenzt_durch": "kein Betriebspunkt"}
    t_kuehl = ema_thermal.rated_torque(geom, axial_mm, kuehlung)
    kt = max(float(bp["Kt_Nm_per_A"]), 1e-12)

    # Dieselben ZWEI Grenzen wie bei allen vier anderen, ueber dieselbe
    # Funktion: eine eigene Rueckgabeform hier waere die Stelle, an der der
    # Paarvergleich fuenf verschieden benannte Dauermomente vergleicht.
    # Der Ankerstrom ist ein KLEMMENstrom (s. ``klemmenstrom``), also wird die
    # Grenze ausdruecklich uebergeben statt sie aus der Hauskonvention zu holen.
    aus = ema_thermal.mit_umrichtergrenze(
        t_kuehl, lambda i: kt * i, geom=geom, i_grenze=klemmenstrom(geom))

    # Die Kommutierung begrenzt die DREHZAHL, nicht das Moment: E waechst mit n,
    # und mit E die Lamellenspannung. Sie gehoert darum NICHT in ``T_dauer`` --
    # sie stuende dort als Moment da und waere keins.
    komm = bp["kommutierung"]
    n_ist = max(float(bp["n_1pmin"]), 1e-9)
    n_komm = n_ist / max(max(komm["ausnutzung"].values()), 1e-9)

    aus.update({
        "T_dauer_Nm": round(float(aus["T_dauer_Nm"]), 1),
        "T_thermisch_Nm": round(float(aus["T_thermisch_Nm"]), 1),
        "T_umrichter_Nm": round(float(aus["T_umrichter_Nm"]), 1),
        "n_kommutierbar_1pmin": round(n_komm, 0),
        "kommutierung_ok": bool(komm["ok"]),
        "kommutierung_bindend": komm["bindend"],
        "hinweis": ("Die Kommutierung begrenzt die DREHZAHL, nicht das Moment "
                    "— sie steht darum als n_kommutierbar daneben und nicht in "
                    "T_dauer. Bei dieser Auslegung bindet dort "
                    f"'{komm['bindend']}'."),
    })
    return aus


def massen_und_kosten(payload: dict) -> dict:
    """Massen und Kosten — Anker- und Erregerkupfer statt Magneten.

    ``ema_screen.massen_und_kosten`` rechnet eine Drehfeldmaschine: Magnete im
    Laeufer, ein GENUTETER Staenderring (Faktor 0,78) und Strangkupfer darin
    (0,30 x 0,55 des Ringvolumens). **Keines davon hat die GSM.** Die Basiswerte
    nur zu uebernehmen und ``magnet_kg`` auf 0 zu setzen reicht deshalb nicht:
    ``gesamt_kg`` und ``kosten`` truegen die Magnete weiter mit. Gemessen kam die
    GSM dabei auf **Ziffer fuer Ziffer dieselbe Masse und dieselben Kosten wie
    die PSM** (40,53 kg / 197 EUR), waehrend ASM, SynRM und EESM darunter lagen —
    eine Zahl, die genau dann falsch ist, wenn man sie vergleichen will.

    Gerechnet wird daher aus den eigenen Teilen, jedes aus der Funktion, die es
    schon beschreibt:

        Welle        aus der Basis (dieselbe Welle)
        Ankereisen   Laeuferscheibe abzueglich der ANKERNUTEN (``ankerwicklung``)
        Ankerkupfer  Leiterzahl x Leiterlaenge x Leiterquerschnitt
        Staendereisen Joch + Schenkelpole (``staenderpole``) — KEIN Nutfaktor,
                     dieser Staender hat keine Nuten
        Erregerkupfer Polzahl x Kupferquerschnitt x mittlere Windungslaenge

    Nicht bilanziert und ausdruecklich gesagt: Kommutator (Lamellen, Ring,
    Isolation), Buersten und Buerstenhalter.
    """
    import math
    import ema_screen
    from ema_pipeline import HAIRPIN_MATS, LAMINATES

    geom = payload["geom"]
    axial = float(payload.get("axial_len") or geom.get("axialLen") or 80.0)
    basis = ema_screen.massen_und_kosten(payload)

    lam_rot = LAMINATES.get(payload.get("rotor_lam", "m270_35a"),
                            LAMINATES["m270_35a"])
    lam_st = LAMINATES.get(payload.get("stator_lam", "m270_35a"),
                           LAMINATES["m270_35a"])
    mat = HAIRPIN_MATS.get(geom.get("armatureMat") or ANKER_MAT,
                           HAIRPIN_MATS[ANKER_MAT])
    rho_cu = float(mat["density"])

    # ── Laeufer: Ankereisen abzueglich der Nuten, plus Ankerkupfer ────────────
    aw = ankerwicklung(geom, axial)
    m_anker_cu = (aw["z_leiter"] * aw["l_leiter_m"] * aw["A_leiter_mm2"] * 1e-6
                  * rho_cu)
    v_nuten_mm3 = (float(aw["n_nut"]) * float(aw["nut_breite_mm"])
                   * float(aw["nut_tiefe_mm"]) * axial)
    m_anker_fe = max(0.0, float(basis["rotoreisen_kg"])
                     - v_nuten_mm3 * 1e-9 * float(lam_rot["density"]))

    # ── Staender: Joch + Schenkelpole, ohne Nutabzug ──────────────────────────
    sp = staenderpole(geom, axial)
    r_so = float(geom["statorOD"]) / 2.0
    r_si = float(geom["statorID"]) / 2.0
    r_joch_i = max(r_so - float(sp["h_joch_mm"]), r_si)
    v_joch = math.pi * (r_so ** 2 - r_joch_i ** 2) * axial
    h_pol = max(r_joch_i - r_si, 0.0)
    v_pole = float(sp["poles"]) * float(sp["b_pol_mm"]) * h_pol * axial
    m_st_fe = (v_joch + v_pole) * 1e-9 * float(lam_st["density"])

    # ── Erregerkupfer an denselben Polen ──────────────────────────────────────
    er = __import__("ema_eesm").erregung(geom, axial)
    v_err = (float(sp["poles"]) * float(er["A_cu_mm2"])
             * float(sp["l_windung_mm"]))
    m_err_cu = v_err * 1e-9 * rho_cu

    m_welle = float(basis["welle_kg"])
    m_cu = m_anker_cu + m_err_cu
    gesamt = m_welle + m_anker_fe + m_st_fe + m_cu

    kosten = {
        "magnet_EUR": 0.0,
        "kupfer_EUR": round(m_cu * ema_screen.PREISE_EUR_KG["kupfer"], 0),
        "stahl_EUR": round((m_anker_fe + m_st_fe + m_welle)
                           * ema_screen.PREISE_EUR_KG["stahl"], 0),
    }
    kosten["gesamt_EUR"] = round(sum(kosten.values()), 0)

    aus = dict(basis)
    aus.update({
        "magnet_kg": 0.0,
        "rotoreisen_kg": round(m_anker_fe, 2),
        "statoreisen_kg": round(m_st_fe, 2),
        "kupfer_kg": round(m_cu, 2),
        "anker_cu_kg": round(m_anker_cu, 3),
        "erreger_cu_kg": round(m_err_cu, 3),
        "gesamt_kg": round(gesamt, 2),
        "kosten": kosten,
        "hinweis": basis["hinweis"] + (" Kein Magnet und kein Staenderstrang, "
                                       "dafuer zwei Kupferkreise: Anker und "
                                       "Erregung. Der Kommutator (Lamellen, "
                                       "Ring, Isolation) und die Buersten sind "
                                       "NICHT bilanziert."),
    })
    return aus


# ── Zeichenmasse ──────────────────────────────────────────────────────────────

# Anteil der Kommutatorlaenge an der Paketlaenge (ueblich 0,25-0,4).
L_KOMM_ANTEIL = 0.30

# Isolationsspalt zwischen zwei Lamellen [mm] (Glimmer, ueblich 0,5-1,0).
LAMELLENSPALT_MM = 0.8


def zeichenmasse(geom: dict, axial_mm: float) -> dict:
    """Alles, was der Zeichner braucht — reine Zahlen, keine Urteile.

    Die GSM ist die EESM von aussen nach innen: Schenkelpole am STAENDER
    (``ema_eesm.polmasse`` mit den Statorradien), gewickelter Anker am Laeufer,
    dazu der Kommutator auf der Welle. Urteile (``ok``, ``passt``) bleiben
    draussen — als JSON-``true`` waeren sie im erzeugten Python-Skript ein
    NameError, und sie gehoeren ohnehin ins Protokoll.
    """
    import ema_radien
    r = ema_radien.radien(geom)
    pg = staenderpole(geom, axial_mm)
    aw = ankerwicklung(geom, axial_mm)

    r_si = r["r_stator_gap_mm"]
    r_so = r["r_stator_aussen_mm"]
    r_a = float(geom["rotorOD"]) / 2.0
    r_wel = max(float(geom["shaftD"]) / 2.0, 1.0)

    # Joch aussen, Pole nach INNEN: Schuh an der Bohrung, Kern darueber.
    r_joch_innen = min(r_so - pg["h_joch_mm"], r_so - 2.0)
    h_pol = max(r_joch_innen - r_si, 2.0)
    h_schuh = max(3.0, min(0.22 * h_pol, 0.6 * h_pol))
    r_kern_innen = r_si + h_schuh
    b_kern = 0.72 * pg["b_pol_mm"] * (r_kern_innen / max(r_si, 1e-9))

    # Erregerspule: Dicke aus dem Kupferquerschnitt je Pol.
    import ema_eesm
    er = ema_eesm.erregung(geom, axial_mm)
    h_kern = max(r_joch_innen - r_kern_innen, 1.0)
    a_wick = float(er["A_cu_mm2"]) / max(ema_eesm._fuellfaktor(), 1e-6)
    d_spule = max(2.0, a_wick / (2.0 * h_kern))

    # Die Laenge kommt aus `kommutator` -- derselben Funktion, die sie auch
    # PRUEFT. Zwei Formeln waeren ein gezeichneter Kommutator, auf den die
    # gerechnete Buerste nicht passt.
    try:
        l_komm = float(kommutator(geom, axial_mm, 0.0)["l_kommutator_mm"])
    except Exception:                                        # noqa: BLE001
        l_komm = max(L_KOMM_ANTEIL * float(axial_mm), 15.0)
    d_komm = max(D_KOMM_ANTEIL * 2.0 * r_a, 2.0 * r_wel + 20.0)

    return {
        "poles": int(pg["poles"]),
        "r_stator_bohrung_mm": round(r_si, 3),
        "r_stator_aussen_mm": round(r_so, 3),
        "r_joch_innen_mm": round(r_joch_innen, 3),
        "r_kern_innen_mm": round(r_kern_innen, 3),
        "h_schuh_mm": round(h_schuh, 3),
        "b_schuh_mm": round(float(pg["b_pol_mm"]), 3),
        "b_kern_mm": round(b_kern, 3),
        "d_spule_mm": round(d_spule, 3),
        "r_anker_mm": round(r_a, 3),
        "n_ankernuten": int(aw["n_nut"]),
        "nut_breite_mm": round(float(aw["nut_breite_mm"]), 3),
        "nut_tiefe_mm": round(float(aw["nut_tiefe_mm"]), 3),
        "k_lamellen": int(aw["k_lamellen"]),
        "d_kommutator_mm": round(d_komm, 2),
        "l_kommutator_mm": round(l_komm, 2),
        "lamellenspalt_mm": LAMELLENSPALT_MM,
    }
