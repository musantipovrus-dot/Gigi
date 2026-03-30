import asyncio
import json
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
DB_PATH = os.getenv("BOT_DB_PATH", "bot.sqlite3")
DEFAULT_TZ = os.getenv("BOT_DEFAULT_TZ", "Europe/Moscow")
FREE_DAYS_ON_START = 7
PROMO_CODE_GOLD = "gold"
PROMO_GOLD_DAYS = 100
CHECK_EVERY_SECONDS = 10

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("tg-broadcast-bot")

(
    CREATE_NAME,
    CREATE_TEXT,
    CREATE_PHOTO,
    CREATE_TARGETS,
    CREATE_INTERVAL,
    CREATE_WINDOW,
    PROMO_INPUT,
    ADD_TARGET_FORWARD,
    EDIT_TEXT_INPUT,
    EDIT_PHOTO_INPUT,
    EDIT_INTERVAL_INPUT,
    EDIT_WINDOW_INPUT,
) = range(12)


@dataclass
class UserRecord:
    user_id: int
    username: str
    ref_code: str
    referred_by: Optional[int]
    referral_balance: float
    subscription_until: Optional[str]


class Database:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    ref_code TEXT UNIQUE,
                    referred_by INTEGER,
                    referral_balance REAL DEFAULT 0,
                    subscription_until TEXT,
                    created_at TEXT NOT NULL,
                    promo_used TEXT,
                    FOREIGN KEY(referred_by) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    chat_type TEXT NOT NULL,
                    username TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(owner_id, chat_id)
                );

                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    photo_file_id TEXT,
                    interval_seconds INTEGER NOT NULL,
                    active_from TEXT NOT NULL,
                    active_to TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    target_ids_json TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    last_sent_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES users(user_id)
                );
                """
            )

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def get_user_by_ref(self, ref_code: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE ref_code = ?", (ref_code,)).fetchone()

    def ensure_user(self, user_id: int, username: str, referred_by: Optional[int] = None) -> sqlite3.Row:
        existing = self.get_user(user_id)
        now = utc_now_iso()
        if existing:
            with self.connect() as conn:
                conn.execute(
                    "UPDATE users SET username = ? WHERE user_id = ?",
                    (username, user_id),
                )
            return self.get_user(user_id)

        ref_code = "ref_" + secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]
        sub_until = (datetime.now(timezone.utc) + timedelta(days=FREE_DAYS_ON_START)).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, username, ref_code, referred_by, subscription_until, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, ref_code, referred_by, sub_until, now),
            )
        return self.get_user(user_id)

    def activate_promo(self, user_id: int, promo_code: str, days: int) -> tuple[bool, str]:
        user = self.get_user(user_id)
        if not user:
            return False, "Пользователь не найден."
        if user["promo_used"] == promo_code:
            return False, "Этот промокод уже использован."

        current_until = parse_dt(user["subscription_until"]) or datetime.now(timezone.utc)
        base = current_until if current_until > datetime.now(timezone.utc) else datetime.now(timezone.utc)
        new_until = base + timedelta(days=days)

        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET subscription_until = ?, promo_used = ? WHERE user_id = ?",
                (new_until.isoformat(), promo_code, user_id),
            )
        return True, new_until.isoformat()

    def targets_for_user(self, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM targets WHERE owner_id = ? ORDER BY title COLLATE NOCASE",
                (owner_id,),
            ).fetchall()

    def add_target(self, owner_id: int, chat_id: int, title: str, chat_type: str, username: Optional[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO targets(owner_id, chat_id, title, chat_type, username, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_id, chat_id) DO UPDATE SET
                    title = excluded.title,
                    chat_type = excluded.chat_type,
                    username = excluded.username
                """,
                (owner_id, chat_id, title, chat_type, username, utc_now_iso()),
            )

    def delete_target(self, owner_id: int, target_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM targets WHERE owner_id = ? AND id = ?", (owner_id, target_id))

    def create_broadcast(self, owner_id: int, data: dict) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO broadcasts(
                    owner_id, name, text, photo_file_id, interval_seconds,
                    active_from, active_to, timezone, target_ids_json,
                    is_active, last_sent_at, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    owner_id,
                    data["name"],
                    data["text"],
                    data.get("photo_file_id"),
                    data["interval_seconds"],
                    data["active_from"],
                    data["active_to"],
                    data["timezone"],
                    json.dumps(data["target_ids"]),
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def broadcasts_for_user(self, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM broadcasts WHERE owner_id = ? ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()

    def get_broadcast(self, owner_id: int, broadcast_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM broadcasts WHERE owner_id = ? AND id = ?",
                (owner_id, broadcast_id),
            ).fetchone()

    def update_broadcast_field(self, owner_id: int, broadcast_id: int, field: str, value):
        allowed = {
            "name",
            "text",
            "photo_file_id",
            "interval_seconds",
            "active_from",
            "active_to",
            "timezone",
            "target_ids_json",
            "is_active",
            "last_sent_at",
        }
        if field not in allowed:
            raise ValueError("Unsupported field")
        with self.connect() as conn:
            conn.execute(
                f"UPDATE broadcasts SET {field} = ?, updated_at = ? WHERE owner_id = ? AND id = ?",
                (value, utc_now_iso(), owner_id, broadcast_id),
            )

    def delete_broadcast(self, owner_id: int, broadcast_id: int):
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM broadcasts WHERE owner_id = ? AND id = ?",
                (owner_id, broadcast_id),
            )

    def all_active_broadcasts(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM broadcasts WHERE is_active = 1").fetchall()

    def count_referred(self, owner_id: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE referred_by = ?",
                (owner_id,),
            ).fetchone()
            return int(row["cnt"])


db = Database(DB_PATH)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def safe_username(user) -> str:
    return user.username or user.full_name or f"user_{user.id}"


def is_subscription_active(user_row: sqlite3.Row) -> bool:
    until = parse_dt(user_row["subscription_until"])
    return bool(until and until > datetime.now(timezone.utc))


def subscription_days_left(user_row: sqlite3.Row) -> int:
    until = parse_dt(user_row["subscription_until"])
    if not until:
        return 0
    delta = until - datetime.now(timezone.utc)
    return max(0, delta.days)


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 Мои рассылки", callback_data="menu:broadcasts"),
                InlineKeyboardButton("👤 Аккаунты", callback_data="menu:targets"),
            ],
            [
                InlineKeyboardButton("💳 Подписка", callback_data="menu:subscription"),
                InlineKeyboardButton("🤝 Рефералы", callback_data="menu:referrals"),
            ],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="menu:help")],
        ]
    )


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]])


