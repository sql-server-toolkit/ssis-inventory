<#
.SYNOPSIS
    Prepara o ambiente local do projeto ssis-inventory.

.DESCRIPTION
    Este script cria o ambiente virtual, atualiza o pip e instala as dependências
    declaradas no requirements.txt.

.USAGE
    No PowerShell, a partir da raiz do repositório:

    .\setup.ps1

    Se a execução de scripts estiver bloqueada:
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "== ssis-inventory :: setup ==" -ForegroundColor Cyan

if (-not (Test-Path "requirements.txt")) {
    Write-Host "ERRO: requirements.txt não encontrado na raiz do projeto." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual .venv..."
    python -m venv .venv
} else {
    Write-Host "Ambiente virtual .venv já existe."
}

Write-Host "Ativando ambiente virtual..."
& ".\.venv\Scripts\Activate.ps1"

Write-Host "Atualizando pip..."
python -m pip install --upgrade pip

Write-Host "Instalando dependências..."
python -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup concluído com sucesso." -ForegroundColor Green
Write-Host "Para ativar manualmente: .\.venv\Scripts\Activate.ps1"
