import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot funcionando!\n\n"
        "Use /buscar seguido do produto.\n"
        "Exemplo: /buscar ar condicionado 12000 btus"
    )


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Digite o produto que deseja procurar.\n\n"
            "Exemplo:\n"
            "/buscar ar condicionado 12000 btus"
        )
        return

    termo = " ".join(context.args)

    try:
        resposta = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={
                "q": termo,
                "limit": 5
            },
            timeout=15
        )

        resposta.raise_for_status()
        dados = resposta.json()

        produtos = dados.get("results", [])

        if not produtos:
            await update.message.reply_text(
                f"Não encontrei produtos para: {termo}"
            )
            return

        mensagem = f"🔎 Resultados para: {termo}\n\n"

        for produto in produtos:
            titulo = produto.get("title", "Produto")
            preco = produto.get("price", 0)
            link = produto.get("permalink", "")

            mensagem += (
                f"🛒 {titulo}\n"
                f"💰 R$ {preco:.2f}\n"
                f"🔗 {link}\n\n"
            )

        await update.message.reply_text(mensagem)

    except Exception as erro:
        print(f"Erro na busca: {erro}")
        await update.message.reply_text(
            "❌ Não consegui consultar o Mercado Livre agora."
        )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot funcionando!")

    def log_message(self, format, *args):
        pass


def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def main():
    if not TOKEN:
        print("ERRO: TELEGRAM_TOKEN não foi configurado.")
        return

    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buscar", buscar))

    print("Bot iniciado com sucesso!")
    app.run_polling()


if __name__ == "__main__":
    main()
