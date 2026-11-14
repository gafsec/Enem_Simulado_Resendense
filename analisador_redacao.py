"""Analisa redação pelas cinco competências do ENEM e sugere nota de treino."""

from __future__ import annotations

import math
import re
import unicodedata

from recursos import COMPETENCIAS, TEMA_REDACAO

NIVEIS = {
    0: "zerada",
    40: "muito insuficiente",
    80: "insuficiente",
    120: "mediana",
    160: "boa",
    200: "excelente",
}

_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ0-9]+")
_FRASE = re.compile(r"[^.!?]+[.!?]|[^.!?]+$")

_TEMA_BASE = {
    "leitura", "ler", "lendo", "lido", "livro", "livros", "leitor", "leitores",
    "biblioteca", "bibliotecas", "letramento", "literacia", "literatura",
    "acesso", "acessar", "escola", "escolas", "escolar", "educacao", "educacao",
    "educação", "brasil", "brasileiro", "brasileira", "jovem", "jovens",
    "aluno", "alunos", "professor", "professores", "cultura", "mediacao",
    "mediação", "habitante", "casa", "lares",
}

_INFORMAL = {
    "ne", "né", "vc", "voce", "pq", "tb", "tbm", "blz", "kk", "kkk", "rs",
    "tipo", "cara", "galera", "super", "mega", "mto", "mt", "td", "tds",
    "eh", "tah", "to", "tô", "ta", "tá", "pra", "pro", "d+", "aff",
}

_ERROS = {
    "faser", "fasiar", "probrema", "naum", "ninguem", "tambem", "experiencia",
    "conciência", "conciencia", "estao", "sao", "nao", "voce", "voceh",
}

_REPERTORIO = {
    "constituicao", "constituição", "ibge", "pnud", "unesco", "freire",
    "candido", "cândido", "bakhtin", "habermas", "platão", "platao",
    "aristoteles", "aristóteles", "pesquisa", "pesquisas", "relatorio",
    "relatório", "dado", "dados", "estatistica", "estatística", "artigo",
    "cidadania", "direito", "direitos", "censo", "segundo", "conforme",
    "filósofo", "filosofo", "sociologo", "sociólogo", "pensador",
}

_CONECTIVOS = {
    "portanto", "assim", "logo", "contudo", "entretanto", "porem", "porém",
    "todavia", "ademais", "outrossim", "alem", "além", "desse", "deste",
    "dessa", "logo", "entao", "então", "pois", "porque", "visto",
    "embora", "ainda", "tambem", "também", "primeiro", "segundo",
    "conclusao", "conclusão", "finalmente", "diante", "sobretudo",
    "entretanto", "enquanto", "quando", "onde", "como", "para",
}

_AGENTES = {
    "governo", "estado", "mec", "escola", "escolas", "familia", "família",
    "familias", "famílias", "midia", "mídia", "ong", "ongs", "prefeitura",
    "municipio", "município", "professores", "sociedade", "uniao", "união",
    "ministerio", "ministério",
}

_ACOES = {
    "criar", "implementar", "promover", "fiscalizar", "investir", "ampliar",
    "garantir", "desenvolver", "oferecer", "realizar", "estabelecer",
    "incentivar", "formar", "capacitar", "construir", "destinar",
}

_MEIOS = {
    "meio", "atraves", "através", "campanha", "campanhas", "projeto",
    "projetos", "lei", "leis", "parceria", "parcerias", "programa",
    "programas", "oficina", "oficinas", "mutirao", "mutirão",
}

_FINS = {
    "para", "fim", "objetivo", "objetivos", "finalidade", "quanto",
}

_VIOLACAO = {
    "censura", "censurar", "proibir livro", "obrigar na marra",
    "punir quem nao le", "excluir analfabetos",
}


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return normal.encode("ascii", "ignore").decode("ascii")


def _tokens(texto: str) -> list[str]:
    return [item.group(0) for item in _PALAVRA.finditer(texto or "")]


def _tokens_norm(texto: str) -> list[str]:
    return [_sem_acento(item).casefold() for item in _tokens(texto)]


