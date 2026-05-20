# Backlog - Web gratuita e internacionalizacao

Issue: https://github.com/sql-server-toolkit/ssis-inventory/issues/1
Branch: `feature/web-ui-i18n`

## Objetivo

Disponibilizar o consumo do SSIS Inventory por meio de uma aplicacao web
gratuita, mantendo o fluxo CLI atual e oferecendo textos de entrada,
orientacao, mensagens e saida nos idiomas PT-BR, EN e ES.

Arquitetura alvo proposta:

- front-end web para selecao de idioma, upload dos arquivos SSIS e escolha dos
  parametros de execucao;
- backend Python para receber os arquivos, armazenar temporariamente, executar a
  rotina de inventario existente e gerar os relatorios;
- disponibilizacao do Excel/JSON para download;
- exclusao dos arquivos de entrada e saida temporarios ao final do fluxo ou por
  rotina de expiracao.

## Decisao de precedencia

As pendencias abaixo estao ordenadas por dependencia tecnica e risco. A ideia e
evitar implementar uma interface bonita antes de decidir como a solucao sera
executada, quais textos precisam ser internacionalizados e qual saida web sera
suportada.

## P0 - Definicoes de produto e arquitetura

- [x] Definir o modo de consumo web inicial: front-end web com upload e backend
  Python para processamento temporario dos arquivos SSIS.
- [x] Definir framework do backend Python: FastAPI.
  - Justificativa: bom suporte a APIs HTTP, upload de arquivos, parametros
    tipados, validacao de entrada, documentacao automatica OpenAPI, testes com
    `TestClient` e baixo acoplamento com o motor atual.
  - Execucao local sugerida: Uvicorn.
  - Escopo do backend: somente orquestrar upload temporario, validacao,
    chamada da rotina Python existente, download dos relatorios e limpeza.
  - Evitar colocar regra de parser SSIS dentro dos handlers HTTP.
- [x] Definir framework/estrategia do front-end: HTML/CSS/JavaScript estatico,
  modular e sem framework no MVP.
  - Justificativa: reduz dependencias, evita etapa de build, facilita hospedagem
    estatica gratuita e aproveita o `index.html` ja existente no repositorio.
  - O front-end deve consumir a API FastAPI via `fetch` e `FormData`.
  - O catalogo de traducoes pode ficar em arquivo JavaScript ou JSON estatico,
    com chaves para PT-BR, EN e ES.
  - Um framework front-end so deve ser reconsiderado se a interface crescer para
    muitas telas, estado complexo, autenticacao ou fluxo assincrono mais rico.
- [x] Definir contrato de upload: `.zip` unico contendo a pasta do projeto SSIS.
  - Justificativa: preserva subpastas, arquivos `.conmgr`, pacotes e estrutura
    original usada por `discover_project_files`.
  - Campo multipart: `project_archive`.
  - Content-Type esperado: `multipart/form-data`.
  - Extensao aceita no MVP: `.zip`.
  - Conteudo aceito dentro do `.zip`: `.dtproj`, `.dtsx`, `.conmgr`, `.ispac` e
    arquivos auxiliares necessarios ao projeto.
  - Estrutura minima valida: ao menos um `.dtproj` ou um `.dtsx`.
  - Upload multiplo de arquivos soltos fica como evolucao posterior, pois pode
    perder estrutura de diretorios e aumentar erro operacional.
  - O backend deve extrair o `.zip` para um diretorio temporario exclusivo por
    execucao e passar esse diretorio como `project_folder` para o motor atual.
  - O backend deve rejeitar `.zip` vazio, corrompido, protegido por senha, com
    caminhos absolutos ou com entradas que tentem sair do diretorio temporario.
