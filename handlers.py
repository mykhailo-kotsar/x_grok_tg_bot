import io
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import chat_store as store
from config import GROK_URL

log = logging.getLogger(__name__)

MENU_TEXT = (
    "📋 *Menu*\n\n"
    "/new — start a new chat\n"
    "/list — list all chats\n"
    "/switch N — switch to chat N\n"
    "/rename N text — rename chat\n"
    "/export N — download chat history\n"
    "/status — session & bot status\n"
    "/cancel — cancel pending Grok response\n"
    "/menu — show this menu"
)

MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🆕 New chat", callback_data="new"),
     InlineKeyboardButton("📋 List", callback_data="list")],
    [InlineKeyboardButton("📊 Status", callback_data="status"),
     InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
])


def _active_chat_id(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.user_data.get("active_chat_id")

def _set_active(context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    context.user_data["active_chat_id"] = chat_id

def _fmt_index(index: list) -> str:
    if not index:
        return "No chats yet. Use /new to start."
    lines = ["📋 *Your chats:*\n"]
    for i, item in enumerate(index, 1):
        ts = time.strftime("%d.%m %H:%M", time.localtime(item.get("last_active", 0)))
        lines.append(f"{i}. {item['title']} — {item['msg_count']} messages [{ts}]")
    lines.append("\n/switch N — open a chat")
    return "\n".join(lines)

def _get_message(update: Update):
    if update.message:
        return update.message
    if update.callback_query:
        return update.callback_query.message
    return None


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    await msg.reply_text(MENU_TEXT, parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    chat_id = _active_chat_id(context)
    if chat_id:
        index = store.load_index(update.effective_user.id)
        item = next((x for x in index if x["id"] == chat_id), None)
        title = item["title"] if item else chat_id
        await msg.reply_text(
            f"👋 Grok Bridge is active.\nCurrent chat: *{title}*\n\n{MENU_TEXT}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB,
        )
    else:
        await msg.reply_text(
            f"👋 Grok Bridge is active.\nNo active chat — use /new to start.\n\n{MENU_TEXT}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MENU_KB,
        )

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    bridge = context.bot_data["bridge"]
    if bridge.is_busy():
        await msg.reply_text("⏳ Grok is thinking. Wait or /cancel")
        return
    status = await msg.reply_text("🔄 Opening new chat...")
    url = await bridge.new_chat()
    if url:
        context.user_data["pending_new_chat_url"] = url
        context.user_data["active_chat_id"] = None
        await status.edit_text("✅ New chat opened. Send your first message.")
    else:
        await status.edit_text("❌ Failed to open new chat.")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    index = store.load_index(update.effective_user.id)
    await msg.reply_text(_fmt_index(index), parse_mode=ParseMode.MARKDOWN)

async def cmd_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    bridge = context.bot_data["bridge"]
    if bridge.is_busy():
        await msg.reply_text("⏳ Grok is thinking. Wait or /cancel")
        return
    args = context.args
    if not args or not args[0].isdigit():
        await msg.reply_text("Usage: /switch N")
        return
    user_id = update.effective_user.id
    item = store.get_chat_by_number(user_id, int(args[0]))
    if not item:
        await msg.reply_text("❌ Chat not found.")
        return
    status = await msg.reply_text(f"🔄 Switching to «{item['title']}»...")
    ok = await bridge.switch_to(item["url"])
    if not ok:
        await status.edit_text("❌ Failed to switch. Check logs.")
        return
    _set_active(context, item["id"])
    store.update_chat_url(user_id, item["id"], bridge.page.url)
    chat = store.load_chat(user_id, item["id"])
    messages = chat.get("messages", [])
    if not messages:
        await status.edit_text(f"✅ Chat «{item['title']}» is active. No history yet.")
        return
    await status.edit_text(f"✅ Chat «{item['title']}». Loading history...")
    current = ""
    parts = []
    for m in messages:
        role = "👤 You" if m["role"] == "user" else "🤖 Grok"
        line = f"{role}:\n{m['text']}\n\n"
        if len(current) + len(line) > 4000:
            parts.append(current)
            current = line
        else:
            current += line
    if current:
        parts.append(current)
    for part in parts:
        await msg.reply_text(part)
    await msg.reply_text(f"💬 Continue — chat «{item['title']}» is active.")

async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    args = context.args
    if not args or len(args) < 2 or not args[0].isdigit():
        await msg.reply_text("Usage: /rename N new title")
        return
    item = store.get_chat_by_number(update.effective_user.id, int(args[0]))
    if not item:
        await msg.reply_text("❌ Chat not found.")
        return
    new_title = " ".join(args[1:])
    store.rename_chat(update.effective_user.id, item["id"], new_title)
    await msg.reply_text(f"✅ Renamed to «{new_title}»")

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    args = context.args
    if not args or not args[0].isdigit():
        await msg.reply_text("Usage: /export N")
        return
    item = store.get_chat_by_number(update.effective_user.id, int(args[0]))
    if not item:
        await msg.reply_text("❌ Chat not found.")
        return
    text = store.export_chat_text(update.effective_user.id, item["id"])
    if not text:
        await msg.reply_text("❌ Chat is empty.")
        return
    buf = io.BytesIO(text.encode())
    buf.name = f"{item['title'][:30]}.txt"
    await msg.reply_document(buf)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    bridge = context.bot_data["bridge"]
    user_id = update.effective_user.id
    chat_id = _active_chat_id(context)
    index = store.load_index(user_id)
    item = next((x for x in index if x["id"] == chat_id), None) if chat_id else None
    await msg.reply_text(
        f"📊 *Status*\n\n"
        f"Session: {'✅ active' if bridge._ready else '❌ inactive'}\n"
        f"Grok: {'⏳ thinking' if bridge.is_busy() else '✅ idle'}\n"
        f"Active chat: {item['title'] if item else 'none'}\n"
        f"Total chats: {len(index)}\n"
        f"Uptime: {bridge.uptime()}",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _get_message(update)
    bridge = context.bot_data["bridge"]
    if bridge.is_busy():
        bridge.cancel()
        await msg.reply_text("⚠️ Cancel signal sent.")
    else:
        await msg.reply_text("Grok is not currently thinking.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bridge = context.bot_data["bridge"]
    user_id = update.effective_user.id
    question = update.message.text

    if question.lower() in (".menu", ".меню"):
        await cmd_menu(update, context)
        return

    if bridge.is_busy():
        await update.message.reply_text("⏳ Grok is still thinking. Wait or /cancel")
        return

    msg = await update.message.reply_text("⏳ Thinking...")
    response = await bridge.ask(question)

    chat_id = _active_chat_id(context)
    pending_url = context.user_data.pop("pending_new_chat_url", None)

    if not chat_id:
        actual_url = await bridge.current_url()
        url = actual_url if actual_url != "about:blank" else (pending_url or GROK_URL)
        new_chat = store.create_chat(user_id, url, question)
        _set_active(context, new_chat["id"])
        chat_id = new_chat["id"]
    else:
        store.update_chat_url(user_id, chat_id, await bridge.current_url())

    store.append_messages(user_id, chat_id, question, response)

    for i in range(0, len(response), 4096):
        chunk = response[i:i + 4096]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    dispatch = {"new": cmd_new, "list": cmd_list, "status": cmd_status, "cancel": cmd_cancel}
    handler = dispatch.get(q.data)
    if handler:
        await handler(update, context)
