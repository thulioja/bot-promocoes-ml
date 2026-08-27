import os
import json
import secrets
import hashlib
import base64
import threading

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

import requests

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


# =========================================================
# CONFIGURAÇÕES
# =========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")

ML_REDIRECT_URI = os.getenv(
    "ML_REDIRECT_URI",
    "https://bot-promocoes-ml-ucr3.onrender.com/oauth/callback"
)

PORT = int(os.getenv("PORT", "10000"))

TOKEN_FILE = "ml_token.json"


# =========================================================
# TOKEN MERCADO LIVRE
# =========================================================

ACCESS_TOKEN = None
REFRESH_TOKEN = None


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
# CARREGAR TOKEN
# =========================================================

def carregar_token():

    global ACCESS_TOKEN
    global REFRESH_TOKEN

    # Primeiro tenta Environment Variables
    ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
    REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")

    if ACCESS_TOKEN:
        print("Access Token carregado das Environment Variables.")
        return

    # Depois tenta arquivo
    if os.path.exists(TOKEN_FILE):

        try:

            with open(
                TOKEN_FILE,
                "r",
                encoding="utf-8"
            ) as arquivo:

                dados = json.load(arquivo)

            ACCESS_TOKEN = dados.get(
                "access_token"
            )

            REFRESH_TOKEN = dados.get(
                "refresh_token"
            )

            if ACCESS_TOKEN:
                print("Access Token carregado do arquivo.")

        except Exception as erro:

            print(
                "Erro ao carregar token:",
                erro
            )


# =========================================================
# SALVAR TOKEN
# =========================================================

