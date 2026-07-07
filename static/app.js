"use strict";

// Состояние
let CATALOG = {};        // id -> product
let MIN_ORDER = 0;
const cart = new Map();  // id -> qty
const CART_KEY = "food-shop-cart";

// Утилиты
const $ = (sel) => document.querySelector(sel);
const rub = (n) => n.toLocaleString("ru-RU") + " ₽";

function saveCart() {
  localStorage.setItem(CART_KEY, JSON.stringify([...cart.entries()]));
}
function loadCart() {
  try {
    const raw = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    for (const [id, qty] of raw) if (CATALOG[id]) cart.set(id, qty);
  } catch { /* игнорируем битый localStorage */ }
}

function cartTotal() {
  let sum = 0;
  for (const [id, qty] of cart) sum += CATALOG[id].price * qty;
  return sum;
}
function cartCount() {
  let n = 0;
  for (const qty of cart.values()) n += qty;
  return n;
}

// --- Рендер каталога ---
function renderCatalog() {
  const grid = $("#catalog-grid");
  grid.innerHTML = "";
  for (const p of Object.values(CATALOG)) {
    const inCart = cart.get(p.id) || 0;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card__img">${p.emoji}</div>
      <div class="card__body">
        <span class="card__cat">${p.cat}</span>
        <div class="card__name">${p.name}</div>
        <div class="card__desc">${p.desc}</div>
        <div class="card__row">
          <div class="card__price">${rub(p.price)} <span class="card__unit">/ ${p.unit}</span></div>
          <div data-control="${p.id}"></div>
        </div>
      </div>`;
    grid.appendChild(card);
    renderCardControl(p.id);
  }
}

function renderCardControl(id) {
  const holder = document.querySelector(`[data-control="${id}"]`);
  if (!holder) return;
  const qty = cart.get(id) || 0;
  if (qty === 0) {
    holder.innerHTML = `<button class="btn" data-add="${id}">В корзину</button>`;
  } else {
    holder.innerHTML =
      `<div class="qty"><button data-dec="${id}">−</button><span>${qty}</span><button data-inc="${id}">+</button></div>`;
  }
}

// --- Изменение корзины ---
function setQty(id, qty) {
  if (qty <= 0) cart.delete(id);
  else cart.set(id, qty);
  saveCart();
  renderCardControl(id);
  updateCartUI();
}
function addToCart(id) { setQty(id, (cart.get(id) || 0) + 1); }
function incCart(id) { setQty(id, (cart.get(id) || 0) + 1); }
function decCart(id) { setQty(id, (cart.get(id) || 0) - 1); }

function updateCartUI() {
  $("#cart-count").textContent = cartCount();
  const total = cartTotal();
  $("#cart-total").textContent = rub(total);
  $("#checkout-total").textContent = rub(total);

  // список в корзине
  const box = $("#cart-items");
  if (cart.size === 0) {
    box.innerHTML = `<p class="cart__empty">Корзина пуста</p>`;
  } else {
    box.innerHTML = "";
    for (const [id, qty] of cart) {
      const p = CATALOG[id];
      const line = document.createElement("div");
      line.className = "cart-line";
      line.innerHTML = `
        <div class="cart-line__emoji">${p.emoji}</div>
        <div class="cart-line__info">
          <div class="cart-line__name">${p.name}</div>
          <div class="cart-line__price">${rub(p.price)} × ${qty} = ${rub(p.price * qty)}</div>
        </div>
        <div class="qty"><button data-dec="${id}">−</button><span>${qty}</span><button data-inc="${id}">+</button></div>`;
      box.appendChild(line);
    }
  }

  // подсказка про минимальную сумму + блокировка кнопки
  const enough = total >= MIN_ORDER;
  const hint = $("#min-order-hint");
  hint.textContent = enough ? "" : `Минимальный заказ ${rub(MIN_ORDER)} — добавьте ещё на ${rub(MIN_ORDER - total)}`;
  $("#checkout-btn").disabled = !enough || cart.size === 0;
}

// --- Открытие/закрытие панелей ---
function openCart() { $("#cart").hidden = false; $("#cart-overlay").hidden = false; }
function closeCart() { $("#cart").hidden = true; $("#cart-overlay").hidden = true; }
function openCheckout() {
  $("#checkout").hidden = false; $("#checkout-overlay").hidden = false;
  $("#checkout-status").textContent = "";
}
function closeCheckout() { $("#checkout").hidden = true; $("#checkout-overlay").hidden = true; }

// --- Отправка заказа ---
async function submitOrder(e) {
  e.preventDefault();
  const form = e.target;
  const status = $("#checkout-status");
  status.textContent = ""; status.className = "";

  const payload = {
    customer: form.customer.value.trim(),
    phone: form.phone.value.trim(),
    address: form.address.value.trim(),
    comment: form.comment.value.trim(),
    pay_method: form.pay_method.value,
    items: [...cart.entries()].map(([id, qty]) => ({ id, qty })),
  };
  if (payload.customer.length < 2 || payload.phone.length < 5 || payload.address.length < 5) {
    status.textContent = "Заполните ФИО, телефон и адрес"; status.className = "err"; return;
  }

  const btn = $("#submit-order");
  btn.disabled = true; btn.textContent = "Отправляем…";
  try {
    const r = await fetch("/api/order", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!r.ok) {
      status.textContent = data.detail || "Не удалось оформить заказ";
      status.className = "err";
      return;
    }
    // очищаем корзину и уводим либо на оплату, либо на «спасибо»
    cart.clear(); saveCart();
    if (data.confirmation_url) location.href = data.confirmation_url;
    else location.href = data.redirect;
  } catch {
    status.textContent = "Нет связи с сервером, попробуйте ещё раз";
    status.className = "err";
  } finally {
    btn.disabled = false; btn.textContent = "Подтвердить заказ";
  }
}

// --- Делегирование кликов ---
document.addEventListener("click", (e) => {
  const t = e.target;
  if (t.dataset.add) addToCart(t.dataset.add);
  else if (t.dataset.inc) incCart(t.dataset.inc);
  else if (t.dataset.dec) decCart(t.dataset.dec);
});

// --- Инициализация ---
async function init() {
  $("#cart-btn").addEventListener("click", openCart);
  $("#cart-close").addEventListener("click", closeCart);
  $("#cart-overlay").addEventListener("click", closeCart);
  $("#checkout-btn").addEventListener("click", () => { closeCart(); openCheckout(); });
  $("#checkout-close").addEventListener("click", closeCheckout);
  $("#checkout-overlay").addEventListener("click", closeCheckout);
  $("#checkout-form").addEventListener("submit", submitOrder);

  try {
    const r = await fetch("/api/catalog");
    const data = await r.json();
    MIN_ORDER = data.min_order;
    for (const p of data.products) CATALOG[p.id] = p;
    $("#min-order-text").textContent = rub(MIN_ORDER);

    if (!data.sales_enabled) {
      $("#paused-banner").hidden = false;
      // прячем возможность заказать
      $("#cart-btn").style.display = "none";
    }
    $("#catalog-loading")?.remove();
    loadCart();
    renderCatalog();
    updateCartUI();
  } catch {
    $("#catalog-grid").innerHTML = `<p class="muted">Не удалось загрузить каталог. Обновите страницу.</p>`;
  }
}

init();
