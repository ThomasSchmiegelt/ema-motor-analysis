"""Differenzierbare Spiegelung der Luftspaltkurve ``B_r(θ)`` aus `_sample_airgap`.

**Warum das im Verlust gebraucht wird:** ein reiner L2-Verlust auf `A` optimiert das
Feldbild. Das Moment kommt aber aus der Luftspaltkurve, und die ist eine *Ableitung*
von `A` auf einem Kreis mit ~140 px Radius — sie kann prozentual weit daneben liegen,
während `A` global glatt und scheinbar gut aussieht. Der zweite Term zwingt das Netz
genau auf die Größe, die nachher zählt.

Gespiegelt wird exakt der Pfad aus `ema_analysis._sample_airgap:583-591` **und
`_circ_smooth:534`**:

    r_ev = r_si_px − 1
    A_ev = bilinear(A, ctr + r_ev·cos θ, ctr + r_ev·sin θ)      θ: 720 Punkte
    B_r  = np.gradient(A_ev, 2π/720) / r_ev
    B_r  = zirkulärer Boxcar über ⌊720·1,5/360⌋ = 3 Punkte

`np.gradient` wird **inklusive seiner einseitigen Ränder** nachgebaut, obwohl das Signal
periodisch ist: es geht nicht um die physikalisch schönere Ableitung, sondern darum,
dass Trainingsverlust und Abnahmemetrik derselbe Operator sind. `tests/test_airgap_torch.py`
vergleicht gegen die Numpy-Fassung.

`B_t` ist **nicht** gespiegelt — es entsteht aus einer Harmonischen-Anpassung auf zwei
Kreisen (rfft + 2×2-System je Ordnung, `:602-620`) und ist kein Abnahme-Gate. Es wird in
`evaluate.py` mit der *echten* Numpy-Funktion gemessen.
"""

import math

import torch
import torch.nn.functional as F

N_THETA = 720                 # ema_analysis._sample_airgap:580
SMOOTH_DEG = 1.5              # ema_analysis.AIRGAP_SMOOTH_DEG


def smoothing_window(n_theta: int = N_THETA, smooth_deg: float = SMOOTH_DEG) -> int:
    """Fensterbreite wie `_sample_airgap:621`."""
    return max(1, int(round(n_theta * smooth_deg / 360.0)))


def circ_smooth(sig: torch.Tensor, win: int) -> torch.Tensor:
    """Zirkulärer Boxcar über die letzte Achse — Spiegelung von `_circ_smooth`.

    Die Numpy-Fassung padded zyklisch, faltet mit ``mode="same"`` und schneidet zurück;
    für ungerades `win` ist das ein zentrierter zyklischer Mittelwert. Gerade Breiten
    wären in der Numpy-Fassung um ein halbes Pixel versetzt — dieser Fall tritt bei den
    festen Konstanten nicht auf und wird hier abgelehnt statt still anders gerechnet.
    """
    if win <= 1:
        return sig
    if win % 2 == 0:
        raise ValueError(f"win={win} ist gerade — nicht zentriert spiegelbar")
    pad = win // 2
    x = F.pad(sig.unsqueeze(-2), (pad, pad), mode="circular").squeeze(-2)
    return F.avg_pool1d(x.reshape(-1, 1, x.shape[-1]), win, stride=1).reshape(sig.shape)


def _gradient(f: torch.Tensor, h: float) -> torch.Tensor:
    """`np.gradient(f, h)` über die letzte Achse: innen zentral, an den Rändern einseitig."""
    out = torch.empty_like(f)
    out[..., 1:-1] = (f[..., 2:] - f[..., :-2]) / (2 * h)
    out[..., 0] = (f[..., 1] - f[..., 0]) / h
    out[..., -1] = (f[..., -1] - f[..., -2]) / h
    return out


class AirgapBr(torch.nn.Module):
    """``A[B,1,N,N]`` + Ringradius ``r_ev[B]`` → ``B_r[B,720]`` (differenzierbar).

    Die Einheit ist dieselbe wie in `_sample_airgap`: A pro Pixel, also folgt aus einem
    normierten `A` ein normiertes `B_r`. Für den Verlust ist das genau richtig — Vorhersage
    und Ziel durchlaufen denselben Operator, der Normierungsfaktor α kürzt sich heraus.
    """

    def __init__(self, n: int, n_theta: int = N_THETA, smooth_deg: float = SMOOTH_DEG):
        super().__init__()
        self.n = n
        self.n_theta = n_theta
        self.win = smoothing_window(n_theta, smooth_deg)
        self.dtheta = 2 * math.pi / n_theta
        # Doppelte Genauigkeit im Puffer: bei float32-cos/sin wäre der Ringpunkt schon
        # um ~1e-6 px versetzt, und der Test gegen `_sample_airgap` würde genau das
        # sehen statt einen echten Spiegelungsfehler.
        theta = torch.arange(n_theta, dtype=torch.float64) * self.dtheta
        self.register_buffer("cos_t", torch.cos(theta), persistent=False)
        self.register_buffer("sin_t", torch.sin(theta), persistent=False)

    def forward(self, a: torch.Tensor, r_ev: torch.Tensor) -> torch.Tensor:
        if a.dim() != 4 or a.shape[1] != 1:
            raise ValueError(f"A muss [B,1,N,N] sein, ist {tuple(a.shape)}")
        n = a.shape[-1]
        ctr = n / 2.0                                   # _rasterise:110
        r = r_ev.to(a.dtype).view(-1, 1)
        x = ctr + r * self.cos_t.to(a.dtype)
        y = ctr + r * self.sin_t.to(a.dtype)
        # grid_sample erwartet [-1,1] mit align_corners=True → dieselbe bilineare
        # Gewichtung wie `_interp2` (das die Ecken ebenfalls auf [0, N-2] klemmt).
        gx = 2.0 * x / (n - 1) - 1.0
        gy = 2.0 * y / (n - 1) - 1.0
        grid = torch.stack([gx, gy], dim=-1).unsqueeze(1)          # [B,1,720,2]
        a_ev = F.grid_sample(a, grid, mode="bilinear",
                             padding_mode="border", align_corners=True)
        a_ev = a_ev[:, 0, 0, :]                                    # [B,720]
        br = _gradient(a_ev, self.dtheta) / r
        return circ_smooth(br, self.win)
