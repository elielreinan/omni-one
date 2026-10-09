"""Abre a janela do OmniOne (interface React servida pelo pywebview)."""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import webview

from .api import Api
from .core import acquire_single_instance


def _frontend_entry() -> str:
    """Localiza a interface: servidor de desenvolvimento, executável ou build local."""
    dev_url = os.environ.get("OMNIONE_DEV_URL")
    if dev_url:
        return dev_url
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS")) / "web"
    else:
        base = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    index = base / "index.html"
    if not index.exists():
        raise SystemExit(
            f"Interface não encontrada em {index}. Rode 'npm install && npm run build' em frontend/."
        )
    return str(index)


def _already_open_message() -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, "O OmniOne já está aberto.", "OmniOne", 0x40)
    else:
        print("O OmniOne já está aberto.")


def main() -> None:
    if not acquire_single_instance():
        _already_open_message()
        return
    webview.create_window(
        "OmniOne",
        _frontend_entry(),
        js_api=Api(),
        width=420,
        height=680,
        min_size=(380, 600),
        background_color="#0b0d12",
    )
    # http_server serve o build local por HTTP (módulos ES não carregam via file://).
    webview.start(http_server=True)