- [x] Definir parametros expostos na interface.
  - `ui_language`: idioma da interface. Tipo: select. Valores: `auto`,
    `pt-BR`, `en`, `es`. Padrao: `auto`. Afeta somente textos da pagina.
    Quando `auto`, o front-end deve tentar detectar o idioma via
    `navigator.language` / `navigator.languages`; se nao encontrar idioma
    suportado, deve assumir `en`.
  - `report_language`: idioma dos relatorios. Tipo: select. Valores: `pt-BR`,
    `en`, `es`. Padrao: idioma resolvido da interface. Se `ui_language=auto`,
    deve usar o idioma detectado ou `en` como fallback. No MVP pode ser aceito
    pela API e aplicado parcialmente ate P4 concluir a internacionalizacao dos
    relatorios.
  - `ignore_disabled`: ignorar componentes desabilitados. Tipo: toggle. Padrao:
    `true`. Mapeia para `AppConfig.ignore_disabled`.
  - `ignore_sql_comments_for_objects`: ignorar comentarios SQL ao extrair
    objetos. Tipo: toggle. Padrao: `true`. Mapeia para
    `AppConfig.ignore_sql_comments_for_objects`.
  - `json_output_mode`: modo do JSON. Tipo: select ou segmented control.
    Valores: `compact`, `full`. Padrao: `compact`. Mapeia para
    `AppConfig.json_output_mode`.
  - `include_raw_sheets`: incluir abas brutas no Excel. Tipo: toggle. Padrao:
    `true`. Mapeia para `AppConfig.include_raw_sheets`.
  - `ignore_temp_tables`: ignorar tabelas temporarias. Tipo: toggle. Padrao:
    `true`. Mapeia para `AppConfig.ignore_temp_tables`.
  - `temp_table_prefixes`: prefixos de tabelas temporarias. Tipo: input de texto
    simples com valores separados por virgula. Padrao: `#`. Mapeia para
    `AppConfig.temp_table_prefixes`.
  - Parametros fora do MVP: `include_raw_sql_in_json` e
    `max_sql_preview_chars`, pois ainda nao sao usados de forma consistente pelo
    fluxo de exportacao atual.
  - O backend deve aplicar defaults seguros quando um parametro nao for enviado.
  - O front-end deve agrupar opcoes avancadas em uma secao recolhivel para nao
    sobrecarregar o usuario no primeiro uso.
- [x] Definir ciclo de vida dos arquivos temporarios.
  - Criar um `job_id` aleatorio por execucao usando UUID ou token seguro.
  - Criar diretorio de trabalho exclusivo por execucao em uma raiz temporaria
    configuravel, por exemplo `SSIS_INVENTORY_WORK_DIR` ou o temp dir do SO.
  - Estrutura sugerida:
    - `{work_root}/{job_id}/upload/` para o `.zip` recebido;
    - `{work_root}/{job_id}/project/` para o conteudo extraido;
    - `{work_root}/{job_id}/output/` para Excel/JSON gerados;
    - `{work_root}/{job_id}/metadata.json` para status minimo sem dados
      sensiveis.
  - Salvar o `.zip` apenas ate a extracao segura terminar.
  - Apagar o `.zip` imediatamente apos extracao bem-sucedida ou erro de
    validacao.
  - Apagar a pasta `project/` imediatamente apos a rotina Python gerar os
    relatorios ou falhar.
  - Manter somente `output/` e `metadata.json` durante a janela de download.
  - Janela de download sugerida para MVP: 30 minutos apos conclusao do job.
  - Apos um download bem-sucedido de Excel e JSON, o backend pode manter os
    arquivos ate a expiracao para permitir nova tentativa dentro da janela.
  - Executar limpeza por expiracao em toda inicializacao do backend e tambem em
    background/best-effort apos cada job.
  - Remover jobs em status `failed`, `expired` ou `completed` quando passarem da
    janela de retencao.
  - Nunca gravar arquivos temporarios dentro do repositorio.
  - Nao expor caminho fisico dos arquivos na API.
  - Registrar falhas de limpeza apenas com `job_id`, status e tipo de erro, sem
    connection strings, nomes de servidores ou conteudo dos arquivos.
  - Se a limpeza falhar, marcar o job para nova tentativa e retornar erro
    generico ao usuario apenas quando isso afetar o download.
