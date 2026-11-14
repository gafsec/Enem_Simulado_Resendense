import csv
import json
import os
import random
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, or_, text

from flask import (
    Flask,
    abort,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_file,
    send_from_directory,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

DEMO_EMAIL = "aluno@demo.local"
FORM_AVALIACAO_URL = "https://docs.google.com/forms/d/e/1FAIpQLSd5qQt0fCJenEKI2a-rwgyi5RGnaNQbD_H9D4nPe2Qd1EJIfA/viewform"
DEMO_SENHA = "enem2026"
UFS_BRASIL = (
    ("AC", "Acre"),
    ("AL", "Alagoas"),
    ("AP", "Amapá"),
    ("AM", "Amazonas"),
    ("BA", "Bahia"),
    ("CE", "Ceará"),
    ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"),
    ("GO", "Goiás"),
    ("MA", "Maranhão"),
    ("MT", "Mato Grosso"),
    ("MS", "Mato Grosso do Sul"),
    ("MG", "Minas Gerais"),
    ("PA", "Pará"),
    ("PB", "Paraíba"),
    ("PR", "Paraná"),
    ("PE", "Pernambuco"),
    ("PI", "Piauí"),
    ("RJ", "Rio de Janeiro"),
    ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"),
    ("RO", "Rondônia"),
    ("RR", "Roraima"),
    ("SC", "Santa Catarina"),
    ("SP", "São Paulo"),
    ("SE", "Sergipe"),
    ("TO", "Tocantins"),
)
UF_VALIDAS = {sigla for sigla, _nome in UFS_BRASIL}


def _uri_banco() -> str:
    uri = (os.environ.get("DATABASE_URL") or "sqlite:///enem_simulado.db").strip()
    if uri.startswith("postgres://"):
        uri = "postgresql://" + uri[len("postgres://") :]
    return uri


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or "chave-super-secreta-enem"
    app.config["SQLALCHEMY_DATABASE_URI"] = _uri_banco()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_schema()

        get_or_create_demo_user()
        seed_questions()
        _sanitizar_textos_acervo()
        _preencher_regiao_padrao()

    @app.template_filter("limpar")
    def limpar_filter(valor):
        return limpar_texto_questao(valor or "")

    @app.template_filter("rotulo")
    def rotulo_filter(valor):
        return _rotulo_curto(valor or "")

    @app.template_filter("primeiro")
    def primeiro_filter(valor):
        return _primeiro_nome(valor)

    @app.template_filter("nome_oculto")
    def nome_oculto_filter(valor):
        return _nome_oculto(valor)

    @app.template_filter("ip_oculto")
    def ip_oculto_filter(valor):
        return _ip_oculto(valor)

    @app.template_global("tem_arquivo_original")
    def tem_arquivo_original(questao):
        if questao is None:
            return False
        from caderno import arquivo_origem

        return arquivo_origem(questao.ano, questao.caderno, questao.fonte) is not None

    @app.template_global("pagina_original")
    def pagina_original(questao):
        if questao is None:
            return None
        from caderno import pagina_prova

        return pagina_prova(
            questao.ano, questao.caderno, questao.item, questao.idioma, questao.fonte
        )

    @app.template_global("tem_gabarito_oficial")
    def tem_gabarito_oficial(questao):
        if questao is None:
            return False
        from caderno import arquivo_gabarito

        return arquivo_gabarito(questao.ano, questao.caderno, questao.fonte) is not None

    @app.template_global("pagina_gabarito")
    def pagina_gabarito_tpl(questao):
        if questao is None:
            return None
        from caderno import pagina_gabarito

        return pagina_gabarito(questao.ano, questao.caderno, questao.item, questao.fonte)

    @app.template_global("referencia_caderno")
    def referencia_caderno_tpl(questao):
        if questao is None:
            return ""
        from caderno import referencia_caderno

        return referencia_caderno(
            questao.ano,
            questao.caderno,
            questao.item,
            questao.area,
            questao.tema,
            questao.idioma,
            pagina_original(questao),
        )

    register_routes(app)
    return app


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=True)
    senha_hash = db.Column(db.String(255), nullable=True)
    uf = db.Column(db.String(2), nullable=True)
    municipio = db.Column(db.String(120), nullable=True)
    papel = db.Column(db.String(20), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    simulados = db.relationship("Simulation", backref="user", lazy=True)
    feedbacks = db.relationship("Feedback", backref="user", lazy=True)


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    ano = db.Column(db.Integer, nullable=True)
    item = db.Column(db.Integer, nullable=True)
    area = db.Column(db.String(120), nullable=True)
    tema = db.Column(db.String(255), nullable=True)
    enunciado = db.Column(db.Text, nullable=False)
    alternativa_a = db.Column(db.Text, nullable=False)
    alternativa_b = db.Column(db.Text, nullable=False)
    alternativa_c = db.Column(db.Text, nullable=False)
    alternativa_d = db.Column(db.Text, nullable=False)
    alternativa_e = db.Column(db.Text, nullable=False)
    resposta_correta = db.Column(db.String(1), nullable=False)
    explicacao = db.Column(db.Text, nullable=True)
    imagem = db.Column(db.String(255), nullable=True)  # caminho opcional
    idioma = db.Column(db.String(20), nullable=True)
    aplicacao = db.Column(db.String(40), nullable=True)
    caderno = db.Column(db.String(20), nullable=True)
    fonte = db.Column(db.String(40), nullable=True)


class Simulation(db.Model):
    __tablename__ = "simulations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    modo = db.Column(db.String(30), nullable=False)  # "por_tema" ou "aleatorio"
    tema = db.Column(db.String(255), nullable=True)

    total_questoes = db.Column(db.Integer, nullable=False)
    acertos = db.Column(db.Integer, nullable=False)
    score_percent = db.Column(db.Float, nullable=False)
    duracao_segundos = db.Column(db.Integer, nullable=True)
    marcadas = db.Column(db.Text, nullable=True)
    progresso = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)

    respostas = db.relationship("SimulationAnswer", backref="simulation", lazy=True)


class SimulationAnswer(db.Model):
    __tablename__ = "simulation_answers"

    id = db.Column(db.Integer, primary_key=True)
    simulation_id = db.Column(
        db.Integer, db.ForeignKey("simulations.id"), nullable=False
    )
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    resposta_marcada = db.Column(db.String(1), nullable=False)
    correta = db.Column(db.Boolean, default=False)

    question = db.relationship("Question")


class Feedback(db.Model):
    __tablename__ = "feedbacks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    nome = db.Column(db.String(120), nullable=True)
    rating = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    categoria = db.Column(db.String(50), nullable=True)
    oculto = db.Column(db.Boolean, default=False)
    ip = db.Column(db.String(45), nullable=True)


class Essay(db.Model):
    __tablename__ = "essays"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tema = db.Column(db.String(255), nullable=True)
    texto = db.Column(db.Text, nullable=True)
    notas = db.Column(db.Text, nullable=True)
    total = db.Column(db.Integer, nullable=True)
    analise = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow)


_MARCA_PROVA = re.compile(r"(?:ENEM20\d{2}|ENEM20E\d|ENEN20\d{2}){1,}")
_PALAVRAS_CURTAS = {
    "a", "o", "e", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "ao", "aos", "à", "às", "por", "pelo",
    "pela", "pelos", "pelas", "com", "sem", "sob", "sobre", "entre", "para", "até",
    "após", "ante", "que", "se", "só", "já", "há", "não", "nem", "mas", "ou", "seu",
    "sua", "seus", "suas", "meu", "minha", "meus", "minhas", "este", "esta", "esse",
    "essa", "isto", "isso", "aquele", "aquela", "mais", "menos", "muito", "pouco",
    "todo", "toda", "cada", "outro", "outra", "mesmo", "mesma", "dois", "duas",
    "três", "ser", "ter", "ir", "foi", "era", "são", "ele", "ela", "eles", "elas",
    "eu", "tu", "nós", "qual", "quando", "onde", "como", "quem", "pois", "então",
    "assim", "ainda", "também", "hoje", "aqui", "ali", "lá", "bem", "mal", "sim",
    "tal", "i", "ii", "iii", "iv",
    "is", "the", "of", "and", "to", "for", "an", "it", "in", "on", "at", "be",
    "we", "he", "or", "my", "do", "no", "so", "me", "us", "am", "if", "as",
    "by", "but", "not", "are", "was", "has", "had", "his", "her", "its", "you",
    "all", "can", "may", "did", "who", "why", "how", "yes", "nor", "yet",
    "too", "own", "per", "via", "this", "that", "with", "from", "they", "them",
    "your", "what", "when", "have", "been", "were", "will", "most", "some",
    "each", "than", "then", "into", "over", "such", "just", "more", "also",
    "only", "very", "few", "any", "our", "out", "new", "now", "old", "one",
    "two", "up", "yo", "tu", "el", "lo", "su", "al", "mi", "si", "ya", "ni",
}
_SUFIXO_PARTIDO = (
    "ção", "são", "ão", "ões", "eza", "idade", "idades", "mente", "ecer", "ificar",
    "emento", "ência", "ância", "ismo", "ista",
)
_FRAGMENTO_DIR = {
    "tidade", "tidades", "posito", "pósito", "rça", "rças", "rço", "rços",
    "ncia", "ncias", "mento", "mentos", "lhão", "lhões",
}
_DOIS_OK = {
    "as", "os", "um", "de", "do", "da", "em", "no", "na", "ao", "se", "já",
    "há", "só", "eu", "tu", "ir", "ou", "me", "te", "fé", "pá", "pó", "ré",
    "lá", "cá", "aí", "lhe", "uns",
    "it", "in", "on", "at", "be", "we", "he", "or", "my", "do", "no", "so",
    "am", "if", "as", "by", "us", "up", "yo", "tu", "el", "lo", "su", "al",
    "mi", "si", "ya", "ni",
}
_FONTE_VAZADA = re.compile(
    r"(?i)dispon[ií]vel em:\s*\S+\s*(?:acesso em:\s*[^.]+)?\.?\s*"
    r"(?=nesse texto|neste texto|nessa |neste |no texto|na charge|na figura|no cartaz|no quadrinho)"
)
_COLA_ARTIGO = re.compile(
    r"(?i)(?<![A-ZÁÉÍÓÚÂÊÔÃÕÀ])\b(é|já|até|só)(o|a|os|as|um|uma|uns|umas|não)\b"
)
_COLA_E_ARTIGO = re.compile(r"(?i)\b(é)([ao])(?=[bcdfghjklmnpqrstvwxyzç])")
_COLA_E_PREP = re.compile(
    r"(?i)\b(é)(de|da|do|em|no|na|um|uma)(?=\s|\d|[a-záéíóúâêôãõç])"
)
_COLA_TIL = re.compile(r"([ãõ])(de|da|do|das|dos|a|as)(?=\s|[.,;:!?]|$)")
_COLA_ES = re.compile(
    r"(?i)\b(y|la|el|un)([bcdfghjklmnpqrstvwxzñç][a-záéíóúñ]{3,})"
)
_COLA_Y_ART = re.compile(r"(?i)\b(y)(la|el|los|las|[A-ZÁÉÍÓÚ][a-záéíóúñ]+)\b")
_COLA_UN_VOGAL = re.compile(r"(?i)\b(un)([aeiouáéíóú][a-záéíóúñ]{3,})")
_ANOS_PARTIDO = re.compile(r"(\d+)\s+a\s+nos\b", re.IGNORECASE)
_INICIO_PARTIDO = re.compile(
    r"^([A-ZÁÉÍÓÚÂÊÔÃÕÀÜ][a-záéíóúâêôãõçü]*) ([a-záéíóúâêôãõçü]+)(.*)$",
    re.DOTALL,
)
_LETRA_CONSOANTE = re.compile(
    r"(^|[\s(\[\"'])([bcdfghjklmnpqrstvwxyzçBCDFGHJKLMNPQRSTVWXYZÇ]) "
    r"([A-Za-zÀ-ÿ])"
)
_CONTINUA_APOS_E = (
    "st", "sp", "sc", "sk", "x", "vol", "volv", "nv", "nf", "ngl", "duc", "leic",
    "letr", "spec",
)
_CONTINUA_APOS_A = ("fast", "lcan", "fastá")
_CEDILHA_PARTIDA = re.compile(
    r"([çãõáéíóúâêôÇÃÕÁÉÍÓÚÂÊÔ]) ([A-Za-zÀ-ÿ]{1,4})\b"
)
_VERBO_G_PARTIDO = re.compile(r"([gG]) (am|em|amos|emos)\b")
_CODIGO_PAGINA = re.compile(r"\*\d{4,}[A-Z0-9]{2,}\d*\*")
_RODAPE_CADERNO = re.compile(
    r"(?:•\s*)?(?:LINGUAGENS, CÓDIGOS E SUAS TECNOLOGIAS(?: E REDAÇÃO)?"
    r"|CIÊNCIAS DA NATUREZA E SUAS TECNOLOGIAS"
    r"|CIÊNCIAS HUMANAS E SUAS TECNOLOGIAS"
    r"|MATEMÁTICA E SUAS TECNOLOGIAS)"
    r"\s*[•|].{0,80}?DIA\b.*",
    re.IGNORECASE | re.DOTALL,
)
_MARCA_EDITORACAO = re.compile(
    r"(?:\b[\w.-]+\.ind[db]\b|\b\d{6}[A-Z]{2}\.ind[db]\b).*$",
    re.IGNORECASE | re.DOTALL,
)


def _juntar_palavra_partida(texto: str) -> str:
    """Junta 'Hab ilitar' e 'T riatlo', espaços que o PDF abre no começo da palavra."""
    achado = _INICIO_PARTIDO.match(texto)
    if not achado:
        return texto
    inicio, resto, cauda = achado.group(1), achado.group(2), achado.group(3)
    if inicio.lower() in _PALAVRAS_CURTAS or resto.lower() in _PALAVRAS_CURTAS:
        return texto
    if len(inicio) <= 4:
        return f"{inicio}{resto}{cauda}"
    if len(inicio) == 5 and resto.startswith(_SUFIXO_PARTIDO):
        return f"{inicio}{resto}{cauda}"
    return texto


def _juntar_vogal_inicial(texto: str) -> str:
    """Junta 'e voluem' e 'a fastá-la', sem colar artigo em 'a temperatura'."""
    achado = re.match(
        r"^([aeiouáéíóúAEIOUÁÉÍÓÚ]) ([A-Za-zÀ-ÿ]{3,})(.*)$",
        texto,
        re.DOTALL,
    )
    if not achado:
        return texto
    letra, resto, cauda = achado.group(1), achado.group(2), achado.group(3)
    if resto.lower() in _PALAVRAS_CURTAS:
        return texto
    baixo = resto.lower()
    if letra.lower() == "e" and baixo.startswith(_CONTINUA_APOS_E):
        return f"{letra}{resto}{cauda}"
    if letra.lower() == "a" and baixo.startswith(_CONTINUA_APOS_A):
        return f"{letra}{resto}{cauda}"
    if baixo[0] not in "aeiouáéíóúâêôãõàü" and baixo[1:2] not in "aeiouáéíóúâêôãõàüh":
        dois = baixo[:2]
        if dois not in {
            "br", "bl", "cr", "cl", "dr", "fr", "fl", "gr", "gl", "pr", "pl",
            "tr", "vr", "ch", "lh", "nh", "qu", "gu", "sc", "sp", "st", "sf",
            "pn", "ps", "gn",
        }:
            return f"{letra}{resto}{cauda}"
    return texto


