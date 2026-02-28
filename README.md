# dahandev — Site com Backend Flask

## Estrutura
```
app.py              ← servidor Flask principal
requirements.txt    ← dependências
Procfile            ← configuração Railway
templates/          ← páginas HTML (Jinja2)
static/             ← CSS, favicon, imagens
```

## Variáveis de ambiente (configurar no Railway)

| Variável | Valor |
|----------|-------|
| `SECRET_KEY` | Uma string longa e aleatória (ex: `openssl rand -hex 32`) |
| `ABACATEPAY_API_KEY` | Sua chave da API do AbacatePay (adicionar quando tiver) |

## Deploy no Railway

1. Crie uma conta em [railway.app](https://railway.app)
2. Clique em **New Project → Deploy from GitHub repo**
3. Selecione este repositório
4. Vá em **Variables** e adicione `SECRET_KEY` com um valor aleatório
5. Railway detecta o `Procfile` e faz o deploy automaticamente
6. Vá em **Settings → Domains** e conecte seu domínio `dahandev.site`

## Rotas

| Rota | Descrição |
|------|-----------|
| `/` | Home |
| `/sobre` | Sobre |
| `/projetos` | Projetos |
| `/galeria` | Galeria |
| `/orcamentos` | Orçamentos |
| `/login` | Login do cliente |
| `/cadastro` | Cadastro do cliente |
| `/area-cliente` | Área do cliente (requer login) |
| `/admin` | Login admin |
| `/admin/painel` | Painel admin |
| `/webhook/abacatepay` | Webhook de pagamento |

## Configurar AbacatePay

1. Crie conta em [abacatepay.com](https://abacatepay.com)
2. Gere uma chave de API no painel deles
3. Adicione no Railway: `ABACATEPAY_API_KEY = sua-chave`
4. Configure o webhook no painel AbacatePay apontando para:
   `https://seudominio.com/webhook/abacatepay`
