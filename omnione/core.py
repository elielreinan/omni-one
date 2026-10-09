"""Lógica do OmniOne: controla o servidor OmniRoute e abre o Claude Code.

Este módulo não depende de interface gráfica; a janela (React) chama estas
funções através de ``omnione.api``.
"""
from __future__ import annotations

import os
import ctypes
import json
import re
import subprocess
import time
import requests
from pathlib import Path
from typing import List, Optional, Tuple

# ─── Configuração ───
# Versão do OmniRoute validada com o OmniOne (usada no fallback via npx).
OMNIROUTE_VERSION = "3.8.51"
DEFAULT_PORT = 20128
HEALTH_PATH = "/api/monitoring/health"

# Faixas de Node.js aceitas pelo OmniRoute 3.8.51 (package.json "engines" e
# bin/nodeRuntimeSupport.mjs): 22.22.2+ na linha 22, e 24.x, 25.x e 26.x.
# Fora disso o CLI encerra imediatamente com erro.
NODE_SECURE_FLOORS = {22: (22, 22, 2), 24: (24, 0, 0), 25: (25, 0, 0), 26: (26, 0, 0)}
NODE_RECOMMENDED = "24 LTS"

# Usuários podem definir OMNIONE_WORKSPACE_ROOT para qualquer pasta com seus projetos.
# O padrão mantém o app portátil entre contas do Windows.
WORKSPACE_ROOT = Path(
    os.environ.get("OMNIONE_WORKSPACE_ROOT", str(Path.home() / "Workspace"))
).expanduser()

# Arquivos do próprio OmniOne ficam fora da pasta de dados do OmniRoute: criar
# ~/.omniroute por conta própria mudaria onde o OmniRoute guarda os dados dele.
OMNIONE_HOME = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".omnione")) / "OmniOne"
OMNIONE_LOGS = OMNIONE_HOME / "logs"
OMNIONE_LAUNCHERS = OMNIONE_HOME / "launchers"
OMNIONE_CLI_CACHE = OMNIONE_HOME / "cli-path.txt"
SERVE_LOG = OMNIONE_LOGS / "serve-launch.log"
DEBUG_LOG = OMNIONE_LOGS / "omnione-debug.log"

# Sem janela de console para os comandos auxiliares (o .exe roda sem console).
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Caracteres com significado especial para o cmd.exe; caminhos do CLI não devem contê-los.
_UNSAFE_CMD_CHARS = re.compile(r'[&|^<>%"!]')
_ANSI_ESCAPES = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Caminho do CLI em cache
_cached_cli_path: Optional[str] = None


def _debug_log(message: str) -> None:
    """Registra tentativas de resolução do CLI quando OMNIONE_DEBUG=1."""
    if os.environ.get("OMNIONE_DEBUG") != "1":
        return
    try:
        OMNIONE_LOGS.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def _cli_is_safe(value: str) -> bool:
    """Rejeita metacaracteres do cmd.exe em caminhos vindos de configuração."""
    return not _UNSAFE_CMD_CHARS.search(value or "")


