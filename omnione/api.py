"""API que a interface React chama via ``window.pywebview.api``.

Cada método público desta classe vira uma função assíncrona no JavaScript.
O pywebview executa cada chamada numa thread própria, então o estado é
protegido por um lock e as operações longas (iniciar/parar) rodam em segundo
plano enquanto a interface consulta ``get_state``.
"""
from __future__ import annotations

import os
import subprocess
import threading
import webbrowser
from typing import Any, Dict

from . import core

SITE_URL = "https://e2dev.me/"

# Estados em que uma operação está em andamento e a verificação periódica pausa.
_BUSY = ("starting", "stopping")


class Api:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = "unknown"
        self._detail = "Verificando o servidor em segundo plano..."

    # ─── Estado ───

    def _set(self, status: str | None = None, detail: str | None = None) -> None:
        with self._lock:
            if status is not None:
                self._status = status
            if detail is not None:
                self._detail = detail

    def _snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"status": self._status, "detail": self._detail}

    def get_state(self) -> Dict[str, Any]:
        """Retorna o status atual, verificando a saúde quando nada está em andamento."""
        with self._lock:
            busy = self._status in _BUSY
        if not busy:
            healthy = core.check_server_health()
            with self._lock:
                if self._status == "unknown":
                    self._detail = (
                        "Servidor respondendo normalmente." if healthy else
                        "O servidor está parado. Clique em Iniciar para começar."
                    )
                if self._status not in _BUSY:
                    self._status = "running" if healthy else "stopped"
        return self._snapshot()

    def get_info(self) -> Dict[str, Any]:
        return {
            "omnirouteVersion": core.OMNIROUTE_VERSION,
            "healthUrl": core.get_health_url(),
            "workspaceRoot": str(core.WORKSPACE_ROOT),
        }

    # ─── Servidor ───

    def start(self) -> Dict[str, Any]:
        """Inicia o servidor, ou reinicia se ele já estiver ativo."""
        with self._lock:
            if self._status in _BUSY:
                return {"status": self._status, "detail": self._detail}
            was_running = self._status == "running"
            self._status = "starting"
            self._detail = (
                "Reiniciando o servidor..." if was_running else
                "Aguarde. O primeiro início pode levar mais tempo se o OmniRoute ainda não estiver no cache."
            )

        def run() -> None:
            if was_running:
                stopped, message = core.stop_server()
                success, message = core.start_server() if stopped else (False, message)
            else:
                success, message = core.start_server()
            self._set("running" if success else "stopped", message)

        threading.Thread(target=run, daemon=True).start()
        return self._snapshot()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._status in _BUSY:
                return {"status": self._status, "detail": self._detail}
            self._status = "stopping"
            self._detail = "Encerrando o servidor..."

        def run() -> None:
            success, message = core.stop_server()
            self._set("stopped" if success else "running", message)

        threading.Thread(target=run, daemon=True).start()
        return self._snapshot()

    # ─── Workspaces e Claude Code ───

    def list_workspaces(self) -> list:
        return [w.name for w in core.get_workspaces()]

    def launch_claude(self, name: str) -> Dict[str, Any]:
        # Só aceita nomes que existem na listagem, evitando caminhos arbitrários.
        workspaces = {w.name: w for w in core.get_workspaces()}
        workspace = workspaces.get(name)
        if workspace is None:
            return {"ok": False, "message": "Selecione um workspace válido."}
        if not core.check_server_health():
            return {"ok": False, "message": "O servidor precisa estar ativo para abrir o Claude Code."}
        if core.launch_claude_code(workspace):
            return {"ok": True, "message": f"Claude Code aberto em {workspace.name}."}
        return {"ok": False, "message": "Não foi possível abrir o Claude Code."}

    # ─── Atalhos ───

    def open_logs(self) -> Dict[str, Any]:
        # No modo daemon o servidor escreve em logs/application/app.log; o
        # serve-launch.log só guarda a saída do comando de início.
        log_file = next((f for f in (core.get_omniroute_log_file(), core.SERVE_LOG) if f.exists()), None)
        if log_file is None:
            return {"ok": False, "message": "Nenhum arquivo de log encontrado."}
        try:
            os.startfile(str(log_file))  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["notepad.exe", str(log_file)])
        return {"ok": True, "message": "Logs abertos."}

    def open_dashboard(self) -> Dict[str, Any]:
        # Abre direto no navegador: `omniroute dashboard` carrega o CLI inteiro
        # e abriria uma janela de console só para isso.
        webbrowser.open(core.get_dashboard_url())
        return {"ok": True, "message": "Abrindo o dashboard..."}

    def open_site(self) -> None:
        webbrowser.open(SITE_URL)
