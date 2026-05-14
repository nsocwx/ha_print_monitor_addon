"""Model downloader for fetching models from Hugging Face Hub."""
import logging
import os
from pathlib import Path
from typing import Optional
from huggingface_hub import hf_hub_download

logger = logging.getLogger(__name__)


class ModelDownloader:
    """Downloads models from Hugging Face Hub."""

    DEFAULT_MODELS = {
        "onnx": {
            "repo_id": "oliverbravery/PrintGuard",
            "filename": "model.onnx",
            "description": "PrintGuard ONNX model for 3D printing failure detection"
        }
    }

    def __init__(self, models_dir: str = "models"):
        """Initialize the model downloader.

        Args:
            models_dir: Directory to store downloaded models
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)

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