- [x] Definir limites operacionais iniciais do MVP.
  - Upload aceito: 1 arquivo `.zip` por execucao.
  - Tamanho maximo do upload compactado: 50 MB.
  - Tamanho maximo total apos extracao: 200 MB.
  - Quantidade maxima de entradas no `.zip`: 2.000 arquivos.
  - Profundidade maxima de diretorios no `.zip`: 20 niveis.
  - Tamanho maximo de um unico arquivo extraido: 50 MB.
  - Timeout de upload: 60 segundos.
  - Timeout de processamento: 5 minutos por job.
  - Concorrencia inicial: 1 job em processamento por instancia.
  - Fila inicial: ate 3 jobs aguardando; acima disso retornar erro amigavel
    para tentar novamente depois.
  - Janela de download: 30 minutos apos conclusao do job.
  - Retencao maxima absoluta de qualquer job: 45 minutos, mesmo em caso de erro
    de estado.
  - Tamanho maximo esperado dos relatorios gerados: 100 MB somando Excel e JSON.
  - Configurar esses limites por variaveis de ambiente para adaptar a hospedagem:
    `SSIS_MAX_UPLOAD_MB`, `SSIS_MAX_EXTRACTED_MB`, `SSIS_MAX_ZIP_ENTRIES`,
    `SSIS_JOB_TIMEOUT_SECONDS`, `SSIS_MAX_ACTIVE_JOBS`,
    `SSIS_MAX_QUEUED_JOBS`, `SSIS_DOWNLOAD_TTL_MINUTES`.
  - Exibir limites principais na interface antes do upload.
  - Se algum limite for excedido, retornar erro traduzivel e remover arquivos
    temporarios ja criados.
- [x] Definir limites de privacidade para upload/processamento de pacotes SSIS.
  - Nao persistir arquivos enviados, arquivos extraidos ou relatorios de forma
    permanente.
  - Nao manter historico de jobs apos a expiracao da janela de download.
  - Nao criar banco de dados com conteudo dos pacotes, connection strings,
    nomes de servidores, usuarios, caminhos internos ou SQL extraido.
  - Nao registrar connection strings completas em logs.
  - Nao registrar SQL extraido, conteudo XML dos pacotes, nomes completos de
    arquivos enviados ou caminhos internos do projeto em logs de aplicacao.
  - Logs permitidos: `job_id`, timestamps, status, tamanho do upload, duracao,
    quantidade agregada de arquivos, tipo de erro e codigo de erro traduzivel.
  - Mascarar qualquer valor sensivel que apareca em excecoes antes de registrar
    logs ou retornar mensagens ao usuario.
  - Retornar mensagens de erro genericas para o usuario quando a falha puder
    conter detalhes internos do pacote.
  - Mostrar aviso antes do upload informando que projetos SSIS podem conter
    dados sensiveis, como servidores, usuarios, connection strings, caminhos e
    comandos SQL.
  - Exigir confirmacao do usuario antes do envio, por checkbox, de que ele tem
    autorizacao para processar os arquivos.
  - Informar claramente a politica de retencao: upload e arquivos extraidos sao
    apagados durante o processamento; relatorios ficam disponiveis por 30
    minutos; retencao maxima absoluta de 45 minutos.
  - Nao usar os arquivos enviados para treinamento, analytics de conteudo,
    exemplos publicos ou qualquer finalidade fora da geracao do relatorio.
  - Nao enviar arquivos SSIS para servicos terceiros alem da infraestrutura de
    hospedagem escolhida para executar o backend.
  - Preferir HTTPS obrigatorio em ambiente publicado.
  - Documentar essas regras no README ou em pagina/politica de privacidade curta
    vinculada na interface.
- [x] Definir quais formatos entram no MVP: somente `.zip` contendo projeto
  SSIS; arquivos `.dtsx`, `.dtproj`, `.conmgr` e `.ispac` serao aceitos dentro
  do pacote compactado.
- [x] Definir plataforma gratuita de publicacao.
  - Front-end MVP: GitHub Pages, publicando os arquivos estaticos
    `index.html`, CSS, JavaScript e catalogo i18n.
  - Backend MVP: Render Free Web Service executando FastAPI/Uvicorn.
  - Justificativa: GitHub Pages e simples para site estatico, mas nao executa
    Python; Render Free Web Service suporta apps Python e tem filesystem
    efemero, adequado ao uso temporario definido para uploads e relatorios.
  - Restricoes aceitas no MVP:
    - cold start quando o backend ficar inativo;
    - filesystem efemero, sem persistencia permanente;
    - sem scaling alem de uma instancia gratuita;
    - suspensao se limites mensais forem excedidos;
    - nao usar para producao critica.
  - Fallback gratuito/baixo custo: Koyeb Free Instance, se Render nao atender
    limites de upload, timeout ou disponibilidade.
  - Fallback cloud com maior controle: Google Cloud Run Free Tier, desde que a
    conta tenha billing configurado, limites de custo e alertas.
