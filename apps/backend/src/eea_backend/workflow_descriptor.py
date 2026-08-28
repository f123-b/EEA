"""Backend-owned workflow descriptors for generic desktop rendering."""

from __future__ import annotations

from typing import Any

GENERIC_EMBEDDED_RELEASE_WORKFLOW: dict[str, Any] = {
    "workflow_id": "generic_embedded_release",
    "version": "1",
    "stages": [
        {
            "id": "requirements",
            "label": "Requirements",
            "capability": "requirements.analyze",
            "input_schema": {},
            "depends_on": [],
        },
        {
            "id": "pin-plan",
            "label": "Pin plan",
            "capability": "pins.generate",
            "input_schema": {},
            "depends_on": ["requirements"],
        },
        {
            "id": "hardware",
            "label": "Hardware",
            "capability": "hardware.generate",
            "input_schema": {},
            "depends_on": ["pin-plan"],
        },
        {
            "id": "firmware",
            "label": "Firmware",
            "capability": "firmware.generate",
            "input_schema": {},
            "depends_on": ["hardware"],
        },
        {
            "id": "verification",
            "label": "Verification",
            "capability": "verification.run",
            "input_schema": {},
            "depends_on": ["firmware"],
        },
        {
            "id": "review",
            "label": "Review",
            "capability": "review.run",
            "input_schema": {},
            "depends_on": ["verification"],
        },
    ],
}


def workflow_descriptor() -> dict[str, Any]:
    """Return a defensive copy so callers cannot mutate the descriptor."""

    return {
        **GENERIC_EMBEDDED_RELEASE_WORKFLOW,
        "stages": [dict(stage) for stage in GENERIC_EMBEDDED_RELEASE_WORKFLOW["stages"]],
    }


__all__ = ["GENERIC_EMBEDDED_RELEASE_WORKFLOW", "workflow_descriptor"]
