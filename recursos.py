"""Regras extras: progresso, TRI aproximada e tema de redação."""

import json
import math

from collections import defaultdict


def eh_admin(user) -> bool:
    return bool(user and (getattr(user, "papel", None) or "") == "admin")


def progresso_carregar(sim) -> dict:
    try:
        dados = json.loads(sim.progresso or "{}")
    except Exception:
        dados = {}
    if not isinstance(dados, dict):
        return {}
    dados.setdefault("rascunhos", {})
    return dados


def progresso_salvar(sim, sessao, rascunhos=None) -> None:
    dados = progresso_carregar(sim)
    if rascunhos is not None:
        dados["rascunhos"] = {str(chave): valor for chave, valor in rascunhos.items()}
    dados["question_ids"] = sessao.get("question_ids") or dados.get("question_ids") or []
    dados["current_index"] = sessao.get("current_index", dados.get("current_index", 0))
    dados["start_time"] = sessao.get("start_time") or dados.get("start_time")
    dados["prazo"] = sessao.get("prazo") or dados.get("prazo")
    dados["formato"] = sessao.get("formato") or dados.get("formato") or "treino"
    dados["correcao"] = sessao.get("correcao") or dados.get("correcao") or "final"
    sim.progresso = json.dumps(dados, ensure_ascii=False)


def aplicar_progresso(sim, sessao) -> bool:
    dados = progresso_carregar(sim)
    ids = dados.get("question_ids") or []
    if not ids:
        return False
    sessao["simulation_id"] = sim.id
    sessao["question_ids"] = [int(item) for item in ids]
    sessao["current_index"] = int(dados.get("current_index") or 0)
    if dados.get("start_time"):
        sessao["start_time"] = dados["start_time"]
    if dados.get("prazo"):
        sessao["prazo"] = dados["prazo"]
    else:
        sessao.pop("prazo", None)
    sessao["formato"] = dados.get("formato") or "treino"
    sessao["correcao"] = dados.get("correcao") or "final"
    return True


def _prob(theta: float, b: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-(theta - b)))
    except OverflowError:
        return 0.0 if theta < b else 1.0


def mapa_dificuldade():
    from app import SimulationAnswer

    totais = defaultdict(int)
    acertos = defaultdict(int)
    for questao_id, correta in SimulationAnswer.query.with_entities(
        SimulationAnswer.question_id, SimulationAnswer.correta
    ):
        totais[questao_id] += 1
        if correta:
            acertos[questao_id] += 1
    mapa = {}
    for questao_id, total in totais.items():
        p = min(0.95, max(0.05, acertos[questao_id] / total))
        mapa[questao_id] = math.log((1.0 - p) / p)
    return mapa


def estimativa_tri(respostas) -> float | None:
    pares = []
    dificuldades = mapa_dificuldade()
    for item in respostas:
        if item.question_id is None:
            continue
        b = dificuldades.get(item.question_id, 0.0)
        pares.append((b, 1.0 if item.correta else 0.0))
    if len(pares) < 3:
        return None
    theta = 0.0
    for _ in range(25):
        probs = [_prob(theta, b) for b, _certo in pares]
        grad = sum(certo - p for (_b, certo), p in zip(pares, probs))
        hess = -sum(p * (1.0 - p) for p in probs)
        if abs(hess) < 1e-6:
            break
        theta -= grad / hess
        theta = max(-4.0, min(4.0, theta))
    return round(max(0.0, min(1000.0, 500.0 + 120.0 * theta)), 0)


TEMA_REDACAO = {
    "titulo": "Desafios para ampliar o acesso à leitura no Brasil",
    "texto": (
        "A leitura amplia o repertório, o pensamento crítico e as chances de estudo. "
        "Ainda assim, parte dos jovens brasileiros lê pouco por falta de livro em casa, "
        "de tempo e de mediação na escola. "
        "Com base na realidade que você conhece, escreva um texto dissertativo-argumentativo "
        "em prosa na norma-padrão da língua portuguesa sobre o tema "
        "\"Desafios para ampliar o acesso à leitura no Brasil\". "
        "Apresente uma proposta de intervenção que respeite os direitos humanos. "
        "Não copie trechos deste enunciado."
    ),
}

COMPETENCIAS = (
    ("c1", "Competência 1", "Domínio da norma-padrão"),
    ("c2", "Competência 2", "Compreensão do tema e repertório"),
    ("c3", "Competência 3", "Organização dos argumentos"),
    ("c4", "Competência 4", "Coesão e articulação"),
    ("c5", "Competência 5", "Proposta de intervenção"),
)
