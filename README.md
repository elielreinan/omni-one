# OmniOne

OmniOne é um controlador compacto do Windows para o servidor **OmniRoute** e o **Claude Code** — sem depender do terminal.

> **"Foi criado para facilitar o uso do OmniRoute para leigos."**

## Por que o OmniOne existe?

O **OmniRoute** é uma ferramenta poderosa, mas quem não vive de terminal costuma se perder entre comandos (`serve`, `stop`, `dashboard`), janelas e atalhos. O OmniOne surgiu para dar um **único clique** para tudo isso: iniciar, parar ou reiniciar o servidor, abrir o Claude Code em um workspace, ver logs e abrir o painel.

**Deixamos claro:** nós **não somos donos nem criadores do OmniRoute** — todo o crédito é do seu autor original. O OmniOne é, na prática, um **plugin / invólucro (wrapper)** por cima do OmniRoute, que cuida da parte de execução e automação para você.

## Como o OmniOne se conecta ao OmniRoute

Validado com o **OmniRoute 3.8.51**.

- Resolve o comando `omniroute` (shim npm no PATH, cópia em cache do `npx` na versão validada ou mais nova, ou download automático via `npx`);
- Confere o Node.js antes de iniciar (o OmniRoute 3.8.51 só roda em Node.js 22.22.2+, 24.x, 25.x ou 26.x);
- Inicia o servidor em segundo plano com `omniroute serve --daemon --port <porta>`;
- Monitora a saúde do servidor em `http://127.0.0.1:<porta>/api/monitoring/health`;
- Abre o Claude Code no workspace selecionado com `omniroute launch --port <porta> -- --model auto/best-free`;
- Para o servidor com `omniroute stop` e, se necessário, encerra à força os PIDs registrados pelo OmniRoute (`server/.pid` e `supervisor/.pid`) ou o processo que estiver escutando na porta.

A porta padrão é `20128`. Se você mudou a porta do OmniRoute (variável `PORT` ou `PORT=` no `.env` da pasta de dados), o OmniOne usa a mesma.

A pasta de dados do OmniRoute é resolvida como o próprio OmniRoute faz: `DATA_DIR`, depois `%USERPROFILE%\.omniroute` (se existir), depois `%APPDATA%\omniroute`. O botão **Abrir logs** abre o log do servidor (`logs\application\app.log` nessa pasta). Os arquivos do próprio OmniOne (log de início, script do Claude Code) ficam em `%LOCALAPPDATA%\OmniOne`.

## Instalar

1. Execute `install_tray_app.ps1` no PowerShell.
2. Use o atalho **OmniOne** criado na Área de Trabalho. A janela abre imediatamente e verifica o servidor em segundo plano.

O instalador cria também a inicialização automática do Windows. Na janela compacta é possível iniciar, parar ou reiniciar o servidor, abrir o Claude Code em um workspace, consultar os logs e abrir o painel. Não há dependência do ícone da bandeja.

## Configurar

### Requisitos
- Windows 10 ou 11
- Node.js **24 LTS** (ou 22.22.2+, 25.x, 26.x) com `npm`. O `npx` baixa o OmniRoute automaticamente na primeira execução; para iniciar mais rápido, instale com `npm install -g omniroute`
- Python 3.x e Node.js **apenas** se quiser reconstruir o executável (seção abaixo)

### Primeiro uso
1. Abra o OmniOne e clique em **Iniciar**. A primeira inicialização pode demorar mais se o OmniRoute ainda não estiver no cache do `npx`.
2. Com o status **"OmniRoute ativo"**, selecione o workspace desejado.
3. Clique em **Abrir Claude Code** — o terminal abre no workspace escolhido.
4. Use **Abrir logs** e **Dashboard** para acompanhar o servidor.

### Workspaces em outro local

Por padrão, o OmniOne lista projetos em `C:\Users\seu-usuário\Workspace`. Para usar outro lugar, defina a variável de ambiente `OMNIONE_WORKSPACE_ROOT` com a pasta que contém seus projetos e abra o OmniOne novamente.

## Código aberto

Este projeto é **código aberto**: você pode usar, estudar, modificar e desenvolver outras ferramentas por cima dele. Pull requests e ideias são bem-vindas — veja as [issues](https://github.com/elielreinan/omni-one/issues).

**Aceito feedbacks e críticas.** Se algo quebrou, faltou ou pode melhorar, abra uma issue ou entre em contato.

## Estrutura do projeto

- `frontend/` — interface em **React + TypeScript** (Vite).
- `omnione/` — backend em **Python**: `core.py` controla o OmniRoute, `api.py` expõe as ações para a interface e `app.py` abre a janela com o [pywebview](https://pywebview.flowrl.com/) (WebView2 do Windows).
- `omnione_tray.py` — ponto de entrada usado pelo PyInstaller.

## Desenvolver a interface

```powershell
cd frontend
npm install
npm run dev
```

No navegador a interface usa um backend simulado, então dá para ajustar o visual sem Windows nem OmniRoute. Use `?status=running` na URL para ver o estado ativo. Para testar com o backend real, rode `$env:OMNIONE_DEV_URL="http://localhost:5173"; python omnione_tray.py` com o `npm run dev` aberto.

## Recriar o executável

```powershell
cd frontend; npm install; npm run build; cd ..
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller omnione_tray.spec --clean
```

O executável gerado fica em `dist\OmniOne Tray.exe`.

## Créditos e avisos

- **OmniRoute** — ferramenta criada originalmente por [Diego Rodrigues de Sa e Souza](https://github.com/diegosouzapw). Todo o crédito é do autor; não somos donos nem criadores do OmniRoute.
- **OmniOne** — interface de controle sobre o OmniRoute, feito por Eli2Dev.

---

Prod por 2E · [https://e2dev.me/](https://e2dev.me/)