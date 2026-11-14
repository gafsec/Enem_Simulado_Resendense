# Enem Simulado Resendense

Portal de simulados do ENEM do Projeto social Resendense, usado com alunos do 3º ano do IFRJ campus Resende.

Na fase de aplicação, a aplicação Flask ficou disponível online para os estudantes. O banco em produção foi PostgreSQL no [Supabase](https://supabase.com/). Cadastro, login e sessão ficam na própria aplicação; contas, simulados e redações são gravados nesse banco. Em desenvolvimento local o padrão é SQLite.

O acervo tem questões oficiais do ENEM de 2009 a 2025 (`data/questoes.json`). Na primeira execução o portal carrega esse arquivo.

Tutorial de uso: https://youtu.be/5-oUtf-qwek
