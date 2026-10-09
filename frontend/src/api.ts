// Ponte com o backend Python (omnione/api.py), exposto pelo pywebview em
// window.pywebview.api. Fora do pywebview (npm run dev no navegador) usamos
// um backend simulado para desenvolver a interface sem Windows.

export type ServerStatus = "unknown" | "running" | "stopped" | "starting" | "stopping";

export interface ServerState {
  status: ServerStatus;
  detail: string;
}

export interface ActionResult {
  ok: boolean;
  message: string;
}

export interface AppInfo {
  omnirouteVersion: string;
  healthUrl: string;
  port: number;
  workspaceRoot: string;
}

export interface OmniOneApi {
  get_state(): Promise<ServerState>;
  get_info(): Promise<AppInfo>;
  start(): Promise<ServerState>;
  stop(): Promise<ServerState>;
  list_workspaces(): Promise<string[]>;
  launch_claude(name: string): Promise<ActionResult>;
  open_logs(): Promise<ActionResult>;
  open_dashboard(): Promise<ActionResult>;
  open_site(): Promise<void>;
}

declare global {
  interface Window {
    pywebview?: { api: OmniOneApi };
  }
}

function createMockApi(): OmniOneApi {
  const params = new URLSearchParams(window.location.search);
  let state: ServerState = {
    status: (params.get("status") as ServerStatus) ?? "stopped",
    detail: "Modo de demonstração: backend simulado no navegador.",
  };
  const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const transition = (busy: ServerStatus, done: ServerStatus, detail: string, message: string) => {
    state = { status: busy, detail };
    setTimeout(() => (state = { status: done, detail: message }), 2500);
    return Promise.resolve(state);
  };
  return {
    get_state: async () => state,
    get_info: async () => ({
      omnirouteVersion: "3.8.51",
      healthUrl: "http://127.0.0.1:20128/api/monitoring/health",
      port: 20128,
      workspaceRoot: "C:\\Users\\voce\\Workspace",
    }),
    start: () => transition("starting", "running", "Iniciando o OmniRoute...", "Servidor iniciado com sucesso"),
    stop: () => transition("stopping", "stopped", "Encerrando o servidor...", "Servidor interrompido com sucesso"),
    list_workspaces: async () =>
      params.get("empty") ? [] : ["api-pagamentos", "blog-pessoal", "landing-e2dev", "omni-one", "scripts-automacao"],
    launch_claude: async (name) => {
      await delay(400);
      return { ok: true, message: `Claude Code aberto em ${name}.` };
    },
    open_logs: async () => ({ ok: true, message: "Logs abertos." }),
    open_dashboard: async () => ({ ok: true, message: "Abrindo o dashboard..." }),
    open_site: async () => void window.open("https://e2dev.me/", "_blank"),
  };
}

let mock: OmniOneApi | null = null;

/** Aguarda o pywebview injetar a API; no navegador cai para o backend simulado. */
export function getApi(): Promise<OmniOneApi> {
  if (window.pywebview?.api) return Promise.resolve(window.pywebview.api);
  return new Promise((resolve) => {
    const onReady = () => resolve(window.pywebview!.api);
    window.addEventListener("pywebviewready", onReady, { once: true });
    setTimeout(() => {
      if (window.pywebview?.api) return;
      window.removeEventListener("pywebviewready", onReady);
      resolve((mock ??= createMockApi()));
    }, 600);
  });
}
