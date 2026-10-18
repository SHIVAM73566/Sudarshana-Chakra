"""
Feature: Holographic Hardware Assembler & Interactive Circuit HUD
Description: Analyzes electronic components on screen or from voice, resolves pin-to-pin wiring,
and launches the interactive Holographic Circuit HUD display.
Triggers: see the arduino parts on my screen, how to assemble these parts, how to connect arduino, circuit diagram, wire arduino, circuit schematic
"""

from typing import Any, Dict
from actions.circuit_assembler import circuit_assembler

FEATURE_METADATA = {
    "name": "circuit_schematic",
    "aliases": ["circuit_assembler", "hardware_assembler", "arduino_circuit", "circuit_wiring", "circuit_hud"],
    "description": (
        "Analyzes electronic components (Arduino, ESP32, sensors, actuators, resistors) on screen or from voice, "
        "calculates pin-to-pin wiring diagrams, safety warnings, and step-by-step assembly guides, "
        "and displays the interactive Holographic Circuit HUD."
    ),
    "triggers": [
        "see the arduino parts on my screen",
        "how to assemble these arduino parts",
        "how to connect these parts",
        "how to assemble it",
        "how to assemble these",
        "show circuit diagram",
        "show wiring diagram",
        "assemble circuit",
        "wire arduino",
        "how to connect arduino",
        "connect dht11 to arduino",
        "connect ultrasonic sensor to arduino",
        "connect servo to arduino",
        "circuit schematic",
        "hardware wiring diagram",
        "circuit assembler",
    ],
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "analyze_screen | assemble_components | show_schematic (default: assemble_components)",
            },
            "components": {
                "type": "STRING",
                "description": "Comma-separated list or description of electronic components (e.g. 'Arduino Pro Mini, DHT11, 10k resistor')",
            },
            "query": {
                "type": "STRING",
                "description": "Specific project goal or wiring instructions (e.g. 'how to connect humidity sensor to arduino')",
            },
        },
    },
    "version": "1.0.0",
    "active": True,
}


def execute(**kwargs) -> Dict[str, Any]:
    """Executes Circuit Assembler action and returns the formatted result."""
    action = kwargs.get("action", "assemble_components")
    components = kwargs.get("components", "")
    query = kwargs.get("query", "")
    
    player = kwargs.get("player")
    speak = kwargs.get("speak")
    return circuit_assembler(action=action, components=components, query=query, player=player, speak=speak)
