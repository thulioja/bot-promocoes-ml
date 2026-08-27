import os
import threading
import secrets
import hashlib
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")
ML_REDIRECT_URI = os.getenv(
    "ML_REDIRECT_URI",
    "https://bot-promocoes-ml-ucr3.onrender.com"
)

# PKCE
CODE_VERIFIER = secrets.token_urlsafe(64)

CODE_CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(CODE_VERIFIER.encode()).digest()
).decode().rstrip("=")

STATE = secrets.token_urlsafe(32)

# Token do Mercado Livre
ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot funcionando!\n\n"
        "Comandos disponíveis:\n"
        "/autorizar - conectar Mercado Livre\n"
        "/buscar produto - procurar produtos"
    )


async def autorizar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    parametros = {
        "response_type": "code",
        "client_id": ML_CLIENT_ID,
        "redirect_uri": ML_REDIRECT_URI,
        "code_challenge": CODE_CHALLENGE,
        "code_challenge_method": "S256",
        "state": STATE
    }

    url = (
        "https://auth.mercadolivre.com.br/authorization?"
        + urlencode(parametros)
    )

    await update.message.reply_text(
        "🔐 Para conectar sua conta do Mercado Livre, abra este link:\n\n"
        + url
    )


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not ACCESS_TOKEN:
        await update.message.reply_text(
            "⚠️ O Mercado Livre ainda não está conectado.\n\n"
            "Use primeiro:\n"
            "/autorizar"
        )
        return

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
            headers={
                "Authorization": f"Bearer {ACCESS_TOKEN}"
            },
            params={
                "q": termo,
                "limit": 5
            },
            timeout=15
        )

        print(
            f"Mercado Livre - Status: {resposta.status_code}"
        )

        resposta.raise_for_status()

        dados = resposta.json()
        produtos = dados.get("results", [])

        if not produtos:
            await update.message.reply_text(
                f"🔎 Não encontrei produtos para:\n{termo}"
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

        print(f"ERRO NA BUSCA: {erro}")

        await update.message.reply_text(
            f"❌ Erro ao consultar o Mercado Livre:\n\n{erro}"
        )


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        global ACCESS_TOKEN

        caminho = urlparse(self.path)

        if caminho.path == "/":

            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"Bot Promocoes Mercado Livre funcionando!"
            )
            return

        if caminho.path == "/oauth/callback":

            parametros = parse_qs(caminho.query)

            code = parametros.get("code", [None])[0]
            state = parametros.get("state", [None])[0]

            if not code:

                self.send_response(400)
                self.end_headers()
                self.wfile.write(
                    b"Codigo de autorizacao nao recebido."
                )
                return

            if state != STATE:

                self.send_response(400)
                self.end_headers()
                self.wfile.write(
                    b"Erro de seguranca: state invalido."
                )
                return

            try:

                resposta = requests.post(
                    "https://api.mercadolibre.com/oauth/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": ML_CLIENT_ID,
                        "client_secret": ML_CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": ML_REDIRECT_URI,
                        "code_verifier": CODE_VERIFIER
                    },
                    headers={
                        "accept": "application/json",
                        "content-type":
                        "application/x-www-form-urlencoded"
                    },
                    timeout=15
                )

                print(
                    "OAuth Mercado Livre:",
                    resposta.status_code,
                    resposta.text[:1000]
                )

                if resposta.status_code != 200:

                    self.send_response(400)
                    self.end_headers()

                    mensagem = (
                        "Erro ao obter Access Token.\n\n"
                        + resposta.text
                    )

                    self.wfile.write(
                        mensagem.encode()
                    )
                    return

                dados = resposta.json()

                ACCESS_TOKEN = dados.get("access_token")

                self.send_response(200)
                self.end_headers()

                self.wfile.write(
                    b"""
                    <html>
                    <body>
                    <h1>Mercado Livre conectado!</h1>
                    <p>Autorizacao concluida com sucesso.</p>
                    <p>Agora voce pode voltar ao Telegram.</p>
                    </body>
                    </html>
                    """
                )

            except Exception as erro:

                print(
                    "ERRO NO OAUTH:",
                    erro
                )

                self.send_response(500)
                self.end_headers()

                self.wfile.write(
                    f"Erro: {erro}".encode()
                )

            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def run_server():

    port = int(
        os.environ.get("PORT", 10000)
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    server.serve_forever()


def main():

    if not TOKEN:

        print(
            "ERRO: TELEGRAM_TOKEN não foi configurado."
        )

        return

    if not ML_CLIENT_ID:

        print(
            "ERRO: ML_CLIENT_ID não foi configurado."
        )

        return

    if not ML_CLIENT_SECRET:

        print(
            "ERRO: ML_CLIENT_SECRET não foi configurado."
        )

        return

    threading.Thread(
        target=run_server,
        daemon=True
    ).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("autorizar", autorizar)
    )

    app.add_handler(
        CommandHandler("buscar", buscar)
    )

    print("Bot iniciado com sucesso!")

    app.run_polling()


if __name__ == "__main__":
    main()