def _faixa(pontos: float) -> int:
    if pontos >= 88:
        return 200
    if pontos >= 72:
        return 160
    if pontos >= 54:
        return 120
    if pontos >= 36:
        return 80
    if pontos >= 16:
        return 40
    return 0


def _metricas(texto: str) -> dict:
    limpo = (texto or "").strip()
    palavras = _tokens(limpo)
    paragrafos = [parte.strip() for parte in re.split(r"\n\s*\n+", limpo) if parte.strip()]
    if not paragrafos and limpo:
        paragrafos = [parte.strip() for parte in limpo.split("\n") if parte.strip()] or [limpo]
    frases = [parte.strip() for parte in _FRASE.findall(limpo) if parte.strip()]
    linhas = max(limpo.count("\n") + 1 if limpo else 0, math.ceil(len(palavras) / 10) if palavras else 0)
    return {
        "texto": limpo,
        "palavras": len(palavras),
        "paragrafos": len(paragrafos),
        "frases": len(frases),
        "linhas": linhas,
        "tokens": _tokens_norm(limpo),
        "paragrafo_textos": paragrafos,
    }


def _palavras_do_tema(tema: dict | None) -> set[str]:
    tema = tema or TEMA_REDACAO
    titulo = _tokens_norm(tema.get("titulo") or "")
    base = set(_TEMA_BASE)
    for item in titulo:
        if len(item) > 3:
            base.add(item)
    return base


def _achados_c1(dados: dict) -> tuple[float, list[str], list[str]]:
    tokens = dados["tokens"]
    originais = [item.casefold() for item in _tokens(dados["texto"])]
    texto = dados["texto"]
    pontos = 62.0
    achados = []
    melhorias = []
    if dados["palavras"] < 40:
        pontos -= 28
        achados.append("O texto é curto demais para julgar a norma com segurança.")
        melhorias.append("Escreva perto de 20 a 30 linhas, com frases completas e pontuação.")
    informal = sorted({item for item in originais + tokens if item in _INFORMAL})
    if informal:
        pontos -= min(30, 7 * len(informal))
        achados.append("Aparece marca de fala informal: " + ", ".join(informal[:5]) + ".")
        melhorias.append("Troque gíria e abreviação por registro formal da norma-padrão.")
    erros = sorted({item for item in originais if item in _ERROS})
    if erros:
        pontos -= min(24, 8 * len(erros))
        achados.append("Há grafia fora da norma: " + ", ".join(erros[:5]) + ".")
        melhorias.append("Revise acento, concordância e palavras como não, também e você.")
    if texto and not re.search(r"[.!?]", texto):
        pontos -= 22
        achados.append("Quase não há ponto final. A pontuação faz parte da competência 1.")
        melhorias.append("Feche cada ideia com ponto. Use vírgula para separar explicações.")
    if re.search(r"[!]{2,}|[?]{2,}", texto):
        pontos -= 8
        achados.append("Pontuação repetida quebra o tom dissertativo.")
        melhorias.append("Use um ponto ou uma interrogação. Evite !!! e ???.")
    if texto.isupper() and dados["palavras"] > 8:
        pontos -= 20
        achados.append("O texto está em maiúsculas.")
        melhorias.append("Escreva em caixa alta e baixa, como em um texto formal.")
    if dados["palavras"] >= 180 and re.search(r"[.!?]", texto) and not informal and not erros:
        pontos += 22
        achados.append("O registro está formal e a pontuação aparece com regularidade.")
    if dados["paragrafos"] >= 3 and dados["palavras"] >= 120:
        pontos += 8
    pontos = max(0.0, min(100.0, pontos))
    if pontos >= 72 and not melhorias:
        melhorias.append("Faça uma última leitura em voz alta para pegar concordância e vírgula.")
    if pontos < 54 and not melhorias:
        melhorias.append("Reescreva em parágrafos curtos, com sujeito, verbo e ponto final.")
    return pontos, achados, melhorias


