<#
.SYNOPSIS
Instala a versão atual do OmniOne e remove atalhos antigos.

.DESCRIPTION
Este script:
1. Copia o OmniOne para um local permanente
2. Remove atalhos antigos da Área de Trabalho
3. Cria um atalho na pasta de Inicialização (auto-start)
4. Cria um atalho na Área de Trabalho
5. Opcionalmente inicia a janela compacta imediatamente
#>

param(
    [switch]$AutoStart = $true,
    [switch]$StartNow = $true
)

$ErrorActionPreference = "Stop"

Write-Host "=== Instalador OmniOne ===" -ForegroundColor Cyan
Write-Host ""

# Paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$exeSource = Join-Path $scriptDir "dist\OmniOne Tray.exe"
$installDir = Join-Path $env:LOCALAPPDATA "OmniOneTray"
$exeTarget = Join-Path $installDir "OmniOne Tray.exe"
$desktop = [Environment]::GetFolderPath("Desktop")
$startup = [Environment]::GetFolderPath("Startup")

# 1. Verify source exists
if (-not (Test-Path $exeSource)) {
    Write-Error "Source executable not found at: $exeSource"
    Write-Host "Crie o executável primeiro: python -m PyInstaller omnione_tray.spec --clean" -ForegroundColor Red
    exit 1
}

# 2. Create install directory
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Write-Host "[OK] Created install directory: $installDir" -ForegroundColor Green
}

# 3. Close an older OmniOne instance so the executable can be updated safely.
$runningApps = Get-Process -Name "OmniOne Tray" -ErrorAction SilentlyContinue
if ($runningApps) {
    Write-Host "[OK] Encerrando a versão anterior do OmniOne..." -ForegroundColor Yellow
    $runningApps | Stop-Process -Force
    Start-Sleep -Seconds 1
}

# 1. Copia o executável
Copy-Item -Path $exeSource -Destination $exeTarget -Force
Write-Host "[OK] Copied executable to: $exeTarget" -ForegroundColor Green

# 2. Remove atalhos antigos da Área de Trabalho
$oldShortcuts = @(
    "Claude Code + OmniRoute.lnk",
    "Parar OmniRoute.lnk",
    "Status OmniRoute.lnk",
    "OmniRoute Tray.lnk"
)

foreach ($shortcut in $oldShortcuts) {
    $path = Join-Path $desktop $shortcut
    if (Test-Path $path) {
        Remove-Item -Path $path -Force
        Write-Host "[OK] Removed old shortcut: $shortcut" -ForegroundColor Yellow
    }
}

# 3. Cria o atalho na Área de Trabalho
$shortcutPath = Join-Path $desktop "OmniOne.lnk"
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($shortcutPath)
$sc.TargetPath = $exeTarget
$sc.WorkingDirectory = $installDir
$sc.Description = "Controlador OmniOne - gerencia o servidor e abre o Claude Code"
$sc.IconLocation = "$exeTarget,0"
$sc.Save()
Write-Host "[OK] Created Desktop shortcut: $shortcutPath" -ForegroundColor Green

# 4. Cria o atalho de Inicialização (auto-start com o Windows)
if ($AutoStart) {
    $startupShortcut = Join-Path $startup "OmniOne.lnk"
    $sc2 = $wsh.CreateShortcut($startupShortcut)
    $sc2.TargetPath = $exeTarget
    $sc2.WorkingDirectory = $installDir
    $sc2.Description = "Controlador OmniOne (inicialização automática)"
    $sc2.IconLocation = "$exeTarget,0"
    $sc2.Save()
    Write-Host "[OK] Created Startup shortcut for auto-start" -ForegroundColor Green
}

# 5. Inicia o app agora
if ($StartNow) {
    Write-Host ""
    Write-Host "Iniciando OmniOne..." -ForegroundColor Cyan
    Start-Process -FilePath $exeTarget -WorkingDirectory $installDir
    Write-Host "[OK] OmniOne iniciado - a janela compacta está pronta" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Instalação concluída ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "O OmniOne foi instalado em:"
Write-Host "  $exeTarget"
Write-Host ""
Write-Host "Recursos:"
Write-Host "  - Janela compacta de controle (abre imediatamente)"
Write-Host "  - Iniciar, parar e reiniciar o servidor OmniOne"
Write-Host "  - Abre o Claude Code em qualquer workspace"
Write-Host "  - Abre logs e dashboard"
Write-Host "  - Inicia automaticamente com o Windows"
Write-Host ""
Write-Host "Atalhos antigos foram removidos da Área de Trabalho."
Write-Host ""
Write-Host "Prod por 2E · https://e2dev.me/" -ForegroundColor Cyan
Write-Host ""
