"""Оплата через ЮKassa.

Если ключи ЮKassa заданы — создаём реальный платёж и возвращаем ссылку на
страницу оплаты. Если ключей нет — работает ДЕМО-режим: возвращаем ссылку на
встроенную страницу-заглушку, которая имитирует успешную оплату. Так весь
сценарий можно показать заказчику до подключения боевого эквайринга.
"""

import logging
import uuid

import httpx

from app.config import Config

logger = logging.getLogger(__name__)

_API = "https://api.yookassa.ru/v3/payments"


async def create_payment(cfg: Config, order_id: int, amount: int, description: str) -> dict:
    """Возвращает {'payment_id': str, 'confirmation_url': str}."""
    if not cfg.yookassa_enabled:
        # демо: ссылка на локальную заглушку оплаты
        return {
            "payment_id": f"demo-{order_id}",
            "confirmation_url": f"{cfg.base_url}/demo/pay?order_id={order_id}",
        }

    payload = {
        "amount": {"value": f"{amount}.00", "currency": cfg.currency},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"{cfg.base_url}/success?order_id={order_id}",
        },
        "description": description,
        "metadata": {"order_id": order_id},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            _API,
            json=payload,
            auth=(cfg.yookassa_shop_id, cfg.yookassa_secret_key),
            headers={"Idempotence-Key": str(uuid.uuid4())},
        )
    resp.raise_for_status()
    data = resp.json()
    return {
        "payment_id": data["id"],
        "confirmation_url": data["confirmation"]["confirmation_url"],
    }
