# 📊 Enriquecímetro

**A evolução do patrimônio declarado pelos candidatos brasileiros.**

> Mostramos os números. Não presumimos a origem.

Site estático, gratuito, apartidário e de código aberto que mostra como o
patrimônio **declarado à Justiça Eleitoral** pelos candidatos mudou entre as
eleições de **2022 e 2026** — com dados oficiais do TSE, metodologia aberta e
zero infraestrutura própria (apenas GitHub, GitHub Actions e GitHub Pages).

O projeto **não** afirma nem insinua que variação patrimonial significa
irregularidade. Ele apresenta números públicos com contexto e deixa as
conclusões para quem lê.

*(screenshot: adicione uma captura da home aqui após o primeiro deploy)*

## Arquitetura

```
TSE / Portal de Dados Abertos
        ↓  (download diário)
GitHub Actions (update-data.yml)
        ↓
Scripts Python de ETL (somente biblioteca padrão — zero dependências)
  download → transform → match → generate → validate → publish
        ↓
JSONs estáticos otimizados (public/data/)
        ↓
HTML + CSS + JavaScript puros (sem frameworks, sem build)
        ↓
GitHub Pages (deploy-pages.yml)
```

Não há servidor, banco de dados, API própria nem serviço pago. O site final é
100% estático.

## Origem dos dados

Exclusivamente o [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br/):

| Dataset | Conteúdo |
|---|---|
| `consulta_cand_{ano}.zip` | Dados cadastrais das candidaturas |
| `bem_candidato_{ano}.zip` | Bens declarados no registro de candidatura |

As URLs ficam centralizadas em [`config/data_sources.json`](config/data_sources.json)
(nunca hardcoded nos scripts). O manifesto público
[`public/data/meta.json`](public/data/meta.json) registra, a cada execução:
data/hora do processamento, URL de cada fonte, `Last-Modified` informado pelo
TSE e data do download. A arquitetura já está preparada para incluir 2014 e
2018 (basta adicionar os anos em `elections`).

## Metodologia (resumo)

Detalhes completos em [`methodology.html`](methodology.html).

- **Soma dos bens**: total declarado = soma de `VR_BEM_CANDIDATO` da eleição,
  tratado em centavos. Sempre o valor declarado, nominal — nunca estimativa de mercado.
- **Mesma pessoa entre eleições**: identificador pessoal dos arquivos do TSE é
  usado **apenas internamente** (nível `exact`); fallback por nome normalizado +
  data de nascimento (`probable`); sem correspondência segura → `unverified`,
  nunca inventamos match. **Só `exact` entra nos rankings.**
- **Variações**: nominal, percentual e multiplicador. Patrimônio anterior R$ 0 →
  percentual `null` (exibido como "não aplicável", nunca "infinito %").
- **Outliers**: selo descritivo "variação atípica" via método de Tukey
  (percentual > Q3 + 3×IQR do conjunto comparável). Não é índice de suspeita.
- **Inflação**: TODO documentado — comparação real (IPCA/IBGE) virá como feature
  separada, sempre distinta da nominal.

## Privacidade

- CPF, e-mail, título de eleitor, endereço e telefone **nunca** são publicados,
  logados ou commitados — são descartados na leitura ou usados só em memória/
  arquivos temporários gitignored durante o matching.
- O ID público de cada candidato deriva do `SQ_CANDIDATO` (número sequencial
  **público** do TSE) — é impossível reconstruir CPF a partir dele.
- `scripts/validate.py` varre todos os arquivos antes da publicação e **aborta**
  se detectar qualquer identificador pessoal. Dados válidos nunca são
  substituídos por dados quebrados.

## Estrutura do projeto