- [x] Registrar a decisao tecnica no README ou em `specs/`.
  - Registrado em `specs/web_i18n_architecture.md`.
  - `specs/sdd_ssis_inventory.md` referencia a nova spec.

## P1 - Contrato de internacionalizacao

- [ ] Criar catalogo central de textos por idioma: PT-BR, EN e ES.
- [ ] Definir idioma padrao da pagina.
- [ ] Implementar deteccao automatica de idioma:
  - ler `navigator.languages` e `navigator.language`;
  - mapear `pt`, `pt-BR` e variantes para `pt-BR`;
  - mapear `es` e variantes para `es`;
  - mapear `en` e variantes para `en`;
  - usar `en` como fallback quando nao houver idioma suportado.
- [ ] Implementar seletor de idioma.
- [ ] Persistir preferencia de idioma no navegador quando o usuario escolher
  manualmente um idioma diferente de `auto`.
- [ ] Internacionalizar textos de navegacao, botoes, labels, instrucoes e mensagens.
- [ ] Internacionalizar textos de saida apresentados na pagina.
- [ ] Revisar textos existentes com caracteres quebrados no README e no `index.html`.
- [ ] Definir convencao de chaves de traducao para evitar duplicacao.

## P2 - Experiencia web

- [ ] Reestruturar o `index.html` para ser a experiencia principal de uso, nao apenas uma landing page.
- [ ] Organizar assets estaticos do front-end:
  - CSS dedicado, por exemplo `web/styles.css`;
  - JavaScript dedicado, por exemplo `web/app.js`;
  - catalogo i18n, por exemplo `web/i18n.js` ou `web/i18n/*.json`.
- [ ] Definir estrategia de configuracao da URL da API:
  - local: `http://localhost:8000`;
  - publicada: URL do backend gratuito;
  - evitar hardcode dificil de alterar.
- [ ] Criar fluxo visual para o usuario escolher idioma e entender o proximo passo.
- [ ] Criar area de entrada para upload:
  - aceitar um unico `.zip` do projeto SSIS no campo `project_archive`;
  - exibir formatos aceitos;
  - exibir limites de tamanho;
  - validar extensoes antes do envio;
  - orientar o usuario sobre dados sensiveis.
- [ ] Criar area de parametros de execucao com labels traduzidos.
  - parametros basicos: `ui_language` com deteccao automatica e
    `report_language`;
  - parametros avancados: `ignore_disabled`,
    `ignore_sql_comments_for_objects`, `json_output_mode`,
    `include_raw_sheets`, `ignore_temp_tables`, `temp_table_prefixes`.
- [ ] Criar area de progresso:
  - upload recebido;
  - arquivos validados;
  - inventario em execucao;
  - relatorio gerado;
  - erro ou sucesso.
- [ ] Criar area de saida:
  - botao para download do Excel;
  - botao para download do JSON;
  - resumo do processamento;
  - warnings traduzidos quando expostos na interface.
- [ ] Implementar estados de interface em JavaScript:
  - idle;
  - validating;
  - uploading;
  - processing;
  - ready;
  - error.
- [ ] Garantir responsividade em desktop e mobile.
- [ ] Garantir acessibilidade basica: labels, contraste, foco de teclado e textos alternativos quando necessario.
- [ ] Manter links para GitHub, documentacao e contato.

## P3 - Integracao com o motor atual

- [ ] Separar regras reutilizaveis da CLI para permitir chamada pelo backend web
  sem depender de argumentos de linha de comando.
- [ ] Criar funcao de servico, por exemplo `run_inventory(project_folder,
  output_folder, config)`, retornando caminhos dos relatorios e resumo da
  execucao.
- [ ] Garantir que qualquer mudanca preserve `python -m app.main`.
- [ ] Criar modulo de backend FastAPI isolado, por exemplo `app/web_api.py` ou
  `app/api/main.py`, importando servicos do motor sem duplicar logica.
