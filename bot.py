from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
import asyncio
import sqlite3
import time
import os
import requests

# ==================== ТВОИ ДАННЫЕ ====================
API_ID = 30898826
API_HASH = "a0e2274e1c075b526cdeb95bfda0ccf5"
BOT_TOKEN = "8698009353:AAFqVVcStd9mMKhcnQuDScTOJ1ZEadGsFsY"
ADMIN_ID = 7489815425
TON_WALLET = "UQCEl_t-XmOV-K2LDpFrtK07td9t_pTmYvFaDHAU4zZuAPxa"

PROMOCODES = {
    "Malot": 5,
    "Lala": 1000
}

# База данных
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
        "Бот запущен и полностью работает!\n\n"
        "Промокод **Lala** — +1000 дней бесплатно\n"
        "Промокод **Malot** — +5 дней бесплатно",
        reply_markup=main_menu()
    )

# Подписка
@app.on_callback_query(filters.regex("subscription"))
async def subscription_menu(client, query: CallbackQuery):
    text = f"""💰 Подписка

Цена: 1 TON = 30 дней
Кошелёк для оплаты:
`{TON_WALLET}`

После оплаты в комментарии укажи свой Telegram ID.

Промокоды:
• Malot — +5 дней
• Lala — +1000 дней"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton("Назад", callback_data="main")]
    ])
    await query.edit_message_text(text, reply_markup=kb)

# Ввод промокода
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
        await message.reply(f"✅ Промокод **{code}** успешно активирован!\nДобавлено **{days} дней** подписки.")
    else:
        await message.reply("❌ Неизвестный промокод.\nИспользуй кнопки меню.")

# Обработка всех кнопок
@app.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    if query.data == "main":
        await query.edit_message_text("👋 Главное меню fe|AutoSender", reply_markup=main_menu())
    else:
        await query.edit_message_text(
            "🔧 Этот раздел пока в разработке.\n\n"
            "Скоро будет:\n"
            "• Добавление аккаунтов\n"
            "• Реальная рассылка с интервалом\n"
            "• Автоответчики",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main")]])
        )

async def main():
    print("MALOT fe|AutoSender — БОТ УСПЕШНО ЗАПУЩЕН!")
    await app.start()
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
