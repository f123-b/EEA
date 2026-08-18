import type { JsonRecord } from "../api/m21";

export const M20_PROFILE_NAME = "embedded-controller-benchmark";
export const M20_PROFILE_VERSION = "1.0";

export const m20PinSpecs = [
  ["UART_TX", "USART2", "TX", "OUT"],
  ["UART_RX", "USART2", "RX", "IN"],
  ["CAN_RX", "FDCAN1", "RX", "IN"],
  ["CAN_TX", "FDCAN1", "TX", "OUT"],
  ["SPI_SCK", "SPI1", "SCK", "OUT"],
  ["SPI_MISO", "SPI1", "MISO", "IN"],
  ["SPI_MOSI", "SPI1", "MOSI", "OUT"],
  ["SPI_CS", "GPIO", "CS", "OUT"],
] as const;

export const m20EvidencePayloads: Record<string, JsonRecord> = {
  device_source: {
    evidence_type: "DEVICE_DB",
    locator: { provider: "STM32CubeG4", device_ref: "STM32G431", package: "UFQFPN48" },
    source_uri: "device://STM32G431/UFQFPN48",
    summary: "Authoritative STM32G431 package and peripheral facts",
  },
  interface_source: {
    evidence_type: "USER_CONFIRMATION",
    locator: { source: "m21-ui-benchmark", interfaces: ["USART2", "FDCAN1", "SPI1"] },
    summary: "UART, CAN, SPI and sensor interface contract",
  },
  rtos_source: {
    evidence_type: "USER_CONFIRMATION",
    locator: { source: "m21-ui-benchmark", rtos: "FreeRTOS", tasks: ["communication_task", "sensor_task", "health_task"] },
    summary: "FreeRTOS task and synchronization contract",
  },
};

export function m20RequirementPayload(projectId: string, evidenceRefs: JsonRecord = {}): JsonRecord {
  return {
    project_id: projectId,
    profile_name: M20_PROFILE_NAME,
    profile_version: M20_PROFILE_VERSION,
    values: {
      "target.device": "STM32G431",
      "target.package": "UFQFPN48",
      "interfaces.uart": "USART2",
      "interfaces.can": "FDCAN1",
      "interfaces.spi": "SPI1",
      "sensor.type": "SPI_SENSOR",
      "rtos.name": "FreeRTOS",
      "rtos.tasks": ["communication_task", "sensor_task", "health_task"],
    },
    evidence_refs: evidenceRefs,
    requirements: [
      {
        code: "M20-CTRL-001",
        title: "Generic controller interfaces",
        requirement_type: "INTERFACE",
        priority: "MUST",
        statement: "The controller shall expose UART, CAN, and SPI sensor interfaces on verified STM32G431 pins.",
        rationale: "M20 generic desktop workflow benchmark",
        acceptance_criteria: ["UART/CAN/SPI pin assignments are rule-verified"],
        source_evidence_refs: ["device_source", "interface_source", "rtos_source"],
      },
      {
        code: "M20-RTOS-001",
        title: "FreeRTOS task execution",
        requirement_type: "FUNCTIONAL",
        priority: "MUST",
        statement: "The controller firmware shall represent communication, sensor, and health FreeRTOS tasks.",
        rationale: "M20 generic desktop workflow benchmark",
        acceptance_criteria: ["FirmwareIR contains the required RTOS tasks"],
        source_evidence_refs: ["device_source", "interface_source", "rtos_source"],
      },
    ],
  };
}

export function m20PinPlanPayload(analysis: JsonRecord): JsonRecord {
  const requirementIds = Array.isArray(analysis.requirement_ids) ? analysis.requirement_ids : [];
  const requirementId = typeof requirementIds[0] === "string" ? requirementIds[0] : undefined;
  const claims = Array.isArray(analysis.claims) ? analysis.claims : [];
  const claimId = typeof (claims[0] as JsonRecord | undefined)?.id === "string" ? (claims[0] as JsonRecord).id : undefined;
  return {
    analysis_id: analysis.id,
    device_ref: "STM32G431",
    package: "UFQFPN48",
    requirements: m20PinSpecs.map(([signal_name, required_peripheral, required_function, direction]) => ({
      signal_name,
      required_peripheral,
      required_function,
      direction,
      ...(requirementId ? { requirement_ids: [requirementId] } : {}),
      ...(claimId ? { claim_ids: [claimId] } : {}),
    })),
  };
}

