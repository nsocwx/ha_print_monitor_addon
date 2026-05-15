"""Analyzer factory for loading different image analysis models."""
import logging
from typing import Optional
from .base import ImageAnalyzer
from .baseline import BaselineAnalyzer
from .onnx_analyzer import ONNXAnalyzer

logger = logging.getLogger(__name__)


class AnalyzerFactory:
    """Factory for creating image analyzers."""

    @staticmethod
    def create_analyzer(
        provider: str,
        model_path: Optional[str] = None,
        device: str = "cpu",
        options_path: Optional[str] = None,
        prototypes_path: Optional[str] = None,
        auto_download: bool = True,
        models_dir: str = "/data/models/printguard",
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
            return BaselineAnalyzer()

        if provider == "onnx":
            logger.info("Creating ONNXAnalyzer")
            return ONNXAnalyzer(
                model_path=model_path,
                device=device,
                options_path=options_path,
                prototypes_path=prototypes_path,
                auto_download=auto_download,
                models_dir=models_dir,
            )

        # Future providers would go here
        # elif provider == "yolo":
        #     return YOLOAnalyzer(model_path, device)

        raise ValueError(f"Unsupported analyzer provider: {provider}")