- [ ] Adicionar dependencias web:
  - `fastapi`;
  - `uvicorn`;
  - `python-multipart` para upload multipart;
  - dependencias de teste HTTP se necessario.
- [ ] Definir contrato de API:
  - `POST /api/inventory` para upload e parametros;
  - resposta com `job_id`, status ou links de download;
  - `GET /api/inventory/{job_id}` para status, se processamento for assincrono;
  - `GET /api/inventory/{job_id}/download/excel`;
  - `GET /api/inventory/{job_id}/download/json`.
- [ ] Decidir se o processamento sera sincrono no MVP ou assincrono com status.
- [ ] Implementar extracao segura de `.zip` evitando path traversal.
- [ ] Criar validacao de extensoes e estrutura minima do projeto SSIS:
  - aceitar upload apenas com extensao `.zip`;
  - exigir pelo menos um `.dtproj` ou `.dtsx` extraido;
  - rejeitar arquivo vazio, corrompido ou protegido por senha;
  - registrar erro amigavel e traduzivel para cada rejeicao.
- [ ] Criar limpeza automatica dos diretorios temporarios:
  - remover `upload/` apos extracao;
  - remover `project/` apos processamento;
  - remover `output/` e `metadata.json` apos expiracao;
  - executar limpeza ao iniciar o backend;
  - executar limpeza best-effort apos cada job.
- [ ] Mapear mensagens de erro da CLI que devem ter equivalentes traduzidos.

## P4 - Saidas e relatorios em PT-BR, EN e ES

- [ ] Mapear nomes atuais de abas, colunas e mensagens do Excel/JSON.
- [ ] Definir se Excel/JSON terao idioma configuravel pelo usuario.
- [ ] Criar camada de traducao para nomes de abas e colunas operacionais.
- [ ] Internacionalizar textos como acoes esperadas, observacoes e warnings publicados.
- [ ] Preservar compatibilidade com consumidores atuais dos arquivos, se os nomes em PT-BR forem usados como contrato.
- [ ] Adicionar testes para garantir que cada idioma gera saidas consistentes.

## P5 - Documentacao

- [ ] Atualizar README com:
  - modo CLI atual;
  - modo web;
  - idiomas suportados;
  - limitacoes do MVP;
  - link da pagina publicada.
- [ ] Criar instrucoes de execucao local da pagina web e do backend.
- [ ] Documentar como adicionar ou alterar traducoes.
- [ ] Documentar decisoes de privacidade e seguranca para arquivos SSIS.
- [ ] Documentar politica de retencao temporaria dos arquivos enviados.
- [ ] Atualizar `specs/sdd_ssis_inventory.md` com o novo canal web.

## P6 - Testes e validacao

- [ ] Executar suite Python existente com `pytest`.
- [ ] Validar que o fluxo CLI continua funcionando.
- [ ] Testar upload valido de projeto SSIS compactado.
- [ ] Testar rejeicao de extensoes invalidas.
- [ ] Testar rejeicao de `.zip` inseguro com caminhos fora do diretorio de trabalho.
- [ ] Testar limpeza dos arquivos temporarios apos processamento:
  - `.zip` removido apos extracao;
  - `project/` removido apos sucesso;
  - `project/` removido apos erro;
  - `output/` preservado durante a janela de download;
  - job expirado removido pela rotina de limpeza.
- [ ] Testar geracao e download de Excel/JSON pelo fluxo web.
- [ ] Validar troca de idioma na pagina.
- [ ] Validar layout em desktop e mobile.
- [ ] Validar que nao ha texto hardcoded fora do catalogo de traducoes, onde aplicavel.
- [ ] Validar ausencia de regressao nos relatorios Excel/JSON.
- [ ] Registrar evidencias de validacao manual no PR.

## P7 - Publicacao gratuita

- [x] Pesquisar e escolher hospedagem gratuita para backend Python: Render Free
  Web Service para o MVP.
