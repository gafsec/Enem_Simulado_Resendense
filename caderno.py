"""Localiza o caderno e o gabarito oficiais, se existirem em data/inep."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PASTA_PDF = RAIZ / "data" / "inep"
PASTA_JSON = RAIZ / "data" / "acervo"

PROVAS = {
    (2025, "D1-CD1"): "2025_PV_impresso_D1_CD1.pdf",
    (2025, "D2-CD7"): "2025_PV_impresso_D2_CD7.pdf",
    (2025, "D2-CD5"): "2025_PV_impresso_D2_CD5.pdf",
    (2024, "D1-CD1"): "2024_PV_impresso_D1_CD1.pdf",
    (2024, "D2-CD7"): "2024_PV_impresso_D2_CD7.pdf",
}
CADERNO_REF = {
    "D1-CD1": ("1º dia", "1", "Azul"),
    "D2-CD7": ("2º dia", "7", "Azul"),
    "D2-CD5": ("2º dia", "5", "Amarelo"),
}


def _pdf(ano, caderno, gabarito=False):
    nome = PROVAS.get((ano, caderno))
    if not nome:
        return None
    if gabarito:
        nome = nome.replace("_PV_", "_GB_")
    caminho = PASTA_PDF / nome
    return caminho if caminho.is_file() else None


def arquivo_origem(ano, caderno, fonte):
    if fonte == "inep":
        return _pdf(ano, caderno)
    if fonte == "enem.dev" and ano:
        caminho = PASTA_JSON / f"enem_{ano}.json"
        if caminho.is_file():
            return caminho
    return None


def arquivo_gabarito(ano, caderno, fonte):
    if fonte != "inep":
        return None
    return _pdf(ano, caderno, gabarito=True)


def pagina_prova(ano, caderno, item, idioma, fonte):
    return None


def pagina_gabarito(ano, caderno, item, fonte):
    caminho = arquivo_gabarito(ano, caderno, fonte)
    if caminho is None:
        return None
    return 1


def referencia_caderno(ano, caderno, item, area, tema=None, idioma=None, pagina=None):
    if not item:
        return ""
    pedacos = [f"questão {int(item):02d}"]
    if ano:
        pedacos.append(f"ENEM {ano}")
    info = CADERNO_REF.get(caderno or "")
    if info:
        dia, numero, cor = info
        pedacos.extend((dia, f"caderno {numero}", f"cor {cor.lower()}"))
    assunto = (tema or area or "").split(",")[0].split(" e suas ")[0].strip()
    if assunto:
        pedacos.append(assunto)
    if idioma == "ingles":
        pedacos.append("opção inglês")
    elif idioma == "espanhol":
        pedacos.append("opção espanhol")
    if pagina:
        pedacos.append(f"página {int(pagina)}")
    return "No arquivo original esta é a " + ", ".join(pedacos) + "."


def item_da_fonte(ano, item, idioma, fonte):
    return None
