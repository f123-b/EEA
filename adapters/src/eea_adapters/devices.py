"""Deterministic STM32 device provider fixture and provider boundary."""

from collections.abc import Iterable

from eea_core.claims import EngineeringValue
from eea_core.enums import EngineeringDimension, EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.intelligence import Device, DevicePin, PinFunction


class Stm32G431FixtureProvider:
    """Small official-style fixture covering the M4 acceptance queries."""

    name = "stm32-structured-fixture/v1"

    def __init__(self) -> None:
        self._device = Device(
            manufacturer="STMicroelectronics",
            family="STM32G4",
            model="STM32G431",
            revision_label="A",
            packages=["UFQFPN48", "LQFP64"],
            memory={"flash_bytes": 131072, "sram_bytes": 32768},
            peripherals=["TIM1", "FDCAN1", "ADC1", "DMA1", "USART2", "SPI1"],
            pins=[
                DevicePin(
                    name="PA8",
                    package="UFQFPN48",
                    package_pin="41",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="TIM1", signal="CH1", alternate_function="AF6")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PB13",
                    package="UFQFPN48",
                    package_pin="30",
                    voltage_domain="VDDIO2",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="TIM1", signal="CH1N", alternate_function="AF6")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA11",
                    package="UFQFPN48",
                    package_pin="35",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=True,
                    functions=[
                        PinFunction(peripheral="FDCAN1", signal="RX", alternate_function="AF9")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA12",
                    package="UFQFPN48",
                    package_pin="36",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=True,
                    functions=[
                        PinFunction(peripheral="FDCAN1", signal="TX", alternate_function="AF9")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA0",
                    package="UFQFPN48",
                    package_pin="10",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="ADC1", signal="IN1", alternate_function=None)
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA2",
                    package="UFQFPN48",
                    package_pin="12",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="USART2", signal="TX", alternate_function="AF7")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA3",
                    package="UFQFPN48",
                    package_pin="13",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="USART2", signal="RX", alternate_function="AF7")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA5",
                    package="UFQFPN48",
                    package_pin="19",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="SPI1", signal="SCK", alternate_function="AF5")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA6",
                    package="UFQFPN48",
                    package_pin="20",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="SPI1", signal="MISO", alternate_function="AF5")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PA7",
                    package="UFQFPN48",
                    package_pin="21",
                    voltage_domain="VDDIO1",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="SPI1", signal="MOSI", alternate_function="AF5")
                    ],
                    source_refs=[self.name],
                ),
                DevicePin(
                    name="PB0",
                    package="UFQFPN48",
                    package_pin="31",
                    voltage_domain="VDDIO2",
                    five_v_tolerant=False,
                    functions=[
                        PinFunction(peripheral="GPIO", signal="CS", alternate_function=None)
                    ],
                    source_refs=[self.name],
                ),
            ],
            dma={"DMA1": {"request_generators": ["ADC1", "TIM1_UP"]}},
            interrupts={"vectors": ["FDCAN1_IT0", "ADC1_1", "TIM1_BRK_TIM15"]},
            electrical={
                "max_vdd": EngineeringValue(
                    unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=3.6
                ),
                "io_voltage": EngineeringValue(
                    unit="V", dimension=EngineeringDimension.VOLTAGE, nominal=3.3
                ),
                "debug_pins": ["PA13", "PA14"],
            },
            source_refs=[self.name],
        )

    def get_device(self, device_ref: str, *, package: str | None = None) -> Device | None:
        normalized = device_ref.replace("-", "").replace("_", "").upper()
        accepted = {"STM32G431", "STM32G4"}
        if normalized not in accepted:
            return None
        if package is not None and package not in self._device.packages:
            return None
        if package is None:
            return self._device
        return self._device.model_copy(
            update={
                "pins": [
                    pin.model_copy(update={"package": package})
                    for pin in self._device.pins
                    if pin.package in {None, package, self._device.packages[0]}
                ],
                "packages": [package],
            }
        )

    def query_pin(
        self,
        device_ref: str,
        pin_name: str,
        *,
        package: str | None = None,
        peripheral: str | None = None,
        signal: str | None = None,
    ) -> DevicePin:
        device = self.get_device(device_ref, package=package)
        if device is None:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_NOT_FOUND,
                "Device or package was not found",
                details={"device_ref": device_ref, "package": package},
            )
        pin = next((item for item in device.pins if item.name == pin_name), None)
        if pin is None:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_NOT_FOUND,
                "Pin was not found for the selected device/package",
                details={"device_ref": device_ref, "pin": pin_name},
            )
        if peripheral is None and signal is None:
            return pin
        if any(
            function.peripheral == peripheral and function.signal == signal
            for function in pin.functions
        ):
            return pin
        raise EngineeringError(
            EngineeringErrorCode.PIN_FUNCTION_INVALID,
            "Pin does not support the requested alternate function",
            details={
                "device_ref": device_ref,
                "pin": pin_name,
                "peripheral": peripheral,
                "signal": signal,
            },
        )


def provider_sources(providers: Iterable[object]) -> tuple[object, ...]:
    """Return a stable provider tuple for application-level multi-source wiring."""

    return tuple(providers)
