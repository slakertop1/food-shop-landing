"""Каталог, заказы (SQLite) и настройки магазина (флаг «продажи включены»)."""

import json
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

_PRODUCTS_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer    TEXT NOT NULL,
    phone       TEXT NOT NULL,
    address     TEXT NOT NULL,
    comment     TEXT,
    items_json  TEXT NOT NULL,
    total       INTEGER NOT NULL,
    pay_method  TEXT NOT NULL,          -- 'online' | 'cod'
    status      TEXT NOT NULL DEFAULT 'new',  -- new | awaiting_payment | paid | canceled
    payment_id  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    cat: str
    price: int
    unit: str
    emoji: str
    desc: str


def load_catalog() -> dict[str, Product]:
    raw = json.loads(_PRODUCTS_FILE.read_text(encoding="utf-8"))
    return {p["id"]: Product(**p) for p in raw}


class Store:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self.catalog: dict[str, Product] = load_catalog()

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA)
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('sales_enabled', '1')"
            )
            await db.commit()

    # --- настройки ---

    async def sales_enabled(self) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'sales_enabled'"
            ) as cur:
                row = await cur.fetchone()
                return row is not None and row[0] == "1"

    async def set_sales_enabled(self, enabled: bool) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE settings SET value = ? WHERE key = 'sales_enabled'",
                ("1" if enabled else "0",),
            )
            await db.commit()

    # --- заказы ---

    async def create_order(
        self,
        customer: str,
        phone: str,
        address: str,
        comment: str,
        items: list[dict],
        total: int,
        pay_method: str,
        status: str,
    ) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "INSERT INTO orders (customer, phone, address, comment, items_json, "
                "total, pay_method, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (customer, phone, address, comment,
                 json.dumps(items, ensure_ascii=False), total, pay_method, status),
            )
            await db.commit()
            return cur.lastrowid

    async def attach_payment(self, order_id: int, payment_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE orders SET payment_id = ?, status = 'awaiting_payment' WHERE id = ?",
                (payment_id, order_id),
            )
            await db.commit()

    async def get_order(self, order_id: int) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def find_order_by_payment(self, payment_id: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM orders WHERE payment_id = ?", (payment_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def set_status(self, order_id: int, status: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE orders SET status = ? WHERE id = ?", (status, order_id)
            )
            await db.commit()
