"""Textos e imagens da página /faq."""

from pathlib import Path

ATUALIZADO_EM = "14/11/2026"
PASTA_PRINTS = Path(__file__).resolve().parent / "static" / "img" / "faq"

ITENS = [
    {
        "id": "entrar",
        "pergunta": "Como entro na plataforma?",
        "resposta": (
            "Em Entrar, use o e-mail e a senha da sua conta. "
            "Se ainda não tiver cadastro, use Cadastrar. "
            "Se esquecer a senha, use Esqueci a senha com o e-mail e o nome da conta."
        ),
        "print": "entrar.png",
        "legenda": "Tela Entrar, com e-mail, senha e o link para criar conta.",
    },
    {
        "id": "cadastro",
        "pergunta": "O que preciso para criar uma conta?",
        "resposta": (
            "Informe nome, e-mail, UF, município e senha (mínimo de 6 caracteres). "
            "A região é obrigatória. "
            "O padrão do projeto é Rio de Janeiro e Resende, mas você escolhe a sua cidade."
        ),
        "print": "cadastro.png",
        "legenda": "Formulário de cadastro com nome, e-mail, UF, município e senha.",
    },
    {
        "id": "conta",
        "pergunta": "Como altero meu cadastro e a região?",
        "resposta": (
            "Em Cadastro você edita nome, UF e município. "
            "O e-mail não muda. "
            "Para trocar a senha, abra Trocar senha e informe a senha atual."
        ),
        "print": "conta.png",
        "legenda": "Meu cadastro, com nome, e-mail travado, UF e município.",
    },
    {
        "id": "simulado",
        "pergunta": "Como monto um simulado?",
        "resposta": (
            "No menu, Tema claro e Tema escuro mudam as cores da tela. "
            "Os textos e os rótulos acompanham o tema escolhido. "
            "Na página inicial, escolha as áreas, a quantidade de questões e o formato. "
            "Treino deixa pausar e pode mostrar o gabarito depois de cada resposta. "
            "Prova cronometrada tem tempo, sem pausa, e o gabarito só no final. "
            "Há também Dia 1 (90 questões, 5h30), Dia 2 (90 questões, 5h) e a prova completa de 180. "
            "Em Filtrar anos, assuntos e opções você marca anos, assuntos, língua estrangeira, "
            "tempo da prova, tipo de correção, só questões novas ou só as que você errou."
        ),
        "print": "inicio.png",
        "legenda": "Novo simulado, com áreas, quantidade, formato e filtros abertos.",
    },
    {
        "id": "prova",
        "pergunta": "Como respondo, marco para rever, pauso ou cancelo?",
        "resposta": (
            "Cada questão do caderno oficial aparece como no impresso, "
            "da QUESTÃO até a seguinte, com texto, figura e alternativas. "
            "A tela indica o número da questão no caderno, o dia, o caderno, a cor, a área, "
            "a opção de língua quando for o caso e a página do arquivo. "
            "Abrir a questão no arquivo abre o caderno já na página dela. "
            "Nas questões da API, o botão mostra o texto original formatado. "
            "No impresso, a figura da questão seguinte às vezes aparece na mesma folha. "
            "Marque uma alternativa e avance. "
            "Se a correção for depois de cada resposta, use Mostrar resposta. "
            "O certo ou o errado aparece no mesmo lugar, a bolinha fica verde se acertou e vermelha se errou, e só então você avança. "
            "Nas provas com caderno do INEP, o link abre o gabarito oficial na página daquela questão. "
            "A barra de números fica depois das respostas e leva a outra questão. "
            "Marcar para rever pinta o número de laranja. Dá para marcar quantas questões quiser, já respondidas ou não. "
            "Sem resposta, dá para avançar. O simulado só termina quando essas pendentes também tiverem alternativa. "
            "Ao marcar a alternativa, o rascunho grava sozinho. "
            "Pausar (só no treino) guarda o progresso. "
            "Se a aba fechar, o simulado volta quando você entrar de novo. "
            "Cancelar apaga o simulado em andamento da sua lista."
        ),
        "print": "quiz.png",
        "legenda": "Questão do simulado, com o texto ou a figura, o número no caderno oficial, as respostas e a barra de números.",
    },
    {
        "id": "desempenho",
        "pergunta": "Onde vejo meu desempenho e os simulados feitos?",
        "resposta": (
            "Em Desempenho aparecem seus simulados, o aproveitamento, as questões respondidas "
            "e as que você errou. Assuntos com mais erro lista os temas classificados "
            "(como Espanhol, Funções ou Geometria) em que você mais errou, "
            "com a quantidade e a porcentagem de erro. "
            "O que não entra em um tema vai para Outros em Linguagens, Outros em Matemática e assim por diante. "
            "Clique nos indicadores para ver o detalhe da área ou do assunto. "
            "A lista traz seus simulados, de 10 em 10, com páginas, e o IP oculto de cada prova, só com o primeiro bloco. "
            "O mesmo usuário pode repetir o IP. "
            "Clique no título da coluna para ordenar. "
            "Use Continuar ou Cancelar se a prova ainda estiver aberta, "
            "ou Revisar para ver o gabarito e a estimativa na escala 0 a 1000. "
            "Nas questões do caderno oficial, o resultado também abre o PDF do gabarito na página da resposta. "
            "Na mesma página está a explicação de como a porcentagem e a estimativa são calculadas."
        ),
        "print": "desempenho.png",
        "legenda": "Painel de desempenho, com indicadores e a lista dos últimos simulados.",
    },
    {
        "id": "notas",
        "pergunta": "Como a nota é calculada?",
        "resposta": (
            "A porcentagem é acertos dividido pelo total de questões, vezes 100. "
            "Cada item vale o mesmo, fácil ou difícil. "
            "A estimativa de 0 a 1000 é um cálculo de treino do portal. "
            "Questões que pouca gente acerta pesam mais. A conta parte de 500 e sobe ou desce. "
            "Não é a TRI oficial do INEP. "
            "Na redação, o analisador sugere uma nota pelas cinco competências. Também é treino."
        ),
        "print": "resultado.png",
        "legenda": "Resultado do simulado, com a porcentagem, a estimativa 0 a 1000 e a explicação do cálculo.",
    },
    {
        "id": "avaliacao",
        "pergunta": "Como avalio o portal?",
        "resposta": (
            "Em Avaliação, clique em Abrir pesquisa no Google Forms. "
            "O link cai no formulário em que a turma preencheu a pesquisa sobre o projeto. "
            "Lá você diz o que achou, quantas vezes usou, o quanto ajudou e o que pode melhorar. "
            "As respostas medem o resultado na comunidade escolar."
        ),
        "print": "avaliacao.png",
        "legenda": "Tela de Avaliação, com o botão que abre a pesquisa no Google Forms.",
        "link_forms": True,
        "link_rotulo": "Abrir pesquisa no Google Forms",
    },
    {
        "id": "redacao",
        "pergunta": "Como treino a redação?",
        "resposta": (
            "Em Redação, leia o tema e escreva o texto. "
            "Clique em Analisar pelo ENEM. O portal lê padrões das cinco competências, "
            "sugere uma nota de 0 a 1000 e aponta o que melhorar. "
            "Abaixo há três exemplos no mesmo tema, com nota de treino, falhas e trecho reescrito. "
            "Você ainda pode salvar a autoavaliação, de 0 a 200 em cada competência. "
            "Isso é treino, não a correção oficial do INEP."
        ),
        "print": "redacao.png",
        "legenda": "Tela de redação, com a análise pelas competências, a nota sugerida e os exemplos de melhoria.",
    },
]


def itens():
    return ITENS
