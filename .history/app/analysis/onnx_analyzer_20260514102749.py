"""ONNX model analyzer for image analysis."""
import logging
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from typing import Optional, Dict, Any, Tuple
import onnxruntime as ort

from .base import ImageAnalyzer, DetectionResult, AnalysisContext, Severity, RecommendedAction

logger = logging.getLogger(__name__)


class ONNXAnalyzer(ImageAnalyzer):
    """ONNX model analyzer for 3D printing failure detection.

    This analyzer uses the PrintGuard ONNX model for detecting 3D printing failures.
    The model is expected to be a classification or detection model that outputs
    probabilities for different failure types.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        detection_threshold: float = 0.5,
        input_size: Tuple[int, int] = (224, 224)
    ):
        """Initialize the ONNX analyzer.

        Args:
            model_path: Path to the ONNX model file
            device: Device to run inference on ('cpu', 'cuda', etc.)
            detection_threshold: Threshold for considering a detection positive
            input_size: Expected input image size (height, width)
        """
        self.model_path = model_path
        self.device = device
        self.detection_threshold = detection_threshold
        self.input_size = input_size
        self.session = None
        self.input_name = None
        self.output_names = None

        # Failure type mappings (these may need adjustment based on the actual model)
        self.failure_types = {
            0: "normal",
            1: "spaghetti_failure",
            2: "blob_over_extrusion",
            3: "layer_shift",
            4: "stringing",
            5: "poor_adhesion",
            6: "warping"
        }

        # Severity mapping for different failure types
        self.severity_mapping = {
            "normal": Severity.LOW,
            "spaghetti_failure": Severity.HIGH,
            "blob_over_extrusion": Severity.MEDIUM,
            "layer_shift": Severity.CRITICAL,
            "stringing": Severity.MEDIUM,
            "poor_adhesion": Severity.HIGH,
            "warping": Severity.MEDIUM
        }

        # Recommended actions for different failures
        self.action_mapping = {
            "normal": RecommendedAction.CONTINUE,
            "spaghetti_failure": RecommendedAction.PAUSE,
            "blob_over_extrusion": RecommendedAction.PAUSE,
            "layer_shift": RecommendedAction.PAUSE,
            "stringing": RecommendedAction.NOTIFY,
            "poor_adhesion": RecommendedAction.PAUSE,
            "warping": RecommendedAction.NOTIFY
        }

    def initialize(self) -> bool:
        """Initialize the ONNX model session."""
        try:
            # Set up ONNX runtime session
            providers = ['CPUExecutionProvider']
            if self.device == 'cuda':
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

            self.session = ort.InferenceSession(self.model_path, providers=providers)

            # Get input/output names
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [output.name for output in self.session.get_outputs()]

            logger.info(f"ONNX model loaded successfully from {self.model_path}")
            logger.info(f"Input: {self.input_name}, Outputs: {self.output_names}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ONNX model: {e}")
            return False

    def preprocess_image(self, image: Image.Image) -> np.ndarray:
        """Preprocess image for model input.

        Args:
            image: PIL Image to preprocess

        Returns:
            Preprocessed image as numpy array
        """
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Resize to model input size
        image = image.resize(self.input_size, Image.Resampling.LANCZOS)

        # Convert to numpy array and normalize
        img_array = np.array(image).astype(np.float32)

        # Normalize to [0, 1]
        img_array = img_array / 255.0

        # Convert to CHW format (channels first)
        img_array = np.transpose(img_array, (2, 0, 1))

        # Add batch dimension
        img_array = np.expand_dims(img_array, axis=0)

        return img_array

    def analyze_image(self, image_data: bytes, context: Optional[AnalysisContext] = None) -> DetectionResult:
        """Analyze an image for 3D printing failures.

        Args:
            image_data: Raw image bytes
            context: Optional analysis context

        Returns:
            DetectionResult with analysis findings
        """
        if not self.session:
            if not self.initialize():
                return DetectionResult(
                    issue_detected=False,
                    explanation="Failed to initialize ONNX model",
                    recommended_action=RecommendedAction.CONTINUE
                )

        try:
            # Load and preprocess image
            image = Image.open(BytesIO(image_data))
            processed_image = self.preprocess_image(image)

            # Run inference
            outputs = self.session.run(self.output_names, {self.input_name: processed_image})

            # Process results
            return self._process_model_output(outputs[0], image)

        except Exception as e:
            logger.error(f"Error during image analysis: {e}")
            return DetectionResult(
                issue_detected=False,
                explanation=f"Analysis failed: {str(e)}",
                recommended_action=RecommendedAction.CONTINUE
            )

    def _process_model_output(self, output: np.ndarray, original_image: Image.Image) -> DetectionResult:
        """Process model output into DetectionResult.

        Args:
            output: Model output array
            original_image: Original PIL image for potential annotation

        Returns:
            DetectionResult with processed findings
        """
        # Squeeze batch dimension if present
        if output.ndim > 1:
            output = np.squeeze(output, axis=0)

        # Handle different output formats
        if output.ndim == 1:
            # Single output vector - assume classification probabilities
            probabilities = output
        elif output.ndim == 2:
            # 2D output - assume [batch, classes] or [H, W] for segmentation
            if output.shape[0] == len(self.failure_types):
                # Classification with class dimension first
                probabilities = output
            else:
                # Assume segmentation or other format - take max probability
                probabilities = np.max(output, axis=(0, 1)) if output.ndim > 1 else output
        else:
            # Fallback - flatten and take max
            probabilities = np.max(output.flatten())

        # Get the most likely class
        if isinstance(probabilities, np.ndarray) and len(probabilities) > 1:
            predicted_class_idx = np.argmax(probabilities)
            confidence = float(probabilities[predicted_class_idx])
            predicted_class = self.failure_types.get(predicted_class_idx, "unknown")
        else:
            # Single value output
            confidence = float(probabilities)
            predicted_class = "failure" if confidence > self.detection_threshold else "normal"

        # Determine if issue detected
        issue_detected = confidence > self.detection_threshold and predicted_class != "normal"

        # Get severity and recommended action
        severity = self.severity_mapping.get(predicted_class, Severity.MEDIUM)
        recommended_action = self.action_mapping.get(predicted_class, RecommendedAction.NOTIFY)

        # Create explanation
        if issue_detected:
            explanation = f"Detected {predicted_class.replace('_', ' ')} with {confidence:.2%} confidence"
        else:
            explanation = f"No printing issues detected (confidence: {confidence:.2%})"

        return DetectionResult(
            issue_detected=issue_detected,
            issue_type=predicted_class if issue_detected else None,
            certainty=confidence,
            severity=severity,
            explanation=explanation,
            recommended_action=recommended_action,
            raw_model_output={
                "probabilities": probabilities.tolist() if isinstance(probabilities, np.ndarray) else [probabilities],
                "predicted_class": predicted_class,
                "all_classes": list(self.failure_types.values())
            }
        )