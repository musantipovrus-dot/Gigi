from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
import asyncio
import sqlite3
import time
import os

# ==================== ТВОИ ДАННЫЕ ====================
API_ID = 30898826
API_HASH = "a0e2274e1c075b526cdeb95bfda0ccf5"
BOT_TOKEN = "8335083958:AAEN3HqQvE0u1KxqAjBYC9kFK8ENYVGWRIQ"
ADMIN_ID = 7489815425
TON_WALLET = "UQCEl_t-XmOV-K2LDpFrtK07td9t_pTmYvFaDHAU4zZuAPxa"

PROMOCODES = {
    "Malot": 5,
    "Lala": 1000
}

conn = sqlite3.connect("autosender.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, subscription_end INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, user_id INTEGER, session_name TEXT, phone TEXT)''')
conn.commit()

app = Client("feAutoSender", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Мои рассылки", callback_data="my_mailings")],
        [InlineKeyboardButton("👤 Аккаунты", callback_data="accounts")],
        [InlineKeyboardButton("💰 Подписка", callback_data="subscription")],
        [InlineKeyboardButton("🤝 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ])

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply(
        "👋 **fe|AutoSender** MALOT Edition\n\n"
        "Бот запущен и работает!\n\n"
        "Промокод **Lala** — 1000 дней бесплатно\n"
        "Промокод **Malot** — 5 дней бесплатно",
        reply_markup=main_menu()
    )

@app.on_callback_query(filters.regex("subscription"))
async def subscription_menu(client, query: CallbackQuery):
    text = f"""💰 Подписка

Цена: 1 TON = 30 дней
Кошелёк: `{TON_WALLET}`

После оплаты в комментарии укажи свой ID.

Промокоды:
• Malot — +5 дней
• Lala — +1000 дней"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton("Назад", callback_data="main")]
    ])
    await query.edit_message_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex("enter_promo"))
async def enter_promo(client, query):
    await query.message.reply("Отправь промокод одним сообщением:")

@app.on_message(filters.text)
async def promo_handler(client, message: Message):
    code = message.text.strip()
    user_id = message.from_user.id

    if code in PROMOCODES:
        days = PROMOCODES[code]
        new_end = int(time.time()) + (days * 86400)
        cursor.execute("INSERT OR REPLACE INTO users (user_id, subscription_end) VALUES (?, ?)", (user_id, new_end))
        conn.commit()
        await message.reply(f"✅ Промокод **{code}** активирован!\n+{days} дней подписки.")
    else:
        await message.reply("❌ Неизвестный промокод. Используй кнопки меню.")

@app.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    if query.data == "main":
        await query.edit_message_text("👋 Главное меню", reply_markup=main_menu())
    else:
        await query.edit_message_text(
            "🔧 Этот раздел пока в разработке.\n\nСкоро будет полная рассылка, добавление аккаунтов и автоответчики.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main")]])
        )

async def main():
    print("MALOT fe|AutoSender — УСПЕШНО ЗАПУЩЕН С НОВЫМ ТОКЕНОМ!")
    await app.start()
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