- [ ] Avaliar opcoes candidatas para backend FastAPI gratuito:
  - Render Free Web Service: simples para FastAPI, mas com cold start e limites
    mensais;
  - Koyeb Free Instance: bom encaixe para APIs/container, validar exigencia de
    cartao, limites e disponibilidade;
  - Railway Free/Trial: bom DX, mas validar creditos mensais e duracao real do
    uso gratuito;
  - PythonAnywhere Free: focado em Python, mas validar suporte pratico a FastAPI,
    limites de CPU, disco e web worker;
  - Google Cloud Run Free Tier: bom para container FastAPI, mas exige projeto
    cloud/billing e controle cuidadoso de limites;
  - Hugging Face Spaces Docker: pode rodar FastAPI em Docker, bom para demo, mas
    validar se e adequado para upload temporario de arquivos sensiveis;
  - Oracle Cloud Always Free VM: mais flexivel, porem exige administracao de VM
    e disponibilidade de capacidade Always Free.
- [ ] Validar se a hospedagem escolhida suporta FastAPI/Uvicorn, escrita
  temporaria em disco, limite de upload compativel e timeout suficiente.
- [ ] Configurar publicacao do front-end estatico:
  - GitHub Pages como plataforma definida para o MVP;
  - publicar a partir de branch/pasta definida no repositorio;
  - garantir que a URL da API do Render seja configuravel no JavaScript.
- [ ] Configurar publicacao do backend no Render:
  - comando de start com Uvicorn;
  - variaveis de ambiente dos limites operacionais;
  - `SSIS_INVENTORY_WORK_DIR` apontando para diretorio temporario permitido;
  - HTTPS fornecido pela plataforma;
  - health check simples.
- [ ] Configurar variaveis de ambiente e limites de seguranca.
- [ ] Garantir que a pagina publicada chama a API correta.
- [ ] Adicionar link publico ao README.
- [ ] Validar a pagina publicada em PT-BR, EN e ES.
- [ ] Abrir PR vinculando a issue #1.

## Marcos sugeridos

1. MVP web com backend local:
   - interface com seletor PT-BR/EN/ES;
   - upload de `.zip`;
   - parametros de execucao;
   - backend Python executando a rotina atual;
   - download de Excel/JSON;
   - limpeza temporaria local.

2. MVP publicado gratuitamente:
   - front-end publicado;
   - backend publicado em ambiente gratuito;
   - politica de retencao documentada;
   - limites operacionais visiveis na interface.

3. Relatorios internacionalizados:
   - Excel/JSON com idioma configuravel;
   - testes cobrindo PT-BR, EN e ES;
   - documentacao de compatibilidade.

4. Fallback documental:
   - caso hospedagem gratuita com backend nao seja viavel no curto prazo,
     manter pagina estatica com instrucoes localizadas e uso CLI.

## Riscos e cuidados

- GitHub Pages nao executa backend Python; se for usado, sera apenas para o
  front-end.
- Processar arquivos em backend gratuito pode criar risco de privacidade,
  timeout, limite de disco, limite de upload e indisponibilidade.
- Arquivos SSIS podem conter connection strings, nomes de servidores, usuarios e
  outras informacoes sensiveis; logs e armazenamento temporario devem ser
  tratados com cuidado.
- O upload de `.zip` exige protecao contra path traversal e arquivos maliciosos.
- Traduzir nomes de colunas pode quebrar usuarios que ja consomem o Excel/JSON
  como contrato.
- O README e o `index.html` atuais tem sinais de encoding quebrado; corrigir isso
  deve entrar antes de ampliar textos em tres idiomas.
- A primeira entrega deve preservar o CLI e isolar o backend web como novo
  adaptador, sem espalhar regras de HTTP pelo parser atual.

## Definicao de pronto

- A branch contem uma aplicacao web utilizavel ou prototipo navegavel.
- A experiencia suporta PT-BR, EN e ES.
- A interface permite upload de um `.zip` contendo o projeto SSIS.
- O backend processa os arquivos em armazenamento temporario.
- Os relatorios Excel/JSON ficam disponiveis para download.
- Os arquivos temporarios sao apagados conforme politica definida.
- O fluxo CLI existente continua funcional.
- A documentacao explica como usar a solucao pela web e pela CLI.
- A estrategia de hospedagem gratuita esta definida e documentada.
- Testes ou validacoes manuais foram executados e registrados.
