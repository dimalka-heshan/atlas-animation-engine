import pytest

from engine.core.models import RenderSettings
from engine.rendering.video import validate_probe
from test_pipeline import probe


def voiced_probe():
    data = probe()
    data["streams"].append({"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000",
        "channels": 2, "duration": "2.0", "start_time": "0"})
    return data


def test_audio_stream_requires_explicit_contract():
    with pytest.raises(ValueError):
        validate_probe(voiced_probe(), RenderSettings())
    result = validate_probe(voiced_probe(), RenderSettings(), expect_audio=True)
    assert result["audio"]["codec"] == "aac"


@pytest.mark.parametrize("field,value", [("duration", "0.4"), ("start_time", "0.2"),
    ("codec_name", "mp3"), ("channels", 1), ("sample_rate", "24000"), ("duration", "nan")])
def test_invalid_audio_stream_rejected(field, value):
    data = voiced_probe(); data["streams"][1][field] = value
    with pytest.raises(ValueError):
        validate_probe(data, RenderSettings(), expect_audio=True)