def bool_status(flag: bool) -> str:
    return "🟢 Активна" if flag else "🔴 Остановлена"


def user_targets_map(owner_id: int) -> dict[int, sqlite3.Row]:
    return {row["id"]: row for row in db.targets_for_user(owner_id)}


def format_targets_list(owner_id: int, target_ids: list[int]) -> str:
    mapping = user_targets_map(owner_id)
    parts = []
    for tid in target_ids:
        target = mapping.get(tid)
        if target:
            parts.append(f"• {target['title']}")
    return "\n".join(parts) if parts else "Не выбраны"


def parse_target_ids(value: str) -> list[int]:
    try:
        data = json.loads(value or "[]")
        return [int(x) for x in data]
    except Exception:
        return []


def create_target_picker(owner_id: int, selected: list[int], done_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    rows = []
    for target in db.targets_for_user(owner_id):
        mark = "✅" if target["id"] in selected else "⬜"
        rows.append([
            InlineKeyboardButton(
                f"{mark} {target['title']}", callback_data=f"pick:{target['id']}"
            )
        ])
    rows.append([InlineKeyboardButton("✅ Готово", callback_data=done_cb)])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


def broadcast_card(owner_id: int, row: sqlite3.Row) -> str:
    targets = parse_target_ids(row["target_ids_json"])
    last_sent = parse_dt(row["last_sent_at"])
    last_sent_text = last_sent.astimezone(ZoneInfo(row["timezone"])).strftime("%d.%m.%Y %H:%M") if last_sent else "ещё не было"
    return (
        f"📋 Рассылка: {row['name']}\n\n"
        f"Статус: {bool_status(bool(row['is_active']))}\n"
        f"Интервал: {row['interval_seconds']} сек\n"
        f"Время активности: {row['active_from']}-{row['active_to']} ({row['timezone']})\n"
        f"Фото: {'есть' if row['photo_file_id'] else 'нет'}\n"
        f"Целевых чатов: {len(targets)}\n"
        f"Последняя отправка: {last_sent_text}\n\n"
        f"Текст:\n{row['text'][:700]}"
    )


def broadcast_actions_kb(row: sqlite3.Row) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Остановить" if row["is_active"] else "🟢 Запустить"
    bid = row["id"]
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(toggle_label, callback_data=f"bc_toggle:{bid}")],
            [
                InlineKeyboardButton("📝 Текст", callback_data=f"bc_text:{bid}"),
                InlineKeyboardButton("🖼 Фото", callback_data=f"bc_photo:{bid}"),
            ],
            [
                InlineKeyboardButton("🎯 Целевые чаты", callback_data=f"bc_targets:{bid}"),
                InlineKeyboardButton("⏱ Интервал", callback_data=f"bc_interval:{bid}"),
            ],
            [
                InlineKeyboardButton("🕘 Время активности", callback_data=f"bc_window:{bid}"),
                InlineKeyboardButton("❌ Удалить", callback_data=f"bc_delete:{bid}"),
            ],
            [InlineKeyboardButton("◀️ Назад", callback_data="menu:broadcasts")],
        ]
    )


