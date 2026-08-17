"""M12 FirmwareIR generation, source snapshots, and sandboxed build execution."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from eea_adapters.sandbox import (
    StructuredCommandExecutor,
    release_tool_policy_network_access,
)
from eea_core.build import BuildDiagnostic, BuildRun
from eea_core.components import DependencyLock
from eea_core.entities import utc_now
from eea_core.enums import BuildProfile, BuildStatus, EngineeringErrorCode, IssueSeverity
from eea_core.errors import EngineeringError
from eea_core.firmware import (
    BSPConfig,
    FirmwareBuildTarget,
    FirmwareBundle,
    FirmwareInterrupt,
    FirmwareIR,
    FirmwareModule,
    FirmwareSourceFile,
    FirmwareTask,
    MemoryLayout,
    PeripheralDriverConfig,
    SharedResource,
    StartupConfig,
)
from eea_core.mcu_config import GPIOConfig, MCUConfigIR
from eea_core.sandbox import CommandSpec, SandboxPolicy, SandboxWorkspace
from eea_core.source import BuildInputSnapshot, SourceRevision


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _empty_hash() -> str:
    return _hash_json({})


def _unique(values: Iterable[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _identifier(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value)
    return normalized.strip("_").lower() or "peripheral"


class FirmwareService:
    """Derive deterministic firmware structure and source candidates from MCUConfigIR."""

    generator_version = "m12.2"

    def generate(
        self,
        config: MCUConfigIR,
        *,
        build_target: FirmwareBuildTarget | None = None,
        board_name: str = "generic-stm32",
        dependency_lock: DependencyLock | None = None,
    ) -> FirmwareBundle:
        failed_rules = [result.rule_id for result in config.rule_results if result.status == "FAIL"]
        if failed_rules:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Firmware generation is blocked by MCUConfigIR rule failures",
                details={"reason": "MCU_CONFIG_RULE_GATE", "rule_ids": failed_rules},
            )
        target = build_target or FirmwareBuildTarget()
        if target.build_system.upper() == "PLATFORMIO":
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "PlatformIO STM32 build adapter is not available in M12A.",
                details={"reason": "PLATFORMIO_ADAPTER_UNAVAILABLE"},
            )
        if target.profile is BuildProfile.DEVICE and dependency_lock is None:
            raise EngineeringError(
                EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
                "DEVICE firmware generation requires a locked dependency closure.",
                details={"reason": "DEPENDENCY_LOCK_REQUIRED"},
            )
        if dependency_lock is not None and (
            dependency_lock.project_id != config.project_id
            or dependency_lock.mcu_config_id != config.id
            or dependency_lock.mcu_config_revision != config.revision
        ):
            raise EngineeringError(
                EngineeringErrorCode.DEPENDENCY_LOCK_STALE,
                "DependencyLock does not match the selected MCUConfigIR.",
                details={"reason": "DEPENDENCY_LOCK_STALE"},
            )
        input_hash = _hash_json(
            {
                "mcu_config": config.model_dump(
                    mode="json",
                    exclude={"id", "created_at", "updated_at", "metadata", "status"},
                ),
                "build_target": target.model_dump(mode="json"),
                "board_name": board_name,
                "dependency_lock_hash": dependency_lock.lock_hash if dependency_lock else None,
                "generator_version": self.generator_version,
                "platform_adapter_version": "m12.2",
            }
        )
        source_files = self._source_files(config, target, input_hash, dependency_lock)
        source_revision = self._source_revision(config, source_files)
        drivers = self._drivers(config)
        interrupts = self._interrupts(config)
        modules = self._modules(config, drivers, interrupts)
        requirements = _unique(
            [
                *config.requirement_ids,
                *[value for item in config.gpio for value in item.requirement_ids],
                *[
                    value
                    for peripheral in config.peripherals
                    for value in peripheral.requirement_ids
                ],
                *[value for item in config.dma for value in item.requirement_ids],
                *[value for item in config.interrupts for value in item.requirement_ids],
            ]
        )
        evidence = _unique(
            [
                *config.evidence_ids,
                *[value for item in config.gpio for value in item.evidence_ids],
                *[value for peripheral in config.peripherals for value in peripheral.evidence_ids],
                *[value for item in config.dma for value in item.evidence_ids],
                *[value for item in config.interrupts for value in item.evidence_ids],
            ]
        )
        firmware = FirmwareIR(
            project_id=config.project_id,
            mcu_config_id=config.id,
            mcu_config_revision=config.revision,
            hardware_ir_id=config.hardware_ir_id,
            hardware_ir_revision=config.hardware_ir_revision,
            circuit_id=config.circuit_id,
            circuit_revision=config.circuit_revision,
            schematic_id=config.schematic_id,
            schematic_revision=config.schematic_revision,
            source_revision_id=source_revision.id,
            layers=["STARTUP", "BSP", "HAL", "APPLICATION"],
            modules=modules,
            tasks=self._tasks(config),
            interrupts=interrupts,
            shared_resources=self._shared_resources(config),
            startup=StartupConfig(),
            clock_tree=config.clock.model_dump(mode="json"),
            peripheral_drivers=drivers,
            memory_layout=MemoryLayout(
                linker_script=config.memory.linker_script_ref if config.memory else None
            ),
            bsp=BSPConfig(
                board_name=board_name,
                component_refs=(
                    [item.component_key for item in dependency_lock.resolved_components]
                    if dependency_lock
                    else []
                ),
            ),
            build_target=target,
            rule_results=list(config.rule_results),
            requirement_ids=requirements,
            evidence_ids=evidence,
            input_hash=input_hash,
            dependency_lock_id=dependency_lock.id if dependency_lock else None,
            dependency_lock_hash=dependency_lock.lock_hash if dependency_lock else None,
            component_refs=(
                [item.component_key for item in dependency_lock.resolved_components]
                if dependency_lock
                else []
            ),
            platform_adapter_id=(
                "stm32cube" if target.profile is BuildProfile.DEVICE else "host-skeleton"
            ),
            platform_adapter_version="m12.2",
        )
        return FirmwareBundle(
            firmware=firmware,
            source_revision=source_revision,
            files=source_files,
            dependency_lock=dependency_lock,
        )

    @staticmethod
    def _source_revision(
        config: MCUConfigIR, files: Sequence[FirmwareSourceFile]
    ) -> SourceRevision:
        manifest = {
            item.path: item.content_hash for item in sorted(files, key=lambda value: value.path)
        }
        manifest_hash = _hash_json(manifest)
        return SourceRevision(
            project_id=config.project_id,
            repository_id=f"generated-firmware:{config.project_id}",
            commit_sha=None,
            tree_hash=manifest_hash,
            dirty=True,
            base_commit=None,
            workspace_revision=0,
            source_manifest_hash=manifest_hash,
            file_manifest=manifest,
            created_by="eea:m12",
        )

    def _source_files(
        self,
        config: MCUConfigIR,
        target: FirmwareBuildTarget,
        input_hash: str,
        dependency_lock: DependencyLock | None,
    ) -> list[FirmwareSourceFile]:
        if target.profile is BuildProfile.DEVICE:
            return self._device_source_files(config, target, input_hash, dependency_lock)
        identifier = str(config.id)
        header = "\n".join(
            [
                "/* Generated by EEA M12; do not edit as source-of-truth. */",
                "#pragma once",
                "",
                f'#define EEA_MCU_CONFIG_ID "{identifier}"',
                f"#define EEA_MCU_CONFIG_REVISION {config.revision}",
                f'#define EEA_HARDWARE_IR_ID "{config.hardware_ir_id}"',
                f'#define EEA_CIRCUIT_IR_ID "{config.circuit_id}"',
                f'#define EEA_SCHEMATIC_IR_ID "{config.schematic_id}"',
                f'#define EEA_CLOCK_SOURCE "{config.clock.source}"',
                "",
                "void eea_firmware_init(void);",
                "",
            ]
        )
        source = "\n".join(
            [
                "/* Generated by EEA M12; do not edit as source-of-truth. */",
                '#include "eea_firmware_config.h"',
                "",
                "void eea_firmware_init(void) {",
                "    /* Realized peripheral setup is supplied by the selected HAL adapter. */",
                "}",
                "",
            ]
        )
        rtos_profile = self._freertos_profile(config)
        if rtos_profile is not None:
            task_names = [
                str(item.get("name"))
                for item in self._freertos_tasks(rtos_profile)
                if item.get("name")
            ]
            source = source.replace(
                "    /* Realized peripheral setup is supplied by the selected HAL adapter. */",
                "    /* FreeRTOS profile: "
                + ", ".join(task_names)
                + "; task/queue realization is selected by the DEVICE adapter. */\n"
                "    /* Realized peripheral setup is supplied by the selected HAL adapter. */",
            )
        main = "\n".join(
            [
                "/* Generated by EEA M12; do not edit as source-of-truth. */",
                '#include "eea_firmware_config.h"',
                "",
                "int main(void) {",
                "    eea_firmware_init();",
                "    for (;;) {",
                "    }",
                "}",
                "",
            ]
        )
        compile_options = (
            f"target_compile_options({target.output_name} PRIVATE "
            f"{' '.join(target.compiler_flags)})"
            if target.compiler_flags
            else None
        )
        link_options = (
            f"target_link_options({target.output_name} PRIVATE {' '.join(target.linker_flags)})"
            if target.linker_flags
            else None
        )
        cmake = "\n".join(
            [
                "# Generated by EEA M12; candidate build adapter.",
                "cmake_minimum_required(VERSION 3.20)",
                f"project({target.output_name} C)",
                "set(CMAKE_C_STANDARD 11)",
                f"add_executable({target.output_name}",
                "    Core/Src/main.c",
                "    Core/Src/eea_firmware_config.c",
                ")",
                f"target_include_directories({target.output_name} PRIVATE Core/Inc)",
                *([compile_options] if compile_options else []),
                *([link_options] if link_options else []),
                "",
            ]
        )
        files: list[tuple[str, str]] = [
            ("Core/Inc/eea_firmware_config.h", header),
            ("Core/Src/eea_firmware_config.c", source),
            ("Core/Src/main.c", main),
            ("CMakeLists.txt", cmake),
            (
                "README.md",
                "\n".join(
                    [
                        "# EEA Generated Firmware Candidate",
                        "",
                        f"- MCUConfigIR: `{identifier}` revision `{config.revision}`",
                        f"- Input hash: `{input_hash}`",
                        f"- Build system: `{target.build_system}`",
                        "",
                    ]
                ),
            ),
        ]
        if target.build_system.upper() == "PLATFORMIO":
            files.append(
                (
                    "platformio.ini",
                    "\n".join(
                        [
                            "; Generated by EEA M12; candidate build adapter.",
                            "\n".join(
                                [
                                    "[env:eea]",
                                    "platform = native",
                                    "build_type = debug",
                                    "build_src_filter = +<Core/Src>",
                                    "build_flags = -ICore/Inc",
                                ]
                            ),
                            "",
                        ]
                    ),
                )
            )
        return [
            FirmwareSourceFile(
                path=path,
                content=content,
                content_hash=_sha256_bytes(content.encode("utf-8")),
                input_hash=input_hash,
                generated_owned=True,
                generator_version=self.generator_version,
            )
            for path, content in sorted(files)
        ]

    def _device_source_files(
        self,
        config: MCUConfigIR,
        target: FirmwareBuildTarget,
        input_hash: str,
        dependency_lock: DependencyLock | None,
    ) -> list[FirmwareSourceFile]:
        if dependency_lock is None:
            raise EngineeringError(
                EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
                "DEVICE source generation requires a locked dependency closure.",
            )
        dependency_files = sorted(
            {path for component in dependency_lock.resolved_components for path in component.files}
        )
        linker_files = [path for path in dependency_files if path.lower().endswith(".ld")]
        if not linker_files:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_BUILD_UNAVAILABLE,
                "Locked DEVICE dependency closure does not contain a linker script.",
            )
        header = "\n".join(
            [
                "/* Generated by EEA M12A; do not edit as source-of-truth. */",
                "#pragma once",
                '#include "stm32g4xx_hal.h"',
                "",
                f'#define EEA_MCU_CONFIG_ID "{config.id}"',
                f"#define EEA_MCU_CONFIG_REVISION {config.revision}",
                f'#define EEA_HARDWARE_IR_ID "{config.hardware_ir_id}"',
                f'#define EEA_CIRCUIT_IR_ID "{config.circuit_id}"',
                f'#define EEA_SCHEMATIC_IR_ID "{config.schematic_id}"',
                "",
                "void eea_firmware_init(void);",
                "void Error_Handler(void);",
                "",
            ]
        )
        if self._freertos_profile(config) is not None:
            header = header.replace(
                '#include "stm32g4xx_hal.h"',
                "\n".join(
                    [
                        '#include "stm32g4xx_hal.h"',
                        '#include "FreeRTOS.h"',
                        '#include "task.h"',
                        '#include "queue.h"',
                        '#include "semphr.h"',
                    ]
                ),
            )
        source_lines = [
            "/* Generated by EEA M12A; deterministic STM32 HAL realization. */",
            '#include "eea_firmware_config.h"',
            "",
            "void Error_Handler(void) {",
            "    __disable_irq();",
            "    while (1) {",
            "    }",
            "}",
            "",
            "static void eea_clock_init(void) {",
            "    RCC_OscInitTypeDef osc = {0};",
            "    RCC_ClkInitTypeDef clocks = {0};",
            "    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;",
            "    osc.HSIState = RCC_HSI_ON;",
            "    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;",
            "    osc.PLL.PLLState = RCC_PLL_NONE;",
            "    if (HAL_RCC_OscConfig(&osc) != HAL_OK) Error_Handler();",
            "    clocks.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK "
            "| RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;",
            "    clocks.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;",
            "    clocks.AHBCLKDivider = RCC_SYSCLK_DIV1;",
            "    clocks.APB1CLKDivider = RCC_HCLK_DIV1;",
            "    clocks.APB2CLKDivider = RCC_HCLK_DIV1;",
            "    if (HAL_RCC_ClockConfig(&clocks, FLASH_LATENCY_0) != HAL_OK) Error_Handler();",
            "}",
            "",
        ]
        rtos_profile = self._freertos_profile(config)
        if rtos_profile is not None:
            source_lines.extend(self._freertos_source_lines(rtos_profile))
        source_lines.extend(self._device_gpio_lines(config))
        source_lines.extend(self._device_peripheral_lines(config))
        source_lines.extend(
            [
                "void eea_firmware_init(void) {",
                "    HAL_Init();",
                "    eea_clock_init();",
                "    eea_gpio_init();",
            ]
        )
        for peripheral in sorted(config.peripherals, key=lambda value: value.instance):
            function_name = f"eea_{_identifier(peripheral.instance)}_init"
            if peripheral.instance.upper().startswith(
                ("TIM", "ADC", "FDCAN", "DMA", "USART", "UART", "SPI")
            ):
                source_lines.append(f"    {function_name}();")
        if rtos_profile is not None:
            source_lines.extend(self._freertos_start_lines(rtos_profile))
        source_lines.extend(["}", ""])
        for interrupt in sorted(config.interrupts, key=lambda value: (value.priority, value.irq)):
            handler = f"eea_{_identifier(interrupt.source)}_irq_handler"
            vector_handler = _identifier(interrupt.irq) + "_IRQHandler"
            source_lines.extend(
                [
                    f"void {handler}(void) {{",
                    "    HAL_IncTick();",
                    "}",
                    "",
                    f"void {vector_handler}(void) {{",
                    f"    {handler}();",
                    "}",
                    "",
                ]
            )
        source = "\n".join(source_lines)
        main = "\n".join(
            [
                "/* Generated by EEA M12A; deterministic STM32 entry point. */",
                '#include "eea_firmware_config.h"',
                "",
                "int main(void) {",
                "    eea_firmware_init();",
                "    for (;;) {",
                "    }",
                "}",
                "",
            ]
        )
        source_paths = [
            f"components/{path}"
            for path in dependency_files
            if path.lower().endswith((".c", ".s", ".S"))
            and not path.lower().endswith("_template.c")
        ]
        include_paths = sorted(
            {
                f"components/{path.rsplit('/', 1)[0]}"
                for path in dependency_files
                if path.lower().endswith(".h") and "/" in path
            }
        )
        defines = {"USE_HAL_DRIVER": "", "STM32G431xx": "", **target.defines}
        compile_flags = [
            "-mcpu=cortex-m4",
            "-mthumb",
            "-mfloat-abi=soft",
            "-ffunction-sections",
            "-fdata-sections",
            *target.compiler_flags,
        ]
        linker = f"components/{linker_files[0]}".replace("\\", "/")
        link_flags = [
            f"-T${{CMAKE_SOURCE_DIR}}/{linker}",
            "-Wl,--gc-sections",
            *target.linker_flags,
        ]
        hal_conf = "\n".join(
            [
                "/* Generated EEA STM32G4 HAL module selection. */",
                "#pragma once",
                "#define HAL_MODULE_ENABLED",
                "#define HAL_RCC_MODULE_ENABLED",
                "#define HAL_GPIO_MODULE_ENABLED",
                "#define HAL_DMA_MODULE_ENABLED",
                "#define HAL_ADC_MODULE_ENABLED",
                "#define HAL_TIM_MODULE_ENABLED",
                "#define HAL_FDCAN_MODULE_ENABLED",
                "#define HAL_UART_MODULE_ENABLED",
                "#define HAL_SPI_MODULE_ENABLED",
                "#define HAL_CORTEX_MODULE_ENABLED",
                "#define HAL_FLASH_MODULE_ENABLED",
                "#define HAL_PWR_MODULE_ENABLED",
                "#define TICK_INT_PRIORITY 0U",
                "#define USE_RTOS 0U",
                "#define PREFETCH_ENABLE 0U",
                "#define INSTRUCTION_CACHE_ENABLE 1U",
                "#define DATA_CACHE_ENABLE 1U",
                "#define VDD_VALUE 3300U",
                "#define HSE_VALUE 24000000U",
                "#define HSE_STARTUP_TIMEOUT 100U",
                "#define HSI_VALUE 16000000U",
                "#define HSI48_VALUE 48000000U",
                "#define LSI_VALUE 32000U",
                "#define LSE_VALUE 32768U",
                "#define LSE_STARTUP_TIMEOUT 5000U",
                "#define EXTERNAL_CLOCK_VALUE 12288000U",
                "#define USE_SPI_CRC 0U",
                '#include "stm32g4xx_hal_def.h"',
                '#include "stm32g4xx_hal_rcc.h"',
                '#include "stm32g4xx_hal_gpio.h"',
                '#include "stm32g4xx_hal_dma.h"',
                '#include "stm32g4xx_hal_adc.h"',
                '#include "stm32g4xx_hal_tim.h"',
                '#include "stm32g4xx_hal_fdcan.h"',
                '#include "stm32g4xx_hal_uart.h"',
                '#include "stm32g4xx_hal_spi.h"',
                '#include "stm32g4xx_hal_cortex.h"',
                '#include "stm32g4xx_hal_flash.h"',
                '#include "stm32g4xx_hal_pwr.h"',
                "#ifndef assert_param",
                "#define assert_param(expr) ((void)0U)",
                "#endif",
                "",
            ]
        )
        define_lines = [
            f"    {key}{('=' + value) if value else ''}" for key, value in sorted(defines.items())
        ]
        cmake_lines = [
            "# Generated by EEA M12A; pinned STM32G431 DEVICE adapter.",
            "cmake_minimum_required(VERSION 3.20)",
            "set(CMAKE_SYSTEM_NAME Generic)",
            "set(CMAKE_SYSTEM_PROCESSOR arm)",
            "set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)",
            "set(CMAKE_C_COMPILER arm-none-eabi-gcc)",
            "set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)",
            "project(eea_device C ASM)",
            f"add_executable({target.output_name}",
            "    Core/Src/main.c",
            "    Core/Src/eea_firmware_config.c",
            *[f"    {path}" for path in source_paths],
            ")",
            f"target_include_directories({target.output_name} PRIVATE",
            "    Core/Inc",
            *[f"    {path}" for path in include_paths],
            ")",
            f"target_compile_definitions({target.output_name} PRIVATE",
            *define_lines,
            ")",
            f"target_compile_options({target.output_name} PRIVATE {' '.join(compile_flags)})",
            f"target_link_options({target.output_name} PRIVATE {' '.join(link_flags)})",
            f'set_target_properties({target.output_name} PROPERTIES SUFFIX ".elf")',
            "",
        ]
        files = [
            ("Core/Inc/eea_firmware_config.h", header),
            ("Core/Inc/stm32g4xx_hal_conf.h", hal_conf),
            ("Core/Src/eea_firmware_config.c", source),
            ("Core/Src/main.c", main),
            ("CMakeLists.txt", "\n".join(cmake_lines)),
            (
                "README.md",
                "\n".join(
                    [
                        "# EEA STM32G431 DEVICE Firmware",
                        "",
                        f"- MCUConfigIR: `{config.id}` revision `{config.revision}`",
                        f"- DependencyLock: `{dependency_lock.lock_hash}`",
                        f"- Target triple: `{target.target_triple}`",
                        f"- Linker script: `{linker}`",
                        "",
                    ]
                ),
            ),
        ]
        if rtos_profile is not None:
            files.append(("Core/Inc/FreeRTOSConfig.h", self._freertos_config_header()))
        return [
            FirmwareSourceFile(
                path=path,
                content=content,
                content_hash=_sha256_bytes(content.encode("utf-8")),
                input_hash=input_hash,
                generated_owned=True,
                generator_version=self.generator_version,
            )
            for path, content in sorted(files)
        ]

    @staticmethod
    def _device_gpio_lines(config: MCUConfigIR) -> list[str]:
        valid_gpio: list[tuple[GPIOConfig, str, str]] = []
        for gpio_config in sorted(config.gpio, key=lambda value: value.signal_ref):
            match = re.fullmatch(r"P([A-K])(\d{1,2})", gpio_config.signal_ref.upper())
            if match is not None:
                valid_gpio.append((gpio_config, match.group(1), match.group(2)))
        if not valid_gpio:
            return ["static void eea_gpio_init(void) {", "}", ""]

        lines = ["static void eea_gpio_init(void) {", "    GPIO_InitTypeDef gpio = {0};"]
        initialized_ports: set[str] = set()
        for gpio_config, port, pin in valid_gpio:
            if port not in initialized_ports:
                lines.append(f"    __HAL_RCC_GPIO{port}_CLK_ENABLE();")
                initialized_ports.add(port)
            mode = {
                "INPUT": "GPIO_MODE_INPUT",
                "OUTPUT": "GPIO_MODE_OUTPUT_PP",
                "ALTERNATE": "GPIO_MODE_AF_PP",
                "ANALOG": "GPIO_MODE_ANALOG",
            }.get(gpio_config.mode.upper(), "GPIO_MODE_INPUT")
            pull = {
                "UP": "GPIO_PULLUP",
                "DOWN": "GPIO_PULLDOWN",
                "NONE": "GPIO_NOPULL",
            }.get((gpio_config.pull or "NONE").upper(), "GPIO_NOPULL")
            speed = {
                "LOW": "GPIO_SPEED_FREQ_LOW",
                "MEDIUM": "GPIO_SPEED_FREQ_MEDIUM",
                "HIGH": "GPIO_SPEED_FREQ_HIGH",
                "VERY_HIGH": "GPIO_SPEED_FREQ_VERY_HIGH",
            }.get((gpio_config.speed or "LOW").upper(), "GPIO_SPEED_FREQ_LOW")
            alternate = gpio_config.alternate_function or "0"
            if re.fullmatch(r"GPIO_AF[0-9]+_[A-Za-z0-9_]+", alternate) is None:
                alternate = "0"
            lines.extend(
                [
                    f"    gpio.Pin = GPIO_PIN_{pin};",
                    f"    gpio.Mode = {mode};",
                    f"    gpio.Pull = {pull};",
                    f"    gpio.Speed = {speed};",
                    f"    gpio.Alternate = {alternate};",
                    f"    HAL_GPIO_Init(GPIO{port}, &gpio);",
                ]
            )
        lines.extend(["}", ""])
        return lines

    @staticmethod
    def _device_peripheral_lines(config: MCUConfigIR) -> list[str]:
        lines: list[str] = []
        supported = {
            "TIM": ("TIM_HandleTypeDef", "HAL_TIM_Base_Init"),
            "ADC": ("ADC_HandleTypeDef", "HAL_ADC_Init"),
            "FDCAN": ("FDCAN_HandleTypeDef", "HAL_FDCAN_Init"),
            "DMA": ("DMA_HandleTypeDef", "HAL_DMA_Init"),
            "USART": ("UART_HandleTypeDef", "HAL_UART_Init"),
            "UART": ("UART_HandleTypeDef", "HAL_UART_Init"),
            "SPI": ("SPI_HandleTypeDef", "HAL_SPI_Init"),
        }
        supported_items = [
            peripheral
            for peripheral in sorted(config.peripherals, key=lambda value: value.instance)
            if next(
                (
                    item
                    for key, item in supported.items()
                    if peripheral.instance.upper().startswith(key)
                ),
                None,
            )
        ]
        for peripheral in supported_items:
            kind, init = next(
                item
                for key, item in supported.items()
                if peripheral.instance.upper().startswith(key)
            )
            identifier = _identifier(peripheral.instance)
            lines.append(f"static {kind} h{identifier};")
            lines.extend(
                [
                    f"static void eea_{identifier}_init(void) {{",
                    f"    h{identifier}.Instance = {peripheral.instance.upper()};",
                    f"    if ({init}(&h{identifier}) != HAL_OK) Error_Handler();",
                    "}",
                    "",
                ]
            )
        return lines

    @staticmethod
    def _freertos_profile(config: MCUConfigIR) -> dict[str, object] | None:
        value = config.capability_snapshot.get("rtos_profile")
        if not isinstance(value, dict) or str(value.get("name", "")) != "FreeRTOS":
            return None
        return value

    @staticmethod
    def _freertos_tasks(profile: dict[str, object]) -> list[dict[str, object]]:
        value = profile.get("tasks", [])
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _profile_int(value: object, default: int | None = None) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _profile_strings(value: object) -> list[str]:
        return [str(item) for item in value] if isinstance(value, list) else []

    @classmethod
    def _tasks(cls, config: MCUConfigIR) -> list[FirmwareTask]:
        profile = cls._freertos_profile(config)
        if profile is None:
            return [FirmwareTask(name="main", priority=0, resources=["mcu_config"])]
        tasks: list[FirmwareTask] = []
        raw_tasks = FirmwareService._freertos_tasks(profile)
        if isinstance(raw_tasks, list):
            for raw in raw_tasks:
                if not isinstance(raw, dict) or not raw.get("name"):
                    continue
                tasks.append(
                    FirmwareTask(
                        name=str(raw["name"]),
                        period_us=cls._profile_int(raw.get("period_us")),
                        deadline_us=cls._profile_int(raw.get("deadline_us")),
                        priority=cls._profile_int(raw.get("priority"), 1),
                        stack_bytes=cls._profile_int(raw.get("stack_bytes"), 512),
                        execution_budget_us=(cls._profile_int(raw.get("execution_budget_us"))),
                        queues=cls._profile_strings(raw.get("queues")),
                        mutexes=cls._profile_strings(raw.get("mutexes")),
                        resources=cls._profile_strings(raw.get("resources")),
                    )
                )
        return tasks or [FirmwareTask(name="main", priority=0, resources=["mcu_config"])]

    @staticmethod
    def _freertos_source_lines(profile: dict[str, object]) -> list[str]:
        raw_tasks = FirmwareService._freertos_tasks(profile)
        tasks = [item for item in raw_tasks if item.get("name")]
        queue_names = sorted(
            {
                str(queue)
                for item in tasks
                for queue in FirmwareService._profile_strings(item.get("queues"))
            }
        )
        mutex_names = sorted(
            {
                str(mutex)
                for item in tasks
                for mutex in FirmwareService._profile_strings(item.get("mutexes"))
            }
        )
        lines = ["/* Generated FreeRTOS application profile from MCUConfigIR. */"]
        lines.extend(
            f"static TaskHandle_t eea_task_{_identifier(str(item['name']))};" for item in tasks
        )
        lines.extend(f"static QueueHandle_t eea_queue_{_identifier(name)};" for name in queue_names)
        lines.extend(
            f"static SemaphoreHandle_t eea_mutex_{_identifier(name)};" for name in mutex_names
        )
        lines.append("")
        for item in tasks:
            name = _identifier(str(item["name"]))
            period_us = FirmwareService._profile_int(item.get("period_us"), 10000) or 10000
            delay_ms = max(1, period_us // 1000)
            lines.extend(
                [
                    f"static void eea_task_{name}_entry(void *argument) {{",
                    "    (void)argument;",
                    "    for (;;) {",
                    f"        vTaskDelay(pdMS_TO_TICKS({delay_ms}U));",
                    "    }",
                    "}",
                    "",
                ]
            )
        return lines

    @staticmethod
    def _freertos_start_lines(profile: dict[str, object]) -> list[str]:
        tasks = [item for item in FirmwareService._freertos_tasks(profile) if item.get("name")]
        queue_names = sorted(
            {
                str(queue)
                for item in tasks
                for queue in FirmwareService._profile_strings(item.get("queues"))
            }
        )
        mutex_names = sorted(
            {
                str(mutex)
                for item in tasks
                for mutex in FirmwareService._profile_strings(item.get("mutexes"))
            }
        )
        lines: list[str] = []
        lines.extend(
            f"    eea_queue_{_identifier(name)} = xQueueCreate(8, sizeof(uint32_t));"
            for name in queue_names
        )
        lines.extend(
            f"    eea_mutex_{_identifier(name)} = xSemaphoreCreateMutex();" for name in mutex_names
        )
        for item in tasks:
            name = _identifier(str(item["name"]))
            priority = FirmwareService._profile_int(item.get("priority"), 1) or 1
            stack_bytes = FirmwareService._profile_int(item.get("stack_bytes"), 512) or 512
            stack_words = max(128, stack_bytes // 4)
            lines.append(
                f'    xTaskCreate(eea_task_{name}_entry, "{name[:15]}", '
                f"{stack_words}U, NULL, {priority}U, &eea_task_{name});"
            )
        lines.extend(["    vTaskStartScheduler();"])
        return lines

    @staticmethod
    def _freertos_config_header() -> str:
        return "\n".join(
            [
                "#pragma once",
                "#define configUSE_PREEMPTION 1",
                "#define configUSE_IDLE_HOOK 0",
                "#define configUSE_TICK_HOOK 0",
                "#define configCPU_CLOCK_HZ (16000000UL)",
                "#define configTICK_RATE_HZ ((TickType_t)1000)",
                "#define configMAX_PRIORITIES 8",
                "#define configMINIMAL_STACK_SIZE 128",
                "#define configTOTAL_HEAP_SIZE ((size_t)(8 * 1024))",
                "#define configMAX_TASK_NAME_LEN 16",
                "#define configUSE_16_BIT_TICKS 0",
                "#define configIDLE_SHOULD_YIELD 1",
                "#define configUSE_MUTEXES 1",
                "#define configUSE_RECURSIVE_MUTEXES 1",
                "#define configUSE_COUNTING_SEMAPHORES 1",
                "#define configUSE_TIMERS 0",
                "#define configSUPPORT_DYNAMIC_ALLOCATION 1",
                "#define configSUPPORT_STATIC_ALLOCATION 0",
                "#define INCLUDE_vTaskDelay 1",
                "#define configPRIO_BITS 4",
                "#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY 15",
                "#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 5",
                "#define configKERNEL_INTERRUPT_PRIORITY "
                "(configLIBRARY_LOWEST_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))",
                "#define configMAX_SYSCALL_INTERRUPT_PRIORITY "
                "(configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))",
                "#define configASSERT(x) if ((x) == 0) { taskDISABLE_INTERRUPTS(); for (;;) {} }",
                "#define vPortSVCHandler SVC_Handler",
                "#define xPortPendSVHandler PendSV_Handler",
                "#define xPortSysTickHandler SysTick_Handler",
                "#define configSYSTICK_CLOCK_HZ (configCPU_CLOCK_HZ)",
                "#define configEXPECTED_IDLE_TIME_BEFORE_SLEEP 2",
                "",
            ]
        )

    @staticmethod
    def _drivers(config: MCUConfigIR) -> list[PeripheralDriverConfig]:
        return [
            PeripheralDriverConfig(
                peripheral=peripheral.instance,
                driver_name=f"eea_{_identifier(peripheral.instance)}_driver",
                init_function=f"eea_{_identifier(peripheral.instance)}_init",
                config_refs=[f"mcu_config:{config.id}"],
                dependencies=sorted({f"dma:{value}" for value in peripheral.dma_refs}),
            )
            for peripheral in sorted(config.peripherals, key=lambda value: value.instance)
        ]

    @staticmethod
    def _interrupts(config: MCUConfigIR) -> list[FirmwareInterrupt]:
        return [
            FirmwareInterrupt(
                source=interrupt.source,
                handler=f"eea_{_identifier(interrupt.source)}_irq_handler",
                priority=interrupt.priority,
                allowed_operations=list(interrupt.allowed_operations),
                communicates_with_tasks=list(interrupt.communicates_with_tasks),
            )
            for interrupt in sorted(
                config.interrupts, key=lambda value: (value.priority, value.irq)
            )
        ]

    @staticmethod
    def _modules(
        config: MCUConfigIR,
        drivers: Sequence[PeripheralDriverConfig],
        interrupts: Sequence[FirmwareInterrupt],
    ) -> list[FirmwareModule]:
        modules = [
            FirmwareModule(
                name="startup",
                layer="STARTUP",
                responsibility="Reset and system initialization entry points.",
                public_api=["Reset_Handler", "SystemInit"],
                testability=["host-smoke"],
                requirement_ids=list(config.requirement_ids),
                evidence_ids=list(config.evidence_ids),
            ),
            FirmwareModule(
                name="bsp",
                layer="BSP",
                responsibility="Board support and MCU configuration boundary.",
                public_api=["eea_firmware_init"],
                dependencies=[driver.driver_name for driver in drivers],
                testability=["host-smoke", "hal-adapter"],
                requirement_ids=list(config.requirement_ids),
                evidence_ids=list(config.evidence_ids),
            ),
        ]
        modules.extend(
            FirmwareModule(
                name=driver.driver_name,
                layer="HAL",
                responsibility=f"Initialize {driver.peripheral} from MCUConfigIR.",
                public_api=[driver.init_function],
                dependencies=list(driver.dependencies),
                testability=["host-smoke", "hal-adapter"],
                requirement_ids=list(config.requirement_ids),
                evidence_ids=list(config.evidence_ids),
            )
            for driver in drivers
        )
        if interrupts:
            modules.append(
                FirmwareModule(
                    name="interrupts",
                    layer="HAL",
                    responsibility=(
                        "Dispatch configured interrupt sources without changing priorities."
                    ),
                    public_api=sorted(item.handler for item in interrupts),
                    testability=["interrupt-vector-review"],
                    requirement_ids=list(config.requirement_ids),
                    evidence_ids=list(config.evidence_ids),
                )
            )
        return modules

    @staticmethod
    def _shared_resources(config: MCUConfigIR) -> list[SharedResource]:
        return [
            SharedResource(
                name=f"dma:{item.request}",
                kind="DMA",
                users=[item.request],
                protection="configuration-immutable",
            )
            for item in sorted(config.dma, key=lambda value: str(value.id))
        ]


class FirmwareBuildService:
    """Materialize only generated candidates inside a sandbox and run an allowlisted build."""

    def __init__(self, executor: StructuredCommandExecutor | None = None) -> None:
        self._executor = executor or StructuredCommandExecutor()

    def build(
        self,
        bundle: FirmwareBundle,
        workspace_root: Path,
        *,
        environment_profile: dict[str, str] | None = None,
        component_cache_root: Path | None = None,
        evidence_root: Path | None = None,
    ) -> tuple[BuildInputSnapshot, BuildRun]:
        workspace_root.mkdir(parents=True, exist_ok=True)
        unknown_rules = [
            result.rule_id for result in bundle.firmware.rule_results if result.status == "UNKNOWN"
        ]
        environment = environment_profile or {
            "os": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }
        toolchain_id = bundle.firmware.build_target.toolchain_id
        executable = self._executable(bundle.firmware.build_target)
        toolchain_executable = self._toolchain_executable(bundle.firmware.build_target)
        toolchain_version = "UNKNOWN"
        build_config_hash = _hash_json(bundle.firmware.build_target.model_dump(mode="json"))
        environment_hash = _hash_json(environment)
        snapshot = self._snapshot(
            bundle,
            build_config_hash=build_config_hash,
            toolchain_id=toolchain_id,
            toolchain_version=toolchain_version,
            environment_hash=environment_hash,
        )
        if unknown_rules:
            diagnostic = self._diagnostic(
                bundle.firmware.project_id,
                "MCU_CONFIG_UNKNOWN",
                "Build is blocked because MCUConfigIR contains UNKNOWN rule results.",
                "TOOLCHAIN",
            )
            return snapshot, self._run(
                bundle,
                snapshot,
                BuildStatus.BLOCKED,
                toolchain_id,
                toolchain_version,
                environment_hash,
                [diagnostic],
                duration_ms=0,
            )

        started_at = datetime.now(UTC)
        with tempfile.TemporaryDirectory(dir=workspace_root) as temporary:
            workspace = SandboxWorkspace.from_root(Path(temporary))
            self._materialize(bundle.files, workspace)
            if bundle.firmware.build_target.profile is BuildProfile.DEVICE:
                try:
                    self._materialize_dependencies(bundle, workspace, component_cache_root)
                except EngineeringError as error:
                    diagnostic = self._diagnostic(
                        bundle.firmware.project_id,
                        error.code.value,
                        error.message,
                        "TOOLCHAIN",
                    )
                    return snapshot, self._run(
                        bundle,
                        snapshot,
                        BuildStatus.BLOCKED,
                        toolchain_id,
                        toolchain_version,
                        environment_hash,
                        [diagnostic],
                    )
            policy = SandboxPolicy(
                # The sandbox authorizes canonical executable identities, never basenames.
                allowed_executables=tuple(
                    sorted(
                        {
                            resolved
                            for name in {executable, toolchain_executable}
                            if (resolved := shutil.which(name)) is not None
                        }
                    )
                ),
                # CMake must be able to start its generator (and Ninja must be
                # able to start one compiler process). Keep the boundary finite
                # while allowing the DEVICE toolchain's required subprocesses.
                max_processes=64,
                network_access=release_tool_policy_network_access(),
            )
            try:
                version = self._executor.execute(
                    self._command_spec((toolchain_executable, "--version"), workspace.root),
                    workspace.root,
                    policy,
                )
                toolchain_version = version.stdout.splitlines()[0].strip() or "UNKNOWN"
                snapshot = self._snapshot(
                    bundle,
                    build_config_hash=build_config_hash,
                    toolchain_id=toolchain_id,
                    toolchain_version=toolchain_version,
                    environment_hash=environment_hash,
                )
                configure, command = self._commands(bundle.firmware.build_target)
                configure_result = self._executor.execute(
                    self._command_spec(configure, workspace.root), workspace.root, policy
                )
                if configure_result.returncode != 0:
                    return snapshot, self._run(
                        bundle,
                        snapshot,
                        BuildStatus.FAIL,
                        toolchain_id,
                        toolchain_version,
                        environment_hash,
                        [
                            self._diagnostic(
                                bundle.firmware.project_id,
                                "BUILD_CONFIGURE_FAILED",
                                configure_result.stderr
                                or configure_result.stdout
                                or "Configure failed.",
                                "CONFIGURE",
                            )
                        ],
                        stdout=configure_result.stdout,
                        stderr=configure_result.stderr,
                        command=list(configure),
                        duration_ms=version.duration_ms + configure_result.duration_ms,
                    )
                result = self._executor.execute(
                    self._command_spec(command, workspace.root), workspace.root, policy
                )
                status = BuildStatus.PASS if result.returncode == 0 else BuildStatus.FAIL
                diagnostics = (
                    []
                    if status is BuildStatus.PASS
                    else [
                        self._diagnostic(
                            bundle.firmware.project_id,
                            "BUILD_FAILED",
                            result.stderr or result.stdout or "Build failed.",
                            "COMPILE",
                        )
                    ]
                )
                artifact_path = self._artifact_path(workspace, bundle.firmware.build_target)
                artifact_hash = (
                    _sha256_bytes(artifact_path.read_bytes()) if artifact_path is not None else None
                )
                if status is BuildStatus.PASS and artifact_hash is None:
                    diagnostics.append(
                        self._diagnostic(
                            bundle.firmware.project_id,
                            "BUILD_ARTIFACT_MISSING",
                            "Build passed but the expected output artifact was not found.",
                            "ARTIFACT",
                        )
                    )
                    status = BuildStatus.UNKNOWN
                duration_ms = (
                    version.duration_ms + configure_result.duration_ms + result.duration_ms
                )
                build_run = self._run(
                    bundle,
                    snapshot,
                    status,
                    toolchain_id,
                    toolchain_version,
                    environment_hash,
                    diagnostics,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    command=list(command),
                    artifact_hash=artifact_hash,
                    duration_ms=duration_ms,
                )
                if evidence_root is not None and artifact_path is not None:
                    self._write_build_evidence(
                        evidence_root,
                        build_run,
                        workspace.root,
                        artifact_path,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        exit_code=result.returncode,
                        configure_command=list(configure),
                        build_command=list(command),
                    )
                return snapshot, build_run
            except EngineeringError as error:
                if error.code not in {
                    EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                    EngineeringErrorCode.TOOL_UNAVAILABLE,
                    EngineeringErrorCode.COMMAND_NOT_ALLOWED,
                }:
                    raise
                diagnostic = self._diagnostic(
                    bundle.firmware.project_id,
                    "TOOL_UNAVAILABLE",
                    error.message,
                    "TOOLCHAIN",
                )
                return snapshot, self._run(
                    bundle,
                    snapshot,
                    BuildStatus.UNKNOWN,
                    toolchain_id,
                    toolchain_version,
                    environment_hash,
                    [diagnostic],
                    duration_ms=0,
                )

    @staticmethod
    def _snapshot(
        bundle: FirmwareBundle,
        *,
        build_config_hash: str,
        toolchain_id: str,
        toolchain_version: str,
        environment_hash: str,
    ) -> BuildInputSnapshot:
        generated_manifest = {
            item.path: item.content_hash
            for item in sorted(bundle.files, key=lambda value: value.path)
        }
        generated_hash = _hash_json(generated_manifest)
        tracked_hash = _empty_hash()
        allowed_hash = _empty_hash()
        dependency_hash = bundle.firmware.dependency_lock_hash or _empty_hash()
        component_manifest = _hash_json(
            sorted(bundle.firmware.component_refs)
            if not bundle.dependency_lock
            else [
                {
                    "component_key": item.component_key,
                    "version": item.version,
                    "revision": item.revision,
                    "manifest_hash": item.manifest_hash,
                    "content_hash": item.content_hash,
                }
                for item in sorted(
                    bundle.dependency_lock.resolved_components,
                    key=lambda value: value.component_key,
                )
            ]
        )
        build_input_hash = _hash_json(
            {
                "tracked_file_manifest_hash": tracked_hash,
                "allowed_untracked_input_hash": allowed_hash,
                "generated_input_hash": generated_hash,
                "submodule_commit_map": {},
                "build_config_hash": build_config_hash,
                "toolchain_id": toolchain_id,
                "toolchain_version": toolchain_version,
                "environment_profile_hash": environment_hash,
                "source_manifest_hash": bundle.source_revision.source_manifest_hash,
                "dependency_lock_hash": dependency_hash,
                "component_manifest_hash": component_manifest,
                "build_profile": bundle.firmware.build_target.profile.value,
            }
        )
        return BuildInputSnapshot(
            project_id=bundle.firmware.project_id,
            source_revision_id=bundle.source_revision.id,
            tracked_file_manifest_hash=tracked_hash,
            allowed_untracked_input_hash=allowed_hash,
            generated_input_hash=generated_hash,
            build_config_hash=build_config_hash,
            build_profile=bundle.firmware.build_target.profile,
            toolchain_id=toolchain_id,
            toolchain_version=toolchain_version,
            environment_profile_hash=environment_hash,
            source_manifest_hash=bundle.source_revision.source_manifest_hash,
            dependency_lock_hash=dependency_hash,
            component_manifest_hash=component_manifest,
            build_input_hash=build_input_hash,
        )

    @staticmethod
    def _materialize(files: Sequence[FirmwareSourceFile], workspace: SandboxWorkspace) -> None:
        for item in files:
            target = workspace.path(item.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="") as stream:
                stream.write(item.content)

    @staticmethod
    def _materialize_dependencies(
        bundle: FirmwareBundle,
        workspace: SandboxWorkspace,
        component_cache_root: Path | None,
    ) -> None:
        if bundle.dependency_lock is None or component_cache_root is None:
            raise EngineeringError(
                EngineeringErrorCode.DEVICE_BUILD_UNAVAILABLE,
                "DEVICE build requires a pre-materialized offline component cache.",
            )
        cache_root = component_cache_root.resolve(strict=False)
        for component in bundle.dependency_lock.resolved_components:
            source_root = cache_root / component.content_hash / component.manifest_hash
            if not source_root.is_dir():
                raise EngineeringError(
                    EngineeringErrorCode.DEVICE_BUILD_UNAVAILABLE,
                    "Required component is not materialized in the offline cache.",
                    details={"component_key": component.component_key},
                )
            for relative in component.files:
                source = (source_root / relative).resolve(strict=False)
                try:
                    source.relative_to(source_root)
                except ValueError as error:
                    raise EngineeringError(
                        EngineeringErrorCode.SANDBOX_VIOLATION,
                        "Component manifest escapes its materialization root.",
                        details={"path": relative},
                    ) from error
                if not source.is_file():
                    raise EngineeringError(
                        EngineeringErrorCode.DEVICE_BUILD_UNAVAILABLE,
                        "Materialized component file is missing.",
                        details={"path": relative},
                    )
                target = workspace.path(f"components/{relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

    @staticmethod
    def _executable(target: FirmwareBuildTarget) -> str:
        return "cmake"

    @staticmethod
    def _toolchain_executable(target: FirmwareBuildTarget) -> str:
        if target.profile is BuildProfile.DEVICE:
            return "arm-none-eabi-gcc"
        return "cmake"

    @staticmethod
    def _command_spec(argv: Sequence[str], workspace: Path) -> CommandSpec:
        """Keep compiler temporary files inside the isolated build workspace."""
        return CommandSpec(
            argv=tuple(argv),
            environment={"TEMP": str(workspace), "TMP": str(workspace)},
        )

    @staticmethod
    def _commands(target: FirmwareBuildTarget) -> tuple[tuple[str, ...], tuple[str, ...]]:
        generator = ("-G", "Ninja") if target.profile is BuildProfile.DEVICE else ()
        return (
            "cmake",
            *generator,
            "-S",
            ".",
            "-B",
            "build",
        ), (
            "cmake",
            "--build",
            "build",
            "--parallel",
            "1",
        )

    @staticmethod
    def _artifact_path(workspace: SandboxWorkspace, target: FirmwareBuildTarget) -> Path | None:
        candidates = [workspace.path(f"build/{target.output_name}")]
        if target.profile is BuildProfile.DEVICE:
            candidates.append(workspace.path(f"build/{target.output_name}.elf"))
        if platform.system() == "Windows":
            candidates.append(workspace.path(f"build/{target.output_name}.exe"))
        for candidate in candidates:
            if candidate.is_file():
                content = candidate.read_bytes()
                if target.profile is BuildProfile.DEVICE and not FirmwareBuildService._is_arm_elf(
                    content
                ):
                    continue
                return candidate
        return None

    @staticmethod
    def _artifact_hash(workspace: SandboxWorkspace, target: FirmwareBuildTarget) -> str | None:
        artifact = FirmwareBuildService._artifact_path(workspace, target)
        return _sha256_bytes(artifact.read_bytes()) if artifact is not None else None

    @staticmethod
    def _write_build_evidence(
        evidence_root: Path,
        build_run: BuildRun,
        working_directory: Path,
        artifact_path: Path,
        *,
        started_at: datetime,
        finished_at: datetime,
        exit_code: int,
        configure_command: list[str],
        build_command: list[str],
    ) -> None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        copied = evidence_root / artifact_path.name
        shutil.copyfile(artifact_path, copied)
        payload = {
            "build_run_id": str(build_run.id),
            "project_id": str(build_run.project_id),
            "firmware_id": str(build_run.firmware_id),
            "source_revision_id": str(build_run.source_revision_id),
            "build_input_snapshot_id": str(build_run.build_input_snapshot_id),
            "build_input_hash": build_run.build_input_hash,
            "profile": build_run.profile.value,
            "toolchain_id": build_run.toolchain_id,
            "toolchain_version": build_run.toolchain_version,
            "command": build_run.command,
            "configure_command": configure_command,
            "build_command": build_command,
            "working_directory": str(working_directory),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": build_run.duration_ms,
            "exit_code": exit_code,
            "artifact_path": str(copied),
            "artifact_size": copied.stat().st_size,
            "artifact_hash": build_run.artifact_hash,
            "status": build_run.status.value,
        }
        (evidence_root / "build-runtime.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    @staticmethod
    def _is_arm_elf(content: bytes) -> bool:
        return (
            len(content) >= 20
            and content[:4] == b"\x7fELF"
            and int.from_bytes(content[18:20], byteorder="little") == 0x28
        )

    @staticmethod
    def _diagnostic(project_id: UUID, code: str, message: str, phase: str) -> BuildDiagnostic:
        return BuildDiagnostic(
            project_id=project_id,
            severity=IssueSeverity.HIGH if phase != "TOOLCHAIN" else IssueSeverity.MEDIUM,
            code=code,
            message=message[:4000],
            phase=phase,  # type: ignore[arg-type]
        )

    @staticmethod
    def _run(
        bundle: FirmwareBundle,
        snapshot: BuildInputSnapshot,
        status: BuildStatus,
        toolchain_id: str,
        toolchain_version: str,
        environment_hash: str,
        diagnostics: list[BuildDiagnostic],
        *,
        stdout: str = "",
        stderr: str = "",
        command: list[str] | None = None,
        artifact_hash: str | None = None,
        duration_ms: int = 0,
    ) -> BuildRun:
        now = utc_now()
        return BuildRun(
            project_id=bundle.firmware.project_id,
            firmware_id=bundle.firmware.id,
            firmware_revision=bundle.firmware.revision,
            source_revision_id=bundle.source_revision.id,
            build_input_snapshot_id=snapshot.id,
            status=status,
            profile=bundle.firmware.build_target.profile,
            toolchain_id=toolchain_id,
            toolchain_version=toolchain_version,
            environment_profile_hash=environment_hash,
            build_input_hash=snapshot.build_input_hash,
            command=command or [],
            diagnostics=diagnostics,
            stdout=stdout[-200_000:],
            stderr=stderr[-200_000:],
            artifact_hash=artifact_hash,
            error_code=(EngineeringErrorCode.BUILD_FAILED if status is BuildStatus.FAIL else None),
            duration_ms=duration_ms,
            created_at=now,
            updated_at=now,
        )


__all__ = ["FirmwareBuildService", "FirmwareService"]
