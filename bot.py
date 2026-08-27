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

TOKEN_FILE = "ml_token.json"

PORT = int(os.getenv("PORT", "10000"))


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
# TOKENS
# =========================================================

ACCESS_TOKEN = None
REFRESH_TOKEN = None
TOKEN_EXPIRES_IN = 0


# =========================================================
# CARREGAR TOKEN
# =========================================================

def carregar_token():

    global ACCESS_TOKEN
    global REFRESH_TOKEN
    global TOKEN_EXPIRES_IN

    ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
    REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")

    if ACCESS_TOKEN:
        print("Access Token carregado das Environment Variables.")
        return

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

        print("Não existe Refresh Token.")

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

            headers={
                "accept": "application/json",
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

    try:

        resposta = requests.request(
            metodo,
            url,
            **kwargs
        )

    except Exception as erro:

        print(
            "Erro na requisição ML:",
            erro
        )

        return None

    if resposta.status_code == 401:

        print(
            "Access Token expirado."
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
                    "Erro após renovar token:",
                    erro
                )

                return None

    return resposta


# =========================================================
# SERVIDOR WEB PARA O RENDER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"Bot Mercado Livre funcionando!"
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
            HealthHandler
        )

        print(
            f"Servidor web iniciado na porta {PORT}"
        )

        servidor.serve_forever()

    except Exception as erro:

        print(
            "Erro no servidor web:",
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
# TESTAR MERCADO LIVRE
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
                "❌ Não foi possível acessar o Mercado Livre."
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
# LIMPAR TERMO DE BUSCA
# =========================================================

def preparar_busca(termo):

    termo = termo.strip()

    termos_remover = [
        "promoção",
        "promocao",
        "oferta",
        "ofertas"
    ]

    palavras = termo.split()

    palavras_filtradas = []

    for palavra in palavras:

        if palavra.lower() not in termos_remover:

            palavras_filtradas.append(palavra)

    return " ".join(
        palavras_filtradas
    )


# =========================================================
# BUSCAR ANÚNCIOS REAIS
# =========================================================

def buscar_produtos_ml(termo):

    url = (
        "https://api.mercadolibre.com/sites/"
        "MLB/search"
    )

    parametros = {

        "q": termo,

        "limit": 10,

        "offset": 0
    }

    resposta = requisicao_ml(

        "GET",

        url,

        params=parametros,

        timeout=30
    )

    if resposta is None:

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
            "Resposta:",
            resposta.text[:2000]
        )

        return None

    try:

        return resposta.json()

    except Exception as erro:

        print(
            "Erro JSON:",
            erro
        )

        return None


# =========================================================
# FILTRAR RESULTADOS
# =========================================================

def filtrar_resultados(
    resultados,
    termo
):

    if not resultados:

        return []

    termo_lower = termo.lower()

    palavras_importantes = [
        palavra
        for palavra in termo_lower.split()
        if len(palavra) > 2
    ]

    produtos_validos = []

    for produto in resultados:

        titulo = produto.get(
            "title",
            ""
        )

        titulo_lower = titulo.lower()

        score = 0

        for palavra in palavras_importantes:

            if palavra in titulo_lower:

                score += 1

        # Para buscas por ar condicionado,
        # exigir que o título contenha termos relacionados.
        if (
            "ar condicionado" in termo_lower
            or "ar-condicionado" in termo_lower
        ):

            if (
                "ar condicionado" not in titulo_lower
                and "ar-condicionado" not in titulo_lower
                and "split" not in titulo_lower
            ):

                continue

        if score >= 1:

            produtos_validos.append(
                produto
            )

    return produtos_validos


