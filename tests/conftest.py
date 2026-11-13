import pytest


@pytest.fixture(autouse=True)
def _isolated_tts_cache(tmp_path, monkeypatch):
    """Mỗi test dùng bộ đệm giọng đọc riêng, không đụng ~/.video_studio của máy."""
    monkeypatch.setenv("VSTUDIO_CACHE_DIR", str(tmp_path / "tts_cache"))
