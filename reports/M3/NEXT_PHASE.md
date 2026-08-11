# Next Phase — M4 Document + Device Intelligence

## Objective

Implement document and device intelligence on top of M3's canonical values and claim lifecycle.

## Planned scope

- Document upload, versioning, `DocumentIR`, and a Docling adapter boundary.
- Extracted engineering claims that preserve source/evidence and enter the M3 resolver.
- STM32 device-provider contracts and deterministic fixture-backed queries.
- Multi-source merge behavior for document and device claims.

## M4 acceptance focus

- Document extraction produces auditable claims and evidence references rather than free-text facts.
- STM32G431 fixture queries cover PA8 / TIM1_CH1 complementary PWM, FDCAN, ADC/DMA, and
  package-aware pin queries.
- Invalid alternate-function selections are rejected explicitly.
- Conflicting document/device data becomes an M3 conflict record; it is not silently overwritten.

## Constraints and sequencing

- Keep external document parsing behind the adapter boundary and retain deterministic fixtures for
  tests.
- M5 remains the required gate before external repository/archive/build execution.
- FIX-03 remains due before M12; FIX-04 remains due in M14 before M15.
- Do not add unsafe hardware execution or FOC control responsibilities in M4.