async def ensure_private(update: Update):
    if update.effective_chat and update.effective_chat.type != ChatType.PRIVATE:
        await update.effective_message.reply_text(
            "Этим меню нужно пользоваться в личке с ботом.",
        )
        return False
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_private(update):
        return
    tg_user = update.effective_user
    payload = None
    if context.args:
        payload = context.args[0]

    referred_by = None
    if payload and payload.startswith("ref_"):
        ref_owner = db.get_user_by_ref(payload)
        if ref_owner and ref_owner["user_id"] != tg_user.id:
            referred_by = int(ref_owner["user_id"])

    user = db.ensure_user(tg_user.id, safe_username(tg_user), referred_by)

    if payload and payload.lower() == PROMO_CODE_GOLD:
        ok, result = db.activate_promo(tg_user.id, PROMO_CODE_GOLD, PROMO_GOLD_DAYS)
        if ok:
            await update.message.reply_text(
                f"✅ Промокод {PROMO_CODE_GOLD} активирован. Подписка продлена до {format_until(result)}"
            )
        else:
            await update.message.reply_text(f"⚠️ {result}")

    text = (
        "📋 Главное меню\n\n"
        "Здесь ты сам выбираешь всё вручную: создаёшь рассылки, добавляешь цели, настраиваешь фото, интервал и время активности.\n\n"
        "Важно: бот может публиковать только в те чаты/группы/каналы, где он добавлен и у него есть права."
    )
    await update.message.reply_text(text, reply_markup=main_menu_kb())


async def menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📋 Главное меню\n\nВыберите раздел:", reply_markup=main_menu_kb()
    )


async def menu_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ Помощь\n\n"
        "1. Добавь бота в нужный чат/группу/канал.\n"
        "2. Выдай ему право отправлять сообщения. Для канала лучше сделать админом.\n"
        "3. В личке открой раздел 'Аккаунты' и добавь цель, переслав любое сообщение или пост из нужного чата/канала.\n"
        "4. Создай рассылку, выбери цели, интервал, время активности и при необходимости фото.\n\n"
        "Поддерживается: текст, фото+подпись, выбор нескольких целей, запуск/остановка, промокод gold на 100 дней."
    )
    await query.edit_message_text(text, reply_markup=back_main_kb())


async def menu_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = db.get_user(query.from_user.id)
    until = user["subscription_until"]
    active = is_subscription_active(user)
    days = subscription_days_left(user)
    text = (
        "💳 Ваша подписка\n\n"
        f"{'✅ Подписка активна' if active else '❌ Подписка неактивна'}\n"
        f"Действует до: {format_until(until) if until else 'не задано'}\n"
        f"Осталось дней: {days}\n\n"
        "Стоимость продления здесь не подключена автоматически — оставлен раздел под дальнейшую интеграцию оплаты.\n"
        "Промокод gold даёт 100 дней бесплатно."
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎟 Ввести промокод", callback_data="sub:promo"),
                InlineKeyboardButton("🔄 Обновить", callback_data="menu:subscription"),
            ],
            [InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")],
        ]
    )
    await query.edit_message_text(text, reply_markup=kb)


async def prompt_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎟 Введите промокод одним сообщением:\n\nДоступный тестовый код: gold",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="menu:subscription")]]
        ),
    )
    return PROMO_INPUT


async def apply_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip().lower()
    if code != PROMO_CODE_GOLD:
        await update.message.reply_text(
            "❌ Промокод не найден. Проверь правильность и попробуй ещё раз.",
            reply_markup=back_main_kb(),
        )
        return ConversationHandler.END

    ok, result = db.activate_promo(update.effective_user.id, code, PROMO_GOLD_DAYS)
    if ok:
        await update.message.reply_text(
            f"✅ Промокод активирован. Подписка действует до {format_until(result)}",
            reply_markup=back_main_kb(),
        )
    else:
        await update.message.reply_text(f"⚠️ {result}", reply_markup=back_main_kb())
    return ConversationHandler.END


