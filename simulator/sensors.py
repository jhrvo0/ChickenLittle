"""Simulador físico 1D de sensores (HC-SR04, TCRT5000, Potenciômetro) e replay de datasets."""

from __future__ import annotations

import csv
import json
import random
from collections import deque
from pathlib import Path
from typing import Protocol

from terminal.communication.protocol import GestureType, SensorFramePayload


class SensorSource(Protocol):
    """Fonte abstrata de quadros de sensores (simulador sintético ou replay de arquivo)."""

    def next_frame(self) -> tuple[int, SensorFramePayload]: ...


class SensorSimulator:
    """Gera séries temporais 1D realistas respeitando limites do HC-SR04 (~60ms/amostra)."""

    MIN_CM = 2.0
    MAX_CM = 400.0

    def __init__(
        self,
        seed: int | None = 42,
        sample_period_ms: int = 60,
        noise_std_cm: float = 0.45,
        dropout_prob: float = 0.02,
        idle_distance_cm: float = 75.0,
    ) -> None:
        self._rng = random.Random(seed)
        self.sample_period_ms = max(20, sample_period_ms)
        self.noise_std_cm = max(0.0, noise_std_cm)
        self.dropout_prob = max(0.0, min(1.0, dropout_prob))
        self.idle_distance_cm = idle_distance_cm
        self._ts_ms = 0
        self._pot_norm = 0.5
        self._trajectory: deque[float | None] = deque()

    def set_potentiometer(self, value: float) -> None:
        self._pot_norm = max(0.0, min(1.0, float(value)))

    def adjust_potentiometer(self, delta: float) -> float:
        self.set_potentiometer(self._pot_norm + delta)
        return self._pot_norm

    def queue_gesture_profile(self, gesture: GestureType) -> None:
        """Enfileira uma trajetória 1D sintética correspondente a um movimento de mão."""
        if gesture == GestureType.APPROACH:
            # Aproximação progressiva de ~44 cm até ~12 cm em 10 amostras (~600ms)
            steps = [44.0 - i * 3.5 for i in range(10)]
        elif gesture == GestureType.RETREAT:
            # Afastamento progressivo de ~12 cm até ~44 cm em 10 amostras
            steps = [12.0 + i * 3.5 for i in range(10)]
        elif gesture == GestureType.HOLD:
            # Mão estacionária próxima (~18 cm) por 10 amostras
            steps = [18.0 for _ in range(10)]
        elif gesture == GestureType.IMPULSE:
            steps = [40.0, 26.0, 11.0, 10.5, 25.0, 42.0]
        elif gesture == GestureType.DOUBLE:
            steps = [38.0, 14.0, 14.5, 30.0, 31.0, 13.5, 14.0, 38.0]
        else:
            # NEUTRAL: fora da zona ativa
            steps = [self.idle_distance_cm for _ in range(8)]

        self._trajectory.extend(steps)

    def next_frame(self) -> tuple[int, SensorFramePayload]:
        self._ts_ms += self.sample_period_ms
        base_dist = self._trajectory.popleft() if self._trajectory else self.idle_distance_cm

        # Simula falha ocasional de eco (timeout ultrassônico) apenas fora de trajetória ou conforme prob
        if base_dist is None or self._rng.random() < self.dropout_prob:
            frame = SensorFramePayload(
                distance_cm=None,
                ir_detected=False,
                pot_norm=self._pot_norm,
                valid_ultrasonic=False,
            )
            return self._ts_ms, frame

        noisy = base_dist + self._rng.gauss(0.0, self.noise_std_cm)
        clamped = max(self.MIN_CM, min(self.MAX_CM, noisy))
        # TCRT5000 reflexivo dispara apenas em curta distância (~ <= 12.5 cm)
        ir_hit = clamped <= 12.5

        frame = SensorFramePayload(
            distance_cm=round(clamped, 2),
            ir_detected=ir_hit,
            pot_norm=self._pot_norm,
            valid_ultrasonic=True,
        )
        return self._ts_ms, frame


class DatasetReplaySource:
    """Reproduz leituras reais ou sintéticas gravadas em CSV ou JSON Lines."""

    def __init__(self, path: str | Path, loop: bool = False) -> None:
        self.path = Path(path)
        self.loop = loop
        self._records: list[tuple[int, SensorFramePayload]] = self._load_records(self.path)
        if not self._records:
            raise ValueError(f"Dataset vazio em '{self.path}'")
        self._idx = 0

    @property
    def total_frames(self) -> int:
        return len(self._records)

    @property
    def exhausted(self) -> bool:
        return not self.loop and self._idx >= len(self._records)

    def next_frame(self) -> tuple[int, SensorFramePayload]:
        if self._idx >= len(self._records):
            if self.loop:
                self._idx = 0
            else:
                return self._records[-1]
        record = self._records[self._idx]
        self._idx += 1
        return record

    @staticmethod
    def _load_records(path: Path) -> list[tuple[int, SensorFramePayload]]:
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de dataset não encontrado: '{path}'")

        suffix = path.suffix.lower()
        records: list[tuple[int, SensorFramePayload]] = []

        if suffix == ".jsonl":
            for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                stripped = line.strip()
                if not stripped:
                    continue
                obj = json.loads(stripped)
                ts_ms = int(obj.get("ts_ms", (idx + 1) * 60))
                data = obj.get("data", obj)
                records.append((ts_ms, SensorFramePayload.from_dict(data)))
            return records

        if suffix == ".csv":
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    ts_ms = int(row.get("ts_ms") or ((idx + 1) * 60))
                    raw_dist = row.get("distance_cm", "")
                    dist = None if raw_dist in ("", "None", "null", "NaN") else float(raw_dist)
                    ir_val = str(row.get("ir_detected", "false")).strip().lower() in (
                        "1",
                        "true",
                        "yes",
                    )
                    pot_val = float(row.get("pot_norm", "0.5"))
                    valid_str = row.get("valid_ultrasonic")
                    valid = (
                        dist is not None
                        if valid_str is None or valid_str == ""
                        else str(valid_str).strip().lower() in ("1", "true", "yes")
                    )
                    records.append(
                        (
                            ts_ms,
                            SensorFramePayload(
                                distance_cm=dist,
                                ir_detected=ir_val,
                                pot_norm=pot_val,
                                valid_ultrasonic=valid,
                            ),
                        )
                    )
            return records

        raise ValueError(f"Formato de dataset não suportado '{suffix}' (use .jsonl ou .csv)")
