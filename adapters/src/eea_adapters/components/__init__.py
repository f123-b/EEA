"""Embedded software component providers."""

from eea_adapters.components.curated import StaticComponentProvider
from eea_adapters.components.stm32cube import Stm32CubeG4Provider

__all__ = ["StaticComponentProvider", "Stm32CubeG4Provider"]
