"""Интернет-магазин на одной странице: каталог, корзина, оформление, оплата.

Запуск:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import load_config
from app.notify import notify_order
from app.payments import create_payment
from app.store import Store

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

cfg = load_config()
store = Store(cfg.db_path)
app = FastAPI(title="Food shop landing", docs_url=None, redoc_url=None)


# ---------- модели запросов ----------

class CartItem(BaseModel):
    id: str
    qty: int = Field(ge=1, le=99)


class OrderIn(BaseModel):
    customer: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=5, max_length=30)
    address: str = Field(min_length=5, max_length=300)
    comment: str = Field(default="", max_length=500)
    pay_method: str = Field(pattern="^(online|cod)$")
    items: list[CartItem] = Field(min_length=1)


class SalesToggle(BaseModel):
    enabled: bool


# ---------- служебное ----------

@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    await store.init()
    mode = "ЮKassa" if cfg.yookassa_enabled else "ДЕМО-оплата"
    logger.info("Магазин «%s» запущен. Режим оплаты: %s", cfg.shop_name, mode)


def _price_cart(items: list[CartItem]) -> tuple[list[dict], int]:
    """Считаем стоимость на СЕРВЕРЕ по каталогу — цене из браузера доверять нельзя."""
    priced: list[dict] = []
    total = 0
    for it in items:
        product = store.catalog.get(it.id)
        if product is None:
            raise HTTPException(400, f"Товар не найден: {it.id}")
        line = product.price * it.qty
        total += line
        priced.append({"id": product.id, "name": product.name,
                       "price": product.price, "qty": it.qty})
    return priced, total


# ---------- API ----------

@app.get("/api/catalog")
async def api_catalog() -> JSONResponse:
    products = [
        {"id": p.id, "name": p.name, "cat": p.cat, "price": p.price,
         "unit": p.unit, "emoji": p.emoji, "desc": p.desc}
        for p in store.catalog.values()
    ]
    return JSONResponse({
        "shop_name": cfg.shop_name,
        "min_order": cfg.min_order,
        "sales_enabled": await store.sales_enabled(),
        "products": products,
    })


@app.post("/api/order")
async def api_order(order: OrderIn) -> JSONResponse:
    if not await store.sales_enabled():
        raise HTTPException(409, "Продажи временно приостановлены")

    priced, total = _price_cart(order.items)
    if total < cfg.min_order:
        raise HTTPException(
            422, f"Минимальная сумма заказа — {cfg.min_order} ₽ (у вас {total} ₽)"
        )

    if order.pay_method == "cod":
        order_id = await store.create_order(
            order.customer, order.phone, order.address, order.comment,
            priced, total, "cod", status="new",
        )
        saved = await store.get_order(order_id)
        await notify_order(cfg, saved, priced, paid=False)
        return JSONResponse({"ok": True, "order_id": order_id,
                             "redirect": f"/success?order_id={order_id}"})

    # онлайн-оплата
    order_id = await store.create_order(
        order.customer, order.phone, order.address, order.comment,
        priced, total, "online", status="new",
    )
    try:
        payment = await create_payment(
            cfg, order_id, total, description=f"{cfg.shop_name}: заказ #{order_id}"
        )
    except Exception:
        logger.exception("Ошибка создания платежа по заказу #%s", order_id)
        await store.set_status(order_id, "canceled")
        raise HTTPException(502, "Не удалось создать платёж, попробуйте позже")

    await store.attach_payment(order_id, payment["payment_id"])
    return JSONResponse({"ok": True, "order_id": order_id,
                         "confirmation_url": payment["confirmation_url"]})


async def _mark_paid_and_notify(order_id: int) -> bool:
    order = await store.get_order(order_id)
    if order is None:
        return False
    if order["status"] == "paid":
        return True  # идемпотентность: повторный вебхук не шлёт второе письмо
    await store.set_status(order_id, "paid")
    import json
    items = json.loads(order["items_json"])
    order["status"] = "paid"
    await notify_order(cfg, order, items, paid=True)
    return True


@app.post("/api/yookassa/webhook")
async def yookassa_webhook(request: Request) -> JSONResponse:
    """Боевой вебхук ЮKassa: подтверждение оплаты приходит сюда."""
    body = await request.json()
    if body.get("event") == "payment.succeeded":
        obj = body.get("object", {})
        order_id = (obj.get("metadata") or {}).get("order_id")
        if order_id is not None:
            await _mark_paid_and_notify(int(order_id))
    return JSONResponse({"ok": True})


# ---------- демо-оплата (когда ЮKassa не подключена) ----------

@app.get("/demo/pay", response_class=HTMLResponse)
async def demo_pay(order_id: int) -> HTMLResponse:
    order = await store.get_order(order_id)
    if order is None:
        raise HTTPException(404, "Заказ не найден")
    return HTMLResponse(f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Демо-оплата</title><link rel="stylesheet" href="/style.css"></head>
<body><div class="pay-demo">
  <div class="pay-demo__card">
    <div class="pay-demo__badge">ДЕМО-режим оплаты</div>
    <h1>Оплата заказа #{order_id}</h1>
    <p class="pay-demo__sum">{order['total']} ₽</p>
    <p class="muted">Это страница-заглушка вместо ЮKassa. Реальные деньги не списываются.
    После подключения эквайринга здесь будет настоящая платёжная форма.</p>
    <button id="pay" class="btn btn--wide">Оплатить (демо)</button>
    <p id="st" class="pay-demo__status"></p>
  </div>
</div>
<script>
document.getElementById('pay').addEventListener('click', async (e) => {{
  e.target.disabled = true; e.target.textContent = 'Обработка…';
  const r = await fetch('/api/demo/confirm', {{method:'POST',
    headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{order_id:{order_id}}})}});
  if (r.ok) location.href = '/success?order_id={order_id}';
  else {{ document.getElementById('st').textContent = 'Ошибка, попробуйте ещё раз';
          e.target.disabled = false; e.target.textContent = 'Оплатить (демо)'; }}
}});
</script></body></html>""")


class DemoConfirm(BaseModel):
    order_id: int


@app.post("/api/demo/confirm")
async def demo_confirm(data: DemoConfirm) -> JSONResponse:
    if cfg.yookassa_enabled:
        raise HTTPException(404, "Демо-оплата отключена")
    ok = await _mark_paid_and_notify(data.order_id)
    if not ok:
        raise HTTPException(404, "Заказ не найден")
    return JSONResponse({"ok": True})


# ---------- админ: включить/выключить продажи ----------

@app.post("/api/admin/sales")
async def admin_sales(data: SalesToggle, x_admin_token: str = Header(default="")) -> JSONResponse:
    if x_admin_token != cfg.admin_token:
        raise HTTPException(403, "Неверный токен администратора")
    await store.set_sales_enabled(data.enabled)
    return JSONResponse({"ok": True, "sales_enabled": data.enabled})


# ---------- страницы ----------

@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/success", response_class=FileResponse)
async def success() -> FileResponse:
    return FileResponse(STATIC_DIR / "success.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
