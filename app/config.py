"""Конфигурация магазина. Всё берётся из переменных окружения (см. .env.example)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Магазин
    shop_name: str
    min_order: int          # минимальная сумма заказа, ₽
    currency: str

    # ЮKassa (если пусто — включается ДЕМО-режим оплаты, без реальных списаний)
    yookassa_shop_id: str
    yookassa_secret_key: str

    # Публичный адрес сайта — нужен для ссылок возврата после оплаты
    base_url: str

    # Уведомления о заказах
    order_email: str        # куда слать заказы
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    telegram_bot_token: str
    telegram_chat_id: str

    # Админ-переключатель «продажи приостановлены»
    admin_token: str

    db_path: str

    @property
    def yookassa_enabled(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.order_email)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_config() -> Config:
    return Config(
        shop_name=os.environ.get("SHOP_NAME", "Лавка вкуса"),
        min_order=int(os.environ.get("MIN_ORDER", "1500")),
        currency=os.environ.get("CURRENCY", "RUB"),
        yookassa_shop_id=os.environ.get("YOOKASSA_SHOP_ID", "").strip(),
        yookassa_secret_key=os.environ.get("YOOKASSA_SECRET_KEY", "").strip(),
        base_url=os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/"),
        order_email=os.environ.get("ORDER_EMAIL", "").strip(),
        smtp_host=os.environ.get("SMTP_HOST", "").strip(),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER", "").strip(),
        smtp_password=os.environ.get("SMTP_PASSWORD", "").strip(),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        admin_token=os.environ.get("ADMIN_TOKEN", "change-me").strip(),
        db_path=os.environ.get("DB_PATH", "data/shop.db"),
    )
