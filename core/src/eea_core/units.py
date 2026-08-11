"""FIX-02 canonical unit normalization and comparison service."""

from collections.abc import Callable
from dataclasses import dataclass
from math import isclose, pi
from typing import TYPE_CHECKING, Literal

from eea_core.enums import EngineeringDimension

if TYPE_CHECKING:
    from eea_core.claims import EngineeringValue


class UnitNormalizationError(ValueError):
    """Raised for unsupported units or dimensionally invalid comparisons."""


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    dimension: EngineeringDimension
    canonical_unit: str
    to_canonical: Callable[[float], float]


def _linear(factor: float, offset: float = 0) -> Callable[[float], float]:
    return lambda value: value * factor + offset


_UNITS: dict[str, UnitDefinition] = {}


def _register(
    dimension: EngineeringDimension,
    canonical_unit: str,
    definitions: dict[str, Callable[[float], float]],
) -> None:
    for unit, conversion in definitions.items():
        _UNITS[unit] = UnitDefinition(dimension, canonical_unit, conversion)


_register(
    EngineeringDimension.VOLTAGE,
    "V",
    {"uV": _linear(1e-6), "mV": _linear(1e-3), "V": _linear(1), "kV": _linear(1e3)},
)
_register(
    EngineeringDimension.CURRENT,
    "A",
    {"uA": _linear(1e-6), "mA": _linear(1e-3), "A": _linear(1), "kA": _linear(1e3)},
)
_register(
    EngineeringDimension.RESISTANCE,
    "ohm",
    {"mohm": _linear(1e-3), "ohm": _linear(1), "kohm": _linear(1e3), "Mohm": _linear(1e6)},
)
_register(
    EngineeringDimension.CAPACITANCE,
    "F",
    {
        "pF": _linear(1e-12),
        "nF": _linear(1e-9),
        "uF": _linear(1e-6),
        "mF": _linear(1e-3),
        "F": _linear(1),
    },
)
_register(
    EngineeringDimension.INDUCTANCE,
    "H",
    {"nH": _linear(1e-9), "uH": _linear(1e-6), "mH": _linear(1e-3), "H": _linear(1)},
)
_register(
    EngineeringDimension.FREQUENCY,
    "Hz",
    {"Hz": _linear(1), "kHz": _linear(1e3), "MHz": _linear(1e6), "GHz": _linear(1e9)},
)
_register(
    EngineeringDimension.TIME,
    "s",
    {
        "ns": _linear(1e-9),
        "us": _linear(1e-6),
        "µs": _linear(1e-6),
        "ms": _linear(1e-3),
        "s": _linear(1),
        "min": _linear(60),
    },
)
_register(
    EngineeringDimension.TEMPERATURE,
    "K",
    {
        "K": _linear(1),
        "C": _linear(1, 273.15),
        "°C": _linear(1, 273.15),
        "F": _linear(5 / 9, 255.3722222222222),
        "°F": _linear(5 / 9, 255.3722222222222),
    },
)
_register(
    EngineeringDimension.ANGLE,
    "rad",
    {"rad": _linear(1), "deg": _linear(pi / 180)},
)
_register(
    EngineeringDimension.ANGULAR_VELOCITY,
    "rad/s",
    {"rad/s": _linear(1), "deg/s": _linear(pi / 180), "rpm": _linear(2 * pi / 60)},
)
_register(
    EngineeringDimension.LENGTH,
    "m",
    {
        "nm": _linear(1e-9),
        "um": _linear(1e-6),
        "µm": _linear(1e-6),
        "mm": _linear(1e-3),
        "cm": _linear(1e-2),
        "m": _linear(1),
        "km": _linear(1e3),
    },
)
_register(
    EngineeringDimension.POWER,
    "W",
    {"mW": _linear(1e-3), "W": _linear(1), "kW": _linear(1e3)},
)
_register(
    EngineeringDimension.ENERGY,
    "J",
    {"mJ": _linear(1e-3), "J": _linear(1), "kJ": _linear(1e3), "Wh": _linear(3600)},
)
_register(
    EngineeringDimension.DIMENSIONLESS,
    "1",
    {"1": _linear(1), "%": _linear(0.01), "ppm": _linear(1e-6)},
)


class UnitNormalizationService:
    """The single place that converts and compares engineering values."""

    @staticmethod
    def canonical_unit(dimension: EngineeringDimension) -> str:
        for definition in _UNITS.values():
            if definition.dimension is dimension:
                return definition.canonical_unit
        raise UnitNormalizationError(f"Unsupported engineering dimension: {dimension}")

    @staticmethod
    def normalize(value: float, unit: str, dimension: EngineeringDimension) -> float:
        definition = _UNITS.get(unit)
        if definition is None:
            raise UnitNormalizationError(f"Unsupported unit: {unit}")
        if definition.dimension is not dimension:
            raise UnitNormalizationError(
                f"Unit {unit} belongs to {definition.dimension}, not {dimension}"
            )
        return definition.to_canonical(value)

    @staticmethod
    def compare(
        left: "EngineeringValue",
        right: "EngineeringValue",
        operator: Literal["==", "<", "<=", ">", ">="],
    ) -> bool:
        if left.dimension is not right.dimension:
            raise UnitNormalizationError(f"Cannot compare {left.dimension} with {right.dimension}")
        left_value = left.require_normalized_nominal()
        right_value = right.require_normalized_nominal()
        if operator == "==":
            return isclose(left_value, right_value, rel_tol=1e-12, abs_tol=1e-12)
        if operator == "<":
            return left_value < right_value
        if operator == "<=":
            return left_value <= right_value
        if operator == ">":
            return left_value > right_value
        return left_value >= right_value
