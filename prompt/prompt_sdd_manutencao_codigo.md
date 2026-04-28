# Regra permanente para projetos SDD

## Manutenibilidade de Código

Todo código gerado no fluxo Spec Driven Development deve ser legível por humanos de diferentes níveis de senioridade com a linguagem.

Obrigatório:

- funções pequenas e com responsabilidade única;
- nomes claros para variáveis, funções, arquivos e módulos;
- docstrings em funções públicas;
- comentários explicando decisões de negócio e regras não óbvias;
- evitar comentários redundantes que apenas repetem a sintaxe da linguagem;
- preservar compatibilidade entre chamadas de função e módulos;
- sempre que houver deduplicação, explicitar a chave lógica usada;
- sempre que houver classificação, documentar a regra aplicada;
- sempre que houver mudança de assinatura de função, ajustar todos os chamadores;
- gerar testes para regras críticas de negócio;
- evitar sequência de hotfixes sem consolidar o contrato entre módulos.

Ao entregar código, incluir:

1. arquivos alterados;
2. motivo da alteração;
3. impacto esperado;
4. como testar;
5. riscos ou limitações conhecidas.
