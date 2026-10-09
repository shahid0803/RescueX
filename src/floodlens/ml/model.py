from __future__ import annotations

try:
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - exercised only without optional ML extra
    torch = None
    nn = None


def _require_torch() -> None:
    if torch is None:
        raise RuntimeError("install the optional ML dependencies with pip install -e .[ml]")


class FloodUNet(nn.Module if nn else object):
    """Small explainable U-Net baseline: encoder, bottleneck, decoder, skip paths."""

    def __init__(self, in_channels: int = 2, out_channels: int = 1, base_channels: int = 16):
        _require_torch()
        super().__init__()
        self.enc1 = self._block(in_channels, base_channels)
        self.enc2 = self._block(base_channels, base_channels * 2)
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = self._block(base_channels * 2, base_channels * 4)
        self.up = nn.ConvTranspose2d(base_channels * 4, base_channels * 2, 2, stride=2)
        self.dec = self._block(base_channels * 4, base_channels * 2)
        self.head = nn.Conv2d(base_channels * 2, out_channels, 1)

    @staticmethod
    def _block(in_channels: int, out_channels: int):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1),
            nn.ReLU(inplace=True),
        )

    def forward(self, inputs):
        target_size = inputs.shape[-2:]
        skip = self.enc1(inputs)
        encoded = self.enc2(self.pool(skip))
        bottleneck = self.bottleneck(self.pool(encoded))
        decoded = self.up(bottleneck)
        if decoded.shape[-2:] != encoded.shape[-2:]:
            decoded = torch.nn.functional.interpolate(decoded, size=encoded.shape[-2:], mode="bilinear", align_corners=False)
        output = self.head(self.dec(torch.cat((decoded, encoded), dim=1)))
        return torch.nn.functional.interpolate(output, size=target_size, mode="bilinear", align_corners=False)