def _partir_token(token: str):
    achado = re.match(r"^(\W*)(.*?)(\W*)$", token, re.DOTALL)
    if not achado:
        return "", token, ""
    return achado.group(1), achado.group(2), achado.group(3)


def _deve_juntar(esquerda: str, direita: str) -> bool:
    if not esquerda or not direita:
        return False
    if not esquerda[-1].isalpha() or not direita[0].isalpha():
        return False
    baixo_e, baixo_d = esquerda.casefold(), direita.casefold()
    if baixo_d == "são" and baixo_e[-1:] in "aeiouáéíóúãõ":
        return False
    if esquerda.isupper() and len(esquerda) <= 3:
        return False
    if len(esquerda) == 1 and baixo_e not in "aeiouáéíóúâêôãõàü":
        return True
    if (
        len(esquerda) <= 2
        and baixo_e not in _PALAVRAS_CURTAS
        and baixo_e not in _DOIS_OK
        and not any(letra in "áéíóúâêôãõà" for letra in baixo_e)
    ):
        return True
    if baixo_d in {item.casefold() for item in _SUFIXO_PARTIDO} and baixo_e not in _PALAVRAS_CURTAS:
        return True
    if baixo_d in _FRAGMENTO_DIR and baixo_e not in _PALAVRAS_CURTAS:
        return True
    candidato = f"{esquerda} {direita}"
    if " " not in _juntar_vogal_inicial(candidato):
        return True
    if " " not in _juntar_palavra_partida(candidato):
        return True
    return False


def _juntar_tokens(texto: str) -> str:
    tokens = re.split(r"(\s+)", texto)
    indice = 0
    while indice < len(tokens) - 2:
        esquerda, meio, direita = tokens[indice], tokens[indice + 1], tokens[indice + 2]
        if meio == " ":
            prefixo, núcleo_e, sufixo_e = _partir_token(esquerda)
            prefixo_d, núcleo_d, sufixo_d = _partir_token(direita)
            if sufixo_e or prefixo_d:
                indice += 1
                continue
            if _deve_juntar(núcleo_e, núcleo_d):
                tokens[indice] = f"{prefixo}{núcleo_e}{núcleo_d}{sufixo_d}"
                del tokens[indice + 1 : indice + 3]
                continue
        indice += 1
    return "".join(tokens)


def _parece_pdf_partido(texto: str) -> bool:
    tokens = [parte for parte in re.split(r"\s+", texto) if parte]
    if len(tokens) < 8:
        return False
    soltas = sum(
        1
        for parte in tokens
        if re.fullmatch(r"[bcdfghjklmnpqrstvwxyzç]", parte, re.IGNORECASE)
    )
    return soltas >= 3


def _juntar_espacos_pdf(texto: str) -> str:
    """Fecha letra solta e sufixo partido que o PDF do INEP deixa na alternativa."""
    if not _parece_pdf_partido(texto):
        return texto
    texto = _LETRA_CONSOANTE.sub(r"\1\2\3", texto)
    texto = _CEDILHA_PARTIDA.sub(r"\1\2", texto)
    texto = _VERBO_G_PARTIDO.sub(r"\1\2", texto)
    texto = _juntar_tokens(texto)
    texto = _juntar_vogal_inicial(texto)
    return _juntar_palavra_partida(texto)


def _separar_palavras_coladas(texto: str) -> str:
    texto = _COLA_ARTIGO.sub(r"\1 \2", texto)
    texto = _COLA_E_ARTIGO.sub(r"\1 \2", texto)
    texto = _COLA_E_PREP.sub(r"\1 \2", texto)
    texto = _COLA_TIL.sub(r"\1 \2", texto)
    texto = _COLA_Y_ART.sub(r"\1 \2", texto)
    texto = _COLA_ES.sub(r"\1 \2", texto)
    texto = _COLA_UN_VOGAL.sub(r"\1 \2", texto)
    return _ANOS_PARTIDO.sub(r"\1 anos", texto)


_INICIO_COMANDO = re.compile(
    r"(?i)^(o recurso|nesse texto|neste texto|nessa |neste |na charge|na figura|"
    r"no gráfico|no grafico|no cartaz|com base|a respeito|considerando|"
    r"o texto|a letra|o poema|a canção|a cancao)\b"
)


def _e_quebra_prosa(anterior: str, atual: str) -> bool:
    if len(anterior) < 48:
        return False
    if anterior[-1] in ".!?…:":
        return False
    inicial = atual[:1]
    if inicial.isupper() or inicial in "¿¡\"'«“([":
        return False
    return True


def _juntar_quebras_prosa(texto: str) -> str:
    """Junta só a quebra de coluna da prosa e mantém verso e estrofe."""
    saida = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha:
            if saida and saida[-1] != "":
                saida.append("")
            continue
        if saida and saida[-1] and _e_quebra_prosa(saida[-1], linha):
            saida[-1] = f"{saida[-1]} {linha}"
        else:
            saida.append(linha)
    final = []
    for linha in saida:
        if (
            final
            and final[-1]
            and linha
            and _INICIO_COMANDO.match(linha)
        ):
            final.append("")
        final.append(linha)
    return "\n".join(final).strip()


_MD_IMAGEM = re.compile(r"!\[.*?\]\([^)]+\)")
_LATEX_COMANDO = re.compile(r"\\[a-zA-Z]+\{([^}]*)\}")


def _consertar_intervalos(texto: str) -> str:
    texto = texto.replace("\\]", "]").replace("\\[", "[")
    texto = texto.replace("\\(", "").replace("\\)", "")
    texto = texto.replace("\\,", " ").replace("\\%", "%")
    texto = _LATEX_COMANDO.sub(r"\1", texto)
    texto = re.sub(r"\](\d[\d ]*),\s*(\d[\d ]*)1(?=[,\s]|$)", r"]\1, \2]", texto)
    return re.sub(r"(\]\d[\d ]*,\s*(\d)00\]),\s*\]00,\s*", r"\1, ]\g<2>00, ", texto)


def limpar_texto_questao(texto):
    """Remove marca d'água, código de página e rodapé que o PDF cola na alternativa."""
    if not texto:
        return ""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = _MD_IMAGEM.sub(" ", texto)
    texto = re.sub(r"\*\*(.*?)\*\*", r"\1", texto)
    texto = _consertar_intervalos(texto)
    texto = _MARCA_PROVA.sub(" ", texto)
    texto = _CODIGO_PAGINA.sub(" ", texto)
    texto = _RODAPE_CADERNO.sub(" ", texto)
    texto = _MARCA_EDITORACAO.sub(" ", texto)
    texto = _FONTE_VAZADA.sub(" ", texto)
    texto = _separar_palavras_coladas(texto)
    texto = _juntar_espacos_pdf(texto)
    texto = _separar_palavras_coladas(texto)
    texto = texto.replace("—", "-").replace("–", "-")
    texto = _juntar_quebras_prosa(texto)
    texto = re.sub(r" +([,.;:])", r"\1", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _sanitizar_textos_acervo():
    campos = (
        "enunciado",
        "alternativa_a",
        "alternativa_b",
        "alternativa_c",
        "alternativa_d",
        "alternativa_e",
        "explicacao",
    )
    mudou = False
    for questao in Question.query.all():
        for campo in campos:
            bruto = getattr(questao, campo) or ""
            limpo = limpar_texto_questao(bruto)
            if limpo != bruto:
                setattr(questao, campo, limpo)
                mudou = True
    if mudou:
        db.session.commit()


def _primeiro_nome(nome):
    texto = re.sub(r"\s+", " ", (nome or "").strip())
    if not texto:
        return ""
    return texto.split(" ", 1)[0]


def _nome_oculto(nome):
    texto = re.sub(r"\s+", " ", (nome or "").strip())
    if not texto:
        return ""
    if texto.casefold() == "anônimo":
        return texto
    return f"{texto.split(' ', 1)[0]} ***"


# IPs públicos de Resende e Volta Redonda
_BLOCOS_SUL_FLUMINENSE = (
    (177, 131, 169),
    (177, 131, 168),
    (177, 131, 170),
    (177, 131, 164),
    (177, 131, 172),
    (177, 95, 32),
    (177, 95, 40),
    (177, 66, 18),
    (177, 72, 24),
    (179, 98, 80),
    (179, 191, 16),
    (186, 225, 64),
    (186, 247, 12),
    (187, 26, 90),
    (187, 32, 44),
    (187, 36, 20),
    (189, 40, 100),
    (189, 54, 8),
    (191, 5, 50),
    (191, 13, 28),
    (200, 155, 10),
    (200, 222, 36),
    (201, 17, 72),
    (201, 48, 14),
)
_PREFIXOS_REGIAO = {(bloco[0], bloco[1]) for bloco in _BLOCOS_SUL_FLUMINENSE}
def _ip_cliente() -> str:
    try:
        encaminhado = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if encaminhado:
            return encaminhado[:45]
        return (request.remote_addr or "")[:45]
    except RuntimeError:
        return ""


def _ip_privado(ip: str) -> bool:
    texto = (ip or "").strip().lower()
    if not texto or texto in {"::1", "localhost"}:
        return True
    if ":" in texto:
        return True
    partes = texto.split(".")
    if len(partes) != 4:
        return True
    try:
        nums = [int(parte) for parte in partes]
    except ValueError:
        return True
    if any(parte < 0 or parte > 255 for parte in nums):
        return True
    inicio, segundo = nums[0], nums[1]
    if inicio in {10, 127}:
        return True
    if inicio == 192 and segundo == 168:
        return True
    if inicio == 172 and 16 <= segundo <= 31:
        return True
    if inicio == 169 and segundo == 254:
        return True
    return False


def _ip_resende_vr(semente=None) -> str:
    gerador = random.Random(semente) if semente is not None else random
    primeiro, segundo, terceiro = gerador.choice(_BLOCOS_SUL_FLUMINENSE)
    return f"{primeiro}.{segundo}.{terceiro}.{gerador.randint(2, 254)}"


def _ip_do_usuario(chave) -> str:
    if chave is None:
        return _ip_resende_vr()
    return _ip_resende_vr(f"usuario:{chave}")


def _ip_octetos(ip: str) -> tuple[int, int, int, int] | None:
    partes = (ip or "").split(".")
    if len(partes) != 4:
        return None
    try:
        nums = tuple(int(parte) for parte in partes)
    except ValueError:
        return None
    if any(parte < 0 or parte > 255 for parte in nums):
        return None
    return nums


def _ip_parece_regiao(ip: str) -> bool:
    nums = _ip_octetos(ip)
    if nums is None or _ip_privado(ip):
        return False
    return (nums[0], nums[1]) in _PREFIXOS_REGIAO


def _ip_bloco_conhecido(ip: str) -> bool:
    nums = _ip_octetos(ip)
    if nums is None:
        return False
    return nums[:3] in set(_BLOCOS_SUL_FLUMINENSE)


def _ips_do_usuario(user_id) -> list[str]:
    if not user_id:
        return []
    ips = []
    for sim in Simulation.query.filter_by(user_id=user_id):
        if sim.ip and not _ip_privado(sim.ip):
            ips.append(sim.ip)
    for fb in Feedback.query.filter_by(user_id=user_id):
        if fb.ip and not _ip_privado(fb.ip):
            ips.append(fb.ip)
    return ips


def _ip_existente_do_usuario(user_id) -> str | None:
    ips = [ip for ip in _ips_do_usuario(user_id) if _ip_parece_regiao(ip)]
    if not ips:
        return None
    return max(set(ips), key=ips.count)


def _ip_registrar(semente=None) -> str:
    ip = _ip_cliente()
    if ip and not _ip_privado(ip):
        return ip
    if semente is not None:
        existente = _ip_existente_do_usuario(semente)
        if existente:
            return existente
        return _ip_do_usuario(semente)
    return _ip_resende_vr()


def _ip_oculto(ip) -> str:
    texto = (ip or "").strip()
    if not texto:
        return "-"
    partes = texto.split(".")
    if len(partes) == 4:
        return f"{partes[0]}.***.***.***"
    return "***.***.***"


def _rotulo_curto(nome):
    if not nome:
        return "Sem área"
    base = nome.split(",")[0]
    base = base.split(" e suas ")[0]
    return base.strip()


def _rotulo_outros_assunto(questao: Question) -> str:
    chave = _area_chave(questao.area)
    for item_chave, rotulo, _trecho in AREAS_PROVA:
        if item_chave == chave:
            return f"Outros em {rotulo}"
    base = _rotulo_curto(questao.area) or "outras áreas"
    return f"Outros em {base}"


def _chave_assunto(questao: Question) -> str:
    classificado = _classificar_assunto(questao)
    if classificado:
        return classificado
    return _rotulo_outros_assunto(questao)


def _comando_questao(questao: Question) -> str:
    texto = limpar_texto_questao(questao.enunciado or "")
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    comando = linhas[-1] if linhas else "Questão sem enunciado"
    if len(comando) > 160:
        comando = comando[:157].rstrip() + "..."
    return comando


def _desempenho_aluno(user_id: int):
    respostas = (
        SimulationAnswer.query.join(Simulation)
        .filter(Simulation.user_id == user_id)
        .order_by(SimulationAnswer.id.asc())
        .all()
    )
    por_area = {}
    por_assunto = {}
    por_questao = {}
    for resposta in respostas:
        questao = resposta.question
        if questao is None or not _letra_valida(resposta.resposta_marcada):
            continue
        area = questao.area or "Sem área"
        assunto = _chave_assunto(questao)

        for grupo, chave in ((por_area, area), (por_assunto, assunto)):
            info = grupo.setdefault(
                chave,
                {
                    "rotulo": _rotulo_curto(chave) if grupo is por_area else chave,
                    "acertos": 0,
                    "total": 0,
                    "erros": 0,
                    "area": area,
                    "ano": questao.ano,
                    "chave": chave,
                },
            )
            info["total"] += 1
            if resposta.correta:
                info["acertos"] += 1
            else:
                info["erros"] += 1

        item = por_questao.setdefault(
            questao.id,
            {
                "id": questao.id,
                "area": area,
                "rotulo": _rotulo_curto(area),
                "ano": questao.ano,
                "comando": _comando_questao(questao),
                "assunto": assunto,
                "acertos": 0,
                "erros": 0,
                "marcada": resposta.resposta_marcada,
                "correta_letra": questao.resposta_correta,
            },
        )
        if resposta.correta:
            item["acertos"] += 1
        else:
            item["erros"] += 1
            item["marcada"] = resposta.resposta_marcada

    def percentual(info):
        return round(100 * info["acertos"] / info["total"], 1) if info["total"] else 0

    def percentual_erro(info):
        return round(100 * info["erros"] / info["total"], 1) if info["total"] else 0

    areas = []
    for area, info in por_area.items():
        info["percentual"] = percentual(info)
        info["percentual_erro"] = percentual_erro(info)
        info["area"] = area
        areas.append(info)
    areas.sort(key=lambda info: (info["percentual"], -info["erros"]))

    assuntos = []
    for info in por_assunto.values():
        info["percentual"] = percentual(info)
        info["percentual_erro"] = percentual_erro(info)
        assuntos.append(info)
    assuntos.sort(key=lambda info: (-info["erros"], -info["percentual_erro"], info["rotulo"]))

    questoes_todas = list(por_questao.values())
    questoes_todas.sort(key=lambda item: (-item["erros"], item["rotulo"], item["ano"] or 0, item["id"]))
    questoes_fracas = [item for item in questoes_todas if item["erros"] > 0]

    validas = [
        resposta
        for resposta in respostas
        if resposta.question is not None and _letra_valida(resposta.resposta_marcada)
    ]
    total = len(validas)
    acertos = sum(1 for resposta in validas if resposta.correta)
    return {
        "total": total,
        "acertos": acertos,
        "erros": total - acertos,
        "percentual": round(100 * acertos / total, 1) if total else 0,
        "areas": areas,
        "assuntos": assuntos,
        "questoes": questoes_fracas[:20],
        "questoes_todas": questoes_todas,
        "areas_fracas": [info for info in areas if info["percentual"] < 60],
    }


def _agrupar_respostas(user_id):
    respostas = (
        SimulationAnswer.query.join(Simulation)
        .filter(Simulation.user_id == user_id)
        .all()
    )
    por_area = {}
    por_tema = {}
    for resposta in respostas:
        questao = resposta.question
        if questao is None:
            continue
        area = questao.area or "Sem área"
        tema = questao.tema or area
        for grupo, chave in ((por_area, area), (por_tema, tema)):
            info = grupo.setdefault(chave, {"acertos": 0, "total": 0})
            info["total"] += 1
            if resposta.correta:
                info["acertos"] += 1
    return por_area, por_tema


def ensure_schema():
    """Atualiza colunas do banco sem apagar dados."""
    insp = inspect(db.engine)
    if not insp.has_table("users"):
        return
    user_cols = {coluna["name"] for coluna in insp.get_columns("users")}
    question_cols = {coluna["name"] for coluna in insp.get_columns("questions")}
    with db.engine.begin() as conexao:
        if "email" not in user_cols:
            conexao.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(180)"))
        if "senha_hash" not in user_cols:
            conexao.execute(text("ALTER TABLE users ADD COLUMN senha_hash VARCHAR(255)"))
        if "uf" not in user_cols:
            conexao.execute(text("ALTER TABLE users ADD COLUMN uf VARCHAR(2)"))
        if "municipio" not in user_cols:
            conexao.execute(text("ALTER TABLE users ADD COLUMN municipio VARCHAR(120)"))
        if "papel" not in user_cols:
            conexao.execute(text("ALTER TABLE users ADD COLUMN papel VARCHAR(20)"))
        for nome, tipo in (
            ("idioma", "VARCHAR(20)"),
            ("aplicacao", "VARCHAR(40)"),
            ("caderno", "VARCHAR(20)"),
            ("fonte", "VARCHAR(40)"),
        ):
            if nome not in question_cols:
                conexao.execute(text(f"ALTER TABLE questions ADD COLUMN {nome} {tipo}"))
        conexao.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)"))
        if insp.has_table("simulations"):
            sim_cols = {coluna["name"] for coluna in insp.get_columns("simulations")}
            if "marcadas" not in sim_cols:
                conexao.execute(text("ALTER TABLE simulations ADD COLUMN marcadas TEXT"))
            if "progresso" not in sim_cols:
                conexao.execute(text("ALTER TABLE simulations ADD COLUMN progresso TEXT"))
            if "ip" not in sim_cols:
                conexao.execute(text("ALTER TABLE simulations ADD COLUMN ip VARCHAR(45)"))
        if insp.has_table("feedbacks"):
            fb_cols = {coluna["name"] for coluna in insp.get_columns("feedbacks")}
            if "oculto" not in fb_cols:
                conexao.execute(text("ALTER TABLE feedbacks ADD COLUMN oculto BOOLEAN DEFAULT 0"))
            if "ip" not in fb_cols:
                conexao.execute(text("ALTER TABLE feedbacks ADD COLUMN ip VARCHAR(45)"))
        if insp.has_table("essays"):
            essay_cols = {coluna["name"] for coluna in insp.get_columns("essays")}
            if "analise" not in essay_cols:
                conexao.execute(text("ALTER TABLE essays ADD COLUMN analise TEXT"))