```
├── .github/workflows/
│   ├── update-data.yml      # ETL diário + commit automático se houver mudança
│   └── deploy-pages.yml     # testes + validação + deploy no Pages
├── config/data_sources.json # URLs oficiais, anos habilitados, limites de validação
├── scripts/
│   ├── common.py            # utilidades puras (parse BRL, CPF, IDs, quartis)
│   ├── download.py          # download com manifesto e detecção de mudanças
│   ├── transform.py         # ZIP → candidaturas agregadas por eleição
│   ├── match_candidates.py  # relacionamento entre eleições (exact/probable/unverified)
│   ├── generate_site_data.py# JSONs otimizados do site (staging)
│   ├── validate.py          # validações críticas + varredura de dados sensíveis
│   └── run_pipeline.py      # orquestrador (publicação atômica)
├── tests/                   # unittest — fixtures sintéticas geradas em tempo de teste
├── public/
│   ├── data/                # JSONs publicados (gerados pelo pipeline)
│   ├── css/  js/            # frontend sem dependências
├── index.html  candidate.html  methodology.html  about.html
└── LICENSE (MIT)
```

Dados publicados: `meta.json` (manifesto), `rankings.json` (carga inicial leve),
`search-index.json` (índice de busca, carregado sob demanda),
`states/{UF}.json`, `candidates/{xy}.json` (detalhes em 256 shards).

## Execução local

Requisitos: **Python 3.10+**. Nada de pip — só biblioteca padrão.

```bash
# testes
python -m unittest discover -s tests -v

# pipeline completo (baixa ~16 MB do TSE)
python scripts/run_pipeline.py

# servir o site localmente
python -m http.server 8000
# abra http://localhost:8000
```

Variáveis opcionais: `ENRIQ_DOWNLOAD_DIR`, `ENRIQ_WORK_DIR`, `ENRIQ_OUTPUT_DIR`
redirecionam os diretórios do pipeline.

## Como publicar (passo a passo, do zero)

1. **Crie o repositório** em github.com (por exemplo `enriquecimetro`), público.
2. **Envie o código**:
   ```bash
   git init
   git add .
   git commit -m "Enriquecímetro: MVP"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/enriquecimetro.git
   git push -u origin main
   ```
3. **Habilite o GitHub Pages**: no repositório, *Settings → Pages → Build and
   deployment → Source*: selecione **GitHub Actions**.
4. **Habilite permissões dos Actions**: *Settings → Actions → General →
   Workflow permissions*: selecione **Read and write permissions** (necessário
   para o commit automático dos dados).
5. **Primeiro processamento**: aba *Actions → "Atualizar dados do TSE" →
   Run workflow*. Ele baixa os dados do TSE, roda o ETL e commita `public/data/`.
6. **Publicação**: o commit do passo 5 dispara automaticamente o deploy no
   Pages. O site fica em `https://SEU_USUARIO.github.io/enriquecimetro/`.

A partir daí o dado se atualiza sozinho todos os dias (05h23 de Brasília); o
commit automático só acontece quando o TSE muda algo, e cada commit redeploya o
site.

## Atualização de dados

- Automática: workflow `update-data.yml` (diário + botão *Run workflow*).
- O workflow roda os testes antes do pipeline e a validação antes de publicar;
  qualquer falha aborta sem tocar nos dados já publicados.
- Sem loop de Actions: o workflow de dados não dispara em `push`.

## Limitações

- Declarações são autodeclaratórias; valores nominais, sem correção pela inflação (por ora).
- Dados de 2026 são preliminares e mudam até a conclusão dos registros.
- Candidaturas sem identificador válido podem ficar sem comparação (`unverified`).
- A comparação inicial cobre 2022 → 2026; 2014 e 2018 são expansão planejada.

## Licença

Código sob [MIT](LICENSE). Dados: públicos, do TSE (Portal de Dados Abertos),
com atribuição em todas as páginas.

## Contribuindo

Issues e PRs são bem-vindos — especialmente correções de metodologia,
acessibilidade e desempenho. Toda contribuição deve preservar: neutralidade
editorial, minimização de dados pessoais e metodologia idêntica para todos os
candidatos, partidos e cargos.
