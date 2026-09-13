# OmniOne

OmniOne é um controlador compacto do Windows para o servidor **OmniRoute** e o **Claude Code** — sem depender do terminal.

> **"Foi criado para facilitar o uso do OmniRoute para leigos."**

## Por que o OmniOne existe?

O **OmniRoute** é uma ferramenta poderosa, mas quem não vive de terminal costuma se perder entre comandos (`serve`, `stop`, `dashboard`), janelas e atalhos. O OmniOne surgiu para dar um **único clique** para tudo isso: iniciar, parar ou reiniciar o servidor, abrir o Claude Code em um workspace, ver logs e abrir o painel.

**Deixamos claro:** nós **não somos donos nem criadores do OmniRoute** — todo o crédito é do seu autor original. O OmniOne é, na prática, um **plugin / invólucro (wrapper)** por cima do OmniRoute, que cuida da parte de execução e automação para você.

## Como o OmniOne se conecta ao OmniRoute

- Resolve o comando `omniroute` (shim npm no PATH, caminho em cache ou instalação automática via `npx`);
- Inicia o servidor em segundo plano com `omniroute serve --daemon`;
- Monitora a saúde do servidor em `http://localhost:20128/api/monitoring/health`;
- Abre o Claude Code no workspace selecionado com `omniroute launch`;
- Para o servidor com `omniroute stop` (e, se necessário, encerra à força usando o PID em `~/.omniroute/server/.pid`).

## Instalar

1. Execute `install_tray_app.ps1` no PowerShell.
2. Use o atalho **OmniOne** criado na Área de Trabalho. A janela abre imediatamente e verifica o servidor em segundo plano.

O instalador cria também a inicialização automática do Windows. Na janela compacta é possível iniciar, parar ou reiniciar o servidor, abrir o Claude Code em um workspace, consultar os logs e abrir o painel. Não há dependência do ícone da bandeja.

## Configurar

### Requisitos
- Windows 10 ou 11
- Node.js com `npm` (o `npx` baixa o OmniRoute automaticamente na primeira execução, se necessário)
- Python 3.x **apenas** se quiser reconstruir o executável (seção abaixo)

### Primeiro uso
1. Abra o OmniOne e clique em **Iniciar / Reiniciar**. A primeira inicialização pode demorar mais se o OmniRoute ainda não estiver no cache do `npx`.
2. Com o status **"OmniRoute ativo"**, selecione o workspace desejado.
3. Clique em **Abrir Claude Code** — o terminal abre no workspace escolhido.
4. Use **Abrir logs** e **Dashboard** para acompanhar o servidor.

### Workspaces em outro local

Por padrão, o OmniOne lista projetos em `C:\Users\seu-usuário\Workspace`. Para usar outro lugar, defina a variável de ambiente `OMNIONE_WORKSPACE_ROOT` com a pasta que contém seus projetos e abra o OmniOne novamente.

## Código aberto

Este projeto é **código aberto**: você pode usar, estudar, modificar e desenvolver outras ferramentas por cima dele. Pull requests e ideias são bem-vindas — veja as [issues](https://github.com/Eli2Dev/omni-one/issues).

**Aceito feedbacks e críticas.** Se algo quebrou, faltou ou pode melhorar, abra uma issue ou entre em contato.

## Recriar o executável

```powershell
python -m PyInstaller omnione_tray.spec --clean
```

O executável gerado fica em `dist\OmniOne Tray.exe`.

## Créditos e avisos

- **OmniRoute** — ferramenta criada originalmente por [Diego Rodrigues de Sa e Souza](https://github.com/diegosouzapw). Todo o crédito é do autor; não somos donos nem criadores do OmniRoute.
- **OmniOne** — interface de controle sobre o OmniRoute, feito por Eli2Dev.

---

Prod por 2E · [https://e2dev.me/](https://e2dev.me/)