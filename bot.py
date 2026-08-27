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

    # Primeiro tenta Environment Variables
    ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
    REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")

    if ACCESS_TOKEN:

        print(
            "Access Token carregado das Environment Variables."
        )

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

            ACCESS_TOKEN = dados.get(
                "access_token"
            )

            REFRESH_TOKEN = dados.get(
                "refresh_token"
            )

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

        print(
            "Token salvo com sucesso."
        )

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

        raise

    # Token expirado
    if resposta.status_code == 401:

        print(
            "Access Token expirado."
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

    if not ML_CLIENT_ID:

        await update.message.reply_text(
            "❌ ML_CLIENT_ID não configurado."
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
                f"{resposta.status_code}\n\n"

                f"{resposta.text[:500]}"
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
# BUSCAR PRODUTOS
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

            "Digite o produto que deseja procurar.\n\n"

            "Exemplo:\n"

            "/buscar ar condicionado 12000 btus"
        )

        return

    termo = " ".join(
        context.args
    )

    await update.message.reply_text(

        f"🔎 Procurando por:\n"
        f"{termo}\n\n"
        f"Aguarde..."
    )

    try:

        # =================================================
        # BUSCA OFICIAL DE PRODUTOS
        # =================================================

        url = (
            "https://api.mercadolibre.com/"
            "products/search"
        )

        resposta = requisicao_ml(

            "GET",

            url,

            params={

                "status": "active",

                "site_id": "MLB",

                "q": termo,

                "limit": 5
            },

            timeout=20
        )

        if resposta is None:

            await update.message.reply_text(

                "❌ Não foi possível conectar "
                "ao Mercado Livre."
            )

            return

        print(
            "Mercado Livre PRODUCTS - Status:",
            resposta.status_code
        )

        print(
            "Mercado Livre PRODUCTS - Resposta:",
            resposta.text[:3000]
        )

        # =================================================
        # TOKEN EXPIRADO
        # =================================================

        if resposta.status_code == 401:

            await update.message.reply_text(

                "⚠️ O acesso ao Mercado Livre "
                "expirou.\n\n"
                "Use /autorizar novamente."
            )

            return

        # =================================================
        # ERRO
        # =================================================

        if resposta.status_code != 200:

            await update.message.reply_text(

                "❌ Erro na consulta do Mercado Livre.\n\n"

                f"Status: "
                f"{resposta.status_code}"
            )

            return

        dados = resposta.json()

        produtos = dados.get(
            "results",
            []
        )

        if not produtos:

            await update.message.reply_text(

                f"🔎 Nenhum produto encontrado para:\n"
                f"{termo}"
            )

            return

        # =================================================
        # MONTAR RESULTADOS
        # =================================================

        mensagem = (

            f"🔎 Resultados para:\n"
            f"{termo}\n\n"
        )

        for produto in produtos[:5]:

            produto_id = produto.get(
                "id",
                ""
            )

            nome = produto.get(
                "name",
                "Produto"
            )

            permalink = produto.get(
                "permalink",
                ""
            )

            mensagem += (

                f"🛒 {nome}\n"

                f"🆔 {produto_id}\n"
            )

            if permalink:

                mensagem += (
                    f"🔗 {permalink}\n"
                )

            mensagem += "\n"

        await update.message.reply_text(
            mensagem
        )

    except Exception as erro:

        print(
            "ERRO NA BUSCA DO MERCADO LIVRE:",
            erro
        )

        await update.message.reply_text(

            "❌ Erro ao consultar o Mercado Livre.\n\n"

            f"{erro}"
        )


# =========================================================
# CALLBACK OAUTH
# =========================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        caminho = urlparse(
            self.path
        )

        # =================================================
        # HOME
        # =================================================

        if caminho.path == "/":

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )

            self.end_headers()

            self.wfile.write(

                b"""
                <html>
                <body>
                <h1>
                Bot Promocoes Mercado Livre funcionando!
                </h1>
                </body>
                </html>
                """
            )

            return

        # =================================================
        # OAUTH CALLBACK
        # =================================================

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

            # =============================================
            # CODE
            # =============================================

            if not code:

                self.send_response(400)

                self.end_headers()

                self.wfile.write(

                    b"Codigo de autorizacao "
                    b"nao recebido."
                )

                return

            # =============================================
            # STATE
            # =============================================

            if state != STATE:

                self.send_response(400)

                self.end_headers()

                self.wfile.write(

                    b"Erro de seguranca: "
                    b"state invalido."
                )

                return

            try:

                # =========================================
                # TROCAR CODE POR TOKEN
                # =========================================

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
                    "OAuth Mercado Livre:",
                    resposta.status_code
                )

                print(
                    "OAuth resposta:",
                    resposta.text[:1000]
                )

                # =========================================
                # ERRO
                # =========================================

                if resposta.status_code != 200:

                    self.send_response(400)

                    self.end_headers()

                    self.wfile.write(

                        (
                            "Erro ao obter Access Token.\n\n"
                            + resposta.text
                        ).encode()
                    )

                    return

                dados = resposta.json()

                # =========================================
                # SALVAR TOKEN
                # =========================================

                salvar_token(
                    dados
                )

                # =========================================
                # SUCESSO
                # =========================================

                self.send_response(200)

                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8"
                )

                self.end_headers()

                self.wfile.write(

                    b"""
                    <html>
                    <body>

                    <h1>
                    Mercado Livre conectado!
                    </h1>

                    <p>
                    Autorizacao concluida com sucesso.
                    </p>

                    <p>
                    Agora voce pode voltar ao Telegram.
                    </p>

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

        # =================================================
        # 404
        # =================================================

        self.send_response(404)

        self.end_headers()

    def log_message(
        self,
        format,
        *args
    ):

        pass


# =========================================================
# SERVIDOR WEB DO RENDER
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

    print(
        f"Servidor web iniciado na porta {port}"
    )

    server.serve_forever()


# =========================================================
# MAIN
# =========================================================

def main():

    # =============================================
    # CARREGAR TOKEN
    # =============================================

    carregar_token()

    # =============================================
    # VERIFICAR TELEGRAM
    # =============================================

    if not TOKEN:

        print(
            "ERRO: TELEGRAM_TOKEN não foi configurado."
        )

        return

    # =============================================
    # VERIFICAR CLIENT ID
    # =============================================

    if not ML_CLIENT_ID:

        print(
            "ERRO: ML_CLIENT_ID não foi configurado."
        )

        return

    # =============================================
    # VERIFICAR CLIENT SECRET
    # =============================================

    if not ML_CLIENT_SECRET:

        print(
            "ERRO: ML_CLIENT_SECRET não foi configurado."
        )

        return

    # =============================================
    # SERVIDOR WEB
    # =============================================

    threading.Thread(

        target=run_server,

        daemon=True

    ).start()

    # =============================================
    # TELEGRAM
    # =============================================

    app = (

        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # =============================================
    # COMANDOS
    # =============================================

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

    # =============================================
    # INICIAR
    # =============================================

    print(
        "Bot iniciado com sucesso!"
    )

    app.run_polling()


# =========================================================
# EXECUTAR
# =========================================================

if __name__ == "__main__":

    main()