def _achados_c2(dados: dict, tema: dict | None) -> tuple[float, list[str], list[str]]:
    tokens = dados["tokens"]
    tema_palavras = _palavras_do_tema(tema)
    hits = [item for item in tokens if item in tema_palavras]
    unicos = set(hits)
    repertorio = [item for item in tokens if item in _REPERTORIO]
    enunciado = _tokens_norm((tema or TEMA_REDACAO).get("texto") or "")
    copia = 0
    if enunciado:
        bloco = " ".join(tokens)
        trecho = " ".join(enunciado[:18])
        if trecho and trecho in bloco:
            copia = 1
    pontos = 20.0 + min(40.0, 7.0 * len(unicos)) + min(28.0, 8.0 * len(set(repertorio)))
    achados = []
    melhorias = []
    if dados["palavras"] < 50:
        pontos = min(pontos, 28)
        achados.append("Há poucas linhas. O ENEM pode zerar texto muito curto.")
        melhorias.append("Desenvolva o tema em introdução, dois argumentos e conclusão.")
    if copia:
        pontos = min(pontos, 24)
        achados.append("Trecho perto demais do enunciado. Copiar a proposta zera ou derruba a nota.")
        melhorias.append("Use suas palavras. O enunciado só aponta o problema.")
    if len(unicos) <= 1 and dados["palavras"] >= 40:
        pontos = min(pontos, 32)
        achados.append("O texto quase não aborda o tema pedido.")
        melhorias.append("Volte ao título e fale dele em todo parágrafo, não só no começo.")
    elif len(unicos) >= 5:
        achados.append("O recorte do tema aparece ao longo do texto.")
    else:
        achados.append("O tema aparece, mas ainda de forma raso ou repetida.")
        melhorias.append("Aprofunde a causa do problema. Não fique só em 'as pessoas precisam ler'.")
    if repertorio:
        achados.append("Há tentativa de repertório: " + ", ".join(sorted(set(repertorio))[:4]) + ".")
        if len(set(repertorio)) == 1:
            melhorias.append("Diga de quem é o dado ou a ideia e ligue isso ao argumento.")
    else:
        pontos = min(pontos, 70)
        achados.append("Não aparece repertório de estudo, dado ou autor.")
        melhorias.append(
            "Traga um repertório ligado ao tema, como Paulo Freire, Antonio Candido "
            "ou o artigo 205 da Constituição."
        )
    if dados["palavras"] >= 220 and len(unicos) >= 6 and len(set(repertorio)) >= 2:
        pontos += 10
    pontos = max(0.0, min(100.0, pontos))
    return pontos, achados, melhorias


def _achados_c3(dados: dict) -> tuple[float, list[str], list[str]]:
    textos = " ".join(dados["paragrafo_textos"]).casefold()
    n = dados["paragrafos"]
    pontos = 28.0
    achados = []
    melhorias = []
    if n <= 1:
        pontos -= 10
        achados.append("Quase tudo está em um bloco só. Falta projeto de texto.")
        melhorias.append("Separe introdução, dois desenvolvimentos e conclusão.")
    elif n == 2:
        pontos += 12
        achados.append("Há começo de divisão, mas ainda faltam partes.")
        melhorias.append("O ENEM trabalha bem com quatro parágrafos.")
    elif n == 3:
        pontos += 28
        achados.append("Há três blocos. Dá para chegar na estrutura clássica com mais um.")
        melhorias.append("Abra com tese, desenvolva duas causas e feche com proposta.")
    else:
        pontos += 40
        achados.append("A divisão em parágrafos ajuda a organizar a tese e os argumentos.")
    if re.search(r"\b(atualmente|no brasil|e notorio|é notório|discute-se|observa-se)\b", textos):
        pontos += 8
    if re.search(r"\b(portanto|assim|diante disso|desse modo|em suma|por fim|logo)\b", textos):
        pontos += 10
        achados.append("Há marca de fechamento, o que sustenta a conclusão.")
    else:
        pontos -= 8
        melhorias.append("Reserve o último parágrafo para retomar a tese e fechar a proposta.")
    if re.search(r"\b(alem disso|além disso|ademais|em segundo|outro ponto|outrossim)\b", textos):
        pontos += 8
        achados.append("Há progressão de um argumento para outro.")
    elif n >= 2:
        melhorias.append("Ligue o segundo argumento com além disso ou outro eixo do problema.")
    if re.search(r"\b(eu fui|minha mae|minha mãe|quando eu era|ai eu)\b", textos):
        pontos -= 16
        achados.append("O texto puxa para o relato pessoal. A prova pede dissertação.")
        melhorias.append("Use o caso só como exemplo rápido e volte à tese pública.")
    if dados["palavras"] >= 200 and n >= 4:
        pontos += 8
    pontos = max(0.0, min(100.0, pontos))
    return pontos, achados, melhorias


