"""Test image analysis."""
import pytest
import numpy as np
from io import BytesIO
from PIL import Image
from app.analysis.baseline import BaselineAnalyzer
from app.analysis.base import AnalysisContext


@pytest.fixture
def analyzer():
    """Create and initialize analyzer."""
    a = BaselineAnalyzer()
    a.initialize()
    return a


def create_test_image(noise_level=0):
    """Create a test image."""
    img_array = np.ones((480, 640, 3), dtype=np.uint8) * 100
    
    if noise_level > 0:
        noise = np.random.randint(-noise_level, noise_level, img_array.shape)
        img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    
    img = Image.fromarray(img_array, 'RGB')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_analyzer_initialization(analyzer):
    """Test analyzer initializes."""
    assert analyzer.initialized is True


@pytest.mark.asyncio
async def test_normal_frame_no_detection(analyzer):
    """Test normal frame doesn't trigger detection."""
    image = create_test_image(noise_level=1)
    result = await analyzer.analyze_frame(image)
    
    assert result.issue_detected is False


@pytest.mark.asyncio
async def test_frame_with_context(analyzer):
    """Test frame analysis with context."""
    image = create_test_image()
    context = AnalysisContext(
        printer_state="printing",
        printer_attributes={},
    )
    
    result = await analyzer.analyze_frame(image, context)
    
    assert result is not None
    assert hasattr(result, 'certainty')
    assert 0.0 <= result.certainty <= 1.0


@pytest.mark.asyncio
async def test_consecutive_frames(analyzer):
    """Test analysis on consecutive frames."""
    image1 = create_test_image(noise_level=2)
    image2 = create_test_image(noise_level=2)
    
    result1 = await analyzer.analyze_frame(image1)
    result2 = await analyzer.analyze_frame(image2)
    
    assert result1 is not None
    assert result2 is not None