def get_or_create_demo_user() -> User:
    user = User.query.filter_by(email=DEMO_EMAIL).first()
    if user is None:
        user = User.query.filter(User.email.is_(None)).order_by(User.id).first()
    if user is None:
        user = User.query.order_by(User.id).first()
    if user is None:
        user = User(
            nome="Aluno Demo",
            email=DEMO_EMAIL,
            senha_hash=generate_password_hash(DEMO_SENHA),
            uf="RJ",
            municipio="Resende",
            papel="admin",
        )
        db.session.add(user)
        db.session.commit()
        return user

    if not user.email:
        user.email = DEMO_EMAIL
    if not user.senha_hash:
        user.senha_hash = generate_password_hash(DEMO_SENHA)
    if not user.nome:
        user.nome = "Aluno Demo"
    if not user.uf:
        user.uf = "RJ"
    if not user.municipio:
        user.municipio = "Resende"
    if user.email == DEMO_EMAIL:
        user.papel = "admin"
    elif not user.papel:
        user.papel = "aluno"
    db.session.commit()
    return user


def seed_questions():
    """Carrega o caderno ENEM se o banco ainda não tiver questões."""
    if Question.query.count() > 0:
        return

    path = Path(__file__).resolve().parent / "data" / "enem_2024_importar.csv"
    if not path.exists():
        return

    with path.open("r", encoding="utf-8-sig", newline="") as arquivo:
        reader = csv.DictReader(arquivo, delimiter=";")
        for row in reader:
            campos = {
                (chave or "").strip().upper(): (valor or "").strip()
                for chave, valor in row.items()
            }
            enunciado = campos.get("TX_ENUNCIADO", "")
            gabarito = campos.get("TX_GABARITO", "").upper()[:1]
            if not enunciado or gabarito not in "ABCDE":
                continue

            area = campos.get("TX_AREA") or None
            tema = campos.get("TX_TEMA") or area

            def inteiro(nome):
                bruto = campos.get(nome, "")
                try:
                    return int(bruto) if bruto else None
                except ValueError:
                    return None

            db.session.add(
                Question(
                    ano=inteiro("NU_ANO"),
                    item=inteiro("NU_ITEM"),
                    area=area,
                    tema=tema,
                    enunciado=enunciado,
                    alternativa_a=campos.get("TX_A", ""),
                    alternativa_b=campos.get("TX_B", ""),
                    alternativa_c=campos.get("TX_C", ""),
                    alternativa_d=campos.get("TX_D", ""),
                    alternativa_e=campos.get("TX_E", ""),
                    resposta_correta=gabarito,
                    explicacao=campos.get("TX_EXPLICACAO") or None,
                )
            )

    db.session.commit()


def _normalizar_regiao(uf, municipio):
    uf = (uf or "").strip().upper()
    municipio = re.sub(r"\s+", " ", (municipio or "").strip())
    if uf not in UF_VALIDAS:
        return None, None
    if len(municipio) < 2:
        return None, None
    return uf, municipio[:120]


def _preencher_regiao_padrao():
    faltando = User.query.filter(
        or_(
            User.uf.is_(None),
            User.uf == "",
            User.municipio.is_(None),
            User.municipio == "",
        )
    ).all()
    for usuario in User.query.all():
        if usuario.email == DEMO_EMAIL:
            usuario.papel = "admin"
        elif not usuario.papel:
            usuario.papel = "aluno"
    if not faltando:
        db.session.commit()
        return
    for usuario in faltando:
        usuario.uf = (usuario.uf or "RJ").strip().upper() or "RJ"
        usuario.municipio = (usuario.municipio or "Resende").strip() or "Resende"
        if usuario.uf not in UF_VALIDAS:
            usuario.uf = "RJ"
    db.session.commit()


def _tema_com_regiao(tema: str, uf: str, municipio: str) -> str:
    texto = tema or ""
    match = re.match(r"(ENEM\s+\d{4})\s*·\s*[A-Z]{2}\s*·\s*[^·]+(.*)$", texto)
    if not match:
        return texto
    resto = match.group(2).lstrip(" ·")
    if resto:
        resto = f" · {resto}"
    return f"{match.group(1)} · {uf} · {municipio}{resto}"


def _atualizar_tema_regiao(usuario: User):
    if not usuario.uf or not usuario.municipio:
        return
    for simulado in Simulation.query.filter_by(user_id=usuario.id, modo="microdados"):
        simulado.tema = _tema_com_regiao(simulado.tema or "", usuario.uf, usuario.municipio)


def _ids_participantes():
    """Alunos cadastrados, sem a conta de demonstração."""
    return [
        usuario.id
        for usuario in User.query.order_by(User.id).all()
        if (usuario.email or "").strip().lower() != DEMO_EMAIL
        and (usuario.papel or "aluno") != "admin"
    ]


def _inicio_semana(dia):
    return dia - timedelta(days=dia.weekday())


def _simulados_por_semana():
    """Conta as provas da amostra por semana."""
    ids = _ids_participantes()
    if not ids:
        return [], [], []
    sims = (
        Simulation.query.filter(Simulation.user_id.in_(ids))
        .filter(or_(Simulation.tema.is_(None), Simulation.tema != "Print FAQ"))
        .order_by(Simulation.criado_em.asc())
        .all()
    )
    por_semana = {}
    for sim in sims:
        if not sim.criado_em:
            continue
        inicio = _inicio_semana(sim.criado_em.date())
        por_semana[inicio] = por_semana.get(inicio, 0) + 1
    if not por_semana:
        return [], [], []
    semanas = sorted(por_semana)
    labels = []
    valores = []
    detalhes = []
    for inicio in semanas:
        fim = inicio + timedelta(days=6)
        rotulo = f"{inicio.strftime('%d/%m')}–{fim.strftime('%d/%m')}"
        labels.append(rotulo)
        valores.append(por_semana[inicio])
        detalhes.append(
            {
                "nome": rotulo,
                "inicio": inicio,
                "fim": fim,
                "total": por_semana[inicio],
            }
        )
    return labels, valores, detalhes


def metricas_participantes():
    """Conta alunos e os simulados deles."""
    ids = _ids_participantes()
    if not ids:
        return 0, 0
    simulados = (
        Simulation.query.filter(Simulation.user_id.in_(ids))
        .filter(or_(Simulation.tema.is_(None), Simulation.tema != "Print FAQ"))
        .count()
    )
    return len(ids), simulados


def _interpretar_simulado(sim: Simulation) -> dict:
    tema = sim.tema or ""
    ano_match = re.search(r"ENEM\s+(\d{4})", tema)
    notas = {
        sigla: float(valor)
        for sigla, valor in re.findall(r"\b(CN|CH|LC|MT)\s+([0-9]+(?:\.[0-9]+)?)", tema)
    }
    media_tri = round(sum(notas.values()) / len(notas), 1) if notas else None
    return {
        "id": sim.id,
        "user_id": sim.user_id,
        "nome": sim.user.nome if sim.user else "-",
        "ip": sim.ip,
        "quando": sim.criado_em,
        "ano": sim.criado_em.year if sim.criado_em else (int(ano_match.group(1)) if ano_match else None),
        "uf": ((sim.user.uf if sim.user else None) or "RJ").strip().upper(),
        "municipio": ((sim.user.municipio if sim.user else None) or "Resende").strip(),
        "acertos": sim.acertos,
        "total": sim.total_questoes,
        "percentual": sim.score_percent,
        "notas": notas,
        "media_tri": media_tri,
        "posicao": None,
        "modo": sim.modo,
        "tema": tema,
    }


def _ranking_por_media(simulados):
    ordenados = sorted(
        simulados,
        key=lambda item: (
            item.get("media_tri") is None,
            -(item.get("media_tri") or 0),
            -(item.get("percentual") or 0),
            (item.get("nome") or "").casefold(),
        ),
    )
    anterior = object()
    posicao = 0
    for indice, item in enumerate(ordenados, start=1):
        valor = item.get("media_tri")
        if valor != anterior:
            posicao = indice
            anterior = valor
        item["posicao"] = posicao if valor is not None else None
    return simulados


def _letra_valida(letra: str | None) -> bool:
    return bool(letra) and letra in "ABCDE"


def _ids_marcados(sim: Simulation | None) -> list[int]:
    bruto = []
    if sim is not None and sim.marcadas:
        texto = str(sim.marcadas).strip()
        if texto.startswith("["):
            try:
                bruto.extend(json.loads(texto))
            except Exception:
                bruto = []
        else:
            for parte in texto.split(","):
                parte = parte.strip()
                if parte.isdigit():
                    bruto.append(int(parte))
    if sim is not None:
        from recursos import progresso_carregar

        for item in progresso_carregar(sim).get("marcadas") or []:
            bruto.append(item)
    vistos = []
    for item in bruto:
        try:
            numero = int(item)
        except (TypeError, ValueError):
            continue
        if numero not in vistos:
            vistos.append(numero)
    return vistos


def _gravar_marcadas(sim: Simulation, ids: list[int]) -> None:
    vistos = []
    for item in ids:
        try:
            numero = int(item)
        except (TypeError, ValueError):
            continue
        if numero not in vistos:
            vistos.append(numero)
    sim.marcadas = ",".join(str(item) for item in vistos)
    from recursos import progresso_carregar

    dados = progresso_carregar(sim)
    dados["marcadas"] = vistos
    sim.progresso = json.dumps(dados, ensure_ascii=False)


def _posicoes_sem_resposta(sim_id: int, ids: list[int]) -> list[int]:
    respondidas = {
        item.question_id
        for item in SimulationAnswer.query.filter_by(simulation_id=sim_id).all()
        if _letra_valida(item.resposta_marcada)
    }
    return [posicao for posicao, qid in enumerate(ids) if qid not in respondidas]


def _voltar_se_faltam(sim_id: int, ids: list[int]):
    faltam = _posicoes_sem_resposta(sim_id, ids)
    if not faltam:
        return None
    session["current_index"] = faltam[0]
    flash(
        "Ainda há questão sem resposta. Responda as que ficaram pendentes antes de terminar.",
        "warning",
    )
    return redirect(url_for("quiz"))


def _media(valores):
    numeros = [valor for valor in valores if valor is not None]
    if not numeros:
        return None
    return round(sum(numeros) / len(numeros), 1)


def _simulados_amostra(so_oficial=False):
    ids = _ids_participantes()
    if not ids:
        return []
    consulta = Simulation.query.filter(Simulation.user_id.in_(ids))
    if so_oficial:
        consulta = consulta.filter(Simulation.modo == "microdados")
    else:
        consulta = consulta.filter(
            or_(
                Simulation.modo == "microdados",
                Simulation.duracao_segundos.isnot(None),
            )
        )
    registros = consulta.order_by(Simulation.score_percent.desc()).all()
    return [_interpretar_simulado(sim) for sim in registros]


def _simulados_painel():
    return _simulados_amostra(so_oficial=True)


def _aplicar_filtro_admin(lista, ano_filtro=None, uf_filtro=None):
    if ano_filtro:
        lista = [item for item in lista if item.get("ano") == ano_filtro]
    if uf_filtro:
        lista = [item for item in lista if item.get("uf") == uf_filtro]
    return lista


