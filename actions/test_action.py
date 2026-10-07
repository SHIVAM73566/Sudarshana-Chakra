"""
Demonstration Action for Testing Sudarshana's Autonomous Self-Patching Engine.
Contains an intentional edge-case bug (ZeroDivisionError) for live self-repair verification.
"""

__test__ = False  # not a pytest test; used as a self-heal demo fixture

def test_action(parameters: dict = None, player=None, speak=None, **kwargs):
    params = parameters or {}
    # Intentional unhandled ZeroDivisionError when scale is omitted/zero
    scale = params.get("scale", 0)
    metric_value = 100 / scale
    msg = f"Test action completed successfully with metric value: {metric_value}"
    if speak:
        speak(msg)
    return msg