def _achados_c4(dados: dict) -> tuple[float, list[str], list[str]]:
    tokens = dados["tokens"]
    conectivos = [item for item in tokens if item in _CONECTIVOS]
    unicos = set(conectivos)
    pontos = 30.0 + min(40.0, 6.5 * len(unicos))
    achados = []
    melhorias = []
    if unicos:
        achados.append("Conectivos encontrados: " + ", ".join(sorted(unicos)[:6]) + ".")
    else:
        pontos -= 12
        achados.append("Faltam conectivos para amarrar as frases e os parágrafos.")
        melhorias.append("Use portanto, além disso, desse modo e contudo com medida.")
    if dados["paragrafos"] >= 3 and len(unicos) >= 4:
        pontos += 14
        achados.append("A articulação entre os blocos está visível.")
    if dados["frases"] >= 4:
        inicio = []
        for frase in re.findall(r"[^.!?]+", dados["texto"]):
            palavras = _tokens_norm(frase)
            if palavras:
                inicio.append(palavras[0])
        if inicio and inicio.count(inicio[0]) >= 3:
            pontos -= 10
            achados.append("Várias frases começam do mesmo jeito, o que enfraquece a coesão.")
            melhorias.append("Varie o sujeito e o conectivo do começo da frase.")
    repetidas = {}
    for item in tokens:
        if len(item) > 5:
            repetidas[item] = repetidas.get(item, 0) + 1
    excesso = [f"{palavra} ({qtd}x)" for palavra, qtd in repetidas.items() if qtd >= 8]
    if excesso:
        pontos -= 8
        achados.append("Há repetição pesada de " + ", ".join(excesso[:3]) + ".")
        melhorias.append("Troque a palavra repetida por sinônimo ou pronome.")
    if dados["palavras"] < 60:
        pontos = min(pontos, 40)
    pontos = max(0.0, min(100.0, pontos))
    if pontos < 54 and not melhorias:
        melhorias.append("Releia o fim de um parágrafo e o começo do outro. A ponte precisa ficar clara.")
    return pontos, achados, melhorias


def _achados_c5(dados: dict) -> tuple[float, list[str], list[str]]:
    tokens = set(dados["tokens"])
    texto = _sem_acento(dados["texto"]).casefold()
    agente = sorted(tokens & _AGENTES)
    acao = sorted(tokens & _ACOES)
    meio = sorted(tokens & _MEIOS)
    fim = any(item in tokens for item in _FINS) and bool(
        re.search(r"\b(para que|a fim|com o objetivo|de modo a)\b", texto)
        or "para" in tokens
    )
    detalhe = bool(
        re.search(
            r"\b(por meio|atraves|através|semanal|mensal|local|publico|público|gratuito)\b",
            texto,
        )
    )
    elementos = [
        ("agente", bool(agente), "quem executa a ação"),
        ("ação", bool(acao), "o que deve ser feito"),
        ("meio", bool(meio) or detalhe, "como a ação acontece"),
        ("fim", bool(fim), "para que a ação serve"),
        ("detalhe", detalhe, "quando, onde ou de que forma específica"),
    ]
    presentes = sum(1 for _nome, ok, _desc in elementos if ok)
    pontos = presentes * 18.0
    achados = []
    melhorias = []
    if presentes == 0:
        achados.append("Não há proposta de intervenção reconhecível.")
        melhorias.append(
            "Feche com os cinco pontos: quem faz, o que faz, como faz, para quê e um detalhe."
        )
    else:
        achados.append(f"A proposta cobre {presentes} de 5 elementos cobrados na competência 5.")
        if agente:
            achados.append("Agente: " + ", ".join(agente[:4]) + ".")
        else:
            melhorias.append("Nomeie o agente, como MEC, prefeituras, escolas ou famílias.")
        if acao:
            achados.append("Ação: " + ", ".join(acao[:4]) + ".")
        else:
            melhorias.append("Use um verbo de intervenção: implementar, ampliar, capacitar, fiscalizar.")
        if not (meio or detalhe):
            melhorias.append("Diga o meio: campanha, parceria, lei, oficina ou mutirão de leitura.")
        if not fim:
            melhorias.append("Complete com a finalidade, por exemplo para ampliar o hábito de ler.")
        if not detalhe:
            melhorias.append("Detalhe tempo ou lugar, como bibliotecas escolares de uso semanal.")
    for marca in _VIOLACAO:
        if marca in texto:
            pontos = 0
            achados.append("A proposta fere direitos humanos e pode zerar a competência 5.")
            melhorias.append("A intervenção precisa respeitar liberdade, dignidade e acesso.")
            break
    if dados["palavras"] >= 180 and presentes >= 4:
        pontos += 10
    pontos = max(0.0, min(100.0, pontos))
    return pontos, achados, melhorias


