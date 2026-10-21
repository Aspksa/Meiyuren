import pytest

from backend.app import semantic


@pytest.fixture(autouse=True)
def no_model_downloads(monkeypatch):
    """Тесты никогда не скачивают модель смысла (около 220 МБ)."""
    monkeypatch.setattr(semantic.SemanticModel, "start_loading", lambda self, **_: False)
    semantic._models.clear()
    yield
    semantic._models.clear()