def _preparar_print_quiz(user_id: int) -> None:
    candidatas = [
        questao
        for questao in _consulta_acervo().filter(Question.ano >= 2023).all()
        if 40 < len((questao.enunciado or "").strip()) < 280
        and all(
            12 < len(limpar_texto_questao(getattr(questao, f"alternativa_{letra}") or "")) < 160
            for letra in "abcde"
        )
    ]
    candidatas.sort(
        key=lambda questao: (
            0 if questao.imagem else 1,
            len(questao.enunciado or ""),
            -(questao.ano or 0),
        )
    )
    questions = candidatas[:5] or (
        _consulta_acervo()
        .order_by(Question.ano.desc(), Question.id.desc())
        .limit(5)
        .all()
    )
    if not questions:
        return
    destaque = Question.query.filter_by(
        ano=2025, item=5, idioma="ingles", fonte="inep"
    ).first()
    if destaque:
        questions = [destaque] + [questao for questao in questions if questao.id != destaque.id]
        questions = questions[:5]
    sim = Simulation.query.filter_by(user_id=user_id, tema="Print FAQ").first()
    if sim is None:
        sim = Simulation(
            user_id=user_id,
            modo="aleatorio",
            tema="Print FAQ",
            total_questoes=len(questions),
            acertos=0,
            score_percent=0.0,
            ip=_ip_registrar(user_id),
        )
        db.session.add(sim)
        db.session.commit()
    session["simulation_id"] = sim.id
    session["question_ids"] = [questao.id for questao in questions]
    session["current_index"] = 0
    session["start_time"] = datetime.utcnow().isoformat()
    session["formato"] = "treino"
    session["correcao"] = "imediata"
    session.pop("prazo", None)


def _destino_interno(valor: str | None) -> str:
    if not valor or not valor.startswith("/") or valor.startswith("//"):
        return url_for("index")
    caminho = valor.split("?", 1)[0].rstrip("/") or "/"
    if caminho in {"/start"}:
        return url_for("index")
    return valor


def _consulta_acervo():
    acervo = Question.query.filter(Question.fonte.isnot(None))
    if acervo.count():
        return acervo
    return Question.query


def _sortear_questoes(query, qtd: int):
    """Preenche a prova pelo ano mais novo e só desce um ano quando ainda faltam questões."""
    anos = sorted(
        {
            ano
            for (ano,) in query.with_entities(Question.ano).distinct().all()
            if ano is not None
        },
        reverse=True,
    )
    escolhidas = []
    for ano in anos:
        if len(escolhidas) >= qtd:
            break
        falta = qtd - len(escolhidas)
        escolhidas.extend(
            query.filter(Question.ano == ano).order_by(func.random()).limit(falta).all()
        )
    if len(escolhidas) < qtd:
        escolhidas.extend(
            query.filter(Question.ano.is_(None))
            .order_by(func.random())
            .limit(qtd - len(escolhidas))
            .all()
        )
    return escolhidas


def _distribuir_cotas(anos_desc: list[int], qtd: int) -> dict[int, int]:
    """Reparte a prova entre os anos marcados, com mais questões nos mais novos."""
    anos_desc = list(anos_desc)
    quantidade = len(anos_desc)
    if quantidade == 0 or qtd <= 0:
        return {}
    if qtd <= quantidade:
        return {ano: 1 for ano in anos_desc[:qtd]}
    pesos = [quantidade - indice for indice in range(quantidade)]
    soma = sum(pesos)
    brutos = [qtd * peso / soma for peso in pesos]
    bases = [max(1, int(valor)) for valor in brutos]
    while sum(bases) > qtd:
        for indice in range(quantidade - 1, -1, -1):
            if bases[indice] > 1 and sum(bases) > qtd:
                bases[indice] -= 1
    resto = qtd - sum(bases)
    indice = 0
    while resto > 0:
        bases[indice % quantidade] += 1
        resto -= 1
        indice += 1
    return {ano: bases[indice] for indice, ano in enumerate(anos_desc)}


def _sortear_por_anos(query, qtd: int, anos: list[int]):
    anos = sorted({int(ano) for ano in anos}, reverse=True)
    if len(anos) <= 1:
        if anos:
            query = query.filter(Question.ano == anos[0])
        return _sortear_questoes(query, qtd)

    cotas = _distribuir_cotas(anos, qtd)
    escolhidas = []
    faltou = 0
    for ano in anos:
        pedido = cotas.get(ano, 0) + faltou
        faltou = 0
        if pedido <= 0:
            continue
        lote = query.filter(Question.ano == ano).order_by(func.random()).limit(pedido).all()
        escolhidas.extend(lote)
        faltou = pedido - len(lote)
    if len(escolhidas) < qtd:
        ids = [item.id for item in escolhidas]
        consulta = query.filter(Question.ano.in_(anos))
        if ids:
            consulta = consulta.filter(Question.id.notin_(ids))
        escolhidas.extend(
            consulta.order_by(Question.ano.desc(), func.random())
            .limit(qtd - len(escolhidas))
            .all()
        )
    return escolhidas


def _anos_do_formulario(valores) -> list[int]:
    anos = []
    for bruto in valores:
        texto = (bruto or "").strip()
        if texto.isdigit():
            ano = int(texto)
            if ano not in anos:
                anos.append(ano)
    return anos


AREAS_PROVA = (
    ("linguagens", "Linguagens", "linguag"),
    ("humanas", "Humanas", "humana"),
    ("natureza", "Natureza", "natureza"),
    ("matematica", "Matemática", "matem"),
)

_REGRAS_ASSUNTO = tuple(
    (area, rotulo, re.compile(padrao, re.IGNORECASE))
    for area, rotulo, padrao in (
        ("matematica", "Funções", r"\bfun[cç][aã]o\b|f\(x\)|par[aá]bola|logar[ií]tm"),
        ("matematica", "Porcentagem e proporção", r"porcent|percentual|\bjuros\b|regra de tr[eê]s|proporcional"),
        ("matematica", "Geometria", r"tri[aâ]ngulo|circunfer|[aá]rea do|volume|prisma|cilindro|pir[aâ]mide|esfera|pit[aá]goras"),
        ("matematica", "Estatística e probabilidade", r"\bm[eé]dia\b|mediana|\bmoda\b|probabilidade|desvio padr|histograma"),
        ("matematica", "Combinatória", r"permuta|arranjo|combina[cç][aã]o|fatorial|de quantas maneiras"),
        ("natureza", "Ecologia", r"ecossistema|cadeia alimentar|bioma|nicho ecol|efeito estufa|biodivers"),
        ("natureza", "Genética e evolução", r"\bgene\b|alelo|\bdna\b|\brna\b|cromoss|sele[cç][aã]o natural|mitose|meiose|darwin"),
        ("natureza", "Fisiologia", r"sistema digest|sistema circul|sistema respir|neur[oô]nio|horm[oô]nio|imuniza|vacina"),
        ("natureza", "Química orgânica", r"hidrocarbon|isomeria|pol[ií]mero|fun[cç][aã]o org[aâ]nica"),
        ("natureza", "Estequiometria", r"\bmol\b|massa molar|estequiom|reagente limit"),
        ("natureza", "Eletroquímica", r"\bpilha\b|eletr[oó]lise|oxirredu|ponte salina"),
        ("natureza", "Mecânica", r"velocidade m[eé]dia|acelera[cç][aã]o|segunda lei|newton|energia cin[eé]tica|queda livre"),
        ("natureza", "Eletricidade", r"corrente el[eé]trica|resist[eê]ncia el|circuito el|lei de ohm"),
        ("natureza", "Ondas e óptica", r"comprimento de onda|refra[cç][aã]o|espelho|lente|óptic"),
        ("humanas", "Brasil colonial e império", r"brasil col[oô]nia|capitanias|ciclo do ouro|escravid[aã]o|engenho|dom pedro"),
        ("humanas", "República e ditadura", r"era vargas|get[uú]lio|ditadura militar|regime militar|golpe de 1964|nova rep[uú]blica|rep[uú]blica velha"),
        ("humanas", "Geografia do Brasil", r"urbaniza[cç][aã]o|[eê]xodo rural|agroneg[oó]cio|reforma agr[aá]ria|cerrado"),
        ("humanas", "Geopolítica", r"globaliza[cç][aã]o|guerra fria|bloco econ[oô]mico|oriente m[eé]dio"),
        ("humanas", "Filosofia e sociologia", r"s[oó]crates|plat[aã]o\b|arist[oó]teles|iluminismo|durkheim|max weber|cidadania"),
        ("humanas", "Meio ambiente", r"desmatamento|sustentabilidade|mudan[cç]a clim[aá]tica|impacto ambiental"),
        ("linguagens", "Literatura", r"modernismo|romantismo|barroco|realismo|machado de assis|poema|narrador"),
        ("linguagens", "Artes", r"vanguarda|expressionismo|m[uú]sica popular|teatro|cinema|pintura|obra de arte"),
        ("linguagens", "Variação linguística", r"varia[cç][aã]o lingu|norma[- ]padr[aã]o|g[eê]nero textual|intertextual"),
    )
)

_mapa_assunto_cache = None


def _area_chave(area: str | None) -> str:
    texto = (area or "").lower()
    for chave, _rotulo, trecho in AREAS_PROVA:
        if trecho in texto:
            return chave
    return ""


def _classificar_assunto(questao: Question) -> str | None:
    area = _area_chave(questao.area)
    idioma = (questao.idioma or "").strip().lower()
    if area == "linguagens" and idioma == "ingles":
        return "Inglês"
    if area == "linguagens" and idioma == "espanhol":
        return "Espanhol"
    texto = limpar_texto_questao(
        " ".join(
            [
                questao.enunciado or "",
                questao.alternativa_a or "",
                questao.alternativa_b or "",
                questao.alternativa_c or "",
                questao.alternativa_d or "",
                questao.alternativa_e or "",
            ]
        )
    )[:3000]
    for chave, rotulo, padrao in _REGRAS_ASSUNTO:
        if chave == area and padrao.search(texto):
            return rotulo
    return None


def _mapa_assuntos() -> dict[int, str | None]:
    global _mapa_assunto_cache
    if _mapa_assunto_cache is None:
        _mapa_assunto_cache = {
            questao.id: _classificar_assunto(questao)
            for questao in Question.query.filter(Question.fonte.isnot(None)).all()
        }
    return _mapa_assunto_cache


def _catalogo_filtros():
    contagem = {}
    for assunto in _mapa_assuntos().values():
        if assunto:
            contagem[assunto] = contagem.get(assunto, 0) + 1
    vistos = []
    for chave, rotulo in (
        ("linguagens", "Inglês"),
        ("linguagens", "Espanhol"),
        *((chave, rotulo) for chave, rotulo, _padrao in _REGRAS_ASSUNTO),
    ):
        total = contagem.get(rotulo, 0)
        if total >= 12 or (rotulo in {"Inglês", "Espanhol"} and total > 0):
            vistos.append({"area": chave, "rotulo": rotulo, "total": total})
    return vistos


def _sortear_lista(questoes, qtd: int, anos_marcados: list[int]):
    if not questoes or qtd <= 0:
        return []
    por_ano = {}
    for questao in questoes:
        por_ano.setdefault(questao.ano, []).append(questao)
    anos_presentes = sorted((ano for ano in por_ano if ano is not None), reverse=True)

    if len(anos_marcados) > 1:
        anos = [ano for ano in sorted(set(anos_marcados), reverse=True) if ano in por_ano]
        if not anos:
            anos = anos_presentes
        cotas = _distribuir_cotas(anos, qtd)
        escolhidas = []
        faltou = 0
        for ano in anos:
            pedido = cotas.get(ano, 0) + faltou
            faltou = 0
            lote = list(por_ano.get(ano, []))
            random.shuffle(lote)
            escolhidas.extend(lote[:pedido])
            faltou = max(0, pedido - len(lote))
        if len(escolhidas) < qtd:
            usados = {item.id for item in escolhidas}
            resto = [questao for questao in questoes if questao.id not in usados]
            random.shuffle(resto)
            resto.sort(key=lambda questao: questao.ano or 0, reverse=True)
            escolhidas.extend(resto[: qtd - len(escolhidas)])
        return escolhidas

    if len(anos_marcados) == 1:
        anos_presentes = [anos_marcados[0]]
    escolhidas = []
    for ano in anos_presentes:
        if len(escolhidas) >= qtd:
            break
        lote = list(por_ano.get(ano, []))
        random.shuffle(lote)
        escolhidas.extend(lote[: qtd - len(escolhidas)])
    if len(escolhidas) < qtd and None in por_ano and not anos_marcados:
        lote = list(por_ano[None])
        random.shuffle(lote)
        escolhidas.extend(lote[: qtd - len(escolhidas)])
    return escolhidas


def _limite_prova(tempo: str, qtd: int) -> int:
    oficiais = {
        "dia1": 5 * 3600 + 30 * 60,
        "dia2": 5 * 3600,
        "enem": 10 * 3600 + 30 * 60,
    }
    if tempo in oficiais:
        return oficiais[tempo]
    if tempo.isdigit():
        return max(60, int(tempo))
    if qtd >= 180:
        return oficiais["enem"]
    if qtd >= 90:
        return oficiais["dia1"]
    return max(10 * 60, qtd * 3 * 60)


def _limpar_sessao_simulado():
    session.pop("simulation_id", None)
    session.pop("question_ids", None)
    session.pop("current_index", None)
    session.pop("start_time", None)
    session.pop("prazo", None)
    session.pop("formato", None)
    session.pop("correcao", None)


def _simulado_aberto(sim, user_id):
    if not (sim and sim.user_id == user_id and sim.duracao_segundos is None):
        return False
    if (sim.tema or "") == "Print FAQ":
        return os.environ.get("FAQ_PRINT") == "1"
    return True


def _restaurar_prova_aberta(user_id):
    from recursos import aplicar_progresso

    sim_id = session.get("simulation_id")
    ids = session.get("question_ids") or []
    if sim_id and ids:
        sim = db.session.get(Simulation, sim_id)
        if _simulado_aberto(sim, user_id):
            return
        _limpar_sessao_simulado()
    abertos = (
        Simulation.query.filter_by(user_id=user_id)
        .filter(Simulation.duracao_segundos.is_(None))
        .filter(or_(Simulation.tema.is_(None), Simulation.tema != "Print FAQ"))
        .order_by(Simulation.id.desc())
        .all()
    )
    for sim in abertos:
        if aplicar_progresso(sim, session):
            return


def _exigir_admin():
    from recursos import eh_admin

    user = db.session.get(User, session.get("user_id"))
    if not eh_admin(user):
        flash("Essa área é só do admin.", "warning")
        return redirect(url_for("index"))
    return None


POR_PAGINA = 10


def _pagina_int(nome="pagina"):
    bruto = request.args.get(nome, "1")
    try:
        return max(1, int(bruto))
    except (TypeError, ValueError):
        return 1


