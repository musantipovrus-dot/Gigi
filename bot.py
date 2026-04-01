from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
import asyncio
import os

API_ID = 30898826
API_HASH = "a0e2274e1c075b526cdeb95bfda0ccf5"
BOT_TOKEN = "8698009353:AAFqVVcStd9mMKhcnQuDScTOJ1ZEadGsFsY"

app = Client("feAutoSender", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Мои рассылки", callback_data="my_mailings")],
        [InlineKeyboardButton("👤 Аккаунты", callback_data="accounts")],
        [InlineKeyboardButton("💰 Подписка", callback_data="subscription")],
        [InlineKeyboardButton("🤝 Рефералы", callback_data="referrals")]
    ])

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply(
        "👋 **fe|AutoSender** MALOT Edition\n\n"
        "Бот запущен успешно!\n\n"
        "Промокод **Lala** = 1000 дней бесплатно\n"
        "Промокод **Malot** = 5 дней бесплатно",
        reply_markup=main_menu()
    )

@app.on_callback_query(filters.regex("subscription"))
async def subscription_menu(client, query: CallbackQuery):
    await query.edit_message_text(
        "💰 Подписка\n\n1 TON = 30 дней\n\nПромокод Lala — 1000 дней",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main")]])
    )

@app.on_callback_query()
async def all_buttons(client, query: CallbackQuery):
    await query.edit_message_text(
        "🔧 Раздел в разработке.\n\nСкоро будет полная рассылка и добавление аккаунтов.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main")]])
    )

async def main():
    print("MALOT AutoSender — ЗАПУЩЕН БЕЗ ОШИБОК!")
    await app.start()
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