# =========================================================
# COMANDO BUSCAR
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

    termo_original = " ".join(
        context.args
    )

    termo = preparar_busca(
        termo_original
    )

    await update.message.reply_text(

        f"🔎 Procurando por:\n"
        f"{termo}\n\n"
        "Aguarde..."
    )

    dados = buscar_produtos_ml(
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
        "Quantidade encontrada:",
        len(resultados)
    )

    resultados = filtrar_resultados(
        resultados,
        termo
    )

    if not resultados:

        await update.message.reply_text(

            f"😕 Não encontrei anúncios "
            f"relevantes para:\n\n"
            f"{termo}\n\n"

            "Tente uma busca mais simples."
        )

        return

    mensagem = (

        f"🔎 Resultados para:\n"
        f"{termo}\n\n"
    )

    contador = 0

    for produto in resultados:

        if contador >= 8:
            break

        titulo = produto.get(
            "title",
            "Produto sem nome"
        )

        preco = produto.get(
            "price"
        )

        moeda = produto.get(
            "currency_id",
            "BRL"
        )

        link = produto.get(
            "permalink"
        )

        vendedor = produto.get(
            "seller",
            {}
        )

        nickname = vendedor.get(
            "nickname",
            ""
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

            except Exception:

                preco_formatado = str(
                    preco
                )

            mensagem += (
                f"💰 {preco_formatado}\n"
            )

        if nickname:

            mensagem += (
                f"👤 {nickname}\n"
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
# CALLBACK OAUTH
# =========================================================

class OAuthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        try:

            consulta = urlparse(
                self.path
            )

            parametros = parse_qs(
                consulta.query
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

                self.send_response(400)

                self.end_headers()

                self.wfile.write(
                    b"State invalido."
                )

                return

            if not code:

                self.send_response(400)

                self.end_headers()

                self.wfile.write(
                    b"Codigo de autorizacao ausente."
                )

                return

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

                timeout=30
            )

            print(
                "OAuth Mercado Livre:",
                resposta.status_code
            )

            print(
                "OAuth resposta:",
                resposta.text[:2000]
            )

            if resposta.status_code == 200:

                dados = resposta.json()

                salvar_token(
                    dados
                )

                self.send_response(
                    200
                )

                self.send_header(
                    "Content-type",
                    "text/html; charset=utf-8"
                )

                self.end_headers()

                self.wfile.write(

                    """
                    <html>
                    <head>
                    <meta charset="utf-8">
                    <title>Autorização concluída</title>
                    </head>
                    <body>
                    <h1>✅ Mercado Livre conectado!</h1>
                    <p>Você pode voltar ao Telegram.</p>
                    </body>
                    </html>
                    """.encode(
                        "utf-8"
                    )
                )

            else:

                self.send_response(
                    400
                )

                self.end_headers()

                self.wfile.write(

                    (
                        "Erro na autorização: "
                        + resposta.text
                    ).encode(
                        "utf-8"
                    )
                )

        except Exception as erro:

            print(
                "ERRO OAUTH:",
                erro
            )

            self.send_response(
                500
            )

            self.end_headers()

            self.wfile.write(

                (
                    "Erro interno: "
                    + str(erro)
                ).encode(
                    "utf-8"
                )
            )

    def log_message(
        self,
        format,
        *args
    ):

        return


def iniciar_oauth_server():

    try:

        servidor = HTTPServer(
            ("0.0.0.0", PORT),
            OAuthHandler
        )

        print(
            f"Servidor OAuth iniciado na porta {PORT}"
        )

        servidor.serve_forever()

    except Exception as erro:

        print(
            "Erro servidor OAuth:",
            erro
        )


# =========================================================
# INICIAR BOT
# =========================================================

def main():

    if not TOKEN:

        print(
            "ERRO: TELEGRAM_TOKEN não configurado."
        )

        return

    carregar_token()

    # Servidor HTTP do Render
    thread_web = threading.Thread(
        target=iniciar_servidor,
        daemon=True
    )

    thread_web.start()

    # Servidor OAuth
    thread_oauth = threading.Thread(
        target=iniciar_oauth_server,
        daemon=True
    )

    thread_oauth.start()

    print(
        "Iniciando bot Telegram..."
    )

    application = (
        Application.builder()
        .token(TOKEN)
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
