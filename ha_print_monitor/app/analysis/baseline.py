"""Baseline image analyzer using image differencing and heuristics."""
import logging
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from typing import Optional
from datetime import datetime
import hashlib

from .base import ImageAnalyzer, DetectionResult, AnalysisContext, Severity, RecommendedAction

logger = logging.getLogger(__name__)

# Thresholds for detection heuristics
MOTION_THRESHOLD = 2000  # Minimum motion pixels to detect movement
BRIGHTNESS_SHIFT_THRESHOLD = 15  # Brightness change threshold
COLOR_SATURATION_ANOMALY = 30  # Detect oversaturated areas
EDGE_DENSITY_THRESHOLD = 0.15  # High edge density anomaly
ANOMALY_SCORE_THRESHOLD = 0.5  # Internal baseline trigger threshold


class BaselineAnalyzer(ImageAnalyzer):
    """Baseline analyzer using image differencing and heuristic patterns.

    This is a proof-of-concept implementation that:
    - Compares frames for unusual movement or changes
    - Detects brightness anomalies
    - Identifies potential blob/extrusion issues via motion patterns
    - Uses multiple frame history to avoid false positives

    This should be replaced with a real model (YOLO, etc.)
    """

    def __init__(self):
        self.initialized = False
        self.frame_history = []
        self.motion_history = []
        self.max_history = 5

    def initialize(self) -> bool:
        """Initialize analyzer."""
        try:
            # Test that cv2 and PIL are available
            test_img = np.zeros((100, 100, 3), dtype=np.uint8)
            _ = cv2.Canny(test_img, 100, 200)
            self.initialized = True
            logger.info("BaselineAnalyzer initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize BaselineAnalyzer: {e}")
            return False

    def cleanup(self):
        """Cleanup resources."""
        self.frame_history.clear()
        self.motion_history.clear()

    async def analyze_frame(
        self,
        image_data: bytes,
        context: Optional[AnalysisContext] = None,
    ) -> DetectionResult:
        """Analyze a frame using baseline heuristics."""
        if not self.initialized:
            return DetectionResult(
                issue_detected=False,
                explanation="Analyzer not initialized"
            )

        try:
            # Convert bytes to numpy array
            img = Image.open(BytesIO(image_data))
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

            # Store in history
            frame_hash = hashlib.md5(image_data).hexdigest()
            self.frame_history.append({
                "frame": frame,
                "hash": frame_hash,
                "timestamp": datetime.utcnow(),
            })

            # Keep only recent frames
            if len(self.frame_history) > self.max_history:
                self.frame_history.pop(0)

            # Perform analysis
            result = self._run_heuristics(frame, context)
            return result

        except Exception as e:
            logger.error(f"Error analyzing frame: {e}")
            return DetectionResult(
                issue_detected=False,
                explanation=f"Analysis error: {str(e)}"
            )

    def _run_heuristics(
        self,
        current_frame: np.ndarray,
        context: Optional[AnalysisContext] = None,
    ) -> DetectionResult:
        """Run heuristic analysis on frame."""

        # If not enough history, return neutral
        if len(self.frame_history) < 2:
            return DetectionResult(issue_detected=False)

        prev_frame_data = self.frame_history[-2]
        prev_frame = prev_frame_data["frame"]

        # Compute motion between frames
        motion_detected, motion_pixels, motion_areas = self._detect_motion(
            prev_frame, current_frame
        )

        # Detect brightness anomalies
        brightness_anomaly = self._detect_brightness_anomaly(prev_frame, current_frame)

        # Detect potential blob/extrusion issues
        blob_score = self._detect_blob_candidate(current_frame)

        # Detect layer shift patterns
        layer_shift_score = self._detect_layer_shift(
            prev_frame, current_frame, motion_areas
        )

        # Compute overall detection score
        scores = {
            "motion": motion_pixels / (current_frame.shape[0] * current_frame.shape[1]) if motion_pixels > 0 else 0,
            "brightness_anomaly": brightness_anomaly,
            "blob_candidate": blob_score,
            "layer_shift": layer_shift_score,
        }

        # Determine if issue detected
        # High motion alone is normal, but unusual patterns combined suggest issue
        combined_anomaly_score = (
            scores["brightness_anomaly"] * 0.3 +
            scores["blob_candidate"] * 0.35 +
            scores["layer_shift"] * 0.35
        )

        issue_detected = combined_anomaly_score > ANOMALY_SCORE_THRESHOLD

        if issue_detected:
            # Determine issue type and severity
            if scores["layer_shift"] > 0.6:
                issue_type = "shifted_layers"
                severity = Severity.HIGH
                explanation = f"Potential layer shift detected (score: {scores['layer_shift']:.1%})"
            elif scores["blob_candidate"] > 0.6:
                issue_type = "blob_or_extrusion"
                severity = Severity.MEDIUM
                explanation = f"Blob or unusual extrusion pattern detected (score: {scores['blob_candidate']:.1%})"
            elif brightness_anomaly > 0.6:
                issue_type = "lighting_anomaly"
                severity = Severity.LOW
                explanation = f"Possible nozzle issue or lighting change (score: {brightness_anomaly:.1%})"
            else:
                issue_type = "anomaly"
                severity = Severity.MEDIUM
                explanation = "Unusual print pattern detected"

            certainty = min(combined_anomaly_score, 0.95)

            # Note: In production, use a real model with proper confidence scores
            # This baseline should only trigger notifications, not auto-pause
            recommended_action = RecommendedAction.NOTIFY

            return DetectionResult(
                issue_detected=True,
                issue_type=issue_type,
                certainty=certainty,
                severity=severity,
                explanation=explanation,
                recommended_action=recommended_action,
                raw_model_output=scores,
            )

        return DetectionResult(
            issue_detected=False,
            certainty=1.0 - combined_anomaly_score,
            explanation="No anomalies detected",
            raw_model_output=scores,
        )

    def _detect_motion(
        self, prev_frame: np.ndarray, curr_frame: np.ndarray
    ) -> tuple:
        """Detect motion between frames.

        Returns:
            (motion_detected, motion_pixels, motion_areas)
        """
        # Compute absolute difference
        diff = cv2.absdiff(prev_frame, curr_frame)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

        # Threshold to binary
        _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

        # Count motion pixels
        motion_pixels = np.count_nonzero(thresh)

        # Find contours for motion areas
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion_areas = [cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 100]

        motion_detected = motion_pixels > MOTION_THRESHOLD

        return motion_detected, motion_pixels, motion_areas

    def _detect_brightness_anomaly(
        self, prev_frame: np.ndarray, curr_frame: np.ndarray
    ) -> float:
        """Detect unusual brightness changes (nozzle-related anomalies)."""
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

        brightness_diff = cv2.absdiff(prev_gray, curr_gray)
        mean_diff = brightness_diff.mean()
        max_diff = brightness_diff.max()

        # Anomaly if large localized brightness change
        bright_pixels = np.sum(brightness_diff > BRIGHTNESS_SHIFT_THRESHOLD)
        bright_ratio = bright_pixels / (prev_frame.shape[0] * prev_frame.shape[1])

        anomaly_score = min(bright_ratio * 2, 1.0)
        return anomaly_score

    def _detect_blob_candidate(self, frame: np.ndarray) -> float:
        """Detect potential blob or filament issues."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Look for very saturated regions (blobs tend to be highly saturated)
        saturation = hsv[:, :, 1]
        high_sat = np.sum(saturation > 200) / saturation.size

        # Detect edges (blobs show unusual edge patterns)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        edge_density = np.count_nonzero(edges) / edges.size

        # Score: combination of saturation and edge anomaly
        blob_score = (high_sat * 0.4 + min(edge_density / EDGE_DENSITY_THRESHOLD, 1.0) * 0.6)
        return blob_score

    def _detect_layer_shift(
        self, prev_frame: np.ndarray, curr_frame: np.ndarray, motion_areas: list
    ) -> float:
        """Detect potential layer shift or misalignment."""
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

        # Compute horizontal and vertical gradients
        sobelx_prev = cv2.Sobel(prev_gray, cv2.CV_64F, 1, 0, ksize=3)
        sobelx_curr = cv2.Sobel(curr_gray, cv2.CV_64F, 1, 0, ksize=3)

        # Compare edge alignment (layer shift causes edge displacement)
        edge_shift = cv2.absdiff(sobelx_prev, sobelx_curr).mean()

        # If motion areas are very localized and edges shift significantly, suggest layer shift
        if len(motion_areas) > 0 and max(motion_areas) > 500:
            shift_score = min(edge_shift / 50, 1.0)
        else:
            shift_score = 0.0

        return shift_score