def analisar(texto: str, tema: dict | None = None) -> dict:
    tema = tema or TEMA_REDACAO
    dados = _metricas(texto)
    funcoes = {
        "c1": _achados_c1,
        "c2": lambda bloco: _achados_c2(bloco, tema),
        "c3": _achados_c3,
        "c4": _achados_c4,
        "c5": _achados_c5,
    }
    competencias = []
    total = 0
    for chave, nome, desc in COMPETENCIAS:
        pontos, achados, melhorias = funcoes[chave](dados)
        nota = _faixa(pontos)
        if dados["palavras"] < 20:
            nota = 0
            if not achados:
                achados = ["Texto insuficiente para correção."]
            if not melhorias:
                melhorias = ["Escreva um texto dissertativo completo sobre o tema."]
        total += nota
        competencias.append(
            {
                "chave": chave,
                "nome": nome,
                "desc": desc,
                "nota": nota,
                "nivel": NIVEIS[nota],
                "achados": achados,
                "melhorias": melhorias,
            }
        )
    resumo = (
        "Nota de treino: "
        f"{total} de 1000. "
        "O analisador lê padrões das cinco competências. "
        "Não substitui a correção oficial do INEP."
    )
    if dados["palavras"] < 50:
        resumo = (
            "O texto ainda é curto para uma nota estável. "
            "Complete perto de 20 a 30 linhas e peça a análise de novo."
        )
    return {
        "palavras": dados["palavras"],
        "paragrafos": dados["paragrafos"],
        "frases": dados["frases"],
        "linhas": dados["linhas"],
        "competencias": competencias,
        "notas": {item["chave"]: item["nota"] for item in competencias},
        "total": total,
        "resumo": resumo,
        "tema": tema.get("titulo"),
    }


