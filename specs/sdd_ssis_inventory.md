# SDD — SSIS Inventory

## 1. 📌 Problem Statement
Projetos SSIS costumam distribuir dependências de banco de dados entre vários arquivos, tarefas e componentes. Isso dificulta a movimentação segura entre ambientes e aumenta o esforço manual de validação.

## 2. 🎯 Objetivos
- Ler um projeto SSIS a partir de uma pasta raiz.
- Identificar conexões em nível de projeto e pacote.
- Mapear componentes que usam essas conexões.
- Extrair SQL e inferir objetos de banco.
- Gerar relatório para apoiar DEV/HOM/PRD.

## 3. 📋 Requisitos
### Funcionais
- Ler `.dtproj`, `.dtsx` e `.conmgr`.
- Extrair connection managers.
- Extrair SQL conhecido.
- Inferir tabelas, views e procedures.
- Exportar resultado em Excel e JSON.

### Não funcionais
- Python 3.10+
- Execução por CLI
- Arquitetura modular
- Logs e warnings rastreáveis

## 4. 🧱 Arquitetura Proposta
### Componentes
- Discovery
- Project parser
- Connection parser
- Package parser
- Component parser
- SQL extractor
- Report generator

### Tecnologias
- Python
- lxml
- pandas
- openpyxl/xlsxwriter
- pytest

### Fluxo de dados
1. Descobrir arquivos
2. Ler projeto
3. Ler conexões
4. Ler pacotes
5. Extrair SQL/objetos
6. Consolidar
7. Exportar

## 5. 📁 Estrutura de Projeto (GitHub)
Ver `README.md`.

## 6. 📝 Especificação (Spec)
### project_discovery
Localiza os arquivos SSIS relevantes.

### ssis_project_parser
Lê `.dtproj` e identifica pacotes e artefatos compartilhados.

### ssis_connection_parser
Extrai atributos das conexões.

### ssis_package_parser
Lê `.dtsx`, coleta conexões locais e componentes.

### ssis_component_parser
Localiza SQL e vínculo com conexões.

### sql_object_extractor
Usa regex/heurística para inferir objetos.

### report_generator
Gera Excel e JSON.

## 7. 🔨 Task Breakdown
1. Criar estrutura do projeto.
2. Implementar dataclasses.
3. Implementar discovery.
4. Implementar parser de projeto.
5. Implementar parser de conexão.
6. Implementar parser de pacote.
7. Implementar extração de objetos.
8. Implementar exportação.
9. Criar testes.
10. Configurar CI.

## 8. 💻 Código Inicial
Disponibilizado na pasta `app/`.

## 9. 🧪 Testes
Disponibilizados na pasta `tests/`.

## 10. 🚀 CI/CD
Workflow GitHub Actions em `.github/workflows/ci.yml`.