def _parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    """Extrai (major, minor, patch) de textos como 'v24.1.0' ou '3.8.51'."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


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


# ─── Pasta de dados e porta do OmniRoute ───

def get_omniroute_data_dir() -> Path:
    """Resolve a pasta de dados como o OmniRoute faz (bin/cli/data-dir.mjs).

    Ordem: DATA_DIR, ~/.omniroute (se existir), %APPDATA%\\omniroute no Windows.
    Calculada a cada chamada porque a pasta pode surgir no primeiro início.
    """
    configured = os.environ.get("DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    legacy = Path.home() / ".omniroute"
    if legacy.is_dir():
        return legacy
    if os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "omniroute"
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / "omniroute"
    return legacy


def _read_env_value(env_file: Path, key: str) -> Optional[str]:
    """Lê KEY=valor de um arquivo .env simples (mesmo formato aceito pelo OmniRoute)."""
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def get_omniroute_port() -> int:
    """Porta do OmniRoute: PORT do ambiente, depois PORT do .env da pasta de dados."""
    candidates = [os.environ.get("PORT"), _read_env_value(get_omniroute_data_dir() / ".env", "PORT")]
    for value in candidates:
        try:
            port = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if 0 < port <= 65535:
            return port
    return DEFAULT_PORT


def get_health_url() -> str:
    # 127.0.0.1 em vez de localhost: o servidor escuta em 0.0.0.0 (IPv4) e, no
    # Windows, "localhost" tenta ::1 primeiro, o que pode estourar o timeout curto.
    return f"http://127.0.0.1:{get_omniroute_port()}{HEALTH_PATH}"


def get_dashboard_url() -> str:
    return f"http://localhost:{get_omniroute_port()}"


def get_omniroute_log_file() -> Path:
    """Log do servidor (logs/application/app.log na pasta de dados, ou APP_LOG_FILE_PATH)."""
    configured = os.environ.get("APP_LOG_FILE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_omniroute_data_dir() / "logs" / "application" / "app.log"


# ─── Node.js e CLI do OmniRoute ───

def check_node_runtime() -> Tuple[bool, str]:
    """Confere se o Node.js instalado é aceito pelo OmniRoute antes de iniciar."""
    try:
        result = subprocess.run(
            ["node", "-v"], capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW
        )
    except FileNotFoundError:
        return False, f"Node.js não encontrado. Instale o Node.js {NODE_RECOMMENDED} em https://nodejs.org e abra o OmniOne de novo."
    except Exception as e:
        _debug_log(f"node -v: {e}")
        return True, ""  # Não bloqueia o início se a verificação em si falhar.

    version = _parse_version(result.stdout)
    if version is None:
        return True, ""
    floor = NODE_SECURE_FLOORS.get(version[0])
    if floor and version >= floor:
        return True, ""
    found = ".".join(str(part) for part in version)
    return False, (
        f"O OmniRoute não aceita o Node.js {found}. Instale o Node.js {NODE_RECOMMENDED} "
        "(ou 22.22.2+) em https://nodejs.org e tente de novo."
    )


def _package_version(cli_mjs: Path) -> Optional[str]:
    """Versão do pacote omniroute ao qual pertence bin/omniroute.mjs."""
    try:
        package_json = cli_mjs.parent.parent / "package.json"
        return json.loads(package_json.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def _is_supported_cli(cli_mjs: Path) -> bool:
    """Aceita apenas caches do npx na versão validada ou mais nova."""
    version = _parse_version(_package_version(cli_mjs) or "")
    return version is not None and version >= _parse_version(OMNIROUTE_VERSION)


def _where(command: str) -> bool:
    try:
        result = subprocess.run(
            ["where", command], capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception as e:
        _debug_log(f"where {command}: {e}")
        return False


def get_omniroute_cmd() -> str:
    """Resolve o comando omniroute (mesma lógica dos arquivos batch)."""
    global _cached_cli_path

    # 1. Prefere o shim npm omniroute.cmd porque o app inicia via cmd.exe.
    if _where("omniroute.cmd"):
        return "omniroute.cmd"

    # 2. Verifica se 'omniroute' está no PATH
    if _where("omniroute"):
        _cached_cli_path = "omniroute"
        return "omniroute"

    # 3. Verifica o caminho em cache (descartado se apontar para versão antiga)
    if OMNIONE_CLI_CACHE.exists():
        try:
            cached = OMNIONE_CLI_CACHE.read_text(encoding="utf-8").strip()
            if cached and Path(cached).exists() and _cli_is_safe(cached) and _is_supported_cli(Path(cached)):
                _cached_cli_path = cached
                return f'node "{cached}"'
        except Exception as e:
            _debug_log(f"cache CLI: {e}")

    # 4. Procura no cache do npx uma cópia na versão validada ou mais nova
    try:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        matches = list(Path(localappdata).glob("npm-cache/_npx/*/node_modules/omniroute/bin/omniroute.mjs"))
        for match in matches:
            if not _cli_is_safe(str(match)) or not _is_supported_cli(match):
                continue
            _cached_cli_path = str(match)
            OMNIONE_CLI_CACHE.parent.mkdir(parents=True, exist_ok=True)
            OMNIONE_CLI_CACHE.write_text(_cached_cli_path, encoding="utf-8")
            return f'node "{_cached_cli_path}"'
    except Exception as e:
        _debug_log(f"cache npm: {e}")

    # 5. Recorre ao npx
    _debug_log("nenhum CLI encontrado; usando fallback npx")
    return f"npx --yes -p omniroute@{OMNIROUTE_VERSION} omniroute"


def get_omniroute_version(cmd: str) -> Optional[Tuple[int, int, int]]:
    """Versão do CLI resolvido (`--version` é um atalho rápido no OmniRoute)."""
    code, out, _ = run_cmd(f"{cmd} --version", timeout=60)
    return _parse_version(out) if code == 0 else None


def run_cmd(cmd: str, cwd: Optional[Path] = None, timeout: int = 30) -> Tuple[int, str, str]:
    """Executa um comando e retorna (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def check_server_health() -> bool:
    """Verifica se o servidor OmniRoute está respondendo."""
    try:
        resp = requests.get(get_health_url(), timeout=3)
        return resp.ok
    except Exception:
        return False


def _read_pid(service: str) -> Optional[int]:
    """Lê <pasta de dados>/<serviço>/.pid, como o OmniRoute grava."""
    pid_file = get_omniroute_data_dir() / service / ".pid"
    try:
        return int(pid_file.read_text().strip())
    except Exception:
        return None


def get_server_pids() -> List[int]:
    """PIDs registrados do supervisor e do servidor (o supervisor primeiro)."""
    return [pid for pid in (_read_pid("supervisor"), _read_pid("server")) if pid]


def find_listening_pids(port: int) -> List[int]:
    """PIDs em LISTENING na porta, via netstat (mesma abordagem do `omniroute stop`)."""
    code, out, _ = run_cmd("netstat -ano", timeout=15)
    if code != 0:
        return []
    pids: List[int] = []
    for line in out.splitlines():
        cols = line.split()
        if len(cols) < 5 or cols[0] not in ("TCP", "TCPv6"):
            continue
        if not cols[1].endswith(f":{port}") or cols[-2].upper() != "LISTENING":
            continue
        try:
            pid = int(cols[-1])
        except ValueError:
            continue
        if pid > 0 and pid not in pids:
            pids.append(pid)
    return pids


def _tail_log(log_file: Path, lines: int = 4) -> str:
    try:
        text = _ANSI_ESCAPES.sub("", log_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""
    useful = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(useful[-lines:])


def start_server() -> Tuple[bool, str]:
    """Inicia o servidor OmniRoute em modo daemon."""
    node_ok, node_message = check_node_runtime()
    if not node_ok:
        return False, node_message

    OMNIONE_LOGS.mkdir(parents=True, exist_ok=True)

    cmd = get_omniroute_cmd()
    port = get_omniroute_port()
    full_cmd = f'{cmd} serve --daemon --port {port} > "{SERVE_LOG}" 2>&1'

    # Executa em segundo plano, sem janela de console
    try:
        process = subprocess.Popen(
            ["cmd.exe", "/d", "/c", full_cmd],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
    except Exception as e:
        return False, f"Falha ao iniciar o processo: {e}"

    # Aguarda o servidor ficar saudável
    for _ in range(60):  # até 120 segundos
        time.sleep(2)
        if check_server_health():
            message = "Servidor iniciado com sucesso"
            version = get_omniroute_version(cmd)
            if version and version < _parse_version(OMNIROUTE_VERSION):
                found = ".".join(str(part) for part in version)
                message += (
                    f". O OmniRoute instalado ({found}) é anterior ao {OMNIROUTE_VERSION}; "
                    "atualize com: npm install -g omniroute@latest"
                )
            return True, message
        # O OmniRoute sai com erro (porta ocupada, Node.js incompatível...) sem subir o servidor.
        if process.poll() not in (None, 0):
            detail = _tail_log(SERVE_LOG)
            return False, "O OmniRoute não iniciou." + (f"\n{detail}" if detail else f" Consulte: {SERVE_LOG}")

    return False, "Servidor não respondeu no tempo esperado. Consulte os logs em: " + str(SERVE_LOG)


def stop_server() -> Tuple[bool, str]:
    """Interrompe o servidor OmniRoute, tratando daemon e supervisor em primeiro plano."""
    cmd = get_omniroute_cmd()
    port = get_omniroute_port()

    # 1. Parada graciosa via comando 'stop' do OmniRoute (no Windows ele espera
    #    até 5 s pelo desligamento antes de forçar)
    run_cmd(f"{cmd} stop", timeout=30)

    # Aguarda um instante para o servidor liberar a porta
    time.sleep(2)

    # 2. Servidor realmente parou?
    if not check_server_health():
        return True, "Servidor interrompido com sucesso"

    # 3a. Ainda responde: encerra os PIDs registrados (supervisor antes do
    #     servidor, para ele não reiniciar o filho).
    pids = get_server_pids()
    for pid in pids:
        run_cmd(f"taskkill /PID {pid} /T /F", timeout=15)
    if pids:
        time.sleep(2)
        if not check_server_health():
            return True, "Servidor interrompido (PID registrado encerrado)"

    # 3b. Fallback: encerra quem está escutando na porta do OmniRoute.
    listeners = find_listening_pids(port)
    for pid in listeners:
        run_cmd(f"taskkill /PID {pid} /T /F", timeout=15)
    if listeners:
        time.sleep(2)
        if not check_server_health():
            return True, f"Servidor interrompido (processo na porta {port} encerrado)"

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
    # Tudo depois de "--" vai direto para o binário claude.
    full_cmd = f"{cmd} launch --port {get_omniroute_port()} -- --model auto/best-free"
    launcher = OMNIONE_LAUNCHERS / "omnione-launch-claude.cmd"

    try:
        OMNIONE_LAUNCHERS.mkdir(parents=True, exist_ok=True)
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
