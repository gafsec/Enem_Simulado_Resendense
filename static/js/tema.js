(function () {
    var chave = "enem-tema";

    function atual() {
        return document.documentElement.getAttribute("data-bs-theme") === "light"
            ? "light"
            : "dark";
    }

    function rotulo(tema) {
        return tema === "dark" ? "Tema claro" : "Tema escuro";
    }

    function aplicar(tema) {
        if (tema !== "light" && tema !== "dark") {
            tema = "dark";
        }
        document.documentElement.setAttribute("data-bs-theme", tema);
        var botao = document.getElementById("btn-tema");
        if (botao) {
            botao.textContent = rotulo(tema);
            botao.setAttribute("aria-pressed", tema === "light" ? "true" : "false");
            botao.setAttribute("title", rotulo(tema));
        }
        document.dispatchEvent(new CustomEvent("tema-alterado", { detail: tema }));
    }

    window.aplicarTema = aplicar;

    document.addEventListener("DOMContentLoaded", function () {
        aplicar(atual());
        var botao = document.getElementById("btn-tema");
        if (!botao) {
            return;
        }
        botao.addEventListener("click", function () {
            var proximo = atual() === "dark" ? "light" : "dark";
            try {
                localStorage.setItem(chave, proximo);
            } catch (erro) {
                /* ignora */
            }
            aplicar(proximo);
        });
    });
})();
