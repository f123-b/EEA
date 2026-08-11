"""Deterministic M11 MCUConfigIR construction and compatibility validation."""

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import cast
from uuid import UUID

from eea_core.architecture import HardwareIR
from eea_core.circuit import CircuitIR
from eea_core.entities import utc_now
from eea_core.enums import EngineeringDimension, EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.mcu_config import (
    DMAIR,
    ClockIR,
    DebugConfigIR,
    GPIOConfig,
    InterruptConfigIR,
    MCUConfigBundle,
    MCUConfigIR,
    MemoryConfigIR,
    PeripheralConfigIR,
)
from eea_core.pin_planner import RuleResult
from eea_core.schematic import SchematicIR


def _unique(values: Iterable[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> Collection[object] | None:
    return value if isinstance(value, (list, tuple, set)) else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class MCUConfigService:
    """Create configuration snapshots and reject unsupported realized settings."""

    rule_version = "1.0"

    def generate(
        self,
        hardware: HardwareIR,
        circuit: CircuitIR,
        schematic: SchematicIR,
        *,
        device_instance_id: UUID,
        clock: ClockIR,
        gpio: Sequence[GPIOConfig] = (),
        peripherals: Sequence[PeripheralConfigIR] = (),
        dma: Sequence[DMAIR] = (),
        interrupts: Sequence[InterruptConfigIR] = (),
        memory: MemoryConfigIR | None = None,
        debug: DebugConfigIR | None = None,
        capability_snapshot: Mapping[str, object] | None = None,
    ) -> MCUConfigBundle:
        self._assert_sources(hardware, circuit, schematic)
        if device_instance_id not in {item.id for item in hardware.device_instances}:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "MCUConfigIR device instance is not present in HardwareIR",
                details={"reason": "DEVICE_INSTANCE_SOURCE_MISMATCH"},
            )
        config = MCUConfigIR(
            project_id=hardware.project_id,
            hardware_ir_id=hardware.id,
            hardware_ir_revision=hardware.revision,
            circuit_id=circuit.id,
            circuit_revision=circuit.revision,
            schematic_id=schematic.id,
            schematic_revision=schematic.revision,
            device_instance_id=device_instance_id,
            clock=clock,
            gpio=list(gpio),
            peripherals=list(peripherals),
            dma=list(dma),
            interrupts=list(interrupts),
            memory=memory,
            debug=debug,
            capability_snapshot=dict(capability_snapshot or {}),
            requirement_ids=_unique(
                [*hardware.requirement_ids, *circuit.requirement_ids, *schematic.requirement_ids]
                + [value for item in gpio for value in item.requirement_ids]
                + [value for item in peripherals for value in item.requirement_ids]
                + [value for item in dma for value in item.requirement_ids]
                + [value for item in interrupts for value in item.requirement_ids]
            ),
            evidence_ids=_unique(
                [*hardware.evidence_ids, *circuit.evidence_ids, *schematic.evidence_ids]
                + list(clock.evidence_ids)
                + [value for item in gpio for value in item.evidence_ids]
                + [value for item in peripherals for value in item.evidence_ids]
                + [value for item in dma for value in item.evidence_ids]
                + [value for item in interrupts for value in item.evidence_ids]
            ),
            pin_assignment_revisions=dict(hardware.pin_assignment_revisions),
        )
        results = self.validate(config, hardware, circuit, schematic)
        return MCUConfigBundle(
            config=config.model_copy(update={"rule_results": results, "updated_at": utc_now()}),
            rule_results=results,
        )

    def validate(
        self,
        config: MCUConfigIR,
        hardware: HardwareIR,
        circuit: CircuitIR,
        schematic: SchematicIR,
    ) -> list[RuleResult]:
        self._assert_sources(hardware, circuit, schematic)
        self._assert_config_sources(config, hardware, circuit, schematic)
        results: list[RuleResult] = []
        known_pin_ids = {
            pin_id for interface in hardware.interfaces for pin_id in interface.pin_assignment_ids
        }
        known_pin_ids.update(
            pin_id for device in hardware.device_instances for pin_id in device.pin_assignment_ids
        )
        configured_pin_ids = self._configured_pin_ids(config)
        invalid_pin_ids = sorted(
            (str(pin_id) for pin_id in configured_pin_ids if pin_id not in known_pin_ids),
            key=str,
        )
        if invalid_pin_ids:
            results.append(
                self._rule(
                    config,
                    "PINMAP_SOURCE_MISMATCH",
                    "FAIL",
                    IssueSeverity.HIGH,
                    invalid_pin_ids,
                    recommendation=(
                        "Reference only pin assignments exposed by the selected HardwareIR."
                    ),
                )
            )
        else:
            if configured_pin_ids:
                results.append(
                    self._rule(
                        config,
                        "PINMAP_SOURCE_VALID",
                        "PASS",
                        IssueSeverity.INFO,
                        [str(value) for value in sorted(configured_pin_ids, key=str)],
                        recommendation="All MCUConfigIR pin references come from HardwareIR.",
                    )
                )
        revision_mismatches = [
            key
            for key, revision in config.pin_assignment_revisions.items()
            if hardware.pin_assignment_revisions.get(key) != revision
        ]
        if revision_mismatches:
            results.append(
                self._rule(
                    config,
                    "PINMAP_REVISION_MISMATCH",
                    "FAIL",
                    IssueSeverity.HIGH,
                    revision_mismatches,
                    recommendation=(
                        "Regenerate MCUConfigIR from the current HardwareIR assignment revisions."
                    ),
                )
            )

        results.extend(self._validate_clock(config))
        results.extend(self._validate_pwms(config))
        results.extend(self._validate_adcs(config))
        results.extend(self._validate_dma(config))
        results.extend(self._validate_interrupts(config))
        if not results:
            results.append(
                self._rule(
                    config,
                    "MCU_CONFIG_VALIDATION_NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    IssueSeverity.INFO,
                    [str(config.id)],
                    recommendation=(
                        "No deterministic MCU configuration rule had an applicable input."
                    ),
                )
            )
        return results

    @staticmethod
    def _assert_sources(hardware: HardwareIR, circuit: CircuitIR, schematic: SchematicIR) -> None:
        if hardware.project_id != circuit.project_id or hardware.project_id != schematic.project_id:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "MCUConfigIR sources belong to different projects",
                details={"reason": "SOURCE_PROJECT_MISMATCH"},
            )
        if (
            circuit.hardware_ir_id != hardware.id
            or circuit.hardware_ir_revision != hardware.revision
            or schematic.circuit_id != circuit.id
            or schematic.circuit_revision != circuit.revision
            or schematic.hardware_ir_id != hardware.id
            or schematic.hardware_ir_revision != hardware.revision
        ):
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "MCUConfigIR source revisions do not match",
                details={"reason": "SOURCE_REVISION_MISMATCH"},
            )

    @staticmethod
    def _assert_config_sources(
        config: MCUConfigIR,
        hardware: HardwareIR,
        circuit: CircuitIR,
        schematic: SchematicIR,
    ) -> None:
        if config.project_id != hardware.project_id:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "MCUConfigIR belongs to a different project than its sources",
                details={"reason": "SOURCE_PROJECT_MISMATCH"},
            )
        if (
            config.hardware_ir_id != hardware.id
            or config.hardware_ir_revision != hardware.revision
            or config.circuit_id != circuit.id
            or config.circuit_revision != circuit.revision
            or config.schematic_id != schematic.id
            or config.schematic_revision != schematic.revision
        ):
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "MCUConfigIR source identity or revision does not match",
                details={"reason": "SOURCE_REVISION_MISMATCH"},
            )

    @staticmethod
    def _configured_pin_ids(config: MCUConfigIR) -> set[UUID]:
        values = {item.pin_assignment_id for item in config.gpio}
        values.update(pin_id for item in config.peripherals for pin_id in item.pin_assignment_ids)
        values.update(
            pin_id
            for peripheral in config.peripherals
            for pwm in peripheral.pwm
            for pin_id in pwm.pin_assignment_ids
        )
        values.update(
            pin_id
            for peripheral in config.peripherals
            for adc in peripheral.adc
            for pin_id in adc.pin_assignment_ids
        )
        if config.debug is not None:
            values.update(config.debug.pin_assignment_ids)
        return values

    def _validate_clock(self, config: MCUConfigIR) -> list[RuleResult]:
        raw_facts = config.capability_snapshot.get("clock_sources")
        facts = _mapping(raw_facts)
        if facts is None:
            available = _sequence(raw_facts)
            if available is not None and config.clock.source not in {
                str(item) for item in available
            }:
                return [
                    self._rule(
                        config,
                        "CLOCK_SOURCE_INVALID",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [config.clock.source],
                        recommendation="Select a clock source supported by the device facts.",
                    )
                ]
            return [
                self._rule(
                    config,
                    "CLOCK_SOURCE_INVALID",
                    "UNKNOWN",
                    IssueSeverity.HIGH,
                    [config.clock.source],
                    recommendation=(
                        "Provide structured clock source capabilities before validation."
                    ),
                )
            ]
        source_facts = facts.get(config.clock.source)
        if source_facts is None:
            available = _sequence(config.capability_snapshot.get("clock_sources"))
            if available is not None and config.clock.source not in {
                str(item) for item in available
            }:
                return [
                    self._rule(
                        config,
                        "CLOCK_SOURCE_INVALID",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [config.clock.source],
                        recommendation="Select a clock source supported by the device facts.",
                    )
                ]
            return [
                self._rule(
                    config,
                    "CLOCK_SOURCE_INVALID",
                    "UNKNOWN",
                    IssueSeverity.HIGH,
                    [config.clock.source],
                    recommendation="Declare the selected clock source capability.",
                )
            ]
        source_mapping = _mapping(source_facts)
        if source_mapping is None:
            return [
                self._rule(
                    config,
                    "CLOCK_SOURCE_INVALID",
                    "PASS",
                    IssueSeverity.INFO,
                    [config.clock.source],
                    recommendation="Clock source is present in the capability snapshot.",
                )
            ]
        maximum = _number(source_mapping.get("max_frequency_hz"))
        if config.clock.target_frequency is None or maximum is None:
            return [
                self._rule(
                    config,
                    "CLOCK_SOURCE_INVALID",
                    "UNKNOWN",
                    IssueSeverity.HIGH,
                    [config.clock.source],
                    recommendation="Provide target frequency and maximum source frequency facts.",
                )
            ]
        target = config.clock.target_frequency
        if target.dimension is not EngineeringDimension.FREQUENCY:
            return [
                self._rule(
                    config,
                    "CLOCK_SOURCE_INVALID",
                    "UNKNOWN",
                    IssueSeverity.HIGH,
                    [config.clock.source],
                    recommendation=(
                        "Use a canonical frequency EngineeringValue for the clock target."
                    ),
                )
            ]
        status = "PASS" if target.require_normalized_nominal() <= maximum else "FAIL"
        return [
            self._rule(
                config,
                "CLOCK_SOURCE_INVALID",
                status,
                IssueSeverity.HIGH,
                [config.clock.source],
                measured=target,
                threshold={"max_frequency_hz": maximum},
                recommendation=(
                    "Reduce the target clock frequency or select a supported source."
                    if status == "FAIL"
                    else "Clock source and target frequency are within declared facts."
                ),
            )
        ]

    def _validate_pwms(self, config: MCUConfigIR) -> list[RuleResult]:
        results: list[RuleResult] = []
        seen: set[tuple[str, str]] = set()
        timers = _mapping(config.capability_snapshot.get("timers"))
        for peripheral in config.peripherals:
            for pwm in peripheral.pwm:
                key = (pwm.timer, pwm.channel)
                if key in seen:
                    results.append(
                        self._rule(
                            config,
                            "TIMER_CHANNEL_CONFLICT",
                            "FAIL",
                            IssueSeverity.HIGH,
                            [pwm.timer, pwm.channel],
                            recommendation=(
                                "Assign each timer channel to one realized PWM configuration."
                            ),
                        )
                    )
                seen.add(key)
                if timers is None or pwm.timer not in timers:
                    results.append(
                        self._rule(
                            config,
                            "PWM_CAPABILITY_MISSING",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            [pwm.timer, pwm.channel],
                            recommendation=(
                                "Provide timer channel capabilities before PWM validation."
                            ),
                        )
                    )
                    continue
                timer_facts = _mapping(timers[pwm.timer])
                if timer_facts is None:
                    results.append(
                        self._rule(
                            config,
                            "PWM_CAPABILITY_MISSING",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            [pwm.timer],
                            recommendation="Declare structured timer capabilities.",
                        )
                    )
                    continue
                channels = _sequence(timer_facts.get("channels"))
                if channels is None:
                    results.append(
                        self._rule(
                            config,
                            "PWM_CAPABILITY_MISSING",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            [pwm.timer],
                            recommendation="Declare supported timer channels.",
                        )
                    )
                elif pwm.channel not in {str(item) for item in channels}:
                    results.append(
                        self._rule(
                            config,
                            "TIMER_CHANNEL_CONFLICT",
                            "FAIL",
                            IssueSeverity.HIGH,
                            [pwm.timer, pwm.channel],
                            recommendation="Select a supported timer channel.",
                        )
                    )
                if pwm.complementary_channel is not None:
                    complementary = timer_facts.get("complementary")
                    if not isinstance(complementary, bool):
                        results.append(
                            self._rule(
                                config,
                                "COMPLEMENTARY_PWM_MISSING",
                                "UNKNOWN",
                                IssueSeverity.HIGH,
                                [pwm.timer, pwm.complementary_channel],
                                recommendation="Declare complementary PWM capability.",
                            )
                        )
                    elif not complementary:
                        results.append(
                            self._rule(
                                config,
                                "COMPLEMENTARY_PWM_MISSING",
                                "FAIL",
                                IssueSeverity.HIGH,
                                [pwm.timer, pwm.complementary_channel],
                                recommendation="Select a timer with complementary PWM support.",
                            )
                        )
                maximum = _number(timer_facts.get("max_frequency_hz"))
                if pwm.switching_frequency is None or maximum is None:
                    results.append(
                        self._rule(
                            config,
                            "TIMER_FREQUENCY_IMPOSSIBLE",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            [pwm.timer, pwm.channel],
                            recommendation="Provide PWM target and timer maximum frequency facts.",
                        )
                    )
                elif pwm.switching_frequency.dimension is not EngineeringDimension.FREQUENCY:
                    results.append(
                        self._rule(
                            config,
                            "TIMER_FREQUENCY_IMPOSSIBLE",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            [pwm.timer, pwm.channel],
                            recommendation="Use a canonical frequency EngineeringValue for PWM.",
                        )
                    )
                else:
                    status = (
                        "PASS"
                        if pwm.switching_frequency.require_normalized_nominal() <= maximum
                        else "FAIL"
                    )
                    results.append(
                        self._rule(
                            config,
                            "TIMER_FREQUENCY_IMPOSSIBLE",
                            status,
                            IssueSeverity.HIGH,
                            [pwm.timer, pwm.channel],
                            measured=pwm.switching_frequency,
                            threshold={"max_frequency_hz": maximum},
                            recommendation=(
                                "Reduce PWM frequency or select a supported timer configuration."
                                if status == "FAIL"
                                else "PWM frequency is within the declared timer limit."
                            ),
                        )
                    )
        return results

    def _validate_adcs(self, config: MCUConfigIR) -> list[RuleResult]:
        results: list[RuleResult] = []
        facts = _mapping(config.capability_snapshot.get("adc"))
        for peripheral in config.peripherals:
            for adc in peripheral.adc:
                refs = [adc.instance, *adc.channels]
                if facts is None or adc.instance not in facts:
                    results.append(
                        self._rule(
                            config,
                            "ADC_CHANNEL_INVALID",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            refs,
                            recommendation="Provide ADC instance and channel capabilities.",
                        )
                    )
                    continue
                adc_facts = _mapping(facts[adc.instance])
                if adc_facts is None:
                    results.append(
                        self._rule(
                            config,
                            "ADC_CHANNEL_INVALID",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            refs,
                            recommendation="Declare structured ADC capabilities.",
                        )
                    )
                    continue
                channels = _sequence(adc_facts.get("channels"))
                if channels is None:
                    results.append(
                        self._rule(
                            config,
                            "ADC_CHANNEL_INVALID",
                            "UNKNOWN",
                            IssueSeverity.HIGH,
                            refs,
                            recommendation="Declare supported ADC channels.",
                        )
                    )
                else:
                    invalid = [
                        channel
                        for channel in adc.channels
                        if channel not in {str(item) for item in channels}
                    ]
                    results.append(
                        self._rule(
                            config,
                            "ADC_CHANNEL_INVALID",
                            "FAIL" if invalid else "PASS",
                            IssueSeverity.HIGH,
                            [adc.instance, *invalid] if invalid else [adc.instance],
                            recommendation=(
                                "Select only channels supported by the ADC instance."
                                if invalid
                                else "ADC channels are supported by the declared instance."
                            ),
                        )
                    )
                if adc.trigger_source is not None:
                    triggers = _sequence(adc_facts.get("triggers"))
                    if triggers is None:
                        results.append(
                            self._rule(
                                config,
                                "ADC_TRIGGER_INVALID",
                                "UNKNOWN",
                                IssueSeverity.HIGH,
                                [adc.instance, adc.trigger_source],
                                recommendation="Declare ADC trigger capabilities.",
                            )
                        )
                    else:
                        valid = adc.trigger_source in {str(item) for item in triggers}
                        results.append(
                            self._rule(
                                config,
                                "ADC_TRIGGER_INVALID",
                                "PASS" if valid else "FAIL",
                                IssueSeverity.HIGH,
                                [adc.instance, adc.trigger_source],
                                recommendation=(
                                    "Select a trigger supported by the ADC instance."
                                    if not valid
                                    else "ADC trigger is supported by the declared instance."
                                ),
                            )
                        )
                if adc.dma_ref is not None:
                    dma_refs = {str(item.id) for item in config.dma} | {
                        item.request for item in config.dma
                    }
                    if adc.dma_ref not in dma_refs:
                        results.append(
                            self._rule(
                                config,
                                "DMA_REQUEST_INVALID",
                                "FAIL",
                                IssueSeverity.HIGH,
                                [adc.instance, adc.dma_ref],
                                recommendation="Reference a configured DMA request.",
                            )
                        )
        return results

    def _validate_dma(self, config: MCUConfigIR) -> list[RuleResult]:
        results: list[RuleResult] = []
        facts = _mapping(config.capability_snapshot.get("dma"))
        for dma in config.dma:
            refs = [dma.controller, dma.channel_or_stream, dma.request]
            if facts is None or dma.controller not in facts:
                results.append(
                    self._rule(
                        config,
                        "DMA_REQUEST_INVALID",
                        "UNKNOWN",
                        IssueSeverity.HIGH,
                        refs,
                        recommendation="Provide DMA controller, channel, and request capabilities.",
                    )
                )
                continue
            controller_facts = _mapping(facts[dma.controller])
            if controller_facts is None:
                results.append(
                    self._rule(
                        config,
                        "DMA_REQUEST_INVALID",
                        "UNKNOWN",
                        IssueSeverity.HIGH,
                        refs,
                        recommendation="Declare structured DMA controller capabilities.",
                    )
                )
                continue
            requests = _sequence(controller_facts.get("requests"))
            channels = _sequence(controller_facts.get("channels"))
            if requests is None or channels is None:
                results.append(
                    self._rule(
                        config,
                        "DMA_REQUEST_INVALID",
                        "UNKNOWN",
                        IssueSeverity.HIGH,
                        refs,
                        recommendation="Declare supported DMA requests and channels.",
                    )
                )
                continue
            valid = dma.request in {str(item) for item in requests} and dma.channel_or_stream in {
                str(item) for item in channels
            }
            results.append(
                self._rule(
                    config,
                    "DMA_REQUEST_INVALID",
                    "PASS" if valid else "FAIL",
                    IssueSeverity.HIGH,
                    refs,
                    recommendation=(
                        "Select a supported DMA request and channel."
                        if not valid
                        else "DMA request and channel are supported."
                    ),
                )
            )
        return results

    def _validate_interrupts(self, config: MCUConfigIR) -> list[RuleResult]:
        results: list[RuleResult] = []
        irq_counts = Counter(item.irq for item in config.interrupts)
        for irq, count in irq_counts.items():
            if count > 1:
                results.append(
                    self._rule(
                        config,
                        "IRQ_PRIORITY_CONFLICT",
                        "FAIL",
                        IssueSeverity.HIGH,
                        [irq],
                        recommendation="Define one deterministic priority for each IRQ source.",
                    )
                )
        facts = _sequence(config.capability_snapshot.get("interrupts"))
        for interrupt in config.interrupts:
            if facts is None:
                results.append(
                    self._rule(
                        config,
                        "IRQ_PRIORITY_CONFLICT",
                        "UNKNOWN",
                        IssueSeverity.HIGH,
                        [interrupt.irq],
                        recommendation="Provide the supported interrupt vector facts.",
                    )
                )
            else:
                valid = interrupt.irq in {str(item) for item in facts}
                results.append(
                    self._rule(
                        config,
                        "IRQ_PRIORITY_CONFLICT",
                        "PASS" if valid else "FAIL",
                        IssueSeverity.HIGH,
                        [interrupt.irq],
                        recommendation=(
                            "Select a supported interrupt vector."
                            if not valid
                            else "Interrupt vector is supported by the declared facts."
                        ),
                    )
                )
        return results

    def _rule(
        self,
        config: MCUConfigIR,
        rule_id: str,
        status: str,
        severity: IssueSeverity,
        affected_refs: list[str],
        *,
        measured: object | None = None,
        threshold: object | None = None,
        recommendation: str,
    ) -> RuleResult:
        return RuleResult(
            project_id=config.project_id,
            rule_id=rule_id,
            rule_version=self.rule_version,
            stage="PRE_GENERATION",
            status=status,  # type: ignore[arg-type]
            severity=severity,
            affected_refs=affected_refs,
            measured=measured,
            threshold=threshold,
            evidence_ids=list(config.evidence_ids),
            recommendation=recommendation,
            input_snapshot={
                "mcu_config_id": str(config.id),
                "hardware_ir_id": str(config.hardware_ir_id),
                "circuit_id": str(config.circuit_id),
                "schematic_id": str(config.schematic_id),
            },
        )


__all__ = ["MCUConfigService"]
