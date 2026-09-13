#!/usr/bin/env python3
from __future__ import annotations
"""Controlador compacto do OmniOne para o OmniRoute e o Claude Code."""

import os
import ctypes
import re
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import requests
from pathlib import Path
from typing import Optional, Tuple

# ─── Configuração ───
OMNIROUTE_VERSION = "3.8.50"
HEALTH_URL = "http://localhost:20128/api/monitoring/health"

# Usuários podem definir OMNIONE_WORKSPACE_ROOT para qualquer pasta com seus projetos.
# O padrão mantém o app portátil entre contas do Windows.
WORKSPACE_ROOT = Path(
    os.environ.get("OMNIONE_WORKSPACE_ROOT", str(Path.home() / "Workspace"))
).expanduser()
OMNIROUTE_DIR = Path.home() / ".omniroute"
OMNIROUTE_LOGS = OMNIROUTE_DIR / "logs"
# Scripts gerados pelo app ficam fora da pasta de logs.
OMNIROUTE_LAUNCHERS = OMNIROUTE_DIR / "launchers"
OMNIROUTE_PID_FILE = OMNIROUTE_DIR / "server" / ".pid"
OMNIROUTE_CACHE = OMNIROUTE_DIR / ".omnione-cli-path"
DEBUG_LOG = OMNIROUTE_LOGS / "omnione-debug.log"

# Caracteres com significado especial para o cmd.exe; caminhos do CLI não devem contê-los.
_UNSAFE_CMD_CHARS = re.compile(r'[&|^<>%"!]')

# Caminho do CLI em cache
_cached_cli_path: Optional[str] = None


def _debug_log(message: str) -> None:
    """Registra tentativas de resolução do CLI quando OMNIONE_DEBUG=1."""
    if os.environ.get("OMNIONE_DEBUG") != "1":
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def _cli_is_safe(value: str) -> bool:
    """Rejeita metacaracteres do cmd.exe em caminhos vindos de configuração."""
    return not _UNSAFE_CMD_CHARS.search(value or "")


def acquire_single_instance() -> bool:
    """Evita controladores OmniOne duplicados em execução no Windows."""
    if os.name != "nt":
        return True
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\OmniOneTrayController")
    if not mutex:
        return True
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


# ─── Funções utilitárias ───