async def menu_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = db.get_user(query.from_user.id)
    bot_username = context.application.bot_data.get("bot_username", "your_bot")
    invited = db.count_referred(query.from_user.id)
    ref_link = f"https://t.me/{bot_username}?start={user['ref_code']}"
    text = (
        "🤝 Реферальная программа\n\n"
        f"Ваша реферальная ссылка:\n{ref_link}\n\n"
        f"👥 Приглашено: {invited}\n"
        f"💰 Баланс: {user['referral_balance']:.2f} USDT\n"
        "📈 Процент с покупок: 25.0%\n"
        "📤 Минимум для вывода: 1.0 USDT\n\n"
        "Сейчас подключен только интерфейс и учёт приглашённых. Реальную оплату и вывод нужно интегрировать отдельно."
    )
    await query.edit_message_text(text, reply_markup=back_main_kb())


async def menu_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    targets = db.targets_for_user(query.from_user.id)
    if not targets:
        text = (
            "👤 Ваши аккаунты / цели\n\n"
            "У вас пока нет добавленных чатов/каналов.\n\n"
            "Чтобы добавить цель, перешлите боту любое сообщение или пост из нужного чата/канала.\n"
            "Перед этим добавь бота в тот чат/канал и выдай права на отправку сообщений."
        )
    else:
        body = "\n".join([f"• {t['title']} ({t['chat_type']})" for t in targets[:20]])
        text = (
            "👤 Ваши аккаунты / цели\n\n"
            f"Подключено: {len(targets)}\n\n{body}\n\n"
            "Можно добавить новые цели пересылкой сообщения из нужного чата/канала."
        )

    rows = [[InlineKeyboardButton("➕ Добавить цель", callback_data="targets:add")]]
    for t in targets[:10]:
        rows.append([InlineKeyboardButton(f"❌ Удалить: {t['title']}", callback_data=f"targets:del:{t['id']}")])
    rows.append([InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def targets_add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ Добавление цели\n\nПерешли сюда любое сообщение или пост из нужного чата/группы/канала.\n\n"
        "Важно: бот должен быть добавлен в эту цель и иметь право отправлять туда сообщения.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="menu:targets")]]
        ),
    )
    return ADD_TARGET_FORWARD


async def targets_add_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    info = None

    if msg.forward_from_chat:
        chat = msg.forward_from_chat
        info = (chat.id, chat.title or chat.username or str(chat.id), chat.type, chat.username)
    elif msg.sender_chat:
        chat = msg.sender_chat
        info = (chat.id, chat.title or chat.username or str(chat.id), chat.type, chat.username)

    if not info:
        await update.message.reply_text(
            "Не удалось определить чат/канал. Перешли именно сообщение или пост из нужной цели.",
            reply_markup=back_main_kb(),
        )
        return ConversationHandler.END

    db.add_target(update.effective_user.id, info[0], info[1], info[2], info[3])
    await update.message.reply_text(
        f"✅ Цель добавлена: {info[1]}\n\nТеперь её можно выбрать в рассылке.",
        reply_markup=back_main_kb(),
    )
    return ConversationHandler.END


async def targets_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, tid = query.data.split(":")
    db.delete_target(query.from_user.id, int(tid))
    await menu_targets(update, context)


async def menu_broadcasts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db.broadcasts_for_user(query.from_user.id)
    if not rows:
        text = "📋 Ваши рассылки\n\nУ вас пока нет рассылок.\n\nВыберите рассылку или создайте новую:"
    else:
        text = "📋 Ваши рассылки\n\nВыберите рассылку:"

    kb_rows = [[InlineKeyboardButton("➕ Создать рассылку", callback_data="bc_new")]]
    for row in rows[:20]:
        icon = "🟢" if row["is_active"] else "⚪"
        kb_rows.append([InlineKeyboardButton(f"{icon} {row['name']}", callback_data=f"bc_open:{row['id']}")])
    kb_rows.append([InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb_rows))


async def create_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not db.targets_for_user(query.from_user.id):
        await query.edit_message_text(
            "Сначала добавь хотя бы одну цель в разделе 'Аккаунты'.",
            reply_markup=back_main_kb(),
        )
        return ConversationHandler.END

    context.user_data["new_bc"] = {
        "timezone": DEFAULT_TZ,
        "target_ids": [],
    }
    await query.edit_message_text(
        "➕ Создание рассылки\n\nШаг 1/6: Введите название рассылки:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="menu:broadcasts")]]
        ),
    )
    return CREATE_NAME


async def create_broadcast_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if len(name) < 2:
        await update.message.reply_text("Название слишком короткое. Попробуй ещё раз.")
        return CREATE_NAME
    context.user_data["new_bc"]["name"] = name
    await update.message.reply_text(
        "Шаг 2/6: Отправьте текст рассылки.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="menu:broadcasts")]]
        ),
    )
    return CREATE_TEXT


