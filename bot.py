import os
import threading
import secrets
import hashlib
import base64
import json
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

# Arquivo local onde o Render mantém o token enquanto
# a instância estiver rodando.
TOKEN_FILE = "ml_token.json"


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
# TOKEN
# =========================================================

ACCESS_TOKEN = None
REFRESH_TOKEN = None
TOKEN_EXPIRES_IN = 0


def carregar_token():

    global ACCESS_TOKEN
    global REFRESH_TOKEN
    global TOKEN_EXPIRES_IN

    # Primeiro tenta variável de ambiente
    ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
    REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")

    if ACCESS_TOKEN:
        print("Access Token carregado das Environment Variables.")
        return

    # Depois tenta arquivo local
    if os.path.exists(TOKEN_FILE):

        try:

            with open(
                TOKEN_FILE,
                "r",
                encoding="utf-8"
            ) as arquivo:

                dados = json.load(arquivo)

            ACCESS_TOKEN = dados.get("access_token")
            REFRESH_TOKEN = dados.get("refresh_token")
            TOKEN_EXPIRES_IN = dados.get(
                "expires_in",
                0
            )

            if ACCESS_TOKEN:

                print(
                    "Access Token carregado do arquivo."
                )

        except Exception as erro:

            print(
                "Erro ao carregar token:",
                erro
            )


def salvar_token(dados):

    global ACCESS_TOKEN
    global REFRESH_TOKEN
    global TOKEN_EXPIRES_IN

    ACCESS_TOKEN = dados.get(
        "access_token"
    )

    REFRESH_TOKEN = dados.get(
        "refresh_token",
        REFRESH_TOKEN
    )

    TOKEN_EXPIRES_IN = dados.get(
        "expires_in",
        0
    )

    dados_salvar = {
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN,
        "expires_in": TOKEN_EXPIRES_IN
    }

    try:

        with open(
            TOKEN_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                dados_salvar,
                arquivo
            )

        print("Token salvo com sucesso.")

    except Exception as erro:

        print(
            "Erro ao salvar token:",
            erro
        )


# =========================================================
# RENOVAR TOKEN
# =========================================================

def renovar_token():

    global ACCESS_TOKEN
    global REFRESH_TOKEN

    if not REFRESH_TOKEN:

        print(
            "Não existe Refresh Token."
        )

        return False

    try:

        resposta = requests.post(

            "https://api.mercadolibre.com/oauth/token",

            data={
                "grant_type":
                    "refresh_token",

                "client_id":
                    ML_CLIENT_ID,

                "client_secret":
                    ML_CLIENT_SECRET,

                "refresh_token":
                    REFRESH_TOKEN
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
            "RENOVAÇÃO TOKEN:",
            resposta.status_code
        )

        if resposta.status_code != 200:

            print(
                resposta.text[:1000]
            )

            return False

        dados = resposta.json()

        salvar_token(dados)

        print(
            "Token renovado com sucesso."
        )

        return True

    except Exception as erro:

        print(
            "Erro ao renovar token:",
            erro
        )

        return False


# =========================================================
# REQUISIÇÃO MERCADO LIVRE
# =========================================================

def requisicao_ml(
    metodo,
    url,
    **kwargs
):

    global ACCESS_TOKEN

    if not ACCESS_TOKEN:

        carregar_token()

    if not ACCESS_TOKEN:

        return None

    headers = kwargs.pop(
        "headers",
        {}
    )

    headers["Authorization"] = (
        f"Bearer {ACCESS_TOKEN}"
    )

    headers["Accept"] = (
        "application/json"
    )

    kwargs["headers"] = headers

    resposta = requests.request(
        metodo,
        url,
        **kwargs
    )

    # Se o token expirou, tenta renovar
    if resposta.status_code == 401:

        print(
            "Access Token expirado. "
            "Tentando renovar..."
        )

        if renovar_token():

            headers["Authorization"] = (
                f"Bearer {ACCESS_TOKEN}"
            )

            resposta = requests.request(
                metodo,
                url,
                **kwargs
            )

    return resposta


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🤖 Bot funcionando!\n\n"
        "Comandos disponíveis:\n\n"
        "/autorizar - conectar Mercado Livre\n"
        "/testar - testar conexão\n"
        "/buscar produto - procurar produtos"
    )


# =========================================================
# AUTORIZAR
# =========================================================

async def autorizar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    parametros = {

        "response_type":
            "code",

        "client_id":
            ML_CLIENT_ID,

        "redirect_uri":
            ML_REDIRECT_URI,

        "code_challenge":
            CODE_CHALLENGE,

        "code_challenge_method":
            "S256",

        "state":
            STATE
    }

    url = (
        "https://auth.mercadolivre.com.br/"
        "authorization?"
        + urlencode(parametros)
    )

    await update.message.reply_text(
        "🔐 Conectar ao Mercado Livre:\n\n"
        + url
    )


# =========================================================
# TESTAR
# =========================================================

async def testar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    carregar_token()

    if not ACCESS_TOKEN:

        await update.message.reply_text(
            "⚠️ Mercado Livre não conectado.\n\n"
            "Use /autorizar."
        )

        return

    try:

        resposta = requisicao_ml(
            "GET",
            "https://api.mercadolibre.com/users/me",
            timeout=20
        )

        if resposta is None:

            await update.message.reply_text(
                "❌ Não existe Access Token."
            )

            return

        print(
            "TESTE ML:",
            resposta.status_code
        )

        if resposta.status_code == 200:

            dados = resposta.json()

            await update.message.reply_text(
                "✅ Access Token válido!\n\n"
                f"ID Mercado Livre: "
                f"{dados.get('id')}\n"
                f"Usuário: "
                f"{dados.get('nickname')}"
            )

        else:

            await update.message.reply_text(
                "❌ Token não aceito.\n\n"
                f"Status: "
                f"{resposta.status_code}"
            )

    except Exception as erro:

        print(
            "ERRO TESTE:",
            erro
        )

        await update.message.reply_text(
            f"❌ Erro:\n{erro}"
        )


# =========================================================
# BUSCAR ANÚNCIOS
# =========================================================

async def buscar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    carregar_token()

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

    termo = " ".join(
