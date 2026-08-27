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
    "https://bot-promocoes-ml-ucr3.onrender.com/oauth/callback"
)


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
# ACCESS TOKEN
# =========================================================

ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")


# =========================================================
# TELEGRAM / START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🤖 Bot funcionando!\n\n"
        "Comandos disponíveis:\n"
        "/autorizar - conectar Mercado Livre\n"
        "/testar - testar autorização do Mercado Livre\n"
        "/buscar produto - procurar produtos"
    )


# =========================================================
# AUTORIZAÇÃO MERCADO LIVRE
# =========================================================

async def autorizar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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
        "🔐 Para conectar sua conta do Mercado Livre, "
        "abra este link:\n\n"
        + url
    )


# =========================================================
# TESTAR ACCESS TOKEN
# =========================================================

async def testar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global ACCESS_TOKEN

    if not ACCESS_TOKEN:

        await update.message.reply_text(
            "⚠️ Nenhum Access Token disponível.\n\n"
            "Use primeiro:\n"
            "/autorizar"
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
            "Teste Access Token - Status:",
            resposta.status_code
        )

        if resposta.status_code == 200:

            dados = resposta.json()

            user_id = dados.get("id")

            nickname = dados.get("nickname")

            await update.message.reply_text(
                "✅ Access Token válido!\n\n"
                f"ID da conta: {user_id}\n"
                f"Usuário: {nickname}\n\n"
                "Agora podemos investigar especificamente "
                "o erro 403 da busca de produtos."
            )

            return

        if resposta.status_code == 401:

            await update.message.reply_text(
                "❌ Access Token inválido ou expirado.\n\n"
                "Será necessário autorizar novamente "
                "o Mercado Livre usando /autorizar."
            )

            return

        if resposta.status_code == 403:

            await update.message.reply_text(
                "❌ Mercado Livre respondeu 403 Forbidden "
                "ao testar o Access Token.\n\n"
                "Isso indica um problema de permissão "
                "ou autorização da aplicação."
            )

            return

        await update.message.reply_text(
            "⚠️ Mercado Livre respondeu:\n\n"
            f"Status: {resposta.status_code}"
        )

    except Exception as erro:

        print(
            "ERRO AO TESTAR ACCESS TOKEN:",
            erro
        )

        await update.message.reply_text(
            "❌ Erro ao testar o Access Token:\n\n"
            f"{erro}"
        )


# =========================================================
# BUSCAR PRODUTOS
# =========================================================

async def buscar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global ACCESS_TOKEN

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
            "Mercado Livre - Status:",
            resposta.status_code
        )

        print(
            "Mercado Livre - Resposta:",
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
                f"🔎 Não encontrei produtos para:\n{termo}"
            )

            return

        mensagem = (
            f"🔎 Resultados para: {termo}\n\n"
        )

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

            mensagem += (
                f"🛒 {titulo}\n"
                f"💰 R$ {preco:.2f}\n"
                f"🔗 {link}\n\n"
            )

        await update.message.reply_text(
            mensagem
        )

    except Exception as erro:

        print(
            "ERRO NA BUSCA:",
            erro
        )

        await update.message.reply_text(
            "❌ Erro ao consultar o Mercado Livre:\n\n"
            f"{erro}"
        )


# =========================================================
# SERVIDOR HTTP / CALLBACK
# =========================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        global ACCESS_TOKEN

        caminho = urlparse(
            self.path
        )

        # -------------------------------------------------
        # HEALTH CHECK
        # -------------------------------------------------

        if caminho.path == "/":

            self.send_response(200)

            self.end_headers()

            self.wfile.write(
                b"Bot Promocoes Mercado Livre funcionando!"
            )

            return

        # -------------------------------------------------
        # OAUTH CALLBACK
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

                   
