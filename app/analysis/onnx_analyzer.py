"""ONNX analyzer for the PrintGuard prototypical-network model."""
import json
import logging
import pickle
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
from PIL import Image

from .base import (
    AnalysisContext,
    DetectionResult,
    ImageAnalyzer,
    RecommendedAction,
    Severity,
)
from .model_downloader import ModelDownloader

logger = logging.getLogger(__name__)

PRINTGUARD_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
PRINTGUARD_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class ONNXAnalyzer(ImageAnalyzer):
    """ONNX analyzer for PrintGuard model artifacts.

    PrintGuard's ONNX model emits an image embedding. The final class decision is
    made by comparing that embedding with cached prototypes from ``prototypes.pkl``.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu",
        options_path: Optional[str] = None,
        prototypes_path: Optional[str] = None,
        auto_download: bool = True,
        models_dir: str = "/data/models/printguard",
        success_label: str = "success",
        sensitivity: float = 1.0,
    ):
        self.model_path = model_path
        self.device = device
        self.options_path = options_path
        self.prototypes_path = prototypes_path
        self.auto_download = auto_download
        self.models_dir = models_dir
        self.success_label = success_label
        self.sensitivity = sensitivity

        self.initialized = False
        self.session: Optional[Any] = None
        self.input_name: Optional[str] = None
        self.output_name: Optional[str] = None
        self.input_size = 224
        self.prototypes: Optional[np.ndarray] = None
        self.class_names: list[str] = []
        self.defect_idx = -1

    def initialize(self) -> bool:
        """Initialize ONNX Runtime and PrintGuard sidecar files."""
        try:
            self._ensure_artifact_paths()
            self._load_options()
            self._load_prototypes()

            ort = self._import_onnxruntime()
            self.session = ort.InferenceSession(
                self.model_path,
                providers=self._execution_providers(ort),
            )
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            self.initialized = True

            logger.info(
                "PrintGuard ONNX model loaded from %s with classes %s",
                self.model_path,
                self.class_names,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ONNX model: {e}")
            self.initialized = False
            return False

    def cleanup(self):
        """Cleanup ONNX resources."""
        self.session = None
        self.initialized = False

    async def analyze_frame(
        self,
        image_data: bytes,
        context: Optional[AnalysisContext] = None,
    ) -> DetectionResult:
        """Analyze a frame for PrintGuard failures."""
        return self.analyze_image(image_data, context)

    def analyze_image(
        self,
        image_data: bytes,
        context: Optional[AnalysisContext] = None,
    ) -> DetectionResult:
        """Analyze an image for 3D printing failures."""
        if not self.initialized and not self.initialize():
            return DetectionResult(
                issue_detected=False,
                explanation="Failed to initialize ONNX model",
                recommended_action=RecommendedAction.CONTINUE,
            )

        try:
            processed_image = self.preprocess_image(Image.open(BytesIO(image_data)))
            outputs = self.session.run(
                [self.output_name],
                {self.input_name: processed_image},
            )
            embedding = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
            return self._process_embedding(embedding)
        except Exception as e:
            logger.error(f"Error during image analysis: {e}")
            return DetectionResult(
                issue_detected=False,
                explanation=f"Analysis failed: {str(e)}",
                recommended_action=RecommendedAction.CONTINUE,
            )

    def preprocess_image(self, image: Image.Image) -> np.ndarray:
        """Apply PrintGuard's preprocessing pipeline."""
        image = image.convert("RGB")
        image = self._resize_shorter_edge(image, 256)
        image = image.convert("L").convert("RGB")
        image = self._center_crop(image, self.input_size)

        img_array = np.asarray(image, dtype=np.float32) / 255.0
        img_array = (img_array - PRINTGUARD_MEAN) / PRINTGUARD_STD
        img_array = np.transpose(img_array, (2, 0, 1))
        return np.expand_dims(img_array.astype(np.float32), axis=0)

    def _ensure_artifact_paths(self):
        if self.model_path and self.options_path and self.prototypes_path:
            return

        model_dir = Path(self.model_path) if self.model_path else Path(self.models_dir)
        model_path_is_directory = self.model_path and not model_dir.suffix
        if self.model_path and model_dir.suffix:
            model_dir = model_dir.parent
        elif model_path_is_directory:
            candidate = model_dir / "model.onnx"
            self.model_path = str(candidate) if candidate.exists() else None

        if self.model_path and not self.options_path:
            options_path = model_dir / "opt.json"
            if options_path.exists():
                self.options_path = str(options_path)
        if self.model_path and not self.prototypes_path:
            prototypes_path = model_dir / "prototypes.pkl"
            if prototypes_path.exists():
                self.prototypes_path = str(prototypes_path)

        if self.model_path and self.options_path and self.prototypes_path:
            return

        if not self.auto_download:
            raise FileNotFoundError(
                "ONNX model_path, options_path, and prototypes_path are required "
                "when auto_download is disabled."
            )

        artifacts = ModelDownloader(str(model_dir)).ensure_printguard_artifacts("onnx")
        if not self.model_path or not Path(self.model_path).exists():
            self.model_path = artifacts.model_path
        self.options_path = self.options_path or artifacts.options_path
        self.prototypes_path = self.prototypes_path or artifacts.prototypes_path

    def _load_options(self):
        with open(self.options_path, "r", encoding="utf-8") as f:
            model_opt = json.load(f)
        x_dim = list(map(int, model_opt.get("model.x_dim", "3,224,224").split(",")))
        if len(x_dim) >= 3:
            self.input_size = int(x_dim[-1])

    def _load_prototypes(self):
        with open(self.prototypes_path, "rb") as f:
            cache_data = _TorchPrototypeUnpickler(f).load()

        prototypes = cache_data["prototypes"]
        if hasattr(prototypes, "detach"):
            prototypes = prototypes.detach().cpu().numpy()
        self.prototypes = np.asarray(prototypes, dtype=np.float32)
        self.class_names = list(cache_data["class_names"])
        self.defect_idx = int(cache_data.get("defect_idx", -1))

    def _process_embedding(self, embedding: np.ndarray) -> DetectionResult:
        distances = np.linalg.norm(self.prototypes - embedding, axis=1)
        predicted_idx = self._apply_sensitivity(int(np.argmin(distances)), distances)
        predicted_label = self.class_names[predicted_idx]
        issue_detected = predicted_label != self.success_label
        certainty = self._distance_certainty(distances, predicted_idx)

        raw_model_output = {
            "predicted_label": predicted_label,
            "class_names": self.class_names,
            "distances": {
                self.class_names[index]: float(distance)
                for index, distance in enumerate(distances)
            },
            "defect_idx": self.defect_idx,
        }

        if issue_detected:
            return DetectionResult(
                issue_detected=True,
                issue_type=predicted_label,
                certainty=certainty,
                severity=Severity.HIGH if certainty >= 0.85 else Severity.MEDIUM,
                explanation=(
                    f"PrintGuard classified the frame as '{predicted_label}' "
                    f"with {certainty:.2%} certainty"
                ),
                recommended_action=RecommendedAction.NOTIFY,
                raw_model_output=raw_model_output,
            )

        return DetectionResult(
            issue_detected=False,
            certainty=certainty,
            explanation="PrintGuard classified the frame as non-defective",
            recommended_action=RecommendedAction.CONTINUE,
            raw_model_output=raw_model_output,
        )

    def _apply_sensitivity(self, predicted_idx: int, distances: np.ndarray) -> int:
        if self.defect_idx < 0 or predicted_idx == self.defect_idx:
            return predicted_idx

        min_distance = float(np.min(distances))
        defect_distance = float(distances[self.defect_idx])
        if defect_distance <= min_distance * self.sensitivity:
            return self.defect_idx
        return predicted_idx

    def _distance_certainty(self, distances: np.ndarray, predicted_idx: int) -> float:
        if len(distances) <= 1:
            return 0.5

        ordered = np.sort(distances)
        best = max(float(ordered[0]), 1e-6)
        second_best = max(float(ordered[1]), best)
        margin = (second_best - best) / second_best
        if predicted_idx != int(np.argmin(distances)):
            margin = max(margin, 0.5)
        return float(np.clip(0.5 + (margin / 2), 0.0, 0.99))

    def _import_onnxruntime(self) -> Any:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError(
                "onnxruntime is required for provider: onnx. Install project "
                "requirements or add onnxruntime to the runtime image."
            ) from exc
        return ort

    def _execution_providers(self, ort: Any) -> list[str]:
        available = ort.get_available_providers()
        providers = []
        if self.device == "cuda" and "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        if "CPUExecutionProvider" in available:
            providers.append("CPUExecutionProvider")
        if not providers:
            raise RuntimeError("No compatible ONNX Runtime providers are available")
        return providers

    def _resize_shorter_edge(self, image: Image.Image, size: int) -> Image.Image:
        width, height = image.size
        if width < height:
            new_width = size
            new_height = round(height * size / width)
        else:
            new_height = size
            new_width = round(width * size / height)
        return image.resize((new_width, new_height), Image.Resampling.BILINEAR)

    def _center_crop(self, image: Image.Image, size: int) -> Image.Image:
        width, height = image.size
        left = max((width - size) // 2, 0)
        top = max((height - size) // 2, 0)
        return image.crop((left, top, left + size, top + size))


class _TorchStorageBytes:
    """Raw torch storage payload decoded without importing torch."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def to_numpy(self, size: Sequence[int], stride: Sequence[int], offset: int) -> np.ndarray:
        item_count = _required_storage_items(size, stride, offset)
        byte_count = item_count * np.dtype(np.float32).itemsize
        if len(self.payload) < byte_count:
            raise ValueError("Torch storage payload is smaller than expected")

        raw_values = np.frombuffer(self.payload[-byte_count:], dtype="<f4", count=item_count)
        shaped = np.empty(tuple(size), dtype=np.float32)
        for index in np.ndindex(*size):
            storage_index = offset + sum(i * s for i, s in zip(index, stride))
            shaped[index] = raw_values[storage_index]
        return shaped


class _TorchPrototypeUnpickler(pickle.Unpickler):
    """Load PrintGuard prototype pickles without requiring PyTorch."""

    def find_class(self, module: str, name: str):
        if module == "torch.storage" and name == "_load_from_bytes":
            return _load_torch_storage_from_bytes
        if module == "torch._utils" and name == "_rebuild_tensor_v2":
            return _rebuild_torch_tensor_v2
        if module == "collections" and name == "OrderedDict":
            return OrderedDict
        return super().find_class(module, name)


def _load_torch_storage_from_bytes(payload: bytes) -> _TorchStorageBytes:
    return _TorchStorageBytes(payload)


def _rebuild_torch_tensor_v2(
    storage: _TorchStorageBytes,
    storage_offset: int,
    size: Sequence[int],
    stride: Sequence[int],
    requires_grad: bool,
    backward_hooks: Any,
) -> np.ndarray:
    return storage.to_numpy(size, stride, storage_offset)


def _required_storage_items(
    size: Sequence[int],
    stride: Sequence[int],
    offset: int,
) -> int:
    if not size:
        return offset + 1
    max_index = offset + sum((dimension - 1) * step for dimension, step in zip(size, stride))
    return max_index + 1
