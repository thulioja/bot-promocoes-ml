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


# =========================================================
# CONFIGURAÇÕES
# =========================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")

ML_REDIRECT_URI = os.getenv(
    "ML_REDIRECT_URI",
    "https://bot-promocoes-ml-ucr3.onrender.com/oauth/callback"
)

ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")


# =========================================================
# PKCE
# =========================================================

CODE_VERIFIER = secrets.token_urlsafe(64)

CODE_CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(
        CODE_VERIFIER.encode()
    ).digest()
).decode().rstrip("=")

STATE = secrets.token_urlsafe(32)


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🤖 Bot funcionando!\n\n"
        "Comandos disponíveis:\n\n"
        "/autorizar - conectar Mercado Livre\n"
        "/testar - testar conexão\n"
        "/buscar produto - procurar produtos"
    )


# =========================================================
# /AUTORIZAR
# =========================================================

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
        "🔐 Conectar ao Mercado Livre:\n\n"
        + url
    )


# =========================================================
# /TESTAR
# =========================================================

async def testar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global ACCESS_TOKEN

    if not ACCESS_TOKEN:

        await update.message.reply_text(
            "⚠️ Mercado Livre não conectado.\n\n"
            "Use /autorizar."
        )

        return

    try:

        resposta = requests.get(
            "https://api.mercadolibre.com/users/me",
            headers={
                "Authorization": f"Bearer {ACCESS_TOKEN}"
            },
            timeout=15
        )

        print(
            "TESTE MERCADO LIVRE:",
            resposta.status_code,
            resposta.text[:500]
        )

        if resposta.status_code == 200:

            dados = resposta.json()

            await update.message.reply_text(
                "✅ Access Token válido!\n\n"
                f"ID Mercado Livre: {dados.get('id')}\n"
                f"Usuário: {dados.get('nickname')}"
            )

        else:

            await update.message.reply_text(
                "❌ Token não aceito.\n\n"
                f"Status: {resposta.status_code}"
            )

    except Exception as erro:

        await update.message.reply_text(
            f"❌ Erro:\n{erro}"
        )


# =========================================================
# /BUSCAR
# =========================================================

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global ACCESS_TOKEN

    if not ACCESS_TOKEN:

        await update.message.reply_text(
            "⚠️ Mercado Livre não conectado.\n\n"
            "Use /autorizar."
        )

        return

    if not context.args:

        await update.message.reply_text(
            "Digite o produto.\n\n"
            "Exemplo:\n"
            "/buscar ar condicionado 12000 btus"
        )

        return

    termo = " ".join(context.args)

    await update.message.reply_text(
        f"🔎 Procurando por:\n"
        f"{termo}\n\n"
        "Aguarde..."
    )

    try:

        # =================================================
        # BUSCA DE ANÚNCIOS REAIS
        # =================================================

        resposta = requests.get(

            "https://api.mercadolibre.com/sites/MLB/search",

            headers={
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Accept": "application/json"
            },

            params={
                "q": termo,
                "limit": 10
            },

            timeout=20
        )

        print(
            "BUSCA ML STATUS:",
            resposta.status_code
        )

        print(
            "BUSCA ML RESPOSTA:",
            resposta.text[:1000]
        )

        resposta.raise_for_status()

        dados = resposta.json()

        produtos = dados.get(
            "results",
            []
        )

        if not produtos:

            await update.message.reply_text(
                "🔎 Nenhum anúncio encontrado."
            )

            return

        mensagem = (
            f"🔥 Ofertas encontradas:\n"
            f"🔎 {termo}\n\n"
        )

        contador = 0

        for produto in produtos:

            titulo = produto.get(
                "title",
                "Produto"
            )

            preco = produto.get(
                "price",
                0
            )

            link = produto.get(
                "permalink",
                ""
            )

            moeda = produto.get(
                "currency_id",
                "BRL"
            )

            # Ignora anúncios sem preço
            if not preco:

                continue

            contador += 1

            if moeda == "BRL":

                preco_formatado = (
                    f"R$ {preco:,.2f}"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

            else:

                preco_formatado = str(preco)

            mensagem += (
                f"🛒 {titulo}\n"
                f"💰 {preco_formatado}\n"
                f"🔗 {link}\n\n"
            )

            if contador >= 5:

                break

        if contador == 0:

            await update.message.reply_text(
                "🔎 Encontrei anúncios, "
                "mas nenhum com preço disponível."
            )

            return

        await update.message.reply_text(
            mensagem,
            disable_web_page_preview=True
        )

    except requests.HTTPError as erro:

        print(
            "ERRO HTTP BUSCA:",
            erro
        )

        await update.message.reply_text(
            "❌ O Mercado Livre recusou a busca.\n\n"
            f"Status: {resposta.status_code}"
        )

    except Exception as erro:

        print(
            "ERRO BUSCA:",
            erro
        )

        await update.message.reply_text(
            f"❌ Erro na busca:\n\n{erro}"
        )


# =========================================================
# SERVIDOR HTTP
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        global ACCESS_TOKEN

        caminho = urlparse(
            self.path
        )

        # -------------------------------------------------
        # PÁGINA PRINCIPAL
        # -------------------------------------------------

        if caminho.path == "/":

            self.send_response(200)
            self.end_headers()

            self.wfile.write(
                b"Bot Promocoes Mercado Livre funcionando!"
            )

            return

        # -------------------------------------------------
        # CALLBACK DO MERCADO LIVRE
        # -------------------------------------------------

        if caminho.path == "/oauth/callback":

            parametros = parse_qs(
                caminho.query
            )

            code = parametros.get(
                "code",
                [None]
            )[0]

            state = parametros.get(
                "state",
                [None]
            )[0]

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

                        "grant_type":
                        "authorization_code",

                        "client_id":
                        ML_CLIENT_ID,

                        "client_secret":
                        ML_CLIENT_SECRET,

                        "code":
                        code,

                        "redirect_uri":
                        ML_REDIRECT_URI,

                        "code_verifier":
                        CODE_VERIFIER
                    },

                    headers={
                        "accept":
                        "application/json",

                        "content-type":
                        "application/x-www-form-urlencoded"
                    },

                    timeout=20
                )

                print(
                    "OAUTH STATUS:",
                    resposta.status_code
                )

                print(
                    "OAUTH RESPOSTA:",
                    resposta.text[:1000]
                )

                if resposta.status_code != 200:

                    self.send_response(400)
                    self.end_headers()

                    self.wfile.write(
                        resposta.text.encode()
                    )

                    return

                dados = resposta.json()

                ACCESS_TOKEN = dados.get(
                    "access_token"
                )

                if not ACCESS_TOKEN:

                    self.send_response(400)
                    self.end_headers()

                    self.wfile.write(
                        b"Access Token nao recebido."
                    )

                    return

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
                    "ERRO OAUTH:",
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

    def log_message(
        self,
        format,
        *args
    ):

        pass


# =========================================================
# RODAR SERVIDOR
# =========================================================

def run_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        HealthHandler
    )

    server.serve_forever()


# =========================================================
# MAIN
# =========================================================

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

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "autorizar",
            autorizar
        )
    )

    app.add_handler(
        CommandHandler(
            "testar",
            testar
        )
    )

    app.add_handler(
        CommandHandler(
            "buscar",
            buscar
        )
    )

    print(
        "Bot iniciado com sucesso!"
    )

    app.run_polling()


if __name__ == "__main__":

    main()