async def create_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Текст пустой. Отправь текст рассылки.")
        return CREATE_TEXT
    context.user_data["new_bc"]["text"] = text
    await update.message.reply_text(
        "Шаг 3/6: Если нужно фото — отправь его сейчас. Если фото не нужно, нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("⏭ Без фото", callback_data="bc_nophoto")],
                [InlineKeyboardButton("❌ Отмена", callback_data="menu:broadcasts")],
            ]
        ),
    )
    return CREATE_PHOTO


async def create_broadcast_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Нужно отправить фото, либо нажать 'Без фото'.")
        return CREATE_PHOTO
    file_id = update.message.photo[-1].file_id
    context.user_data["new_bc"]["photo_file_id"] = file_id
    selected = context.user_data["new_bc"].get("target_ids", [])
    await update.message.reply_text(
        "Шаг 4/6: Выберите целевые чаты/каналы:",
        reply_markup=create_target_picker(
            update.effective_user.id, selected, "pick_done:new", "menu:broadcasts"
        ),
    )
    return CREATE_TARGETS


async def create_broadcast_skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_bc"]["photo_file_id"] = None
    selected = context.user_data["new_bc"].get("target_ids", [])
    await query.edit_message_text(
        "Шаг 4/6: Выберите целевые чаты/каналы:",
        reply_markup=create_target_picker(
            query.from_user.id, selected, "pick_done:new", "menu:broadcasts"
        ),
    )
    return CREATE_TARGETS


async def create_broadcast_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split(":")[1])
    selected = context.user_data["new_bc"].setdefault("target_ids", [])
    if target_id in selected:
        selected.remove(target_id)
    else:
        selected.append(target_id)
    await query.edit_message_reply_markup(
        reply_markup=create_target_picker(
            query.from_user.id, selected, "pick_done:new", "menu:broadcasts"
        )
    )
    return CREATE_TARGETS


async def create_broadcast_targets_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = context.user_data["new_bc"].get("target_ids", [])
    if not selected:
        await query.answer("Выбери хотя бы одну цель.", show_alert=True)
        return CREATE_TARGETS
    await query.edit_message_text(
        "Шаг 5/6: Введите интервал в секундах. Например: 100",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="menu:broadcasts")]]
        ),
    )
    return CREATE_INTERVAL


async def create_broadcast_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.isdigit() or int(text) < 30:
        await update.message.reply_text("Интервал должен быть числом не меньше 30 секунд.")
        return CREATE_INTERVAL
    context.user_data["new_bc"]["interval_seconds"] = int(text)
    await update.message.reply_text(
        f"Шаг 6/6: Введите время активности в формате ЧЧ:ММ-ЧЧ:ММ\n"
        f"Например: 09:00-23:59\n"
        f"Часовой пояс сейчас: {DEFAULT_TZ}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data="menu:broadcasts")]]
        ),
    )
    return CREATE_WINDOW


async def create_broadcast_window(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = (update.message.text or "").strip()
    parsed = parse_window(value)
    if not parsed:
        await update.message.reply_text("Неверный формат. Пример: 09:00-23:59")
        return CREATE_WINDOW

    data = context.user_data.get("new_bc", {})
    data["active_from"], data["active_to"] = parsed
    bc_id = db.create_broadcast(update.effective_user.id, data)
    row = db.get_broadcast(update.effective_user.id, bc_id)
    context.user_data.pop("new_bc", None)
    await update.message.reply_text(
        "✅ Рассылка создана. Ниже её карточка:",
    )
    await update.message.reply_text(
        broadcast_card(update.effective_user.id, row),
        reply_markup=broadcast_actions_kb(row),
    )
    return ConversationHandler.END


async def open_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    row = db.get_broadcast(query.from_user.id, bid)
    if not row:
        await query.answer("Рассылка не найдена", show_alert=True)
        return
    await query.edit_message_text(
        broadcast_card(query.from_user.id, row),
        reply_markup=broadcast_actions_kb(row),
    )


async def toggle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    row = db.get_broadcast(query.from_user.id, bid)
    if not row:
        return
    user = db.get_user(query.from_user.id)
    if not is_subscription_active(user):
        await query.answer("Подписка неактивна. Активируй промокод или продли подписку.", show_alert=True)
        return

    targets = parse_target_ids(row["target_ids_json"])
    if not targets:
        await query.answer("У рассылки нет целей.", show_alert=True)
        return
    db.update_broadcast_field(query.from_user.id, bid, "is_active", 0 if row["is_active"] else 1)
    row = db.get_broadcast(query.from_user.id, bid)
    await query.edit_message_text(
        broadcast_card(query.from_user.id, row),
        reply_markup=broadcast_actions_kb(row),
    )


async def delete_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    db.delete_broadcast(query.from_user.id, bid)
    await query.edit_message_text("❌ Рассылка удалена.", reply_markup=back_main_kb())


async def edit_text_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    context.user_data["edit_bid"] = bid
    await query.edit_message_text(
        "📝 Отправьте новый текст рассылки:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data=f"bc_open:{bid}")]]
        ),
    )
    return EDIT_TEXT_INPUT


