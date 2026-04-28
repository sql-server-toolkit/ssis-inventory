<#
.SYNOPSIS
    Executa o inventário SSIS.

.USAGE
    .\run_inventory.ps1 -ProjectFolder "C:\caminho\projeto_ssis" -OutputFolder ".\output"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectFolder,

    [Parameter(Mandatory=$false)]
    [string]$OutputFolder = ".\output"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "ERRO: ambiente .venv não encontrado. Execute .\setup.ps1 primeiro." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ProjectFolder)) {
    Write-Host "ERRO: ProjectFolder não encontrado: $ProjectFolder" -ForegroundColor Red
    exit 1
}

& ".\.venv\Scripts\Activate.ps1"

python -m app.main --project-folder "$ProjectFolder" --output-folder "$OutputFolder"
