import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ExternalLink,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Loader2,
  Play,
  RotateCw,
  Search,
  Square,
  Terminal,
} from "lucide-react";
import { getApi, type AppInfo, type OmniOneApi, type ServerState, type ServerStatus } from "./api";

const POLL_MS = 2000;

const STATUS_LABEL: Record<ServerStatus, string> = {
  unknown: "Verificando...",
  running: "OmniRoute ativo",
  stopped: "OmniRoute parado",
  starting: "Iniciando...",
  stopping: "Parando...",
};

type Toast = { ok: boolean; message: string; id: number };

export default function App() {
  const [api, setApi] = useState<OmniOneApi | null>(null);
  const [state, setState] = useState<ServerState>({ status: "unknown", detail: "Verificando o servidor..." });
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [launching, setLaunching] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastTimer = useRef<number>();

  const notify = useCallback((ok: boolean, message: string) => {
    setToast({ ok, message, id: Date.now() });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }, []);

  useEffect(() => {
    getApi().then(async (a) => {
      setApi(a);
      setInfo(await a.get_info());
      const names = await a.list_workspaces();
      setWorkspaces(names);
      setSelected(names[0] ?? null);
    });
  }, []);

  // Consulta o status periodicamente; o backend pausa a verificação durante início/parada.
  useEffect(() => {
    if (!api) return;
    let alive = true;
    const tick = async () => {
      const s = await api.get_state();
      if (alive) setState(s);
    };
    tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [api]);

  const { status } = state;
  const busy = status === "starting" || status === "stopping";
  const running = status === "running";

  const filtered = useMemo(
    () => workspaces.filter((w) => w.toLowerCase().includes(query.trim().toLowerCase())),
    [workspaces, query],
  );

  const onStart = async () => api && setState(await api.start());
  const onStop = async () => api && setState(await api.stop());
  const onLaunch = async () => {
    if (!api || !selected) return;
    setLaunching(true);
    const r = await api.launch_claude(selected);
    setLaunching(false);
    notify(r.ok, r.message);
  };
  const onLogs = async () => {
    if (!api) return;
    const r = await api.open_logs();
    if (!r.ok) notify(false, r.message);
  };
  const onDashboard = async () => api && notify(true, (await api.open_dashboard()).message);

  return (
    <div className="app">
      <header className="header">
        <img className="logo" src="./omnione-logo.jpeg" alt="" />
        <div className="title">
          <h1>OmniOne</h1>
          <p>Controle do OmniRoute e Claude Code</p>
        </div>
        {info && <span className="chip">v{info.omnirouteVersion}</span>}
      </header>

      <section className={`card status status--${status}`}>
        <div className="status__row">
          <span className="pulse" aria-hidden />
          <div className="status__text">
            <span className="eyebrow">Servidor</span>
            <strong>{STATUS_LABEL[status]}</strong>
          </div>
          <span className="port">:{info?.port ?? 20128}</span>
        </div>
        <p className="status__detail">{state.detail}</p>
        <div className="row">
          <button className="btn btn--primary" onClick={onStart} disabled={busy || !api}>
            {status === "starting" ? (
              <Loader2 className="spin" size={16} />
            ) : running ? (
              <RotateCw size={16} />
            ) : (
              <Play size={16} />
            )}
            {running ? "Reiniciar" : "Iniciar"}
          </button>
          <button className="btn btn--ghost" onClick={onStop} disabled={!running}>
            {status === "stopping" ? <Loader2 className="spin" size={16} /> : <Square size={14} />}
            Parar
          </button>
        </div>
      </section>

      <section className="card workspaces">
        <div className="section-head">
          <h2>Workspace</h2>
          <span className="muted">{workspaces.length} projetos</span>
        </div>
        {workspaces.length > 0 ? (
          <>
            <label className="search">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar projeto" />
            </label>
            <ul className="list" role="listbox">
              {filtered.map((name) => (
                <li key={name}>
                  <button
                    role="option"
                    aria-selected={name === selected}
                    className={`item ${name === selected ? "item--active" : ""}`}
                    onClick={() => setSelected(name)}
                    onDoubleClick={() => running && onLaunch()}
                  >
                    <FolderOpen size={16} />
                    <span>{name}</span>
                  </button>
                </li>
              ))}
              {filtered.length === 0 && <li className="empty">Nada encontrado para “{query}”.</li>}
            </ul>
          </>
        ) : (
          <div className="empty empty--box">
            Nenhum workspace em <code>{info?.workspaceRoot ?? "…"}</code>. Defina <code>OMNIONE_WORKSPACE_ROOT</code> para
            usar outra pasta.
          </div>
        )}
        <button className="btn btn--accent btn--block" onClick={onLaunch} disabled={!running || !selected || launching}>
          {launching ? <Loader2 className="spin" size={16} /> : <Terminal size={16} />}
          Abrir Claude Code
        </button>
        {!running && workspaces.length > 0 && <p className="hint">Inicie o servidor para abrir o Claude Code.</p>}
      </section>

      <section className="tiles">
        <button className="tile" onClick={onLogs} disabled={!running}>
          <FileText size={18} />
          <span>Logs</span>
        </button>
        <button className="tile" onClick={onDashboard} disabled={!running}>
          <LayoutDashboard size={18} />
          <span>Dashboard</span>
        </button>
      </section>

      <footer className="footer">
        <button className="link" onClick={() => api?.open_site()}>
          Prod por 2E · e2dev.me <ExternalLink size={12} />
        </button>
      </footer>

      {toast && (
        <div key={toast.id} className={`toast ${toast.ok ? "" : "toast--error"}`} role="status">
          {toast.message}
        </div>
      )}
    </div>
  );
}
