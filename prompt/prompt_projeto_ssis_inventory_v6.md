# Prompt atualizado - ssis-inventory

Atue no contexto do projeto `ssis-inventory`.

Regras críticas:
1. `connection_name` deve conter somente Connection Manager real.
2. Nunca usar caminho de componente `Package\...\Componente` como conexão associada.
3. `EXEC` e `EXECUTE` devem gerar `object_type = procedure`.
4. Literais em `SqlTaskData` com prefixos `p_`, `sp_`, `usp_`, `pr_`, `proc_` devem ser tratados como procedure.
5. Literais de destino OLE DB como `[dbo].[Tabela]` continuam sendo table.
6. Objetos em SQL comentado devem ser ignorados quando `ignore_sql_comments_for_objects = true`.
7. Componentes desabilitados devem ser ignorados quando `ignore_disabled = true`.
8. Parâmetros devem ficar em `config/application_parameters.json`, não hardcoded no código.