async def edit_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bid = context.user_data.get("edit_bid")
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Текст пустой.")
        return EDIT_TEXT_INPUT
    db.update_broadcast_field(update.effective_user.id, bid, "text", text)
    row = db.get_broadcast(update.effective_user.id, bid)
    context.user_data.pop("edit_bid", None)
    await update.message.reply_text(
        "✅ Текст обновлён.",
    )
    await update.message.reply_text(
        broadcast_card(update.effective_user.id, row), reply_markup=broadcast_actions_kb(row)
    )
    return ConversationHandler.END


async def edit_photo_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    context.user_data["edit_bid"] = bid
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗑 Убрать фото", callback_data=f"bc_photorm:{bid}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"bc_open:{bid}")],
        ]
    )
    await query.edit_message_text("🖼 Отправьте новое фото для рассылки:", reply_markup=kb)
    return EDIT_PHOTO_INPUT


async def edit_photo_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bid = context.user_data.get("edit_bid")
    if not update.message.photo:
        await update.message.reply_text("Нужно отправить фото.")
        return EDIT_PHOTO_INPUT
    file_id = update.message.photo[-1].file_id
    db.update_broadcast_field(update.effective_user.id, bid, "photo_file_id", file_id)
    row = db.get_broadcast(update.effective_user.id, bid)
    context.user_data.pop("edit_bid", None)
    await update.message.reply_text("✅ Фото обновлено.")
    await update.message.reply_text(
        broadcast_card(update.effective_user.id, row), reply_markup=broadcast_actions_kb(row)
    )
    return ConversationHandler.END


async def remove_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    db.update_broadcast_field(query.from_user.id, bid, "photo_file_id", None)
    row = db.get_broadcast(query.from_user.id, bid)
    context.user_data.pop("edit_bid", None)
    await query.edit_message_text(
        broadcast_card(query.from_user.id, row), reply_markup=broadcast_actions_kb(row)
    )
    return ConversationHandler.END


async def edit_interval_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    context.user_data["edit_bid"] = bid
    await query.edit_message_text(
        "⏱ Введите новый интервал в секундах, не меньше 30:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data=f"bc_open:{bid}")]]
        ),
    )
    return EDIT_INTERVAL_INPUT


async def edit_interval_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bid = context.user_data.get("edit_bid")
    value = (update.message.text or "").strip()
    if not value.isdigit() or int(value) < 30:
        await update.message.reply_text("Нужно число не меньше 30.")
        return EDIT_INTERVAL_INPUT
    db.update_broadcast_field(update.effective_user.id, bid, "interval_seconds", int(value))
    row = db.get_broadcast(update.effective_user.id, bid)
    context.user_data.pop("edit_bid", None)
    await update.message.reply_text("✅ Интервал обновлён.")
    await update.message.reply_text(
        broadcast_card(update.effective_user.id, row), reply_markup=broadcast_actions_kb(row)
    )
    return ConversationHandler.END


async def edit_window_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    context.user_data["edit_bid"] = bid
    await query.edit_message_text(
        "🕘 Введите новое окно активности в формате ЧЧ:ММ-ЧЧ:ММ\nНапример: 09:00-23:59",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отмена", callback_data=f"bc_open:{bid}")]]
        ),
    )
    return EDIT_WINDOW_INPUT


async def edit_window_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bid = context.user_data.get("edit_bid")
    value = (update.message.text or "").strip()
    parsed = parse_window(value)
    if not parsed:
        await update.message.reply_text("Неверный формат. Пример: 09:00-23:59")
        return EDIT_WINDOW_INPUT
    db.update_broadcast_field(update.effective_user.id, bid, "active_from", parsed[0])
    db.update_broadcast_field(update.effective_user.id, bid, "active_to", parsed[1])
    row = db.get_broadcast(update.effective_user.id, bid)
    context.user_data.pop("edit_bid", None)
    await update.message.reply_text("✅ Время активности обновлено.")
    await update.message.reply_text(
        broadcast_card(update.effective_user.id, row), reply_markup=broadcast_actions_kb(row)
    )
    return ConversationHandler.END


