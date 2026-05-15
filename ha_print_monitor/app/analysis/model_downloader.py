"""Model downloader for fetching models from Hugging Face Hub."""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelArtifacts:
    """Local paths for a downloaded model and its sidecar files."""

    model_path: str
    options_path: Optional[str] = None
    prototypes_path: Optional[str] = None


class ModelDownloader:
    """Downloads models from Hugging Face Hub."""

    PRINTGUARD_REPO_ID = "nsocwx/PrintGuard"
    PRINTGUARD_SIDECARS = ("opt.json", "prototypes.pkl")

    DEFAULT_MODELS = {
        "onnx": {
            "repo_id": PRINTGUARD_REPO_ID,
            "filename": "model.onnx",
            "description": "PrintGuard ONNX model for 3D printing failure detection"
        },
        "pytorch": {
            "repo_id": PRINTGUARD_REPO_ID,
            "filename": "model.pt",
            "description": "PrintGuard PyTorch model for 3D printing failure detection"
        }
    }

    def __init__(self, models_dir: str = "/data/models/printguard"):
        """Initialize the model downloader.

        Args:
            models_dir: Directory to store downloaded models
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def download_model(
        self,
        provider: str,
        repo_id: Optional[str] = None,
        filename: Optional[str] = None,
        force: bool = False
    ) -> str:
        """Download a model from Hugging Face Hub.

        Args:
            provider: Model provider (e.g., 'onnx')
            repo_id: Hugging Face repo ID (optional, uses default if not provided)
            filename: Model filename (optional, uses default if not provided)
            force: Force re-download even if file exists

        Returns:
            Path to the downloaded model file

        Raises:
            ValueError: If provider is not supported
            Exception: If download fails
        """
        if provider not in self.DEFAULT_MODELS:
            raise ValueError(f"Unsupported provider: {provider}")

        # Use provided values or defaults
        model_config = self.DEFAULT_MODELS[provider]
        repo_id = repo_id or model_config["repo_id"]
        filename = filename or model_config["filename"]

        model_path = self.models_dir / filename

        # Check if model already exists
        if model_path.exists() and not force:
            logger.info(f"Model already exists at {model_path}")
            return str(model_path)

        try:
            logger.info(f"Downloading {provider} model from {repo_id}/{filename}")
            hf_hub_download = self._import_huggingface_hub()

            # Download the model
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False
            )

            logger.info(f"Successfully downloaded model to {downloaded_path}")
            return downloaded_path

        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise

    def ensure_printguard_artifacts(
        self,
        provider: str,
        force: bool = False,
    ) -> ModelArtifacts:
        """Ensure PrintGuard model and sidecar files are available locally.

        Args:
            provider: Model provider (``onnx`` or ``pytorch``)
            force: Force re-download even if files exist

        Returns:
            Paths to the model, options, and prototypes files
        """
        model_path = self.download_model(provider, force=force)
        sidecar_paths = {}

        for filename in self.PRINTGUARD_SIDECARS:
            local_path = self.models_dir / filename
            if local_path.exists() and not force:
                logger.info(f"PrintGuard sidecar already exists at {local_path}")
                sidecar_paths[filename] = str(local_path)
                continue

            logger.info(
                f"Downloading PrintGuard sidecar {filename} from {self.PRINTGUARD_REPO_ID}"
            )
            hf_hub_download = self._import_huggingface_hub()
            sidecar_paths[filename] = hf_hub_download(
                repo_id=self.PRINTGUARD_REPO_ID,
                filename=filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False
            )

        return ModelArtifacts(
            model_path=model_path,
            options_path=sidecar_paths["opt.json"],
            prototypes_path=sidecar_paths["prototypes.pkl"],
        )

    def _import_huggingface_hub(self):
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise ImportError(
                "huggingface-hub is required for automatic model downloads. "
                "Install project requirements or set auto_download: false and "
                "provide model_path, options_path, and prototypes_path manually."
            ) from exc
        return hf_hub_download

    def get_model_path(self, provider: str) -> Optional[str]:
        """Get the local path to a downloaded model.

        Args:
            provider: Model provider

        Returns:
            Path to model file if it exists, None otherwise
        """
        if provider not in self.DEFAULT_MODELS:
            return None

        filename = self.DEFAULT_MODELS[provider]["filename"]
        model_path = self.models_dir / filename

        return str(model_path) if model_path.exists() else None
