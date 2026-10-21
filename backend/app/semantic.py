"""Понимание 2.0, этап 5: модель смысла внутри приложения, без Ollama и без сети в чате.

Модель paraphrase-multilingual-MiniLM-L12-v2 (ONNX, около 220 МБ) работает через
fastembed. Файлы модели скачиваются один раз в режиме простоя в data/models;
тексты пользователя никуда не отправляются. Без fastembed или без скачанной
модели всё работает как раньше: на словах и триграммах.
"""
from __future__ import annotations

from array import array
import logging
import math
from pathlib import Path
import threading

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSIONS = 384
# Метка модели в отпечатке вектора: смена модели или её файлов пересчитывает все векторы.
REVISION = 1
VERSION = f"{MODEL}@{REVISION}:"
# Пишется только после полной загрузки: обрыв скачивания не считается готовой моделью.
COMPLETE = ".meiyuren-complete"
# Сходство, при котором факт подходит к вопросу без общих слов («кофе» → «эспрессо»).
MATCH = 0.55

try:  # Необязательная зависимость.
    from fastembed import TextEmbedding
except ImportError:  # pragma: no cover - зависит от окружения
    TextEmbedding = None


class SemanticModel:
    def __init__(self, folder: Path):
        self.folder = folder
        self._lock = threading.Lock()
        self._model = None
        self._loader: threading.Thread | None = None
        self._then = None
        self.state = "not-installed" if TextEmbedding is None else "not-loaded"
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def downloaded(self) -> bool:
        try:
            return (self.folder / COMPLETE).read_text(encoding="utf-8") == VERSION
        except OSError:
            return False

    def load(self, *, allow_download: bool) -> bool:
        """Загрузить модель; скачивание разрешено только из режима простоя."""
        if self._model is not None:
            return True
        if TextEmbedding is None or (not allow_download and not self.downloaded()):
            return False
        with self._lock:
            if self._model is not None:
                return True
            self.state = "loading" if self.downloaded() else "downloading"
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                # Без разрешения на скачивание библиотека не идёт в сеть даже при неполном кэше.
                self._model = TextEmbedding(MODEL, cache_dir=str(self.folder),
                                            local_files_only=not allow_download)
                (self.folder / COMPLETE).write_text(VERSION, encoding="utf-8")
                self.state, self.error = "ready", None
            except Exception as exc:  # сеть, диск, повреждённый файл — пробуем в другой раз
                logging.getLogger(__name__).warning("Модель смысла не загрузилась: %s", exc)
                self.state, self.error = "failed", type(exc).__name__
                return False
        return True

    def start_loading(self, *, allow_download: bool, then=None) -> bool:
        """Загрузка в отдельном потоке: скачивание не задерживает разбор сообщений.

        then — что сделать сразу после загрузки (режим простоя считает векторы, не дожидаясь
        следующего запуска через полчаса)."""
        if self._model is not None:
            return True
        if TextEmbedding is None or (not allow_download and not self.downloaded()):
            return False
        if self._loader is None or not self._loader.is_alive():
            self._then = then
            self._loader = threading.Thread(target=self._load_then, args=(allow_download,),
                                            name="meiyuren-semantic", daemon=True)
            self._loader.start()
        return False

    def _load_then(self, allow_download: bool) -> None:
        if self.load(allow_download=allow_download) and self._then is not None:
            try:
                self._then()
            except Exception as exc:  # индексация повторится в следующем простое
                logging.getLogger(__name__).warning("Векторы смысла не посчитались: %s", exc)

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            raise RuntimeError("model not loaded")
        vectors = []
        # Замок берётся на маленькую пачку: вопрос из чата не ждёт всю индексацию простоя.
        for start in range(0, len(texts), 8):
            with self._lock:
                vectors.extend(self._model.embed(texts[start:start + 8], batch_size=8))
        return [normalize([float(x) for x in v]) for v in vectors]

    def status(self) -> dict:
        return {"model": MODEL, "state": "ready" if self.ready else self.state,
                "downloaded": self.downloaded(), "error": self.error}


_models: dict[Path, SemanticModel] = {}
_registry_lock = threading.Lock()


def model_for(database: Path) -> SemanticModel:
    """Одна модель на папку данных: и чат, и режим простоя используют её."""
    folder = Path(database).parent / "models"
    with _registry_lock:
        if folder not in _models:
            _models[folder] = SemanticModel(folder)
        return _models[folder]


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


def pack(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack(blob: bytes) -> array:
    values = array("f")
    values.frombytes(blob)
    return values


def similarity(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))
