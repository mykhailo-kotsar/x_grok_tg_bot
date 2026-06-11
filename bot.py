import asyncio
import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)
from config import TG_TOKEN
from grok_bridge import GrokBridge
from handlers import (
    cmd_start, cmd_menu, cmd_new, cmd_list, cmd_switch,
    cmd_rename, cmd_export, cmd_status, cmd_cancel,
    handle_message, handle_callback,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main():
    bridge = GrokBridge()
    await bridge.start()

    app = Application.builder().token(TG_TOKEN).build()
    app.bot_data["bridge"] = bridge

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("switch", cmd_switch))
    app.add_handler(CommandHandler("rename", cmd_rename))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message", "callback_query"])

    logging.info("Application started")

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
