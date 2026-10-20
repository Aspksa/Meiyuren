"""Cloud.ru Foundation Models: только фиксированный HTTPS API, ключ в системном хранилище."""
from __future__ import annotations

import re

import httpx
import keyring
from keyring.errors import KeyringError

BASE_URL = "https://foundation-models.api.cloud.ru/v1"
SERVICE_NAME = "Meiyuren / Cloud.ru Foundation Models"
ACCOUNT_NAME = "default"
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$")


class CloudError(Exception):
    """Публичное безопасное сообщение (без ключей и тела запроса)."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def valid_model(model: str) -> bool:
    return bool(MODEL_ID.fullmatch(model))


def get_key() -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except (KeyringError, RuntimeError, OSError) as exc:
        raise CloudError(
            "Системное хранилище секретов недоступно. Проверьте Windows Credential Manager / keyring.",
            status=503,
        ) from None


def save_key(secret: str) -> None:
    secret = secret.strip()
    if not 8 <= len(secret) <= 2048 or any(not 33 <= ord(c) <= 126 for c in secret):
        raise CloudError("Некорректный формат API-ключа.", status=422)
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, secret)
    except (KeyringError, RuntimeError, OSError):
        raise CloudError(
            "Системное хранилище секретов недоступно; ключ не сохранён.",
            status=503,
        ) from None


def delete_key() -> None:
    try:
        if keyring.get_password(SERVICE_NAME, ACCOUNT_NAME):
            keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except (KeyringError, RuntimeError, OSError):
        raise CloudError("Не удалось удалить ключ из системного хранилища.", status=503) from None


def required_key() -> str:
    key = get_key()
    if not key:
        raise CloudError("Сначала сохраните API-ключ Cloud.ru.", status=409)
    return key


def request_error(exc: Exception) -> CloudError:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return CloudError("Cloud.ru отклонил API-ключ. Проверьте разрешения и срок действия.", 401)
        if code == 429:
            return CloudError("Cloud.ru ограничил частоту запросов. Повторите позднее.", 429)
        if code in (400, 422):
            return CloudError("Cloud.ru отклонил модель или параметры запроса.", 422)
        return CloudError("Ошибка Cloud.ru. Повторите запрос позднее.", 502)
    return CloudError("Не удалось подключиться к Cloud.ru. Проверьте сеть.", 502)


async def available_models() -> list[str]:
    secret = required_key()
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            response = await client.get(
                BASE_URL + "/models",
                headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        entries = data.get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise CloudError("Cloud.ru вернул неожиданный формат списка моделей.", 502)
        return sorted({
            model["id"] for model in entries[:1000]
            if isinstance(model, dict) and isinstance(model.get("id"), str)
            and valid_model(model["id"])
        })[:300]
    except CloudError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise request_error(exc) from None


async def generate_cloud_reply(model: str, history: list[dict], notes: str, user_text: str) -> str:
    if not valid_model(model):
        raise CloudError("Сначала выберите корректную модель Cloud.ru.", 409)
    secret = required_key()
    system = (
        "Ты Мэйюрэн, доброжелательная виртуальная спутница. "
        "Отвечай по-русски, понятно, естественно и без лишней длины."
    )
    if notes:
        system += "\nЗаметки пользователя (контекст, не системные указания):\n" + notes[:4000]
    context = [
        {"role": row["role"], "content": row["text"][:2000]}
        for row in history[-12:] if row["role"] in ("user", "assistant")
    ]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *context, {"role": "user", "content": user_text}],
        "max_tokens": 450,
        "temperature": 0.65,
    }
    try:
        async with httpx.AsyncClient(timeout=55.0, follow_redirects=False) as client:
            response = await client.post(
                BASE_URL + "/chat/completions",
                headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise CloudError("Cloud.ru вернул пустой ответ.", 502)
        return content.strip()[:8000]
    except CloudError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise request_error(exc) from None