EXEMPLOS = (
    {
        "id": "fraca",
        "titulo": "Exemplo fraco",
        "faixa": "Nota baixa",
        "texto": (
            "Eu acho que as pessoas tem que ler mais porque leitura e legal. "
            "Tipo na minha escola quase ninguem pega livro na biblioteca e isso e ruim ne. "
            "A galera prefere o celular o dia todo. O governo tem que fazer alguma coisa. Fim."
        ),
        "melhorias": (
            "Tire o tom de conversa (tipo, né, galera) e escreva na norma-padrão.",
            "Abra com uma tese sobre o acesso à leitura no Brasil, não com 'eu acho'.",
            "Separe quatro parágrafos e desenvolva duas causas, por exemplo casa sem livro e escola sem mediação.",
            "Troque 'o governo tem que fazer alguma coisa' por uma proposta com agente, ação, meio e finalidade.",
        ),
        "reescrita": (
            "A falta de acesso à leitura no Brasil se agrava quando a escola não media o livro "
            "e o jovem fica só no celular. "
            "Diante disso, o Ministério da Educação pode ampliar acervos escolares por meio de "
            "convênios com bibliotecas públicas, a fim de garantir tempo semanal de leitura mediada."
        ),
    },
    {
        "id": "mediana",
        "titulo": "Exemplo mediano",
        "faixa": "Nota no meio",
        "texto": (
            "No Brasil, ainda é comum encontrar jovens que leem pouco, mesmo com mais escolas "
            "e mais acesso a telas. A leitura forma o pensamento crítico, porém o hábito não "
            "se constrói sozinho.\n\n"
            "Um dos motivos é a ausência de livros em casa. Pesquisas mostram que muitos lares "
            "não têm estante nem rotina de ler em família. Sem esse contato, a escola vira o "
            "único espaço possível, e nem sempre dá conta. Além disso, falta mediação: o aluno "
            "ganha o livro e não ganha quem converse sobre ele.\n\n"
            "Portanto, é necessário que o governo invista em leitura para mudar esse quadro "
            "e ampliar o acesso no país."
        ),
        "melhorias": (
            "O tema está certo, mas o repertório é vago. Troque 'pesquisas mostram' por um dado ou autor.",
            "O terceiro parágrafo fecha cedo. Falta um segundo argumento mais desenvolvido.",
            "A proposta tem agente e ação, porém sem meio, detalhe e finalidade clara.",
            "Complete a intervenção com como, onde e para quê, respeitando os direitos humanos.",
        ),
        "reescrita": (
            "Segundo o artigo 205 da Constituição, a educação é direito de todos. "
            "Assim, o MEC, em parceria com prefeituras, pode criar horários semanais de leitura "
            "mediada nas escolas públicas, com acervo renovado, para que o estudante saia do "
            "contato ocasional e forme hábito."
        ),
    },
    {
        "id": "boa",
        "titulo": "Exemplo bom",
        "faixa": "Nota alta de treino",
        "texto": (
            "A Constituição federal afirma, no artigo 205, que a educação é direito de todos "
            "e dever do Estado. Mesmo assim, o acesso à leitura no Brasil segue desigual: "
            "falta livro em casa, falta tempo e falta quem media o texto na escola. "
            "Esse conjunto reduz o repertório e as chances de estudo.\n\n"
            "Em primeiro lugar, o livro ainda não circula em muitos lares. Dados de hábitos "
            "de leitura mostram lares sem nenhum exemplar e jovens que só encontram texto "
            "na tela, em fragmentos. Sem acervo próximo, a leitura vira evento raro, não rotina. "
            "Antonio Candido já ligava a literatura ao direito à humanização. Quando esse "
            "direito falha, a cidadania também estreita.\n\n"
            "Além disso, a escola nem sempre dá conta da mediação. Paulo Freire lembra que "
            "ler a palavra se liga a ler o mundo. Sem professor com tempo, biblioteca aberta "
            "e conversa sobre o texto, o aluno decodifica frases e não constrói sentido. "
            "O celular compete com essa escuta e, sem projeto, ganha o espaço vazio.\n\n"
            "Diante disso, o Ministério da Educação, em parceria com prefeituras e bibliotecas "
            "públicas, deve implementar horários semanais de leitura mediada nas escolas, "
            "por meio de acervo renovado e formação de professores, a fim de garantir o hábito "
            "de ler com acompanhamento. A ação precisa ser gratuita e aberta às famílias, "
            "respeitando a liberdade de escolha das obras."
        ),
        "melhorias": (
            "O texto já cobre tema, repertório, progressão e proposta completa.",
            "Na revisão, evite repetir 'falta' na introdução e varie um conectivo no fechamento.",
            "Se quiser subir ainda mais, detalhe um indicador e o prazo da política, sem copiar prova antiga.",
        ),
        "reescrita": "",
    },
)


def exemplos_analisados(tema: dict | None = None) -> list[dict]:
    tema = tema or TEMA_REDACAO
    lista = []
    for item in EXEMPLOS:
        analise = analisar(item["texto"], tema)
        lista.append({**item, "analise": analise})
    return lista
