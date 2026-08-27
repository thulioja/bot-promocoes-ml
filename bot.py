import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot funcionando!")


def main():
    if not TOKEN:
        print("ERRO: TELEGRAM_TOKEN não foi configurado.")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Bot iniciado com sucesso!")
    app.run_polling()


if __name__ == "__main__":
    main()
