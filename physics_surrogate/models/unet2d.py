"""2D-UNet für Stufe 1 (Material+Quelle → Vektorpotential A).

**Warum ein eigenes Netz und nicht `physicsnemo.models.unet.UNet`:** das ist ein reines
3D-Netz (`MaxPool3d`/`AvgPool3d`, `Expected 5D input tensor (B,C,D,H,W)` — verifiziert
mit physicsnemo 2.1.1). Ein 2D-Feld als D=1-Volumen durchzuschieben scheitert am Pooling
(D halbiert sich nicht), und ein Umbau des Fremdcodes wäre teurer als diese ~120 Zeilen.
Stufe 2 (3D-Elmer) benutzt dagegen das Original.

Es leitet trotzdem von `physicsnemo.Module` ab: das legt die Konstruktorargumente mit in
den Checkpoint, sodass `Module.from_checkpoint(pfad)` das Netz **ohne** Kenntnis der
Architektur wiederherstellt. Genau das braucht der Dienst in AP1.4 — sonst müsste dort
eine zweite Stelle die Hyperparameter kennen und könnte still von der trainierten
abweichen.

Aufbau: klassisches UNet, `model_depth` Ebenen à `num_conv_blocks` Faltungen, MaxPool
zwischen den Ebenen, transponierte Faltung im Aufstieg, Skip-Verbindungen per Konkat,
1×1-Faltung als Kopf. GroupNorm statt BatchNorm, weil bei 512² nur Batchgrößen von 2–8
in 24 GB passen — BatchNorm-Statistiken wären dort verrauscht.
"""

from dataclasses import dataclass

import torch
import torch.nn as nn

from physicsnemo.core import ModelMetaData, Module


@dataclass
class MetaData(ModelMetaData):
    jit: bool = False
    cuda_graphs: bool = False
    amp: bool = True
    auto_grad: bool = True


def _norm(kind: str | None, ch: int) -> nn.Module:
    if kind is None or kind == "none":
        return nn.Identity()
    if kind == "groupnorm":
        return nn.GroupNorm(num_groups=min(8, ch), num_channels=ch)
    if kind == "batchnorm":
        return nn.BatchNorm2d(ch)
    raise ValueError(f"unbekannte Normalisierung: {kind}")


class _ConvBlock(nn.Sequential):
    def __init__(self, c_in: int, c_out: int, norm: str | None):
        super().__init__(
            nn.Conv2d(c_in, c_out, 3, padding=1, bias=norm in (None, "none")),
            _norm(norm, c_out),
            nn.SiLU(inplace=True),
        )


class UNet2D(Module):
    """``x[B,in_channels,H,W] → y[B,out_channels,H,W]`` (H, W durch 2^(depth-1) teilbar).

    Parameter
    ---------
    in_channels, out_channels
        4 bzw. 1 für Stufe 1 (iron/magnet/air/J → A).
    model_depth
        Zahl der Auflösungsebenen inklusive Flaschenhals.
    base_channels
        Kanäle auf der feinsten Ebene; verdoppeln sich je Ebene bis `max_channels`.
    max_channels
        Deckel gegen den VRAM — bei 512² und Tiefe 5 wären 1024 Kanäle im Flaschenhals
        weder nötig noch bezahlbar.
    """

    def __init__(self, in_channels: int = 4, out_channels: int = 1,
                 model_depth: int = 5, base_channels: int = 32,
                 max_channels: int = 256, num_conv_blocks: int = 2,
                 normalization: str | None = "groupnorm", pooling: str = "avg"):
        super().__init__(meta=MetaData())
        if model_depth < 2:
            raise ValueError("model_depth muss ≥ 2 sein")
        self.model_depth = model_depth
        chans = [min(base_channels * 2 ** i, max_channels) for i in range(model_depth)]

        self.down = nn.ModuleList()
        c_prev = in_channels
        for c in chans:
            blocks = [_ConvBlock(c_prev, c, normalization)]
            blocks += [_ConvBlock(c, c, normalization) for _ in range(num_conv_blocks - 1)]
            self.down.append(nn.Sequential(*blocks))
            c_prev = c
        # Mittelwert- statt Maximum-Pooling: der Quellkanal ist VORZEICHENBEHAFTET (die
        # Magnetquelle ist eine ±-Dipolschicht auf den Magnetflanken), MaxPool wirft den
        # negativen Anteil weg, und Mittelwert-Pooling ist zugleich der
        # Restriktionsoperator der Mehrgitterverfahren für dieselbe Gleichung.
        # Gemessen macht es allerdings keinen Unterschied (s. conf/fdm.yaml) — die Wahl
        # steht auf dem Argument, nicht auf einem Messvorteil.
        self.pool = {"avg": nn.AvgPool2d(2), "max": nn.MaxPool2d(2)}[pooling]

        self.up = nn.ModuleList()
        self.up_conv = nn.ModuleList()
        for i in range(model_depth - 1, 0, -1):
            self.up.append(nn.ConvTranspose2d(chans[i], chans[i - 1], 2, stride=2))
            blocks = [_ConvBlock(2 * chans[i - 1], chans[i - 1], normalization)]
            blocks += [_ConvBlock(chans[i - 1], chans[i - 1], normalization)
                       for _ in range(num_conv_blocks - 1)]
            self.up_conv.append(nn.Sequential(*blocks))

        self.head = nn.Conv2d(chans[0], out_channels, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        step = 2 ** (self.model_depth - 1)
        if x.shape[-1] % step or x.shape[-2] % step:
            raise ValueError(
                f"Eingang {tuple(x.shape[-2:])} ist nicht durch {step} teilbar "
                f"(model_depth={self.model_depth})")
        skips = []
        for i, block in enumerate(self.down):
            x = block(x)
            if i < self.model_depth - 1:
                skips.append(x)
                x = self.pool(x)
        for up, conv, skip in zip(self.up, self.up_conv, reversed(skips)):
            x = conv(torch.cat([up(x), skip], dim=1))
        return self.head(x)
