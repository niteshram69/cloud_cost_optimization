"""Shared enums used across classification, pricing, and decision layers."""

from enum import Enum


class DataTemperature(str, Enum):
    """Storage intent classes used for optimization decisions."""

    HOT = "HOT"
    COLD = "COLD"
    ARCHIVE = "ARCHIVE"


class DecisionMode(str, Enum):
    """Optimization execution mode."""

    DRY_RUN = "dry_run"
    ENFORCED = "enforced"


class DecisionAction(str, Enum):
    """Action chosen by the optimization engine."""

    KEEP = "keep"
    MIGRATE = "migrate"
