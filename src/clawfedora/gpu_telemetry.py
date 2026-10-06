"""B580 xe DRM client memory sampling, including peaks during inference."""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import TracebackType


@lru_cache(maxsize=1)
def b580_slot() -> str:
    output = subprocess.run(
        ["lspci", "-Dnn"], check=True, capture_output=True, text=True, timeout=10
    ).stdout
    matches = [line.split()[0] for line in output.splitlines() if "B580" in line and "Intel" in line]
    if len(matches) != 1:
        raise ValueError("B580 PCI unique non identifiée")
    return matches[0]


def xe_vram_mib(slot: str, proc: Path = Path("/proc")) -> float:
    clients: dict[str, float] = {}
    for file in proc.glob("[0-9]*/fdinfo/*"):
        try:
            fields = dict(line.split(":", 1) for line in file.read_text().splitlines() if ":" in line)
        except (OSError, ValueError):
            continue
        if fields.get("drm-driver", "").strip() != "xe" or fields.get("drm-pdev", "").strip() != slot:
            continue
        client = fields.get("drm-client-id", "").strip()
        if not client:
            continue
        values: list[float] = []
        for key, raw in fields.items():
            if not re.fullmatch(r"drm-memory-vram\d*", key):
                continue
            match = re.fullmatch(r"\s*(\d+)\s+(KiB|MiB|bytes|B)\s*", raw)
            if match:
                divisor = {"KiB": 1024, "MiB": 1, "bytes": 1024 * 1024, "B": 1024 * 1024}[match[2]]
                values.append(int(match[1]) / divisor)
        if values:
            clients[client] = sum(values)
    if not clients:
        raise ValueError(
            "VRAM B580 xe non observable: fdinfo manquant/inaccessible; aucune mesure substituée"
        )
    return sum(clients.values())


class PeakSampler:
    def __init__(self, sample: Callable[[], float], interval: float = 0.1) -> None:
        self.sample = sample
        self.interval = interval
        self.peak: float | None = None
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _take(self) -> None:
        try:
            value = self.sample()
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        self.peak = value if self.peak is None else max(self.peak, value)
        self.samples += 1

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._take()

    def __enter__(self) -> PeakSampler:
        self._take()
        self._thread.start()
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._take()

    def value(self) -> float:
        if self.peak is None:
            raise ValueError("aucun échantillon VRAM B580 pendant l'inférence")
        return self.peak
