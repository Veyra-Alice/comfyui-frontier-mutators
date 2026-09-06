"""Random, reproducible parameter mutation nodes for ComfyUI.

Unlocked nodes sample on every queue. Locking a node preserves the most recent
sample when the node instance is still live; after a restart, it recreates a
stable sample from ``random_seed``. The effective seed is always returned so an
unlocked result can be reproduced later.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
import threading
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any


U64_MAX = (1 << 64) - 1
I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
DISTRIBUTIONS = ("gaussian", "uniform", "fixed")


def _stable_fingerprint(values: dict[str, Any]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bounded_gaussian(
    rng: random.Random,
    centre: float,
    sigma: float,
    clip_sigma: float,
) -> float:
    if sigma == 0:
        return centre
    sigma = abs(sigma)
    if clip_sigma <= 0:
        return rng.gauss(centre, sigma)

    radius = sigma * clip_sigma
    lower = centre - radius
    upper = centre + radius
    for _ in range(256):
        candidate = rng.gauss(centre, sigma)
        if lower <= candidate <= upper:
            return candidate

    # Rejection failure is fantastically unlikely, but returning a bounded
    # value is better than making an image queue fail mysteriously.
    return min(max(rng.gauss(centre, sigma), lower), upper)


def _raw_sample(
    rng: random.Random,
    distribution: str,
    centre: float,
    spread: float,
    clip_sigma: float,
) -> float:
    if distribution == "fixed":
        return centre
    if distribution == "uniform":
        radius = abs(spread)
        return rng.uniform(centre - radius, centre + radius)
    if distribution == "gaussian":
        return _bounded_gaussian(rng, centre, spread, clip_sigma)
    raise ValueError(f"Unsupported distribution: {distribution}")


def _quantise(value: float, quantum: float) -> float:
    if quantum <= 0:
        return value
    value_decimal = Decimal(str(value))
    quantum_decimal = Decimal(str(quantum))
    units = (value_decimal / quantum_decimal).quantize(
        Decimal("1"), rounding=ROUND_HALF_EVEN
    )
    return float(units * quantum_decimal)


class _FrontierMutatorBase:
    CATEGORY = "Veyra/Frontier"
    FUNCTION = "mutate"
    RETURN_NAMES = ("value", "effective_seed")
    SEARCH_ALIASES = ["random parameter", "parameter noise", "gaussian random", "mutation"]

    def __init__(self) -> None:
        self._state_lock = threading.Lock()
        self._last_signature: tuple[Any, ...] | None = None
        self._last_value: int | float | None = None
        self._last_effective_seed: int | None = None

    @classmethod
    def IS_CHANGED(cls, lock_current: bool, **kwargs: Any) -> float | str:
        if not lock_current:
            return float("NaN")
        return _stable_fingerprint({"lock_current": lock_current, **kwargs})

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        distribution: str,
        spread: float,
        clip_sigma: float,
        hard_min: int | float,
        hard_max: int | float,
        quantum: int | float,
    ) -> bool | str:
        if distribution not in DISTRIBUTIONS:
            return f"distribution must be one of {DISTRIBUTIONS}"
        if not math.isfinite(float(spread)) or spread < 0:
            return "spread must be a finite, non-negative number"
        if not math.isfinite(float(clip_sigma)) or clip_sigma < 0:
            return "clip_sigma must be a finite, non-negative number"
        if hard_min > hard_max:
            return "hard_min must not exceed hard_max"
        if not math.isfinite(float(quantum)) or quantum < 0:
            return "quantum must be a finite, non-negative number"
        return True

    def _signature(
        self,
        distribution: str,
        centre: int | float,
        spread: float,
        clip_sigma: float,
        hard_min: int | float,
        hard_max: int | float,
        quantum: int | float,
        random_seed: int,
    ) -> tuple[Any, ...]:
        return (
            distribution,
            centre,
            spread,
            clip_sigma,
            hard_min,
            hard_max,
            quantum,
            random_seed,
        )

    def _draw(
        self,
        rng: random.Random,
        distribution: str,
        centre: int | float,
        spread: float,
        clip_sigma: float,
    ) -> int | float:
        return _raw_sample(rng, distribution, float(centre), spread, clip_sigma)

    def _apply_quantum(self, value: int | float, quantum: int | float) -> int | float:
        return _quantise(float(value), float(quantum))

    def _convert(self, value: int | float) -> int | float:
        raise NotImplementedError

    def mutate(
        self,
        distribution: str,
        centre: int | float,
        spread: float,
        clip_sigma: float,
        hard_min: int | float,
        hard_max: int | float,
        quantum: int | float,
        random_seed: int,
        lock_current: bool,
    ) -> dict[str, Any]:
        if hard_min > hard_max:
            raise ValueError("hard_min must not exceed hard_max")
        if spread < 0 or clip_sigma < 0 or quantum < 0:
            raise ValueError("spread, clip_sigma, and quantum must be non-negative")

        signature = self._signature(
            distribution,
            centre,
            spread,
            clip_sigma,
            hard_min,
            hard_max,
            quantum,
            random_seed,
        )

        with self._state_lock:
            if lock_current and self._last_signature == signature and self._last_value is not None:
                value = self._last_value
                effective_seed = self._last_effective_seed
            else:
                effective_seed = int(random_seed) if lock_current else secrets.randbits(64)
                rng = random.Random(effective_seed)
                raw = self._draw(rng, distribution, centre, spread, clip_sigma)
                raw = self._apply_quantum(raw, quantum)
                raw = min(max(raw, hard_min), hard_max)
                value = self._convert(raw)
                effective_seed = int(effective_seed)
                self._last_signature = signature
                self._last_value = value
                self._last_effective_seed = effective_seed

        return {
            "ui": {
                "sample": [str(value)],
                "effective_seed": [str(effective_seed)],
                "locked": ["locked" if lock_current else "rerolls each queue"],
            },
            "result": (value, effective_seed),
        }


class FrontierFloatMutator(_FrontierMutatorBase):
    """Mutate continuous controls such as CFG, denoise, or control strength."""

    RETURN_TYPES = ("FLOAT", "INT")
    DESCRIPTION = "Explore fixed, uniform, or Gaussian variations around a floating-point value."

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "distribution": (DISTRIBUTIONS,),
                "centre": (
                    "FLOAT",
                    {"default": 1.0, "min": -1.0e12, "max": 1.0e12, "step": 0.01},
                ),
                "spread": (
                    "FLOAT",
                    {
                        "default": 0.05,
                        "min": 0.0,
                        "max": 1.0e12,
                        "step": 0.001,
                        "tooltip": "Gaussian sigma, or uniform half-width.",
                    },
                ),
                "clip_sigma": (
                    "FLOAT",
                    {
                        "default": 3.0,
                        "min": 0.0,
                        "max": 20.0,
                        "step": 0.1,
                        "tooltip": "Truncate Gaussian samples at this many sigma; 0 disables truncation.",
                    },
                ),
                "hard_min": (
                    "FLOAT",
                    {"default": 0.0, "min": -1.0e12, "max": 1.0e12, "step": 0.01},
                ),
                "hard_max": (
                    "FLOAT",
                    {"default": 100.0, "min": -1.0e12, "max": 1.0e12, "step": 0.01},
                ),
                "quantum": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 1.0e12,
                        "step": 0.001,
                        "tooltip": "Round to this increment; 0 preserves full precision.",
                    },
                ),
                "random_seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": U64_MAX, "control_after_generate": True},
                ),
                "lock_current": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Hold the last live sample; after restart, reproduce from random_seed.",
                    },
                ),
            }
        }

    def _convert(self, value: int | float) -> float:
        return float(value)


class FrontierIntegerMutator(_FrontierMutatorBase):
    """Mutate integer controls such as latent seed, steps, or dimensions."""

    RETURN_TYPES = ("INT", "INT")
    DESCRIPTION = "Explore fixed, uniform, or Gaussian variations around an integer value."

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "distribution": (DISTRIBUTIONS,),
                "centre": ("INT", {"default": 0, "min": I64_MIN, "max": U64_MAX}),
                "spread": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.0,
                        "max": float(I64_MAX),
                        "step": 1.0,
                        "tooltip": "Gaussian sigma, or uniform half-width.",
                    },
                ),
                "clip_sigma": (
                    "FLOAT",
                    {
                        "default": 3.0,
                        "min": 0.0,
                        "max": 20.0,
                        "step": 0.1,
                        "tooltip": "Truncate Gaussian samples at this many sigma; 0 disables truncation.",
                    },
                ),
                "hard_min": ("INT", {"default": 0, "min": I64_MIN, "max": U64_MAX}),
                "hard_max": ("INT", {"default": I64_MAX, "min": I64_MIN, "max": U64_MAX}),
                "quantum": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": I64_MAX,
                        "tooltip": "Round to this integer increment.",
                    },
                ),
                "random_seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": U64_MAX, "control_after_generate": True},
                ),
                "lock_current": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Hold the last live sample; after restart, reproduce from random_seed.",
                    },
                ),
            }
        }

    def _draw(
        self,
        rng: random.Random,
        distribution: str,
        centre: int | float,
        spread: float,
        clip_sigma: float,
    ) -> int:
        centre = int(centre)
        if distribution == "fixed":
            return centre
        if distribution == "uniform":
            radius = int(round(abs(spread)))
            return rng.randint(centre - radius, centre + radius)
        if distribution == "gaussian":
            offset = _bounded_gaussian(rng, 0.0, spread, clip_sigma)
            return centre + int(round(offset))
        raise ValueError(f"Unsupported distribution: {distribution}")

    def _apply_quantum(self, value: int | float, quantum: int | float) -> int:
        value = int(value)
        quantum = int(quantum)
        if quantum <= 1:
            return value
        quotient, remainder = divmod(value, quantum)
        if remainder * 2 >= quantum:
            quotient += 1
        return quotient * quantum

    def _convert(self, value: int | float) -> int:
        return int(value)
