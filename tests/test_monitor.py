"""Test monitor state handling."""
from app.core.config import PrinterConfig
from app.services.monitor import PrintMonitorService


def make_service(printing_states):
    """Build a monitor service shell without initializing external clients."""
    service = object.__new__(PrintMonitorService)
    service.printer = PrinterConfig(printing_states=printing_states)
    service.printer_state = None
    return service


def test_only_active_printing_states_are_considered_printing():
    """Configured non-printing states must not trigger capture or analysis."""
    service = make_service(
        [
            "idle",
            "busy",
            "printing",
            "paused",
            "finished",
            "ready",
            "printing_sd",
        ]
    )

    assert service.is_printer_printing("printing") is True
    assert service.is_printer_printing("Printing") is True
    assert service.is_printer_printing("printing_sd") is True
    assert service.is_printer_printing("idle") is False
    assert service.is_printer_printing("busy") is False
    assert service.is_printer_printing("paused") is False
    assert service.is_printer_printing("ready") is False


def test_unconfigured_printing_variant_is_not_assumed_printing():
    """The configured states still constrain what counts as printing."""
    service = make_service(["printing"])

    assert service.is_printer_printing("printing") is True
    assert service.is_printer_printing("printing_streaming") is False


def test_progress_value_parsing():
    assert PrintMonitorService._parse_progress_value("42") == 42.0
    assert PrintMonitorService._parse_progress_value("42.5%") == 42.5
    assert PrintMonitorService._parse_progress_value("-5") == 0.0
    assert PrintMonitorService._parse_progress_value("105") == 100.0
    assert PrintMonitorService._parse_progress_value("unknown") is None