export function m20CircuitPayload(hardware: JsonRecord, requirementId?: string): JsonRecord {
  const components = [
    { reference: "MCU", kind: "MCU", device_ref: "STM32G431", package: "UFQFPN48" },
    { reference: "U1", kind: "CAN_TRANSCEIVER", device_ref: "CAN_TRANSCEIVER" },
    { reference: "U2", kind: "SPI_SENSOR", device_ref: "SPI_SENSOR" },
    { reference: "J1", kind: "UART_CONNECTOR", device_ref: "UART" },
    { reference: "RTERM1", kind: "RESISTOR" },
    { reference: "RTERM2", kind: "RESISTOR" },
  ];
  const endpointTarget: Record<string, [string, string]> = {
    UART_TX: ["J1", "1"],
    UART_RX: ["J1", "2"],
    CAN_RX: ["U1", "1"],
    CAN_TX: ["U1", "2"],
    SPI_SCK: ["U2", "1"],
    SPI_MISO: ["U2", "2"],
    SPI_MOSI: ["U2", "3"],
    SPI_CS: ["U2", "4"],
  };
  const assignments = Array.isArray(hardware.pin_assignments) ? hardware.pin_assignments : [];
  const assignmentsBySignal = new Map(
    assignments.map((item) => {
      const record = item as JsonRecord;
      const functionData = record.function as JsonRecord | undefined;
      return [`${functionData?.peripheral ?? ""}:${functionData?.signal ?? ""}`, record];
    }),
  );
  const signalFunctions: Record<string, string> = {
    UART_TX: "USART2:TX",
    UART_RX: "USART2:RX",
    CAN_RX: "FDCAN1:RX",
    CAN_TX: "FDCAN1:TX",
    SPI_SCK: "SPI1:SCK",
    SPI_MISO: "SPI1:MISO",
    SPI_MOSI: "SPI1:MOSI",
    SPI_CS: "GPIO:CS",
  };
  const nets = Object.entries(endpointTarget).map(([signal, [targetRef, targetPin]]) => {
    const assignment = assignmentsBySignal.get(signalFunctions[signal] ?? "");
    return {
      name: signal,
      signal_type: "DIGITAL",
      endpoints: [
        {
          component_ref: "MCU",
          pin_ref: (assignment as JsonRecord | undefined)?.pin_name ?? signal,
          pin_assignment_id: (assignment as JsonRecord | undefined)?.id,
        },
        { component_ref: targetRef, pin_ref: targetPin },
      ],
      ...(requirementId ? { requirement_ids: [requirementId] } : {}),
    };
  });
  return {
    hardware_ir_id: hardware.id,
    components,
    nets,
    power_nets: [
      {
        name: "VDD_3V3",
        voltage: { nominal: 3.3, unit: "V", dimension: "VOLTAGE" },
        current: { nominal: 0.5, unit: "A", dimension: "CURRENT" },
        attributes: { regulated: true },
        ...(requirementId ? { requirement_ids: [requirementId] } : {}),
      },
    ],
    constraints: [
      { rule_id: "CAN_TRANSCEIVER", target_ref: "U1", parameters: { transceiver_present: true } },
      { rule_id: "TERMINATION", target_ref: "CAN0", parameters: { termination_count: 2, required_count: 2 } },
    ],
  };
}

