"""Уведомления о новом/оплаченном заказе: email (SMTP) и Telegram."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import Config

logger = logging.getLogger(__name__)


def _order_text(order: dict, items: list[dict], paid: bool) -> str:
    lines = [
        f"Заказ #{order['id']} — {'ОПЛАЧЕН онлайн' if paid else 'новый'}",
        "",
        f"Покупатель: {order['customer']}",
        f"Телефон: {order['phone']}",
        f"Адрес: {order['address']}",
    ]
    if order.get("comment"):
        lines.append(f"Комментарий: {order['comment']}")
    method = "онлайн-оплата" if order["pay_method"] == "online" else "наличными/картой курьеру"
    lines += ["", f"Способ оплаты: {method}", "", "Состав:"]
    for it in items:
        lines.append(f"  • {it['name']} × {it['qty']} = {it['price'] * it['qty']} ₽")
    lines += ["", f"Итого: {order['total']} ₽"]
    return "\n".join(lines)


def _send_email_sync(cfg: Config, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_user or cfg.order_email
    msg["To"] = cfg.order_email
    msg.set_content(body)
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if cfg.smtp_user:
            smtp.login(cfg.smtp_user, cfg.smtp_password)
        smtp.send_message(msg)


async def notify_order(cfg: Config, order: dict, items: list[dict], paid: bool) -> None:
    """Шлём заказ на email и в Telegram. Сбой одного канала не мешает другому."""
    text = _order_text(order, items, paid)
    subject = f"{cfg.shop_name}: заказ #{order['id']}"

    if cfg.email_enabled:
        try:
            # блокирующий smtplib уводим в отдельный поток, чтобы не тормозить event loop
            await asyncio.to_thread(_send_email_sync, cfg, subject, text)
        except Exception:
            logger.exception("Не удалось отправить email по заказу #%s", order["id"])
    else:
        logger.info("Email не настроен — заказ #%s:\n%s", order["id"], text)

    if cfg.telegram_enabled:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage",
                    json={"chat_id": cfg.telegram_chat_id, "text": "🛒 " + text},
                )
        except Exception:
            logger.exception("Не удалось отправить Telegram по заказу #%s", order["id"])