def salvar_token(dados):

    global ACCESS_TOKEN
    global REFRESH_TOKEN

    ACCESS_TOKEN = dados.get(
        "access_token"
    )

    novo_refresh = dados.get(
        "refresh_token"
    )

    if novo_refresh:
        REFRESH_TOKEN = novo_refresh

    dados_salvar = {
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN
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
            "Refresh Token não encontrado."
        )

        return False

    try:

        resposta = requests.post(

            "https://api.mercadolibre.com/oauth/token",

            data={
                "grant_type": "refresh_token",
                "client_id": ML_CLIENT_ID,
                "client_secret": ML_CLIENT_SECRET,
                "refresh_token": REFRESH_TOKEN
            },

            timeout=30
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

        salvar_token(
            dados
        )

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

    carregar_token()

    if not ACCESS_TOKEN:

        print(
            "Mercado Livre não conectado."
        )

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

    try:

        resposta = requests.request(
            metodo,
            url,
            **kwargs
        )

    except Exception as erro:

        print(
            "Erro na requisição:",
            erro
        )

        return None

    # Token expirado
    if resposta.status_code == 401:

        print(
            "Token expirado. Tentando renovar..."
        )

        if renovar_token():

            headers["Authorization"] = (
                f"Bearer {ACCESS_TOKEN}"
            )

            try:

                resposta = requests.request(
                    metodo,
                    url,
                    **kwargs
                )

            except Exception as erro:

                print(
                    "Erro após renovação:",
                    erro
                )

                return None

    return resposta


# =========================================================
# SERVIDOR HTTP
# =========================================================

class ServidorHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        try:

            parsed = urlparse(
                self.path
            )

            caminho = parsed.path

            # ---------------------------------------------
            # HEALTH CHECK
            # ---------------------------------------------

            if caminho == "/":

                self.send_response(
                    200
                )

                self.send_header(
                    "Content-Type",
                    "text/plain; charset=utf-8"
                )

                self.end_headers()

                self.wfile.write(
                    b"Bot Mercado Livre funcionando!"
                )

                return

            # ---------------------------------------------
            # CALLBACK MERCADO LIVRE
            # ---------------------------------------------

            if caminho == "/oauth/callback":

                parametros = parse_qs(
                    parsed.query
                )

                code = parametros.get(
                    "code",
                    [None]
                )[0]

                state_recebido = parametros.get(
                    "state",
                    [None]
                )[0]

                if state_recebido != STATE:

                    self.enviar_html(
                        400,
                        "❌ Erro de segurança",
                        "O STATE recebido não confere."
                    )

                    return

                if not code:

                    self.enviar_html(
                        400,
                        "❌ Código ausente",
                        "O Mercado Livre não enviou o código."
                    )

                    return

                print(
                    "Código OAuth recebido."
                )

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

                    timeout=30
                )

                print(
                    "OAuth Mercado Livre:",
                    resposta.status_code
                )

                if resposta.status_code == 200:

                    dados = resposta.json()

                    salvar_token(
                        dados
                    )

                    self.enviar_html(
                        200,
                        "✅ Mercado Livre conectado!",
                        "A autorização foi concluída. "
                        "Agora volte ao Telegram e use /testar."
                    )

                else:

                    print(
                        "Erro OAuth:",
                        resposta.text[:2000]
                    )

                    self.enviar_html(
                        400,
                        "❌ Erro na autorização",
                        "O Mercado Livre recusou a autorização."
                    )

                return

            # ---------------------------------------------
            # OUTRA ROTA
            # ---------------------------------------------

            self.send_response(
                404
            )

            self.end_headers()

        except Exception as erro:

            print(
                "ERRO SERVIDOR:",
                erro
            )

            try:

                self.enviar_html(
                    500,
                    "❌ Erro interno",
                    str(erro)
                )

            except Exception:
                pass

    def enviar_html(
        self,
        status,
        titulo,
        mensagem
    ):

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.end_headers()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{titulo}</title>
        </head>
        <body>
            <h1>{titulo}</h1>
            <p>{mensagem}</p>
        </body>
        </html>
        """

        self.wfile.write(
            html.encode("utf-8")
        )

    def log_message(
        self,
        format,
        *args
    ):

        return


def iniciar_servidor():

    try:

        servidor = HTTPServer(
            ("0.0.0.0", PORT),
            ServidorHandler
        )

        print(
            f"Servidor HTTP iniciado na porta {PORT}"
        )

        servidor.serve_forever()

    except Exception as erro:

        print(
            "Erro servidor HTTP:",
            erro
        )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "🤖 Bot funcionando!\n\n"

        "Comandos:\n\n"

        "/autorizar - conectar Mercado Livre\n"

        "/testar - testar conexão\n"

        "/buscar produto - procurar anúncios"
    )


# =========================================================
# AUTORIZAR
# =========================================================

async def autorizar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not ML_CLIENT_ID:

        await update.message.reply_text(
            "❌ ML_CLIENT_ID não configurado no Render."
        )

        return

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

        "🔐 Clique no link abaixo para "
        "autorizar o Mercado Livre:\n\n"

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

    resposta = requisicao_ml(

        "GET",

        "https://api.mercadolibre.com/users/me",

        timeout=30
    )

    if resposta is None:

        await update.message.reply_text(
            "❌ Não foi possível consultar o Mercado Livre."
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

            "❌ Mercado Livre recusou o token.\n\n"

            f"Status: {resposta.status_code}"
        )


# =========================================================
# BUSCAR ANÚNCIOS
# =========================================================

def buscar_anuncios(
    termo
):

    url = (
        "https://api.mercadolibre.com/sites/MLB/search"
    )

    parametros = {

        "q": termo,

        "limit": 20,

        "offset": 0
    }

    print(
        "BUSCANDO:",
        termo
    )

    # -----------------------------------------------------
    # TESTE: busca sem enviar Authorization
    # -----------------------------------------------------

    try:

        resposta = requests.get(

            url,

            params=parametros,

            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            },

            timeout=30
        )

    except Exception as erro:

        print(
            "Erro na busca Mercado Livre:",
            erro
        )

        return None

    print(
        "BUSCA ANÚNCIOS:",
        resposta.status_code
    )

    print(
        "URL:",
        resposta.url
    )

    if resposta.status_code != 200:

        print(
            "RESPOSTA ML:",
            resposta.text[:3000]
        )

        return None

    try:

        return resposta.json()

    except Exception as erro:

        print(
            "Erro ao interpretar JSON:",
            erro
        )

        return None


# =========================================================
# FILTRO
# =========================================================

def produto_relevante(
    produto,
    termo
):

    titulo = produto.get(
        "title",
        ""
    ).lower()

    termo_lower = termo.lower()

    # Busca de ar condicionado
    if (
        "ar condicionado" in termo_lower
        or "ar-condicionado" in termo_lower
    ):

        palavras_obrigatorias = [
            "ar condicionado",
            "ar-condicionado",
            "split",
            "climatizador"
        ]

        if not any(
            palavra in titulo
            for palavra in palavras_obrigatorias
        ):

            return False

    # Capas e controles não interessam
    palavras_excluir = [
        "capa",
        "controle remoto",
        "controle universal",
        "suporte para",
        "suporte de parede",
        "peças"
    ]

    for palavra in palavras_excluir:

        if palavra in titulo:

            return False

    return True


# =========================================================
# BUSCAR
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
        context.args
    ).strip()

    await update.message.reply_text(

        f"🔎 Procurando por:\n"
        f"{termo}\n\n"
        f"Aguarde..."
    )

    dados = buscar_anuncios(
        termo
    )

    if dados is None:

        await update.message.reply_text(

            "❌ Não consegui consultar "
            "os anúncios do Mercado Livre.\n\n"

            "Tente novamente em alguns segundos."
        )

        return

    resultados = dados.get(
        "results",
        []
    )

    print(
        "Resultados recebidos:",
        len(resultados)
    )

    resultados_filtrados = []

    for produto in resultados:

        if produto_relevante(
            produto,
            termo
        ):

            resultados_filtrados.append(
                produto
            )

    print(
        "Resultados após filtro:",
        len(resultados_filtrados)
    )

    if not resultados_filtrados:

        await update.message.reply_text(

            "😕 Não encontrei anúncios "
            "relevantes para:\n\n"

            f"{termo}\n\n"

            "Tente uma busca diferente."
        )

        return

    mensagem = (
        f"🔎 Resultados para:\n"
        f"{termo}\n\n"
    )

    contador = 0

    for produto in resultados_filtrados:

        if contador >= 8:
            break

        titulo = produto.get(
            "title",
            "Produto sem nome"
        )

        preco = produto.get(
            "price"
        )

        link = produto.get(
            "permalink"
        )

        frete = produto.get(
            "shipping",
            {}
        )

        frete_gratis = frete.get(
            "free_shipping",
            False
        )

        contador += 1

        mensagem += (
            f"🛒 {titulo}\n"
        )

        if preco is not None:

            try:

                preco_formatado = (
                    f"R$ {float(preco):,.2f}"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                mensagem += (
                    f"💰 {preco_formatado}\n"
                )

            except Exception:

                mensagem += (
                    f"💰 R$ {preco}\n"
                )

        if frete_gratis:

            mensagem += (
                "🚚 Frete grátis\n"
            )

        if link:

            mensagem += (
                f"🔗 {link}\n"
            )

        mensagem += "\n"

    await update.message.reply_text(

        mensagem,

        disable_web_page_preview=True
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TELEGRAM_TOKEN:

        print(
            "❌ ERRO: TELEGRAM_TOKEN não configurado."
        )

        return

    carregar_token()

    # Apenas UM servidor na porta 10000
    thread_servidor = threading.Thread(
        target=iniciar_servidor,
        daemon=True
    )

    thread_servidor.start()

    print(
        "Iniciando bot Telegram..."
    )

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "autorizar",
            autorizar
        )
    )

    application.add_handler(
        CommandHandler(
            "testar",
            testar
        )
    )

    application.add_handler(
        CommandHandler(
            "buscar",
            buscar
        )
    )

    print(
        "Bot iniciado com sucesso!"
    )

    application.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# EXECUTAR
# =========================================================

if __name__ == "__main__":

    main()