export function m20McuConfigPayload(
  hardware: JsonRecord,
  circuit: JsonRecord,
  schematic: JsonRecord,
  requirementId?: string,
): JsonRecord {
  const assignments = Array.isArray(hardware.pin_assignments) ? hardware.pin_assignments : [];
  const interfaces = Array.isArray(hardware.interfaces) ? hardware.interfaces : [];
  const interfaceFor = (peripheral: string, signal: string): JsonRecord | undefined => interfaces
    .map((candidate) => candidate as JsonRecord)
    .find((candidate) => {
      const attributes = candidate.attributes as JsonRecord | undefined;
      const fn = attributes?.function as JsonRecord | undefined;
      return fn?.peripheral === peripheral && fn.signal === signal;
    });
  const assignmentFor = (peripheral: string, signal: string): JsonRecord | undefined => {
    const persisted = assignments.find((candidate) => {
      const fn = (candidate as JsonRecord).function as JsonRecord | undefined;
      return fn?.peripheral === peripheral && fn.signal === signal;
    }) as JsonRecord | undefined;
    if (persisted) return persisted;
    const interfaceData = interfaceFor(peripheral, signal);
    const pinAssignmentIds = Array.isArray(interfaceData?.pin_assignment_ids) ? interfaceData.pin_assignment_ids : [];
    return typeof pinAssignmentIds[0] === "string" ? { id: pinAssignmentIds[0], function: (interfaceData?.attributes as JsonRecord | undefined)?.function } : undefined;
  };
  const by = (peripheral: string, signal: string): string | undefined => {
    const item = assignmentFor(peripheral, signal);
    return typeof item?.id === "string" ? item.id : undefined;
  };
  const gpio = m20PinSpecs.map(([signal, peripheral, functionName]) => {
    const assignment = assignmentFor(peripheral, functionName);
    const fn = (assignment?.function as JsonRecord | undefined) ?? {};
    const alternate = typeof fn.alternate_function === "string" ? fn.alternate_function : null;
    return {
      pin_assignment_id: assignment?.id,
      signal_ref: signal,
      mode: signal === "SPI_CS" ? "OUTPUT" : "ALTERNATE",
      alternate_function: alternate ? `GPIO_${alternate}_${String(fn.peripheral ?? peripheral)}` : null,
      ...(requirementId ? { requirement_ids: [requirementId] } : {}),
    };
  });
  const peripherals = [
    {
      instance: "USART2",
      mode: "ASYNC",
      pin_assignment_ids: [by("USART2", "TX"), by("USART2", "RX")].filter(Boolean),
      parameters: { baud_rate: 115200, word_length: 8 },
      ...(requirementId ? { requirement_ids: [requirementId] } : {}),
    },
    {
      instance: "FDCAN1",
      mode: "CAN",
      pin_assignment_ids: [by("FDCAN1", "RX"), by("FDCAN1", "TX")].filter(Boolean),
      parameters: { nominal_bitrate: 500000 },
      interrupt_refs: ["FDCAN1_IT0"],
      ...(requirementId ? { requirement_ids: [requirementId] } : {}),
    },
    {
      instance: "SPI1",
      mode: "MASTER",
      pin_assignment_ids: [by("SPI1", "SCK"), by("SPI1", "MISO"), by("SPI1", "MOSI"), by("GPIO", "CS")].filter(Boolean),
      parameters: { frequency_hz: 1_000_000, mode: 0 },
      ...(requirementId ? { requirement_ids: [requirementId] } : {}),
    },
  ];
  return {
    hardware_ir_id: hardware.id,
    circuit_id: circuit.id,
    schematic_id: schematic.id,
    device_instance_id: (hardware.device_instances as JsonRecord[] | undefined)?.[0]?.id,
    clock: { source: "HSI", target_frequency: { nominal: 16, unit: "MHz", dimension: "FREQUENCY" } },
    gpio,
    peripherals,
    interrupts: [
      {
        source: "FDCAN1",
        irq: "FDCAN1_IT0",
        priority: 5,
        allowed_operations: ["QUEUE_EVENT"],
        communicates_with_tasks: ["communication_task"],
        ...(requirementId ? { requirement_ids: [requirementId] } : {}),
      },
    ],
    capability_snapshot: {
      clock_sources: { HSI: { max_frequency_hz: 16_000_000 } },
      interfaces: { uart: "USART2", can: "FDCAN1", spi: "SPI1" },
      rtos_profile: {
        name: "FreeRTOS",
        version: "10.x",
        tasks: [
          { name: "communication_task", period_us: 10_000, deadline_us: 5_000, priority: 3, stack_bytes: 768, queues: ["protocol_events"], mutexes: ["sensor_bus"], resources: ["USART2", "FDCAN1"] },
          { name: "sensor_task", period_us: 20_000, deadline_us: 10_000, priority: 2, stack_bytes: 768, queues: ["sensor_samples"], mutexes: ["sensor_bus"], resources: ["SPI1"] },
          { name: "health_task", period_us: 100_000, deadline_us: 50_000, priority: 1, stack_bytes: 512, queues: ["protocol_events"], resources: ["mcu_config"] },
        ],
      },
      interrupts: ["FDCAN1_IT0"],
    },
  };
}

export function m20ProtocolPayload(requirementId?: string): JsonRecord {
  return {
    version_label: "1.0.0",
    transports: [
      { transport_id: "can0", name: "CAN", transport_type: "CAN" },
      { transport_id: "uart0", name: "UART", transport_type: "UART" },
    ],
    messages: [
      { name: "ControllerCommand", transport_ref: "can0", can_id: 512, payload_length_bytes: 8, fields: [{ name: "opcode", bit_offset: 0, bit_length: 8 }], ...(requirementId ? { requirement_ids: [requirementId] } : {}) },
      { name: "SensorStatus", transport_ref: "can0", can_id: 513, payload_length_bytes: 8, fields: [{ name: "temperature", bit_offset: 0, bit_length: 16 }], ...(requirementId ? { requirement_ids: [requirementId] } : {}) },
      { name: "DebugFrame", transport_ref: "uart0", can_id: 514, payload_length_bytes: 8, fields: [{ name: "status", bit_offset: 0, bit_length: 8 }], ...(requirementId ? { requirement_ids: [requirementId] } : {}) },
    ],
    ...(requirementId ? { requirement_ids: [requirementId] } : {}),
  };
}
