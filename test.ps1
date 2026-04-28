<#
.SYNOPSIS
    Executa os testes automatizados do ssis-inventory.

.USAGE
    .\test.ps1
#>

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "ERRO: ambiente .venv não encontrado. Execute .\setup.ps1 primeiro." -ForegroundColor Red
    exit 1
}

& ".\.venv\Scripts\Activate.ps1"

pytest
