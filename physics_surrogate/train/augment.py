"""Exakte Symmetrien des FDM-Operators als Datenaugmentierung (16×).

Warum überhaupt: der Lauf vom 31.07.2026 hat bei Epoche 37 **überangepasst**, nicht
unterangepasst — `train rel_l2_A` 0,097 gegen `val` 0,157 (+61 %), auf `B_r` sogar
+83 %, und `val rel_l2_Br` stand ab Epoche 27 bei 0,21 still, während der Trainingswert
weiter fiel. Mehr Kapazität allein hätte das verschlimmert. Der billigste Hebel gegen
eine Generalisierungslücke ist mehr Vielfalt — und die gibt es hier **umsonst und exakt**,
weil der diskrete Operator selbst symmetrisch ist.

**Was ausgenutzt wird**

1. *Diedergruppe D4* (4 Drehungen × Spiegelung, 8 Elemente). `∇·(ν∇A) = −J` ist eine
   skalare Gleichung, der 5-Punkt-Stern mit harmonisch gemittelten Flächen-ν ist unter
   Achsentausch und Achsenspiegelung invariant, und das Gebiet ist ein Quadrat mit
   Dirichlet-Rand. Also löst `A(g·x)` das Problem `(µ(g·x), J(g·x))` **exakt**.
2. *Vorzeichen*: der Löser ist linear in der Quelle, `J → −J` ergibt `A → −A`. Das
   betrifft nur die vorzeichenbehafteten Kanäle (`J`, optional `A_free`), nicht die
   Material-One-Hots.

**Der Fallstrick, ohne den es still kaputtgeht.** D4 spiegelt ein `n×n`-Raster um
`(n−1)/2 = 255,5`, die Maschine ist aber auf `n/2 = 256,0` zentriert (gemessen:
Materialschwerpunkt 255,996/256,004, Ausdehnung 52…460) — und genau bei `n/2` tastet
`_sample_airgap` den Luftspaltring ab. Jede Achsenspiegelung verschöbe die Maschine
deshalb um **1 px** gegen den Ring, bei einem nur ~3,7 px breiten Luftspaltband ein
Viertel der Bandbreite: gemessen sprang `max|B_r|` dabei um bis zum **20-Fachen**, weil
der Ring in die Eisenkante geriet. Deshalb wird nach jeder Achsenspiegelung um 1 px
zurückgeschoben (`torch.roll`). Das Umlaufen am Rand ist folgenlos — dort ist das Feld
durch die 1,25-fache Luftpolsterung praktisch null.

**Wie exakt es wirklich ist** (11.08.2026, Löser gegen Löser in float64 — der Vergleich
gegen das float16-abgelegte Ziel hätte einen Fehler dieser Größe verdeckt): die reine
D4-Abbildung ist exakt (Maschinengenauigkeit, s. `mrot90` = Transposition, die keinen
Rückschub braucht). Der Rückschub selbst ist es *nicht ganz*: er lässt am Gebietsrand
eine Zeile umlaufen, in der die verschobene Lösung dann nicht mehr exakt auf der
Dirichlet-Null sitzt. Gemessen über 10 Geometrien ist der Rest im **relativen L2**
— der Größe, die der Verlust misst — höchstens **1,2e-3**: das 26-Fache unter dem
Genauigkeitsziel von 3e-2 und dreimal kleiner als das float16-Rauschen der Ablage
selbst. Das Nullen der Randzeile ändert daran nichts (geprüft), also unterbleibt es.

`max|B_r|` bleibt auf allen 8 Abbildungen exakt gleich (Verhältnis 1,000) — das ist der
Nachweis, dass der Rückschub den Ring wirklich trifft.
"""

import torch

# rot90^k dreht ebenfalls um (n−1)/2; diese Verschiebung stellt n/2 wieder her.
_ROLL_AFTER_ROT = {1: (1, 0), 2: (1, 1), 3: (0, 1)}

# Kanäle 0..2 sind One-Hot(Eisen, Magnet, Luft) und vorzeichenlos; ab Kanal 3 stehen die
# in der Quelle linearen Größen (J, optional A_free), die beim Vorzeichentausch mitgehen.
FIRST_SIGNED_CHANNEL = 3


def d4(t: torch.Tensor, k: int, mirror: bool) -> torch.Tensor:
    """Ein Element von D4 auf ``[..., H, W]``, zentrumstreu bezüglich ``n/2``."""
    if mirror:
        t = torch.roll(torch.flip(t, (-1,)), 1, -1)
    if k:
        t = torch.roll(torch.rot90(t, k, (-2, -1)), _ROLL_AFTER_ROT[k], (-2, -1))
    return t


MODES = ("d4_sign", "sign")


def augment(x: torch.Tensor, y: torch.Tensor,
            gen: torch.Generator | None = None,
            mode: str = "d4_sign") -> tuple[torch.Tensor, torch.Tensor]:
    """Zufälliges Gruppenelement auf ein Paar ``(x[B,C,H,W], y[B,1,H,W])``.

    Die geometrische Abbildung wird **je Batch** gezogen (ein `rot90` auf dem ganzen
    Batch statt acht auf Teilbatches), das Vorzeichen **je Sample** — das kostet nichts
    und verdoppelt die Vielfalt innerhalb des Batches.

    ``mode``:
      * ``"d4_sign"`` — die vollen 16 Symmetrien (D4 × Vorzeichen).
      * ``"sign"`` — **nur** der Vorzeichentausch, 2×. Gedacht als Antwort auf den
        Befund vom 11.08.2026 (`fdm_v2`): D4 schließt zwar die Generalisierungslücke
        vollständig, kostet dafür aber so viel Kapazität, dass das Netz unterangepasst
        bleibt. Der Grund ist plausibel asymmetrisch zwischen den beiden Anteilen —
        Faltungen sind **nicht** rotationsäquivariant, das Netz muss den Operator unter
        D4 also achtfach getrennt lernen, und der Nutzen davon ist gering, weil die
        Maschinen bei der Inferenz immer kanonisch liegen (zentriert, achsparallel).
        Der Vorzeichentausch dagegen liegt **in** der Testverteilung (der Rotorwinkel
        läuft über eine Polteilung, `J` wechselt dabei das Vorzeichen) und ist eine
        lineare Symmetrie, keine Orientierungsvervielfachung. Er ist damit der Anteil,
        von dem Nutzen ohne den Kapazitätspreis zu erwarten ist — **erwartet, nicht
        gemessen**; belegt ist bislang nur, dass die volle Form schadet.
    """
    if mode not in MODES:
        raise ValueError(f"augment(mode={mode!r}): erlaubt sind {MODES}")

    if mode == "d4_sign":
        r = torch.randint(8, (1,), generator=gen, device="cpu")
        k, mirror = int(r) % 4, int(r) >= 4
        x, y = d4(x, k, mirror), d4(y, k, mirror)

    sign = torch.randint(2, (x.shape[0], 1, 1, 1), generator=gen,
                         device="cpu").to(x.device, x.dtype) * 2 - 1
    x = x.clone()
    x[:, FIRST_SIGNED_CHANNEL:] *= sign
    return x, y * sign
