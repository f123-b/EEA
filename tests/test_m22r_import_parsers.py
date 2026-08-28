"""M22R parser contracts: structural extraction stays candidate-scoped."""

from eea_application.import_parsers import parse_dbc, parse_ioc, parse_kicad


def test_ioc_parser_extracts_mcu_clock_pin_peripheral_and_unknown_lines() -> None:
    result = parse_ioc(
        "\n".join(
            [
                "Mcu.Name=STM32G431CBUx",
                "Mcu.Package=LQFP48",
                "Mcu.Core= Cortex-M4",
                "RCC.AHBCLKFreq_Value=170000000",
                "PA0.Signal=GPIO_Output",
                "USART1.Mode=Asynchronous",
                "broken line",
            ]
        ),
        source_file="board.ioc",
    )
    values = {item.semantic_key: item for item in result.candidates}
    assert result.status == "PASS"
    assert values["ioc.mcu"].proposed_value["part_number"] == "STM32G431CBUx"
    assert values["ioc.pin:PA0"].proposed_value["signal"] == "GPIO_Output"
    assert values["ioc.peripheral:USART1"].proposed_value["mode"] == "Asynchronous"
    assert any(item.status == "UNKNOWN" for item in result.candidates)


def test_kicad_parser_extracts_symbols_nets_and_malformed_unknown() -> None:
    result = parse_kicad(
        '(kicad_sch (symbol (property "Reference" "U1") '
        '(property "Value" "STM32G4") (lib_id "MCU:STM32G4")) '
        '(net 1 "GND") (label "RESET"))',
        source_file="board.kicad_sch",
    )
    keys = {item.semantic_key for item in result.candidates}
    assert "kicad.symbol:U1" in keys
    assert "kicad.net:1" in keys
    assert result.candidates[-1].proposed_value["status"] == "DETECTED"

    malformed = parse_kicad("(kicad_sch (symbol", source_file="bad.kicad_sch")
    assert malformed.status == "UNKNOWN"
    assert malformed.candidates[0].status == "UNKNOWN"


def test_dbc_parser_extracts_standard_extended_signed_and_motorola_signals() -> None:
    result = parse_dbc(
        "\n".join(
            [
                "BO_ 256 Standard: 8 ECU",
                ' SG_ Speed : 0|16@1+ (0.1,0) [0|250] "km/h" ECU',
                "BO_ 2147483904 Extended: 8 ECU",
                ' SG_ Torque : 15|12@0- (1,-10) [-10|100] "Nm" ECU',
            ]
        ),
        source_file="network.dbc",
    )
    messages = [
        item.proposed_value
        for item in result.candidates
        if item.semantic_key.startswith("dbc.message:") and "name" in item.proposed_value
    ]
    assert len(messages) == 2
    standard = next(item for item in messages if item["name"] == "Standard")
    extended = next(item for item in messages if item["name"] == "Extended")
    assert standard["extended_id"] is False
    assert extended["extended_id"] is True
    assert standard["signals"][0]["byte_order"] == "LITTLE_ENDIAN"
    assert extended["signals"][0]["byte_order"] == "MOTOROLA_BIG_ENDIAN"
    assert extended["signals"][0]["signed"] is True


def test_dbc_parser_keeps_malformed_signal_as_unknown_candidate() -> None:
    result = parse_dbc("BO_ 1 Frame: 8 ECU\n SG_ Broken : bad", source_file="bad.dbc")
    assert result.status == "UNKNOWN"
    assert any(item.status == "UNKNOWN" for item in result.candidates)