def get_omniroute_cmd() -> str:
    """Resolve o comando omniroute (mesma lógica dos arquivos batch)."""
    global _cached_cli_path

    # 1. Prefere o shim npm omniroute.cmd porque o app inicia via cmd.exe.
    try:
        result = subprocess.run(["where", "omniroute.cmd"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return "omniroute.cmd"
    except Exception as e:
        _debug_log(f"where omniroute.cmd: {e}")

    # 2. Verifica se 'omniroute' está no PATH
    try:
        result = subprocess.run(["where", "omniroute"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            _cached_cli_path = "omniroute"
            return "omniroute"
    except Exception as e:
        _debug_log(f"where omniroute: {e}")

    # 3. Verifica o caminho em cache
    if OMNIROUTE_CACHE.exists():
        try:
            cached = OMNIROUTE_CACHE.read_text(encoding="utf-8").strip()
            if cached and Path(cached).exists() and _cli_is_safe(cached):
                _cached_cli_path = cached
                return f'node "{cached}"'
        except Exception as e:
            _debug_log(f"cache CLI: {e}")

    # 4. Procura no cache do npm
    try:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        matches = list(Path(localappdata).glob("npm-cache/_npx/*/node_modules/omniroute/bin/omniroute.mjs"))
        for match in matches:
            if not _cli_is_safe(str(match)):
                continue
            _cached_cli_path = str(match)
            OMNIROUTE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            OMNIROUTE_CACHE.write_text(_cached_cli_path, encoding="utf-8")
            return f'node "{_cached_cli_path}"'
    except Exception as e:
        _debug_log(f"cache npm: {e}")

    # 5. Recorre ao npx
    _debug_log("nenhum CLI encontrado; usando fallback npx")
    return f"npx --yes -p omniroute@{OMNIROUTE_VERSION} omniroute"


def run_cmd(cmd: str, cwd: Optional[Path] = None, timeout: int = 30) -> Tuple[int, str, str]:
    """Executa um comando e retorna (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def check_server_health() -> bool:
    """Verifica se o servidor OmniRoute está respondendo."""
    try:
        resp = requests.get(HEALTH_URL, timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def get_server_pid() -> Optional[int]:
    """Obtém o PID do servidor a partir do arquivo .pid do OmniRoute."""
    if OMNIROUTE_PID_FILE.exists():
        try:
            return int(OMNIROUTE_PID_FILE.read_text().strip())
        except Exception:
            pass
    return None


def start_server() -> Tuple[bool, str]:
    """Inicia o servidor OmniRoute em modo daemon."""
    OMNIROUTE_LOGS.mkdir(parents=True, exist_ok=True)
    log_file = OMNIROUTE_LOGS / "serve-launch.log"

    cmd = get_omniroute_cmd()
    full_cmd = f'{cmd} serve --daemon > "{log_file}" 2>&1'

    # Executa em segundo plano
    try:
        subprocess.Popen(
            ["cmd.exe", "/d", "/c", full_cmd],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as e:
        return False, f"Falha ao iniciar o processo: {e}"

    # Aguarda o servidor ficar saudável
    for _ in range(60):  # até 120 segundos
        time.sleep(2)
        if check_server_health():
            return True, "Servidor iniciado com sucesso"

    return False, "Servidor não respondeu no tempo esperado. Consulte os logs em: " + str(log_file)


def stop_server() -> Tuple[bool, str]:
    """Interrompe o servidor OmniRoute, tratando daemon e supervisor em primeiro plano."""
    cmd = get_omniroute_cmd()

    # 1. Parada graciosa via comando 'stop' do OmniRoute
    code, out, err = run_cmd(f"{cmd} stop", timeout=15)

    # Aguarda um instante para o servidor liberar a porta
    time.sleep(2)

    # 2. Servidor realmente parou?
    if not check_server_health():
        return True, "Servidor interrompido com sucesso"

    # 3a. Servidor voltou — provavelmente um supervisor em primeiro plano.
    #     Tenta primeiro encerrar pelo PID registrado no arquivo .pid.
    pid = get_server_pid()
    if pid:
        run_cmd(f"taskkill /PID {pid} /T /F", timeout=15)
        time.sleep(2)
        if not check_server_health():
            return True, "Servidor interrompido (PID registrado encerrado)"

    # 3b. Fallback: encerra apenas processos node/omniroute cujo comando contenha 'serve'.
    try:
        ps_cmd = (
            'powershell -NoProfile -Command '
            '"$servers = @(Get-CimInstance Win32_Process | Where-Object { '
            '($_.Name -eq \'node.exe\' -or $_.Name -like \'omniroute*.exe\') -and '
            '$_.CommandLine -and $_.CommandLine -match \'omniroute\' -and $_.CommandLine -match \'\\bserve\\b\' }); '
            'if ($servers.Count -eq 0) { exit 1 }; '
            'foreach ($p in $servers) { '
            'Write-Host (\'[..] Encerrando PID \' + $p.ProcessId + \' (\' + $p.Name + \')\'); '
            'taskkill /PID $p.ProcessId /T /F 2>&1 | Out-Null }; exit 0"'
        )
        code, out, err = run_cmd(ps_cmd, timeout=15)
        time.sleep(2)

        if not check_server_health():
            return True, "Servidor interrompido (árvore do supervisor encerrada)"
    except Exception as e:
        return False, f"Erro ao interromper o supervisor: {e}"

    return False, "Servidor ainda respondendo após as tentativas de encerramento"


def launch_claude_code(workspace: Path) -> bool:
    """Abre o Claude Code conectado ao OmniRoute em um terminal visível."""
    try:
        workspace = workspace.resolve(strict=True)
    except (OSError, RuntimeError):
        print(f"Workspace inválido ou inexistente: {workspace}")
        return False
    if not workspace.is_dir():
        print(f"Workspace não é uma pasta: {workspace}")
        return False

    cmd = get_omniroute_cmd()
    full_cmd = f'{cmd} launch -- --model auto/best-free'
    launcher = OMNIROUTE_LAUNCHERS / "omnione-launch-claude.cmd"

    try:
        OMNIROUTE_LAUNCHERS.mkdir(parents=True, exist_ok=True)
        launcher.write_text(
            "@echo off\n"
            "title OmniOne - Claude Code\n"
            "echo [OmniOne] Abrindo Claude Code...\n"
            f"call {full_cmd}\n"
            "echo.\n"
            "echo [OmniOne] Claude Code foi encerrado. Codigo: %errorlevel%\n"
            "pause\n",
            encoding="utf-8",
        )
        subprocess.Popen(
            ["cmd.exe", "/d", "/k", str(launcher)],
            cwd=str(workspace),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True
    except Exception as e:
        print(f"Falha ao abrir o Claude Code: {e}")
        return False


def get_workspaces() -> list:
    """Lista as pastas de workspace disponíveis."""
    if not WORKSPACE_ROOT.exists():
        return []
    try:
        return sorted((d for d in WORKSPACE_ROOT.iterdir() if d.is_dir()), key=lambda d: d.name.lower())
    except OSError:
        return []


class OmniOneWindowApp:
    """Janela compacta de controle que abre sem esperar o servidor."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OmniOne")
        self.root.geometry("360x460")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.server_status = "unknown"
        self.running = False
        self.status_label = None
        self.status_detail = None
        self.start_button = None
        self.stop_button = None
        self.workspace_box = None
        self.action_buttons = []
        self._build_window()

    # ─── Agendamento seguro da GUI ───

    def _safe_after(self, ms: int, func, *args):
        """Agenda um callback na thread principal, tolerando o fechamento da janela."""
        self.root.after(ms, self._safe_apply, func, *args)

    def _safe_apply(self, func, *args):
        """Aplica o callback, ignorando erros quando a janela já foi destruída."""
        try:
            func(*args)
        except tk.TclError:
            pass  # A janela foi fechada antes do callback executar

    def _build_window(self):
        self.root.configure(padx=18, pady=16)
        ttk.Label(self.root, text="OmniOne", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(self.root, text="Controle do OmniRoute e Claude Code", foreground="#666666").pack(anchor="w", pady=(0, 16))

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", pady=(0, 14))
        self.status_label = tk.Label(status_frame, text="●  Verificando...", font=("Segoe UI", 12, "bold"), anchor="w")
        self.status_label.pack(fill="x")
        self.status_detail = tk.Label(status_frame, text="A janela está pronta; a verificação ocorre em segundo plano.", fg="#666666", anchor="w", justify="left", wraplength=320)
        self.status_detail.pack(fill="x", pady=(4, 0))

        controls = ttk.Frame(self.root)
        controls.pack(fill="x")
        self.start_button = ttk.Button(controls, text="Iniciar / Reiniciar", command=self.on_start_server)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.stop_button = ttk.Button(controls, text="Parar", command=self.on_stop_server)
        self.stop_button.pack(side="left", fill="x", expand=True)

        ttk.Separator(self.root).pack(fill="x", pady=16)
        ttk.Label(self.root, text="Workspace", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.workspace_box = ttk.Combobox(self.root, state="readonly")
        self.workspace_box.pack(fill="x", pady=(6, 8))
        claude_button = ttk.Button(self.root, text="Abrir Claude Code", command=self.on_launch_selected_workspace)
        claude_button.pack(fill="x")
        self.action_buttons.append(claude_button)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", pady=(16, 0))
        logs_button = ttk.Button(bottom, text="Abrir logs", command=self.on_view_logs)
        logs_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        dashboard_button = ttk.Button(bottom, text="Dashboard", command=self.on_open_dashboard)
        dashboard_button.pack(side="left", fill="x", expand=True)
        self.action_buttons.extend([logs_button, dashboard_button])

        # Rodapé com a assinatura do projeto
        self.footer_link = tk.Label(self.root, text="Prod por 2E · https://e2dev.me/", fg="#0067c0", cursor="hand2", anchor="w")
        self.footer_link.pack(fill="x", pady=(14, 0))
        self.footer_link.bind("<Button-1>", lambda e: self._open_site())

        self.refresh_workspaces()

    def _open_site(self):
        """Abre o site do projeto no navegador padrão."""
        import webbrowser
        webbrowser.open("https://e2dev.me/")

    def refresh_workspaces(self):
        workspaces = get_workspaces()
        names = [workspace.name for workspace in workspaces]
        self.workspace_box["values"] = names
        if names:
            self.workspace_box.current(0)
        else:
            self.workspace_box.set("Nenhum workspace encontrado")

    def set_status(self, status: str):
        self.server_status = status
        labels = {
            "running": ("●  OmniRoute ativo", "#16803c"),
            "stopped": ("●  OmniRoute parado", "#b42318"),
            "starting": ("●  Iniciando OmniRoute...", "#b54708"),
            "stopping": ("●  Parando OmniRoute...", "#b54708"),
            "unknown": ("●  Verificando...", "#666666"),
        }
        label, color = labels.get(status, labels["unknown"])
        self.status_label.configure(text=label, fg=color)
        self.start_button.configure(state="disabled" if status in ("starting", "stopping") else "normal")
        self.stop_button.configure(state="normal" if status == "running" else "disabled")
        for button in self.action_buttons:
            button.configure(state="normal" if status == "running" else "disabled")

    def set_detail(self, message: str):
        self.status_detail.configure(text=message)

    def check_status_loop(self):
        if not self.running:
            return
        if self.server_status not in ("starting", "stopping"):
            def check_in_background():
                healthy = check_server_health()
                self._safe_after(0, self.set_status, "running" if healthy else "stopped")

            threading.Thread(target=check_in_background, daemon=True).start()
        self._safe_after(5000, self.check_status_loop)

    def on_start_server(self):
        if self.server_status in ("starting", "stopping"):
            return
        was_running = self.server_status == "running"
        self.set_status("starting")
        self.set_detail("Aguarde. O primeiro início pode levar mais tempo se o OmniRoute ainda não estiver no cache.")

        def do_start():
            if was_running:
                stopped, stop_message = stop_server()
                success, message = (start_server() if stopped else (False, stop_message))
            else:
                success, message = start_server()
            self._safe_after(0, self.set_status, "running" if success else "stopped")
            self._safe_after(0, self.set_detail, message)

        threading.Thread(target=do_start, daemon=True).start()

    def on_stop_server(self):
        self.set_status("stopping")
        self.set_detail("Encerrando o servidor...")

        def do_stop():
            success, message = stop_server()
            self._safe_after(0, self.set_status, "stopped" if success else "running")
            self._safe_after(0, self.set_detail, message)

        threading.Thread(target=do_stop, daemon=True).start()

    def on_launch_selected_workspace(self):
        names = list(self.workspace_box["values"])
        index = self.workspace_box.current()
        if index < 0 or index >= len(names):
            self.set_detail("Selecione um workspace válido.")
            return
        self.on_launch_claude(WORKSPACE_ROOT / names[index])

    def on_launch_claude(self, workspace: Path):
        if self.server_status != "running":
            self.set_detail("O servidor precisa estar ativo para abrir o Claude Code.")
            return

        def do_launch():
            success = launch_claude_code(workspace)
            message = f"Claude Code aberto em {workspace.name}." if success else "Não foi possível abrir o Claude Code."
            self._safe_after(0, self.set_detail, message)

        threading.Thread(target=do_launch, daemon=True).start()

    def on_view_logs(self):
        log_file = OMNIROUTE_LOGS / "serve-launch.log"
        if log_file.exists():
            try:
                os.startfile(str(log_file))
            except Exception:
                subprocess.Popen(["notepad.exe", str(log_file)])
        else:
            self.set_detail("Nenhum arquivo de log encontrado.")

    def on_open_dashboard(self):
        try:
            subprocess.Popen(f"{get_omniroute_cmd()} dashboard", shell=True)
        except Exception:
            import webbrowser
            webbrowser.open("http://localhost:20128")

    def on_exit(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.running = True
        self._safe_after(100, self.check_status_loop)
        self.root.mainloop()


def main():
    if not acquire_single_instance():
        messagebox.showinfo("OmniOne", "O OmniOne já está aberto.")
        return
    app = OmniOneWindowApp()
    app.run()


if __name__ == "__main__":
    main()