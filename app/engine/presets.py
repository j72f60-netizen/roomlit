"""Editing presets.

Every number here is a conservative bound.  The engine measures each photo and
then moves it *toward* the preset's target, never beyond the stated limits, so
a photo that is already well exposed is barely touched.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    key: str
    # Overall brightness target (median luma, gamma space, windows excluded).
    target_median: float
    # Largest exposure move allowed, in stops (linear-light equivalent).
    max_ev: float
    # White balance: fraction of the measured cast that is corrected, and the
    # largest per-channel gain change that is ever applied.
    wb_strength: float
    wb_max: float
    # Tone: 0..1 strengths.
    shadow_lift: float
    highlight_recover: float
    contrast: float
    # Detail.
    clarity: float
    sharpen: float
    denoise: float
    # Targeted, colour-safe adjustments (0..1).
    whites_clean: float
    blue_lift: float
    vibrance: float
    # Overall colourfulness factor.  <1 counteracts the saturation gain that brightening brings.
    saturation: float = 1.0


PRESETS: dict[str, Preset] = {
    "natural": Preset(
        key="natural",
        target_median=0.44,
        max_ev=0.30,
        wb_strength=0.50,
        wb_max=0.05,
        shadow_lift=0.18,
        highlight_recover=0.20,
        contrast=0.04,
        clarity=0.10,
        sharpen=0.30,
        denoise=0.45,
        whites_clean=0.25,
        blue_lift=0.10,
        vibrance=0.00,
        saturation=1.0,
    ),
    "premium": Preset(
        key="premium",
        target_median=0.52,
        max_ev=0.65,
        wb_strength=0.70,
        wb_max=0.08,
        shadow_lift=0.42,
        highlight_recover=0.38,
        contrast=0.12,
        clarity=0.22,
        sharpen=0.50,
        denoise=0.65,
        whites_clean=0.55,
        blue_lift=0.40,
        vibrance=0.02,
        saturation=0.96,
    ),
    "bright": Preset(
        key="bright",
        target_median=0.57,
        max_ev=0.80,
        wb_strength=0.80,
        wb_max=0.10,
        shadow_lift=0.68,
        highlight_recover=0.70,
        contrast=0.09,
        clarity=0.18,
        sharpen=0.45,
        denoise=0.80,
        whites_clean=0.80,
        blue_lift=0.60,
        vibrance=0.02,
        saturation=0.92,
    ),
    # The professional-listing brief in one look: brighter without losing natural shadows, open dark areas, fresh white
    # bedding (cast removed from whites only) and a visibly brighter blue sofa (same hue, same saturation), consistent
    # across a folder.  Highlights stay protected, so windows and white linen keep their texture.
    "pro": Preset(
        key="pro",
        target_median=0.54,
        max_ev=0.70,
        wb_strength=0.80,
        wb_max=0.09,
        shadow_lift=0.55,
        highlight_recover=0.50,
        contrast=0.10,
        clarity=0.24,
        sharpen=0.52,
        denoise=0.70,
        whites_clean=0.85,
        blue_lift=0.85,
        vibrance=0.02,
        saturation=0.95,
    ),
}

DEFAULT_MODE = "premium"


def get_preset(key: str) -> Preset:
    try:
        return PRESETS[key]
    except KeyError:
        raise ValueError(f"unknown mode: {key!r}")
