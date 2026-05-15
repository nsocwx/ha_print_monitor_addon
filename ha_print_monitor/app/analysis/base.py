"""Image analysis framework and models."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Issue severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendedAction(str, Enum):
    """Recommended actions."""
    CONTINUE = "continue"
    NOTIFY = "notify"
    PAUSE = "pause"


@dataclass
class DetectionResult:
    """Result from image analysis."""
    issue_detected: bool
    issue_type: Optional[str] = None
    certainty: float = 0.0  # 0.0 to 1.0
    severity: Severity = Severity.LOW
    explanation: str = ""
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE
    annotated_image_path: Optional[str] = None
    raw_model_output: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_detected": self.issue_detected,
            "issue_type": self.issue_type,
            "certainty": self.certainty,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "recommended_action": self.recommended_action.value,
            "annotated_image_path": self.annotated_image_path,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AnalysisContext:
    """Context for analysis including history."""
    printer_state: str
    printer_attributes: Dict[str, Any]
    previous_frames: list = field(default_factory=list)
    previous_results: list = field(default_factory=list)


class ImageAnalyzer(ABC):
    """Abstract base class for image analyzers."""

    @abstractmethod
    async def analyze_frame(
        self,
        image_data: bytes,
        context: Optional[AnalysisContext] = None,
    ) -> DetectionResult:
        """Analyze a frame for print failures.

        Args:
            image_data: Image bytes (JPG, PNG, etc.)
            context: Analysis context with history

        Returns:
            DetectionResult with findings
        """
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the analyzer.

        Returns:
            True if initialization successful
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup resources."""
        pass
