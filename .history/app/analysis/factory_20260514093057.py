"""Analyzer factory for loading different image analysis models."""
import logging
from typing import Optional
from .base import ImageAnalyzer
from .baseline import BaselineAnalyzer

logger = logging.getLogger(__name__)


class AnalyzerFactory:
    """Factory for creating image analyzers."""

    @staticmethod
    def create_analyzer(
        provider: str,
        model_path: Optional[str] = None,
        device: str = "cpu",
        detection_threshold: float = 0.5,
    ) -> ImageAnalyzer:
        """Create an analyzer instance.

        Args:
            provider: Analyzer provider name (baseline, yolo, onnx, etc.)
            model_path: Path to model file if applicable
            device: Device to run on (cpu, cuda, etc.)

        Returns:
            ImageAnalyzer instance

        Raises:
            ValueError: If provider is not supported
        """
        if provider == "baseline":
            logger.info("Creating BaselineAnalyzer")
            return BaselineAnalyzer(detection_threshold=detection_threshold)

        if provider in ("onnx", "yolo"):
            if not model_path:
                raise ValueError("model_path is required for ONNX analyzer")
            logger.info("Creating ONNXAnalyzer")
            from .onnx_analyzer import ONNXAnalyzer

            return ONNXAnalyzer(model_path, device, detection_threshold=detection_threshold)

        raise ValueError(f"Unsupported analyzer provider: {provider}")