async def edit_targets_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[1])
    row = db.get_broadcast(query.from_user.id, bid)
    if not row:
        return ConversationHandler.END
    context.user_data["edit_bid"] = bid
    context.user_data["edit_target_ids"] = parse_target_ids(row["target_ids_json"])
    await query.edit_message_text(
        "🎯 Выберите цели для рассылки:",
        reply_markup=create_target_picker(
            query.from_user.id,
            context.user_data["edit_target_ids"],
            f"pick_done:edit:{bid}",
            f"bc_open:{bid}",
        ),
    )
    return CREATE_TARGETS


async def edit_targets_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split(":")[1])
    selected = context.user_data.setdefault("edit_target_ids", [])
    if target_id in selected:
        selected.remove(target_id)
    else:
        selected.append(target_id)
    bid = context.user_data.get("edit_bid")
    await query.edit_message_reply_markup(
        reply_markup=create_target_picker(
            query.from_user.id, selected, f"pick_done:edit:{bid}", f"bc_open:{bid}"
        )
    )
    return CREATE_TARGETS


async def edit_targets_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bid = int(query.data.split(":")[2])
    selected = context.user_data.get("edit_target_ids", [])
    if not selected:
        await query.answer("Выбери хотя бы одну цель.", show_alert=True)
        return CREATE_TARGETS
    db.update_broadcast_field(query.from_user.id, bid, "target_ids_json", json.dumps(selected))
    row = db.get_broadcast(query.from_user.id, bid)
    context.user_data.pop("edit_bid", None)
    context.user_data.pop("edit_target_ids", None)
    await query.edit_message_text(
        broadcast_card(query.from_user.id, row), reply_markup=broadcast_actions_kb(row)
    )
    return ConversationHandler.END


def parse_window(value: str) -> Optional[tuple[str, str]]:
    if "-" not in value:
        return None
    left, right = value.split("-", 1)
    try:
        datetime.strptime(left, "%H:%M")
        datetime.strptime(right, "%H:%M")
        return left, right
    except ValueError:
        return None


async def scheduler_loop(app: Application):
    await app.bot.initialize()
    while True:
        try:
            await process_due_broadcasts(app)
        except Exception:
            logger.exception("scheduler cycle failed")
        await asyncio.sleep(CHECK_EVERY_SECONDS)


async def process_due_broadcasts(app: Application):
    rows = db.all_active_broadcasts()
    now_utc = datetime.now(timezone.utc)
    for row in rows:
        user = db.get_user(row["owner_id"])
        if not user or not is_subscription_active(user):
            db.update_broadcast_field(row["owner_id"], row["id"], "is_active", 0)
            continue

        tz_name = row["timezone"] or DEFAULT_TZ
        try:
            local_now = now_utc.astimezone(ZoneInfo(tz_name))
        except Exception:
            local_now = now_utc.astimezone(ZoneInfo(DEFAULT_TZ))

        current_hm = local_now.strftime("%H:%M")
        if not (row["active_from"] <= current_hm <= row["active_to"]):
            continue

        last_sent = parse_dt(row["last_sent_at"])
        if last_sent and (now_utc - last_sent).total_seconds() < int(row["interval_seconds"]):
            continue

        target_ids = parse_target_ids(row["target_ids_json"])
        target_map = user_targets_map(row["owner_id"])

        success_sent = False
        for tid in target_ids:
            target = target_map.get(tid)
            if not target:
                continue
            try:
                if row["photo_file_id"]:
                    await app.bot.send_photo(
                        chat_id=target["chat_id"],
                        photo=row["photo_file_id"],
                        caption=row["text"][:1024],
                    )
                else:
                    await app.bot.send_message(
                        chat_id=target["chat_id"],
                        text=row["text"],
                    )
                success_sent = True
                await asyncio.sleep(0.2)
            except Exception as exc:
                logger.warning(
                    "send failed broadcast=%s chat=%s error=%s",
                    row["id"],
                    target["chat_id"],
                    exc,
                )
        if success_sent:
            db.update_broadcast_field(row["owner_id"], row["id"], "last_sent_at", now_utc.isoformat())


async def post_init(app: Application):
    me = await app.bot.get_me()
    app.bot_data["bot_username"] = me.username
    app.create_task(scheduler_loop(app))


def format_until(value: Optional[str]) -> str:
    dt = parse_dt(value)
    if not dt:
        return "—"
    return dt.astimezone(ZoneInfo(DEFAULT_TZ)).strftime("%d.%m.%Y %H:%M")


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Отменено.", reply_markup=back_main_kb())
    elif update.message:
        await update.message.reply_text("Отменено.", reply_markup=back_main_kb())
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        await update.effective_message.reply_text(
            "Используй /start и кнопки меню.", reply_markup=main_menu_kb()
        )