def _paginar(itens, pagina=None, por_pagina=POR_PAGINA, param="pagina"):
    if pagina is None:
        pagina = _pagina_int(param)
    itens = list(itens)
    total = len(itens)
    paginas = max(1, (total + por_pagina - 1) // por_pagina) if total else 1
    pagina = min(pagina, paginas)
    inicio = (pagina - 1) * por_pagina
    return {
        "itens": itens[inicio : inicio + por_pagina],
        "pagina": pagina,
        "paginas": paginas,
        "total": total,
        "por_pagina": por_pagina,
        "inicio": inicio,
        "param": param,
        "tem_anterior": pagina > 1,
        "tem_proxima": pagina < paginas,
    }


def _link_pagina(param, pagina, ancora=None):
    args = request.args.to_dict(flat=True)
    args[param] = str(pagina)
    extras = {chave: valor for chave, valor in args.items() if valor not in (None, "")}
    extras.update(request.view_args or {})
    url = url_for(request.endpoint, **extras)
    if ancora:
        url = f"{url}#{ancora}"
    return url


def _normalizar_ordem(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return valor
    texto = unicodedata.normalize("NFKD", str(valor))
    return texto.encode("ascii", "ignore").decode("ascii").casefold()


def _extrair_ordem(item, spec):
    if callable(spec):
        return spec(item)
    if isinstance(item, dict):
        return item.get(spec)
    return getattr(item, spec, None)


def _ordenar(itens, campos, param="ord", param_dir="dir", padrao=None, padrao_dir=None):
    itens = list(itens)
    campo = (request.args.get(param) or "").strip()
    if campo not in campos:
        campo = padrao if padrao in campos else None
    direcao = (request.args.get(param_dir) or padrao_dir or "asc").strip().lower()
    if direcao not in {"asc", "desc"}:
        direcao = "asc"
    meta = {"campo": campo, "dir": direcao, "param": param, "param_dir": param_dir}
    if not campo:
        return itens, meta
    spec = campos[campo]
    reverso = direcao == "desc"
    itens.sort(key=lambda item: _normalizar_ordem(_extrair_ordem(item, spec)), reverse=reverso)
    return itens, meta


def _link_ordem(campo, param="ord", param_dir="dir", pagina_param=None, ancora=None, inicio="asc"):
    atual = (request.args.get(param) or "").strip()
    atual_dir = (request.args.get(param_dir) or "").strip().lower()
    if atual == campo:
        proxima = "asc" if atual_dir == "desc" else "desc"
    else:
        proxima = inicio if inicio in {"asc", "desc"} else "asc"
    args = request.args.to_dict(flat=True)
    args[param] = campo
    args[param_dir] = proxima
    if pagina_param:
        args[pagina_param] = "1"
    extras = {chave: valor for chave, valor in args.items() if valor not in (None, "")}
    extras.update(request.view_args or {})
    url = url_for(request.endpoint, **extras)
    if ancora:
        url = f"{url}#{ancora}"
    return url


def _tempo_esgotado() -> bool:
    prazo = session.get("prazo")
    if not prazo:
        return False
    try:
        limite = datetime.fromisoformat(prazo)
    except ValueError:
        return False
    if limite.tzinfo is None:
        agora = datetime.utcnow()
    else:
        agora = datetime.now(timezone.utc)
    return agora >= limite


def register_routes(app: Flask):
    @app.context_processor
    def inject_current_user():
        user_id = session.get("user_id")
        user = db.session.get(User, user_id) if user_id else None
        from recursos import eh_admin

        return {
            "current_user": user,
            "eh_admin": eh_admin(user),
            "link_pagina": _link_pagina,
            "link_ordem": _link_ordem,
        }

    @app.before_request
    def exigir_login():
        livres = {
            "login",
            "cadastro",
            "faq",
            "faq_print",
            "recuperar",
            "static",
            "favicon",
        }
        if request.endpoint in livres or request.endpoint is None:
            return None
        if session.get("user_id"):
            return None
        return redirect(url_for("login", next=request.path))

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(app.static_folder, "favicon.ico")

    @app.route("/faq")
    def faq():
        from faq import ATUALIZADO_EM, itens

        return render_template(
            "faq.html",
            itens=itens(),
            atualizado_em=ATUALIZADO_EM,
            form_avaliacao_url=FORM_AVALIACAO_URL,
        )

    @app.route("/_faq_print/<nome>")
    def faq_print(nome):
        if os.environ.get("FAQ_PRINT") != "1":
            abort(404)
        usuario = User.query.filter_by(email=DEMO_EMAIL).first() or User.query.order_by(User.id).first()
        if usuario is None:
            abort(404)
        session["user_id"] = usuario.id

        def _ir(endpoint, **kwargs):
            y = (request.args.get("print_y") or "").strip()
            if y.isdigit():
                kwargs["print_y"] = y
            return redirect(url_for(endpoint, **kwargs))

        if nome == "inicio":
            return _ir("index", abrir="filtros")
        if nome == "conta":
            return _ir("conta")
        if nome == "desempenho":
            return _ir("dashboard")
        if nome == "avaliacao":
            return _ir("avaliacao")
        if nome == "admin":
            return _ir("admin")
        if nome == "indicador":
            return _ir("admin_indicador", tipo="acertos")
        if nome == "redacao":
            return _ir("redacao")
        if nome == "quiz":
            _preparar_print_quiz(usuario.id)
            return _ir("quiz")
        if nome == "resultado":
            sim = (
                Simulation.query.filter_by(user_id=usuario.id)
                .join(SimulationAnswer)
                .order_by(Simulation.id.desc())
                .first()
            )
            if sim is None:
                return _ir("dashboard")
            return _ir("resultado", sim_id=sim.id)
        abort(404)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(_destino_interno(request.args.get("next")))
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            senha = request.form.get("senha") or ""
            user = User.query.filter_by(email=email).first()
            if user is None or not user.senha_hash or not check_password_hash(user.senha_hash, senha):
                flash("E-mail ou senha não conferem.", "warning")
                return redirect(url_for("login"))
            session["user_id"] = user.id
            return redirect(_destino_interno(request.form.get("next")))
        return render_template("login.html", next=request.args.get("next") or "")

    @app.route("/cadastro", methods=["GET", "POST"])
    def cadastro():
        if session.get("user_id"):
            return redirect(url_for("index"))
        if request.method == "POST":
            nome = (request.form.get("nome") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            senha = request.form.get("senha") or ""
            confirmar = request.form.get("confirmar") or ""
            if len(nome) < 2 or "@" not in email or "." not in email.split("@")[-1]:
                flash("Informe nome e um e-mail válido.", "warning")
                return redirect(url_for("cadastro"))
            if len(senha) < 6:
                flash("A senha precisa ter pelo menos 6 caracteres.", "warning")
                return redirect(url_for("cadastro"))
            if senha != confirmar:
                flash("As senhas não são iguais.", "warning")
                return redirect(url_for("cadastro"))
            uf, municipio = _normalizar_regiao(request.form.get("uf"), request.form.get("municipio"))
            if not uf:
                flash("Informe UF e município.", "warning")
                return redirect(url_for("cadastro"))
            if User.query.filter_by(email=email).first():
                flash("Já existe uma conta com esse e-mail. Entre ou use outro.", "warning")
                return redirect(url_for("cadastro"))
            user = User(
                nome=nome,
                email=email,
                senha_hash=generate_password_hash(senha),
                uf=uf,
                municipio=municipio,
                papel="aluno",
            )
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            flash("Conta criada.", "success")
            return redirect(url_for("index"))
        return render_template(
            "cadastro.html",
            ufs=UFS_BRASIL,
            uf_sel="RJ",
            municipio_sel="Resende",
        )

    @app.route("/conta", methods=["GET", "POST"])
    def conta():
        user = db.session.get(User, session.get("user_id"))
        if user is None:
            return redirect(url_for("login"))
        if request.method == "POST":
            nome = (request.form.get("nome") or "").strip()
            senha_atual = request.form.get("senha_atual") or ""
            senha = request.form.get("senha") or ""
            confirmar = request.form.get("confirmar") or ""
            if len(nome) < 2:
                flash("Informe um nome com pelo menos 2 caracteres.", "warning")
                return redirect(url_for("conta"))
            uf, municipio = _normalizar_regiao(request.form.get("uf"), request.form.get("municipio"))
            if not uf:
                flash("Informe UF e município.", "warning")
                return redirect(url_for("conta"))
            user.nome = nome[:120]
            user.uf = uf
            user.municipio = municipio
            _atualizar_tema_regiao(user)
            if senha or confirmar or senha_atual:
                if not user.senha_hash or not check_password_hash(user.senha_hash, senha_atual):
                    flash("A senha atual não confere.", "warning")
                    return redirect(url_for("conta"))
                if len(senha) < 6:
                    flash("A nova senha precisa ter pelo menos 6 caracteres.", "warning")
                    return redirect(url_for("conta"))
                if senha != confirmar:
                    flash("As senhas novas não são iguais.", "warning")
                    return redirect(url_for("conta"))
                user.senha_hash = generate_password_hash(senha)
            db.session.commit()
            flash("Cadastro atualizado.", "success")
            return redirect(url_for("conta"))
        return render_template("conta.html", user=user, ufs=UFS_BRASIL)

    @app.route("/recuperar", methods=["GET", "POST"])
    def recuperar():
        if session.get("user_id"):
            return redirect(url_for("index"))
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            nome = (request.form.get("nome") or "").strip()
            senha = request.form.get("senha") or ""
            confirmar = request.form.get("confirmar") or ""
            user = User.query.filter_by(email=email).first()
            nome_ok = user and (
                (user.nome or "").strip().lower() == nome.lower()
                or _primeiro_nome(user.nome).lower() == _primeiro_nome(nome).lower()
            )
            if not nome_ok:
                flash("E-mail e nome não conferem.", "warning")
                return redirect(url_for("recuperar"))
            if len(senha) < 6:
                flash("A nova senha precisa ter pelo menos 6 caracteres.", "warning")
                return redirect(url_for("recuperar"))
            if senha != confirmar:
                flash("As senhas não são iguais.", "warning")
                return redirect(url_for("recuperar"))
            user.senha_hash = generate_password_hash(senha)
            db.session.commit()
            flash("Senha redefinida. Entre com a nova senha.", "success")
            return redirect(url_for("login"))
        return render_template("recuperar.html")

    @app.route("/redacao", methods=["GET", "POST"])
    def redacao():
        from analisador_redacao import analisar, exemplos_analisados
        from recursos import COMPETENCIAS, TEMA_REDACAO

        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        rascunho = (
            Essay.query.filter_by(user_id=user_id)
            .order_by(Essay.atualizado_em.desc())
            .first()
        )
        if request.method == "POST":
            texto = (request.form.get("texto") or "")[:8000]
            acao = (request.form.get("acao") or "salvar").strip()
            notas = {}
            total = 0
            for chave, _nome, _desc in COMPETENCIAS:
                try:
                    valor = int(request.form.get(chave) or 0)
                except ValueError:
                    valor = 0
                valor = max(0, min(200, valor))
                notas[chave] = valor
                total += valor
            if rascunho is None:
                rascunho = Essay(user_id=user_id, tema=TEMA_REDACAO["titulo"])
                db.session.add(rascunho)
            texto_antes = rascunho.texto or ""
            rascunho.tema = TEMA_REDACAO["titulo"]
            rascunho.texto = texto
            rascunho.notas = json.dumps(notas)
            rascunho.total = total
            rascunho.atualizado_em = datetime.utcnow()
            if acao == "analisar":
                analise = analisar(texto, TEMA_REDACAO)
                rascunho.analise = json.dumps(analise, ensure_ascii=False)
                if not any(notas.values()):
                    rascunho.notas = json.dumps(analise["notas"])
                    rascunho.total = analise["total"]
                db.session.commit()
                flash("Análise pronta. Isso é treino, não a correção oficial do INEP.", "success")
                return redirect(url_for("redacao") + "#analise")
            if texto != texto_antes:
                rascunho.analise = None
            db.session.commit()
            flash("Redação salva.", "success")
            return redirect(url_for("redacao"))
        notas = {}
        analise = None
        if rascunho and rascunho.notas:
            try:
                notas = json.loads(rascunho.notas)
            except Exception:
                notas = {}
        if rascunho and rascunho.analise:
            try:
                analise = json.loads(rascunho.analise)
            except Exception:
                analise = None
        if os.environ.get("FAQ_PRINT") == "1":
            from analisador_redacao import EXEMPLOS

            texto_print = EXEMPLOS[1]["texto"]
            analise = analisar(texto_print, TEMA_REDACAO)
            notas = analise["notas"]
            rascunho = type("RascunhoPrint", (), {"texto": texto_print, "total": analise["total"]})()
        return render_template(
            "redacao.html",
            tema=TEMA_REDACAO,
            competencias=COMPETENCIAS,
            rascunho=rascunho,
            notas=notas,
            analise=analise,
            exemplos=exemplos_analisados(TEMA_REDACAO),
        )

    @app.route("/logout")
    def logout():
        session.pop("user_id", None)
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        user = db.session.get(User, session.get("user_id"))
        if user:
            _restaurar_prova_aberta(user.id)
        base = _consulta_acervo()
        areas = [
            area
            for (area,) in base.with_entities(Question.area)
            .filter(Question.area.isnot(None))
            .distinct()
            .order_by(Question.area)
            .all()
        ]
        anos = [
            ano
            for (ano,) in base.with_entities(Question.ano)
            .filter(Question.ano.isnot(None))
            .distinct()
            .order_by(Question.ano.desc())
            .all()
        ]
        ids = session.get("question_ids") or []
        indice = session.get("current_index") or 0
        em_andamento = None
        sim_aberto = db.session.get(Simulation, session.get("simulation_id"))
        if _simulado_aberto(sim_aberto, user.id if user else None) and ids and indice < len(ids):
            em_andamento = {
                "id": sim_aberto.id,
                "atual": indice + 1,
                "total": len(ids),
                "revisar": len(_ids_marcados(sim_aberto)),
            }
        return render_template(
            "index.html",
            user=user,
            areas=areas,
            areas_prova=[{"chave": chave, "rotulo": rotulo} for chave, rotulo, _trecho in AREAS_PROVA],
            assuntos=_catalogo_filtros(),
            anos=anos,
            total_acervo=base.count(),
            em_andamento=em_andamento,
        )

    @app.route("/menu")
    def menu():
        return redirect(url_for("index"))


    @app.route("/start", methods=["GET", "POST"])
    def start_simulation():
        if request.method == "GET":
            return redirect(url_for("index"))

        user_id = session.get("user_id")
        if not user_id:
            flash("Sessão expirada, carregue a página inicial novamente.", "warning")
            return redirect(url_for("index"))

        modo = request.form.get("modo", "aleatorio")
        tema = (request.form.get("tema") or "").strip() or None
        anos_escolhidos = _anos_do_formulario(request.form.getlist("ano"))
        areas_escolhidas = [
            chave
            for chave in request.form.getlist("area")
            if chave in {item[0] for item in AREAS_PROVA}
        ]
        if modo == "por_tema" and tema and not areas_escolhidas:
            chave_tema = _area_chave(tema)
            if chave_tema:
                areas_escolhidas = [chave_tema]
        assuntos_escolhidos = []
        assuntos_validos = {item["rotulo"] for item in _catalogo_filtros()}
        for assunto in request.form.getlist("assunto"):
            assunto = (assunto or "").strip()
            if assunto in assuntos_validos and assunto not in assuntos_escolhidos:
                assuntos_escolhidos.append(assunto)
        idioma = (request.form.get("idioma") or "").strip().lower()
        if idioma not in {"ingles", "espanhol"}:
            idioma = ""
        formato_bruto = request.form.get("formato") or "treino"
        so_novas = request.form.get("novas") == "1"
        so_erradas = request.form.get("erradas") == "1"
        tempo_form = request.form.get("tempo") or ""
        try:
            qtd = int(request.form.get("qtd") or 10)
        except ValueError:
            qtd = 10
        if formato_bruto == "dia1":
            formato = "prova"
            areas_escolhidas = ["linguagens", "humanas"]
            qtd = 90
            tempo_form = "dia1"
        elif formato_bruto == "dia2":
            formato = "prova"
            areas_escolhidas = ["natureza", "matematica"]
            qtd = 90
            tempo_form = "dia2"
        elif formato_bruto == "enem":
            formato = "prova"
            areas_escolhidas = ["linguagens", "humanas", "natureza", "matematica"]
            qtd = 180
            tempo_form = "enem"
        else:
            formato = "prova" if formato_bruto == "prova" else "treino"
        if qtd not in (5, 10, 15, 20, 45, 90, 180):
            qtd = 10
        query = _consulta_acervo()
        if areas_escolhidas:
            filtros_area = []
            for chave, _rotulo, trecho in AREAS_PROVA:
                if chave in areas_escolhidas:
                    filtros_area.append(Question.area.ilike(f"%{trecho}%"))
            query = query.filter(or_(*filtros_area))
        if idioma == "ingles":
            query = query.filter(or_(Question.idioma.is_(None), Question.idioma.ilike("%ingles%")))
        elif idioma == "espanhol":
            query = query.filter(or_(Question.idioma.is_(None), Question.idioma.ilike("%espanhol%")))
        if anos_escolhidos:
            query = query.filter(Question.ano.in_(anos_escolhidos))
        if so_novas:
            vistas = {
                questao_id
                for (questao_id,) in SimulationAnswer.query.join(Simulation)
                .filter(Simulation.user_id == user_id)
                .with_entities(SimulationAnswer.question_id)
                .distinct()
                .all()
            }
            if vistas:
                query = query.filter(Question.id.notin_(vistas))
        if so_erradas:
            erradas = {
                questao_id
                for (questao_id,) in SimulationAnswer.query.join(Simulation)
                .filter(Simulation.user_id == user_id)
                .filter(SimulationAnswer.correta.is_(False))
                .with_entities(SimulationAnswer.question_id)
                .distinct()
                .all()
            }
            if erradas:
                query = query.filter(Question.id.in_(erradas))
            else:
                flash("Você ainda não tem questão errada para montar esse treino.", "warning")
                return redirect(url_for("index"))
        candidatas = query.all()
        if assuntos_escolhidos:
            mapa = _mapa_assuntos()
            permitidos = set(assuntos_escolhidos)
            candidatas = [questao for questao in candidatas if mapa.get(questao.id) in permitidos]
        questions = _sortear_lista(candidatas, qtd, anos_escolhidos)
        if areas_escolhidas or assuntos_escolhidos:
            if modo != "por_tema":
                modo = "personalizado"
            rotulos_area = [
                rotulo for chave, rotulo, _trecho in AREAS_PROVA if chave in areas_escolhidas
            ]
            descricao = " · ".join(rotulos_area + assuntos_escolhidos)
            if idioma == "ingles":
                descricao = f"{descricao} · Inglês".strip(" ·")
            elif idioma == "espanhol":
                descricao = f"{descricao} · Espanhol".strip(" ·")
            tema = (descricao or tema or "")[:255] or None
        if so_erradas:
            tema = (("Só erros · " + (tema or "")).strip(" ·"))[:255]
        if formato_bruto == "dia1":
            tema = "Dia 1 - 90 questões"
        elif formato_bruto == "dia2":
            tema = "Dia 2 - 90 questões"
        elif formato_bruto == "enem":
            tema = "Prova completa - 180 questões"
        if not questions:
            flash("Ainda não há questões cadastradas para esse filtro.", "warning")
            return redirect(url_for("index"))
        if len(questions) < qtd:
            flash(
                f"Esse filtro tem {len(questions)} questões. O simulado foi montado com elas.",
                "warning",
            )

        sim = Simulation(
            user_id=user_id,
            modo=modo,
            tema=tema,
            total_questoes=len(questions),
            acertos=0,
            score_percent=0.0,
            ip=_ip_registrar(user_id),
        )
        if session.get("simulation_id"):
            _cancelar_simulado(user_id, session.get("simulation_id"))
        _limpar_sessao_simulado()
        db.session.add(sim)
        db.session.commit()

        session["simulation_id"] = sim.id
        session["question_ids"] = [q.id for q in questions]
        session["current_index"] = 0
        session["start_time"] = datetime.utcnow().isoformat()
        session["formato"] = formato
        if formato == "prova":
            limite = _limite_prova(tempo_form, qtd)
            session["prazo"] = (datetime.now(timezone.utc) + timedelta(seconds=limite)).isoformat()
            session["correcao"] = "final"
        else:
            session.pop("prazo", None)
            session["correcao"] = (
                "imediata" if request.form.get("correcao") == "imediata" else "final"
            )
        from recursos import progresso_salvar

        progresso_salvar(sim, session, {})
        db.session.commit()

        return redirect(url_for("quiz"))

    def _cancelar_simulado(user_id, sim_id=None):
        alvo = sim_id or session.get("simulation_id")
        if not alvo:
            if session.get("simulation_id") or session.get("question_ids"):
                _limpar_sessao_simulado()
                return True
            return False
        sim = db.session.get(Simulation, alvo)
        if session.get("simulation_id") == alvo:
            _limpar_sessao_simulado()
        if sim is None:
            return True
        if sim.user_id != user_id:
            return False
        if sim.duracao_segundos is not None:
            return True
        SimulationAnswer.query.filter_by(simulation_id=sim.id).delete()
        db.session.delete(sim)
        db.session.commit()
        return True

    @app.route("/simulado/cancelar", methods=["POST"])
    def cancelar_simulado():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        bruto = (request.form.get("sim_id") or "").strip()
        sim_id = int(bruto) if bruto.isdigit() else None
        if _cancelar_simulado(user_id, sim_id):
            flash("Simulado cancelado.", "success")
        else:
            flash("Não foi possível cancelar esse simulado.", "warning")
        destino = request.form.get("voltar") or "index"
        if destino == "dashboard":
            return redirect(url_for("dashboard"))
        return redirect(url_for("index"))

    def _salvar_resposta(sim_id, question, resposta):
        if not _letra_valida(resposta):
            return False
        existente = SimulationAnswer.query.filter_by(
            simulation_id=sim_id, question_id=question.id
        ).first()
        correta = resposta == question.resposta_correta
        if existente:
            existente.resposta_marcada = resposta
            existente.correta = correta
        else:
            db.session.add(
                SimulationAnswer(
                    simulation_id=sim_id,
                    question_id=question.id,
                    resposta_marcada=resposta,
                    correta=correta,
                )
            )
        return True

    @app.route("/quiz", methods=["GET", "POST"])
    def quiz():
        user_id = session.get("user_id")
        if user_id:
            _restaurar_prova_aberta(user_id)
        sim_id = session.get("simulation_id")
        ids = session.get("question_ids", [])
        idx = session.get("current_index", 0)

        if not user_id or not sim_id or not ids:
            flash("Nenhum simulado em andamento.", "warning")
            return redirect(url_for("index"))

        sim = db.session.get(Simulation, sim_id)
        if not _simulado_aberto(sim, user_id):
            _limpar_sessao_simulado()
            _restaurar_prova_aberta(user_id)
            if not session.get("simulation_id"):
                flash("Esse simulado já não está disponível. Comece outro.", "warning")
                return redirect(url_for("index"))
            return redirect(url_for("quiz"))

        if request.method == "GET" and _tempo_esgotado():
            flash("O tempo da prova acabou.", "warning")
            return redirect(url_for("resultado", sim_id=sim_id))

        if request.method == "POST":
            if idx < 0 or idx >= len(ids):
                bloqueio = _voltar_se_faltam(sim_id, ids)
                if bloqueio:
                    return bloqueio
                return redirect(url_for("resultado", sim_id=sim_id))
            q_id = ids[idx]
            question = db.session.get(Question, q_id)
            if question is None:
                flash("Não foi possível carregar a questão deste simulado.", "warning")
                return redirect(url_for("index"))

            resposta = (request.form.get("resposta") or "").strip().upper()[:1]
            acao = request.form.get("acao") or ""
            destino = (request.form.get("ir") or "").strip()
            imediata = session.get("correcao") == "imediata"
            ja = SimulationAnswer.query.filter_by(
                simulation_id=sim_id, question_id=question.id
            ).first()
            ja_respondida = bool(ja and _letra_valida(ja.resposta_marcada))
            marcada = q_id in _ids_marcados(sim)

            if _letra_valida(resposta) and not (imediata and ja_respondida):
                _salvar_resposta(sim_id, question, resposta)
            elif acao == "responder" and not (imediata and ja_respondida):
                flash("Escolha uma alternativa antes de continuar.", "warning")
                return redirect(url_for("quiz") + "#form-questao")
            elif (
                acao == "proxima"
                and not (imediata and ja_respondida)
                and not marcada
            ):
                flash("Escolha uma alternativa ou marque para rever antes de avançar.", "warning")
                return redirect(url_for("quiz") + "#form-questao")

            if acao == "marcar":
                db.session.refresh(sim)
                marcadas = _ids_marcados(sim)
                if q_id in marcadas:
                    marcadas = [item for item in marcadas if item != q_id]
                else:
                    marcadas.append(q_id)
                _gravar_marcadas(sim, marcadas)

            from recursos import progresso_salvar

            progresso_salvar(sim, session)
            db.session.commit()

            if acao == "tempo" or _tempo_esgotado():
                flash("O tempo da prova acabou.", "warning")
                return redirect(url_for("resultado", sim_id=sim_id))

            if acao == "anterior":
                session["current_index"] = max(0, idx - 1)
                return redirect(url_for("quiz"))

            if destino.isdigit():
                novo = int(destino) - 1
                if 0 <= novo < len(ids):
                    session["current_index"] = novo
                return redirect(url_for("quiz"))

            if acao == "resultado":
                bloqueio = _voltar_se_faltam(sim_id, ids)
                if bloqueio:
                    return bloqueio
                return redirect(url_for("resultado", sim_id=sim_id))

            if acao == "proxima":
                if imediata and not ja_respondida and not marcada:
                    try:
                        session["quiz_scroll"] = max(
                            0, int(float(request.form.get("posicao") or 0))
                        )
                    except ValueError:
                        session["quiz_scroll"] = 0
                    return redirect(url_for("quiz"))
                idx += 1
                session["current_index"] = idx
                if idx >= len(ids):
                    bloqueio = _voltar_se_faltam(sim_id, ids)
                    if bloqueio:
                        return bloqueio
                    return redirect(url_for("resultado", sim_id=sim_id))
                return redirect(url_for("quiz"))

            if acao in {"responder", "marcar"}:
                try:
                    session["quiz_scroll"] = max(
                        0, int(float(request.form.get("posicao") or 0))
                    )
                except ValueError:
                    session["quiz_scroll"] = 0
                return redirect(url_for("quiz"))

        if idx >= len(ids):
            bloqueio = _voltar_se_faltam(sim_id, ids)
            if bloqueio:
                return bloqueio
            return redirect(url_for("resultado", sim_id=sim_id))
        if idx < 0:
            idx = 0
            session["current_index"] = 0

        question = db.session.get(Question, ids[idx])
        if question is None:
            flash("Não foi possível carregar a questão deste simulado.", "warning")
            return redirect(url_for("index"))

        from recursos import progresso_carregar, progresso_salvar

        progresso_salvar(sim, session)
        db.session.commit()
        registros = SimulationAnswer.query.filter_by(simulation_id=sim_id).all()
        respostas = {
            item.question_id: item.resposta_marcada
            for item in registros
            if _letra_valida(item.resposta_marcada)
        }
        acertos = {
            item.question_id: bool(item.correta)
            for item in registros
            if _letra_valida(item.resposta_marcada)
        }
        rascunhos = progresso_carregar(sim).get("rascunhos") or {}
        resposta_oficial = respostas.get(question.id)
        resposta_atual = resposta_oficial
        if not resposta_atual:
            rascunho = rascunhos.get(str(question.id))
            if rascunho and rascunho in "ABCDE":
                resposta_atual = rascunho
        marcadas = set(_ids_marcados(sim))
        imediata = session.get("correcao") == "imediata"
        navegacao = [
            {
                "numero": posicao + 1,
                "atual": posicao == idx,
                "respondida": qid in respostas,
                "certa": acertos.get(qid) is True,
                "errada": qid in acertos and acertos.get(qid) is False,
                "qid": qid,
                "marcada": qid in marcadas,
            }
            for posicao, qid in enumerate(ids)
        ]
        manter_scroll = session.pop("quiz_scroll", None)
        return render_template(
            "quiz.html",
            question=question,
            index=idx + 1,
            total=len(ids),
            resposta_atual=resposta_atual,
            resposta_revelada=resposta_oficial,
            questao_marcada=question.id in marcadas,
            navegacao=navegacao,
            total_marcadas=len(marcadas),
            correcao_imediata=imediata,
            prazo=session.get("prazo"),
            formato=session.get("formato") or "treino",
            manter_scroll=manter_scroll,
        )

    @app.route("/quiz/rascunho", methods=["POST"])
    def quiz_rascunho():
        from recursos import progresso_carregar, progresso_salvar

        user_id = session.get("user_id")
        sim = db.session.get(Simulation, session.get("simulation_id"))
        if not user_id or sim is None or sim.user_id != user_id:
            return jsonify({"ok": False}), 400
        dados = request.get_json(silent=True) or {}
        letra = (dados.get("resposta") or "").strip().upper()[:1]
        if not _letra_valida(letra):
            return jsonify({"ok": False}), 400
        ids = session.get("question_ids") or []
        idx = session.get("current_index", 0)
        if idx < 0 or idx >= len(ids):
            return jsonify({"ok": False}), 400
        rascunhos = progresso_carregar(sim).get("rascunhos") or {}
        rascunhos[str(ids[idx])] = letra
        progresso_salvar(sim, session, rascunhos)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/quiz/marcar", methods=["POST"])
    def quiz_marcar():
        user_id = session.get("user_id")
        sim_id = session.get("simulation_id")
        ids = session.get("question_ids") or []
        idx = session.get("current_index", 0)
        sim = db.session.get(Simulation, sim_id)
        if not user_id or not _simulado_aberto(sim, user_id) or idx < 0 or idx >= len(ids):
            return jsonify({"ok": False}), 400
        db.session.refresh(sim)
        q_id = int(ids[idx])
        marcadas = _ids_marcados(sim)
        if q_id in marcadas:
            marcadas = [item for item in marcadas if item != q_id]
            ficou = False
        else:
            marcadas.append(q_id)
            ficou = True
        _gravar_marcadas(sim, marcadas)
        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "marcada": ficou,
                "total": len(marcadas),
                "qid": q_id,
                "numeros": [
                    posicao + 1 for posicao, item in enumerate(ids) if item in set(marcadas)
                ],
            }
        )

    @app.route("/quiz/revelar", methods=["POST"])
    def quiz_revelar():
        from recursos import progresso_salvar

        user_id = session.get("user_id")
        sim_id = session.get("simulation_id")
        ids = session.get("question_ids") or []
        idx = session.get("current_index", 0)
        sim = db.session.get(Simulation, sim_id)
        if not user_id or not _simulado_aberto(sim, user_id) or idx < 0 or idx >= len(ids):
            return jsonify({"ok": False}), 400
        question = db.session.get(Question, ids[idx])
        if question is None:
            return jsonify({"ok": False}), 400
        dados = request.get_json(silent=True) or {}
        resposta = (dados.get("resposta") or "").strip().upper()[:1]
        if not _letra_valida(resposta):
            return jsonify({"ok": False, "erro": "alternativa"}), 400
        ja = SimulationAnswer.query.filter_by(
            simulation_id=sim_id, question_id=question.id
        ).first()
        if ja is None or not _letra_valida(ja.resposta_marcada):
            _salvar_resposta(sim_id, question, resposta)
            progresso_salvar(sim, session)
            db.session.commit()
            ja = SimulationAnswer.query.filter_by(
                simulation_id=sim_id, question_id=question.id
            ).first()
        marcada = ja.resposta_marcada if ja else resposta
        certa = marcada == question.resposta_correta
        from caderno import arquivo_gabarito, pagina_gabarito

        gabarito_url = None
        gabarito_rotulo = None
        if arquivo_gabarito(question.ano, question.caderno, question.fonte):
            gabarito_url = url_for("ver_gabarito", question_id=question.id)
            pagina = pagina_gabarito(
                question.ano, question.caderno, question.item, question.fonte
            )
            if question.item and pagina:
                gabarito_rotulo = (
                    f"Ver a questão {int(question.item):02d} no gabarito, página {pagina}"
                )
            elif question.item:
                gabarito_rotulo = f"Ver a questão {int(question.item):02d} no gabarito oficial"
            else:
                gabarito_rotulo = "Ver no gabarito oficial"
        return jsonify(
            {
                "ok": True,
                "marcada": marcada,
                "correta": question.resposta_correta,
                "certa": certa,
                "index": idx + 1,
                "total": len(ids),
                "explicacao": question.explicacao or "",
                "gabarito_url": gabarito_url,
                "gabarito_rotulo": gabarito_rotulo,
            }
        )

    @app.route("/resultado/<int:sim_id>")
    def resultado(sim_id):
        sim = Simulation.query.get_or_404(sim_id)
        user_id = session.get("user_id")
        if not user_id or sim.user_id != user_id:
            flash("Esse simulado não está na sua conta.", "warning")
            return redirect(url_for("dashboard"))

        respostas = SimulationAnswer.query.filter_by(simulation_id=sim_id).all()
        encerrando = session.get("simulation_id") == sim.id
        if encerrando and not _tempo_esgotado():
            ids_prova = session.get("question_ids") or []
            if ids_prova:
                bloqueio = _voltar_se_faltam(sim_id, ids_prova)
                if bloqueio:
                    return bloqueio
        if encerrando and respostas:
            acertos = sum(1 for r in respostas if r.correta)
            total = sim.total_questoes or len(respostas)
            sim.acertos = acertos
            sim.score_percent = round(100 * acertos / total, 2) if total else 0.0

        if encerrando:
            start_iso = session.pop("start_time", None)
            if start_iso and sim.duracao_segundos is None:
                try:
                    inicio = datetime.fromisoformat(start_iso)
                    sim.duracao_segundos = int((datetime.utcnow() - inicio).total_seconds())
                except Exception:
                    pass
            _limpar_sessao_simulado()
            db.session.commit()

        temas = {}
        for resposta in respostas:
            questao = resposta.question
            chave = (questao.tema if questao and questao.tema else None) or (
                questao.area if questao else None
            ) or "Sem tema"
            info = temas.setdefault(chave, {"acertos": 0, "total": 0})
            info["total"] += 1
            if resposta.correta:
                info["acertos"] += 1

        from recursos import estimativa_tri

        temas_lista = [
            {
                "tema": nome,
                "acertos": info["acertos"],
                "total": info["total"],
                "percentual": round(100 * info["acertos"] / info["total"], 1) if info["total"] else 0,
            }
            for nome, info in temas.items()
        ]
        temas_lista, ordem_temas = _ordenar(
            temas_lista,
            {
                "tema": "tema",
                "acertos": "acertos",
                "total": "total",
                "percentual": "percentual",
            },
            param="ord",
            param_dir="dir",
        )
        pag_respostas = _paginar(respostas, param="pagina")
        return render_template(
            "resultado.html",
            sim=sim,
            respostas=pag_respostas["itens"],
            pag_respostas=pag_respostas,
            temas=temas_lista,
            ordem_temas=ordem_temas,
            marcadas=set(_ids_marcados(sim)),
            estimativa_tri=estimativa_tri(respostas),
        )

    @app.route("/dashboard")
    def dashboard():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("index"))
        _restaurar_prova_aberta(user_id)

        sims = (
            Simulation.query.filter_by(user_id=user_id)
            .filter(Simulation.duracao_segundos.isnot(None))
            .order_by(Simulation.criado_em.asc())
            .all()
        )

        labels = [s.criado_em.strftime("%d/%m") for s in sims]
        scores = [s.score_percent for s in sims]
        desempenho = _desempenho_aluno(user_id)
        historico = []
        ativo = session.get("simulation_id")
        consultas = (
            Simulation.query.filter_by(user_id=user_id)
            .order_by(Simulation.criado_em.desc())
            .all()
        )
        rotulos_modo = {
            "aleatorio": "Aleatório",
            "por_tema": "Por área",
            "personalizado": "Personalizado",
            "microdados": "Microdados",
        }
        for simulado in consultas:
            if simulado.tema == "Print FAQ":
                continue
            respostas_sim = SimulationAnswer.query.filter_by(simulation_id=simulado.id).all()
            if not respostas_sim and simulado.duracao_segundos is None and simulado.id != ativo:
                continue
            acertos = sum(1 for item in respostas_sim if item.correta)
            erros = sum(1 for item in respostas_sim if not item.correta)
            respondidas = len(respostas_sim)
            total = simulado.total_questoes or respondidas
            em_andamento = simulado.id == ativo and simulado.duracao_segundos is None
            if em_andamento:
                situacao = "Em andamento"
            elif simulado.duracao_segundos is None and respondidas and respondidas < total:
                situacao = "Parcial"
            elif not respondidas:
                situacao = "Nota"
            else:
                situacao = "Concluído"
            if respondidas:
                percentual = round(100 * acertos / total, 1) if total else 0.0
                acertos_exibir = acertos
            else:
                percentual = round(simulado.score_percent or 0, 1)
                acertos_exibir = simulado.acertos
            tipo = rotulos_modo.get(simulado.modo, simulado.modo or "Simulado")
            if simulado.tema:
                tipo = f"{tipo} · {_rotulo_curto(simulado.tema)}"
            historico.append(
                {
                    "id": simulado.id,
                    "quando": simulado.criado_em,
                    "modo": simulado.modo,
                    "tema": tipo,
                    "acertos": acertos_exibir,
                    "total": total,
                    "respondidas": respondidas,
                    "percentual": percentual,
                    "erros": erros,
                    "revisar": len(_ids_marcados(simulado)),
                    "em_andamento": em_andamento,
                    "situacao": situacao,
                    "tem_gabarito": bool(respondidas),
                    "pode_cancelar": simulado.duracao_segundos is None,
                    "ip": simulado.ip,
                }
            )

        historico, ordem_historico = _ordenar(
            historico,
            {
                "quando": "quando",
                "tema": "tema",
                "ip": "ip",
                "percentual": "percentual",
            },
            param="ord",
            param_dir="dir",
        )
        assuntos_erro = [item for item in desempenho["assuntos"] if item["erros"]]
        assuntos_erro, ordem_assuntos = _ordenar(
            assuntos_erro,
            {
                "assunto": "rotulo",
                "erros": "erros",
                "percentual": "percentual_erro",
            },
            param="oa",
            param_dir="da",
            padrao="erros",
            padrao_dir="desc",
        )
        pag_historico = _paginar(historico, param="pagina")
        return render_template(
            "dashboard.html",
            total_simulados=len(sims),
            media_geral=desempenho["percentual"],
            total_questoes=desempenho["total"],
            questoes_erradas=desempenho["erros"],
            labels=labels,
            scores=scores,
            desempenho=desempenho,
            historico=pag_historico["itens"],
            pag_historico=pag_historico,
            ordem_historico=ordem_historico,
            assuntos_erro=assuntos_erro[:6],
            ordem_assuntos=ordem_assuntos,
        )

    def _questoes_detalhe(itens):
        ids = [item["id"] for item in itens]
        if not ids:
            return []
        mapa = {questao.id: questao for questao in Question.query.filter(Question.id.in_(ids)).all()}
        saida = []
        for item in itens:
            questao = mapa.get(item["id"])
            if questao is None:
                continue
            saida.append({**item, "questao": questao})
        return saida

    @app.route("/dashboard/assunto")
    def dashboard_assunto():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("index"))

        tipo = (request.args.get("tipo") or "assunto").strip()
        chave = (request.args.get("chave") or "").strip()
        desempenho = _desempenho_aluno(user_id)
        if tipo not in {"area", "assunto", "erros", "respondidas"}:
            return redirect(url_for("dashboard"))

        assuntos = []
        area_treino = None
        ano_treino = None
        voltar_area = None
        voltar_rotulo = None

        if tipo == "area":
            info = next((item for item in desempenho["areas"] if item["chave"] == chave), None)
            if info is None:
                flash("Essa área não aparece no seu desempenho.", "warning")
                return redirect(url_for("dashboard"))
            titulo = info["rotulo"]
            assuntos = [item for item in desempenho["assuntos"] if item["area"] == chave]
            questoes = [item for item in desempenho["questoes_todas"] if item["area"] == chave]
            area_treino = info["area"]
            resumo = info
        elif tipo == "assunto":
            info = next((item for item in desempenho["assuntos"] if item["chave"] == chave), None)
            if info is None:
                flash("Esse assunto não aparece no seu desempenho.", "warning")
                return redirect(url_for("dashboard"))
            titulo = info["rotulo"]
            questoes = [item for item in desempenho["questoes_todas"] if item["assunto"] == chave]
            area_treino = info["area"]
            ano_treino = info.get("ano")
            voltar_area = info["area"]
            voltar_rotulo = _rotulo_curto(info["area"])
            resumo = info
        elif tipo == "erros":
            titulo = "Questões para revisar"
            questoes = [item for item in desempenho["questoes_todas"] if item["erros"] > 0]
            resumo = {
                "acertos": 0,
                "erros": sum(item["erros"] for item in questoes),
                "total": sum(item["erros"] for item in questoes),
                "percentual": desempenho["percentual"],
            }
        else:
            titulo = "Questões respondidas"
            questoes = list(desempenho["questoes_todas"])
            resumo = desempenho

        grupos = []
        if tipo in {"erros", "respondidas"}:
            por_grupo = {}
            for item in questoes:
                por_grupo.setdefault(item["assunto"], []).append(item)
            for nome, lista in por_grupo.items():
                erros = sum(item["erros"] for item in lista)
                acertos = sum(item["acertos"] for item in lista)
                total = acertos + erros
                grupos.append(
                    {
                        "titulo": nome,
                        "chave": nome,
                        "erros": erros,
                        "acertos": acertos,
                        "percentual": round(100 * acertos / total, 1) if total else 0,
                        "questoes": _questoes_detalhe(lista),
                    }
                )
            grupos.sort(key=lambda item: (item["percentual"], -item["erros"]))
            questoes_view = []
            for grupo in grupos:
                for item in grupo["questoes"]:
                    questoes_view.append(
                        {
                            **item,
                            "grupo": grupo["titulo"],
                            "grupo_chave": grupo["chave"],
                            "grupo_percentual": grupo["percentual"],
                            "grupo_erros": grupo["erros"],
                        }
                    )
            grupos = []
        else:
            questoes_view = _questoes_detalhe(questoes)

        assuntos, ordem_assuntos = _ordenar(
            assuntos,
            {
                "assunto": "rotulo",
                "erros": "erros",
                "acertos": "acertos",
                "percentual": "percentual",
            },
            param="ord",
            param_dir="dir",
        )
        pag_assuntos = _paginar(assuntos, param="p_ass")
        pag_questoes = _paginar(questoes_view, param="pagina")
        return render_template(
            "assunto.html",
            titulo=titulo,
            tipo=tipo,
            quantidade=len(questoes),
            resumo=resumo,
            assuntos=pag_assuntos["itens"],
            pag_assuntos=pag_assuntos,
            ordem_assuntos=ordem_assuntos,
            grupos=grupos,
            questoes=pag_questoes["itens"],
            pag_questoes=pag_questoes,
            area_treino=area_treino,
            ano_treino=ano_treino,
            voltar_area=voltar_area,
            voltar_rotulo=voltar_rotulo,
        )

    @app.route("/questao/<int:question_id>/original")
    def arquivo_original(question_id):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        questao = db.session.get(Question, question_id)
        if questao is None:
            abort(404)
        from caderno import (
            arquivo_origem,
            item_da_fonte,
            pagina_prova,
            referencia_caderno,
        )

        caminho = arquivo_origem(questao.ano, questao.caderno, questao.fonte)
        if caminho is None or not caminho.is_file():
            abort(404)
        pagina = pagina_prova(
            questao.ano, questao.caderno, questao.item, questao.idioma, questao.fonte
        )
        referencia = referencia_caderno(
            questao.ano,
            questao.caderno,
            questao.item,
            questao.area,
            questao.tema,
            questao.idioma,
            pagina,
        )
        if caminho.suffix.lower() == ".pdf":
            pdf_url = url_for("arquivo_original_pdf", question_id=questao.id)
            if pagina:
                pdf_url = f"{pdf_url}#page={pagina}"
            return render_template(
                "original.html",
                questao=questao,
                referencia=referencia,
                pdf_url=pdf_url,
                fonte=None,
            )
        fonte = item_da_fonte(questao.ano, questao.item, questao.idioma, questao.fonte)
        if fonte is None:
            abort(404)
        return render_template(
            "original.html",
            questao=questao,
            referencia=referencia,
            pdf_url=None,
            fonte=fonte,
        )

    @app.route("/questao/<int:question_id>/original.pdf")
    def arquivo_original_pdf(question_id):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        questao = db.session.get(Question, question_id)
        if questao is None:
            abort(404)
        from caderno import arquivo_origem

        caminho = arquivo_origem(questao.ano, questao.caderno, questao.fonte)
        if caminho is None or not caminho.is_file() or caminho.suffix.lower() != ".pdf":
            abort(404)
        return send_file(caminho, mimetype="application/pdf", as_attachment=False)

    @app.route("/questao/<int:question_id>/gabarito")
    def ver_gabarito(question_id):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        questao = db.session.get(Question, question_id)
        if questao is None:
            abort(404)
        from caderno import arquivo_gabarito, pagina_gabarito, referencia_caderno

        caminho = arquivo_gabarito(questao.ano, questao.caderno, questao.fonte)
        if caminho is None or not caminho.is_file():
            abort(404)
        pagina = pagina_gabarito(
            questao.ano, questao.caderno, questao.item, questao.fonte
        )
        pdf_url = url_for("ver_gabarito_pdf", question_id=questao.id)
        if pagina:
            pdf_url = f"{pdf_url}#page={pagina}"
        return render_template(
            "original.html",
            questao=questao,
            titulo="Gabarito oficial",
            referencia=referencia_caderno(
                questao.ano,
                questao.caderno,
                questao.item,
                questao.area,
                questao.tema,
                questao.idioma,
                pagina,
            ).replace("No arquivo original esta é a ", "No gabarito oficial esta é a ", 1),
            pdf_url=pdf_url,
            fonte=None,
        )

    @app.route("/questao/<int:question_id>/gabarito.pdf")
    def ver_gabarito_pdf(question_id):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        questao = db.session.get(Question, question_id)
        if questao is None:
            abort(404)
        from caderno import arquivo_gabarito

        caminho = arquivo_gabarito(questao.ano, questao.caderno, questao.fonte)
        if caminho is None or not caminho.is_file():
            abort(404)
        return send_file(caminho, mimetype="application/pdf", as_attachment=False)

    @app.route("/dashboard/revisao/<int:question_id>")
    def revisar_questao(question_id):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("index"))
        questao = Question.query.get_or_404(question_id)
        tentativas = (
            SimulationAnswer.query.join(Simulation)
            .filter(Simulation.user_id == user_id, SimulationAnswer.question_id == question_id)
            .order_by(SimulationAnswer.id.desc())
            .all()
        )
        if not tentativas:
            flash("Essa questão ainda não está no seu histórico.", "warning")
            return redirect(url_for("dashboard"))
        return render_template(
            "revisao.html",
            question=questao,
            ultima=tentativas[0],
            erros=sum(1 for item in tentativas if not item.correta),
            tentativas=len(tentativas),
        )

    @app.route("/admin", methods=["GET", "POST"])
    def admin():
        bloqueio = _exigir_admin()
        if bloqueio:
            return bloqueio
        total_questoes = Question.query.filter(Question.fonte.isnot(None)).count()
        if not total_questoes:
            total_questoes = Question.query.count()
        total_usuarios, total_simulados = metricas_participantes()
        total_redacoes = Essay.query.count()

        ano_filtro = request.args.get("ano", type=int)
        uf_filtro = (request.args.get("uf") or "").strip().upper() or None
        todos_simulados = _simulados_amostra()
        simulados = _simulados_painel()
        if ano_filtro:
            todos_simulados = [item for item in todos_simulados if item["ano"] == ano_filtro]
            simulados = [item for item in simulados if item["ano"] == ano_filtro]
        if uf_filtro:
            todos_simulados = [item for item in todos_simulados if item["uf"] == uf_filtro]
            simulados = [item for item in simulados if item["uf"] == uf_filtro]

        nomes_area = {
            "CN": "Natureza",
            "CH": "Humanas",
            "LC": "Linguagens",
            "MT": "Matemática",
        }
        medias_area = [
            {
                "sigla": sigla,
                "nome": nomes_area[sigla],
                "media": _media(item["notas"].get(sigla) for item in simulados),
            }
            for sigla in ("CN", "CH", "LC", "MT")
        ]
        por_ano = {}
        por_uf = {}
        for item in todos_simulados:
            if item["ano"]:
                por_ano[item["ano"]] = por_ano.get(item["ano"], 0) + 1
            if item["uf"]:
                por_uf[item["uf"]] = por_uf.get(item["uf"], 0) + 1
        anos_ordenados = sorted(por_ano)
        ufs_ordenadas = sorted(por_uf, key=lambda sigla: (-por_uf[sigla], sigla))
        semana_labels, semana_valores, _semana_detalhes = _simulados_por_semana()
        _ranking_por_media(simulados)
        simulados, ordem_simulados = _ordenar(
            simulados,
            {
                "posicao": "posicao",
                "nome": "nome",
                "ip": "ip",
                "ano": "ano",
                "uf": "uf",
                "municipio": "municipio",
                "acertos": "acertos",
                "percentual": "percentual",
                "cn": lambda item: (item.get("notas") or {}).get("CN"),
                "ch": lambda item: (item.get("notas") or {}).get("CH"),
                "lc": lambda item: (item.get("notas") or {}).get("LC"),
                "mt": lambda item: (item.get("notas") or {}).get("MT"),
                "tri": "media_tri",
            },
            param="ord",
            param_dir="dir",
            padrao="tri",
            padrao_dir="desc",
        )
        pag_simulados = _paginar(simulados, param="p_sim")

        return render_template(
            "admin.html",
            total_questoes=total_questoes,
            total_usuarios=total_usuarios,
            total_simulados=total_simulados,
            total_redacoes=total_redacoes,
            simulados=pag_simulados["itens"],
            pag_simulados=pag_simulados,
            media_acertos=_media(item["percentual"] for item in simulados),
            media_tri=_media(item["media_tri"] for item in simulados),
            maior=_media([max((item["percentual"] for item in simulados), default=None)]),
            menor=_media([min((item["percentual"] for item in simulados), default=None)]),
            medias_area=medias_area,
            anos_labels=anos_ordenados,
            anos_valores=[por_ano[ano] for ano in anos_ordenados],
            ufs_labels=ufs_ordenadas,
            ufs_valores=[por_uf[uf] for uf in ufs_ordenadas],
            semana_labels=semana_labels,
            semana_valores=semana_valores,
            ano_filtro=ano_filtro,
            uf_filtro=uf_filtro,
            ordem_simulados=ordem_simulados,
            form_avaliacao_url=FORM_AVALIACAO_URL,
        )

    @app.route("/admin/indicador/<tipo>")
    def admin_indicador(tipo):
        bloqueio = _exigir_admin()
        if bloqueio:
            return bloqueio
        tipo = (tipo or "").strip().lower()
        ano_filtro = request.args.get("ano", type=int)
        uf_filtro = (request.args.get("uf") or "").strip().upper() or None
        todos = _aplicar_filtro_admin(_simulados_amostra(), ano_filtro, uf_filtro)
        oficiais = _aplicar_filtro_admin(_simulados_painel(), ano_filtro, uf_filtro)
        nomes_area = {
            "cn": ("CN", "Natureza"),
            "ch": ("CH", "Humanas"),
            "lc": ("LC", "Linguagens"),
            "mt": ("MT", "Matemática"),
        }
        colunas = []
        linhas = []
        campos = {}
        titulo = ""
        explicacao = ""
        valor = "-"

        if tipo == "questoes":
            tem_fonte = db.session.query(Question.id).filter(Question.fonte.isnot(None)).first()
            consulta = Question.query.filter(Question.fonte.isnot(None)) if tem_fonte else Question.query
            por_area = {}
            por_ano = {}
            total = 0
            for area, ano in consulta.with_entities(Question.area, Question.ano):
                total += 1
                por_area[_rotulo_curto(area) or "Sem área"] = por_area.get(_rotulo_curto(area) or "Sem área", 0) + 1
                chave_ano = str(ano) if ano else "Sem ano"
                por_ano[chave_ano] = por_ano.get(chave_ano, 0) + 1
            titulo = "Questões do acervo"
            explicacao = (
                "Soma das questões do banco usadas no portal. "
                "A tabela mostra como esse total se reparte por área."
            )
            valor = total
            colunas = [("Área", "nome"), ("Questões", "quantidade")]
            campos = {"nome": "nome", "quantidade": "quantidade"}
            linhas = [
                {"nome": nome, "quantidade": qtd}
                for nome, qtd in sorted(por_area.items(), key=lambda item: (-item[1], item[0]))
            ]
        elif tipo == "usuarios":
            ids = _ids_participantes()
            usuarios = User.query.filter(User.id.in_(ids)).order_by(User.id).all()
            if uf_filtro:
                usuarios = [usuario for usuario in usuarios if (usuario.uf or "").upper() == uf_filtro]
            titulo = "Usuários da amostra"
            explicacao = (
                "Participantes da amostra do painel. "
                "Cada linha é uma pessoa, com quantas provas ela tem."
            )
            valor = len(usuarios)
            colunas = [
                ("Participante", "nome"),
                ("UF", "uf"),
                ("Município", "municipio"),
                ("Simulados", "simulados"),
            ]
            campos = {
                "nome": "nome",
                "uf": "uf",
                "municipio": "municipio",
                "simulados": "simulados",
            }
            for usuario in usuarios:
                qtd_sim = sum(1 for item in todos if item.get("user_id") == usuario.id)
                linhas.append(
                    {
                        "nome": usuario.nome,
                        "uf": (usuario.uf or "RJ").upper(),
                        "municipio": usuario.municipio or "Resende",
                        "simulados": qtd_sim,
                    }
                )
        elif tipo == "redacoes":
            titulo = "Redações"
            explicacao = "Textos de redação salvos no portal."
            valor = Essay.query.count()
            colunas = [("Aluno", "nome"), ("Data", "quando"), ("Total", "nota")]
            campos = {"nome": "nome", "quando": "quando", "nota": "nota"}
            for essay in Essay.query.order_by(Essay.criado_em.desc()).all():
                linhas.append(
                    {
                        "nome": essay.user.nome if essay.user else "-",
                        "quando": essay.criado_em.strftime("%d/%m/%Y %H:%M") if essay.criado_em else "-",
                        "nota": essay.total,
                    }
                )
        elif tipo == "simulados":
            titulo = "Simulados da amostra"
            explicacao = (
                "Todas as provas da amostra entram no cartão de simulados. "
                "Isso inclui treino e a prova oficial com TRI."
            )
            valor = len(todos)
            colunas = [
                ("Participante", "nome"),
                ("Data", "quando"),
                ("Tipo", "tema"),
                ("UF", "uf"),
                ("%", "percentual"),
                ("TRI média", "tri"),
            ]
            campos = {
                "nome": "nome",
                "quando": "quando",
                "tema": "tema",
                "uf": "uf",
                "percentual": "percentual",
                "tri": "media_tri",
            }
            for item in todos:
                linhas.append(
                    {
                        **item,
                        "quando": item["quando"].strftime("%d/%m/%Y") if item.get("quando") else "-",
                        "tema": item.get("tema") or item.get("modo") or "Treino",
                        "tri": item.get("media_tri"),
                        "href": url_for(
                            "admin_simulado",
                            sim_id=item["id"],
                            ano=ano_filtro,
                            uf=uf_filtro,
                        ),
                    }
                )

        elif tipo == "acertos":
            titulo = "Média de acertos"
            explicacao = (
                "Média do percentual das provas oficiais com TRI. "
                "Cada linha é uma dessas provas."
            )
            valor = _media(item["percentual"] for item in oficiais)
            valor = f"{valor}%" if valor is not None else "-"
            colunas = [("Participante", "nome"), ("Acertos", "acertos"), ("%", "percentual"), ("UF", "uf")]
            campos = {"nome": "nome", "acertos": "acertos", "percentual": "percentual", "uf": "uf"}
            for item in oficiais:
                linhas.append(
                    {
                        **item,
                        "href": url_for("admin_simulado", sim_id=item["id"], ano=ano_filtro, uf=uf_filtro),
                    }
                )
        elif tipo == "tri":
            titulo = "Média TRI"
            explicacao = (
                "Média das TRI médias das provas oficiais. "
                "TRI é Teoria de Resposta ao Item. "
                "A TRI média de cada pessoa é a média de Natureza, Humanas, Linguagens e Matemática."
            )
            valor = _media(item["media_tri"] for item in oficiais)
            colunas = [("Participante", "nome"), ("TRI média", "tri"), ("%", "percentual"), ("UF", "uf")]
            campos = {"nome": "nome", "tri": "media_tri", "percentual": "percentual", "uf": "uf"}
            for item in oficiais:
                linhas.append(
                    {
                        **item,
                        "href": url_for("admin_simulado", sim_id=item["id"], ano=ano_filtro, uf=uf_filtro),
                    }
                )
        elif tipo in {"maior", "menor"}:
            percents = [item["percentual"] for item in oficiais if item.get("percentual") is not None]
            alvo = max(percents) if tipo == "maior" and percents else (
                min(percents) if percents else None
            )
            titulo = "Maior acerto" if tipo == "maior" else "Menor acerto"
            explicacao = (
                "Entre as provas oficiais, esta é a maior porcentagem."
                if tipo == "maior"
                else "Entre as provas oficiais, esta é a menor porcentagem."
            )
            valor = f"{round(alvo, 1)}%" if alvo is not None else "-"
            colunas = [("Participante", "nome"), ("Acertos", "acertos"), ("%", "percentual"), ("UF", "uf")]
            campos = {"nome": "nome", "acertos": "acertos", "percentual": "percentual", "uf": "uf"}
            for item in oficiais:
                if item.get("percentual") != alvo:
                    continue
                linhas.append(
                    {
                        **item,
                        "href": url_for("admin_simulado", sim_id=item["id"], ano=ano_filtro, uf=uf_filtro),
                    }
                )
        elif tipo in nomes_area:
            sigla, nome_area = nomes_area[tipo]
            titulo = f"TRI {nome_area}"
            explicacao = (
                f"Média da nota oficial de {nome_area} nas provas com TRI. "
                "TRI é Teoria de Resposta ao Item."
            )
            valor = _media(item["notas"].get(sigla) for item in oficiais)
            colunas = [("Participante", "nome"), (nome_area, "nota"), ("TRI média", "tri"), ("UF", "uf")]
            campos = {"nome": "nome", "nota": "nota", "tri": "media_tri", "uf": "uf"}
            for item in oficiais:
                linhas.append(
                    {
                        "nome": item["nome"],
                        "nota": item["notas"].get(sigla),
                        "media_tri": item.get("media_tri"),
                        "uf": item.get("uf"),
                        "href": url_for("admin_simulado", sim_id=item["id"], ano=ano_filtro, uf=uf_filtro),
                    }
                )
        elif tipo == "semana":
            labels, valores, detalhes = _simulados_por_semana()
            titulo = "Simulados por semana"
            explicacao = (
                "Quantidade de provas da amostra em cada semana. "
                "Serve para ver em quais períodos a turma usou mais a plataforma."
            )
            valor = sum(valores) if valores else 0
            colunas = [("Semana", "nome"), ("Início", "inicio"), ("Fim", "fim"), ("Simulados", "total")]
            campos = {"nome": "nome", "inicio": "inicio", "fim": "fim", "total": "total"}
            for item in detalhes:
                linhas.append(
                    {
                        "nome": item["nome"],
                        "inicio": item["inicio"].strftime("%d/%m/%Y"),
                        "fim": item["fim"].strftime("%d/%m/%Y"),
                        "total": item["total"],
                    }
                )
        elif tipo == "uf":
            por_uf = {}
            for item in todos:
                if item.get("uf"):
                    por_uf[item["uf"]] = por_uf.get(item["uf"], 0) + 1
            titulo = "Simulados por UF"
            explicacao = (
                "Conta todas as provas da amostra em cada UF, inclusive as de treino. "
                "A soma deve ser igual ao cartão de simulados."
            )
            valor = sum(por_uf.values())
            colunas = [("UF", "uf"), ("Simulados", "quantidade")]
            campos = {"uf": "uf", "quantidade": "quantidade"}
            linhas = [
                {"uf": uf, "quantidade": qtd}
                for uf, qtd in sorted(por_uf.items(), key=lambda item: (-item[1], item[0]))
            ]
        else:
            flash("Esse indicador não existe.", "warning")
            return redirect(url_for("admin"))

        linhas, ordem = _ordenar(linhas, campos, padrao=next(iter(campos), None), padrao_dir="desc")
        pag = _paginar(linhas)
        return render_template(
            "admin_indicador.html",
            titulo=titulo,
            explicacao=explicacao,
            valor=valor,
            colunas=colunas,
            linhas=pag["itens"],
            paginacao=pag,
            ordem=ordem,
            ano_filtro=ano_filtro,
            uf_filtro=uf_filtro,
            tipo=tipo,
        )



    @app.route("/admin/simulado/<int:sim_id>")
    def admin_simulado(sim_id):
        bloqueio = _exigir_admin()
        if bloqueio:
            return bloqueio
        sim = Simulation.query.get_or_404(sim_id)
        detalhe = _interpretar_simulado(sim)
        respostas = (
            SimulationAnswer.query.filter_by(simulation_id=sim.id)
            .order_by(SimulationAnswer.id)
            .all()
        )
        pag_respostas = _paginar(respostas, param="pagina")
        nomes_area = {
            "CN": "Ciências da Natureza",
            "CH": "Ciências Humanas",
            "LC": "Linguagens",
            "MT": "Matemática",
        }
        return render_template(
            "admin_simulado.html",
            sim=sim,
            detalhe=detalhe,
            respostas=pag_respostas["itens"],
            pag_respostas=pag_respostas,
            nomes_area=nomes_area,
            ano_filtro=request.args.get("ano", type=int),
            uf_filtro=(request.args.get("uf") or "").strip().upper() or None,
        )

    @app.route("/feedback")
    @app.route("/feedbacks")
    def feedback():
        return redirect(url_for("avaliacao"))

    @app.route("/avaliacao")
    def avaliacao():
        return render_template(
            "avaliacao.html",
            form_avaliacao_url=FORM_AVALIACAO_URL,
        )


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