def build_app() -> Application:
    if TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Укажи токен в BOT_TOKEN или прямо в переменной TOKEN")

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    promo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_promo, pattern=r"^sub:promo$")],
        states={PROMO_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_promo)]},
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern=r"^menu:subscription$")],
        allow_reentry=True,
    )

    add_target_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(targets_add_prompt, pattern=r"^targets:add$")],
        states={
            ADD_TARGET_FORWARD: [
                MessageHandler(filters.ALL & ~filters.COMMAND, targets_add_forward),
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern=r"^menu:targets$")],
        allow_reentry=True,
    )

    create_bc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_broadcast_start, pattern=r"^bc_new$")],
        states={
            CREATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_broadcast_name)],
            CREATE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_broadcast_text)],
            CREATE_PHOTO: [
                MessageHandler(filters.PHOTO, create_broadcast_photo),
                CallbackQueryHandler(create_broadcast_skip_photo, pattern=r"^bc_nophoto$"),
            ],
            CREATE_TARGETS: [
                CallbackQueryHandler(create_broadcast_pick, pattern=r"^pick:\d+$"),
                CallbackQueryHandler(create_broadcast_targets_done, pattern=r"^pick_done:new$"),
            ],
            CREATE_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_broadcast_interval)],
            CREATE_WINDOW: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_broadcast_window)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conv, pattern=r"^menu:broadcasts$"),
        ],
        allow_reentry=True,
    )

    edit_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_text_prompt, pattern=r"^bc_text:\d+$")],
        states={EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_save)]},
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern=r"^bc_open:\d+$")],
        allow_reentry=True,
    )

    edit_photo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_photo_prompt, pattern=r"^bc_photo:\d+$")],
        states={EDIT_PHOTO_INPUT: [MessageHandler(filters.PHOTO, edit_photo_save)]},
        fallbacks=[
            CallbackQueryHandler(remove_photo, pattern=r"^bc_photorm:\d+$"),
            CallbackQueryHandler(cancel_conv, pattern=r"^bc_open:\d+$"),
        ],
        allow_reentry=True,
    )

    edit_interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_interval_prompt, pattern=r"^bc_interval:\d+$")],
        states={EDIT_INTERVAL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_interval_save)]},
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern=r"^bc_open:\d+$")],
        allow_reentry=True,
    )

    edit_window_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_window_prompt, pattern=r"^bc_window:\d+$")],
        states={EDIT_WINDOW_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_window_save)]},
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern=r"^bc_open:\d+$")],
        allow_reentry=True,
    )

    edit_targets_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_targets_prompt, pattern=r"^bc_targets:\d+$")],
        states={
            CREATE_TARGETS: [
                CallbackQueryHandler(edit_targets_pick, pattern=r"^pick:\d+$"),
                CallbackQueryHandler(edit_targets_done, pattern=r"^pick_done:edit:\d+$"),
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern=r"^bc_open:\d+$")],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(promo_conv)
    app.add_handler(add_target_conv)
    app.add_handler(create_bc_conv)
    app.add_handler(edit_text_conv)
    app.add_handler(edit_photo_conv)
    app.add_handler(edit_interval_conv)
    app.add_handler(edit_window_conv)
    app.add_handler(edit_targets_conv)

    app.add_handler(CallbackQueryHandler(menu_main, pattern=r"^menu:main$"))
    app.add_handler(CallbackQueryHandler(menu_help, pattern=r"^menu:help$"))
    app.add_handler(CallbackQueryHandler(menu_subscription, pattern=r"^menu:subscription$"))
    app.add_handler(CallbackQueryHandler(menu_referrals, pattern=r"^menu:referrals$"))
    app.add_handler(CallbackQueryHandler(menu_targets, pattern=r"^menu:targets$"))
    app.add_handler(CallbackQueryHandler(menu_broadcasts, pattern=r"^menu:broadcasts$"))
    app.add_handler(CallbackQueryHandler(targets_delete, pattern=r"^targets:del:\d+$"))
    app.add_handler(CallbackQueryHandler(open_broadcast, pattern=r"^bc_open:\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_broadcast, pattern=r"^bc_toggle:\d+$"))
    app.add_handler(CallbackQueryHandler(delete_broadcast, pattern=r"^bc_delete:\d+$"))
    app.add_handler(MessageHandler(filters.ALL, unknown))

    return app


def main():
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
