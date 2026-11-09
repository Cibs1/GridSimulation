# Como correr a simulação (versão v0.5)

Há **duas formas** de correr isto:

| | O quê | Como | Demora |
|---|---|---|---|
| **1** | **Simulação visual** no browser | duplo clique em `correr_visual.bat` | abre em segundos |
| **2** | **Experiências completas** (todas, 30 sementes cada) + estatística + figuras | duplo clique em `correr_experiencias.bat` | ~30 min |

Os dois `.bat` estão na pasta `projeto_v1` e usam o ambiente Python `.venv` que já está criado.

---

## Preparar o ambiente (só uma vez, já está feito neste PC)

Num terminal, dentro da pasta `projeto_v1`:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Precisa de Python 3.12 ou mais recente.

---

## Forma 1 — Simulação visual

Duplo clique em **`correr_visual.bat`** (ou no terminal: `correr_visual.bat`).
Abre uma página no browser com a comunidade animada.

- À esquerda, em **Controls**: ▶ para correr, **Step** para avançar 1 hora,
  **Steps per frame = 24** para avançar 1 dia de cada vez.
- Em **Scenario** mudas os parâmetros e carregas em **Reset**:

| Controlo | O que muda |
|---|---|
| Seed | a "semente" aleatória: outras casas, outro ano de tempo, outras falhas |
| Households | número de casas |
| Share with PV | fração das casas com painéis |
| Pricing mechanism | regra de preços: `none`, `fixed`, `mid_market`, `sdr`, `dynamic`, `bill_sharing` |
| Storage / Battery capacity | sem bateria, baterias individuais ou bateria comunitária, e o total de kWh |
| Demand-response flexibility | quanto do consumo diário as casas podem mudar de hora |
| Outages per year | falhas de rede por ano |
| Membership change | liga as entradas/saídas da comunidade (de 30 em 30 dias) |
| Members at start / Min. savings to stay | % de membros no início / poupança mínima para ficar (€ por 30 dias) |
| Weather year (PVGIS) | `random` (sorteado pela semente) ou um ano de 2014 a 2023 |
| Temperature effect on demand | efeito da temperatura no consumo (0 = desligado; 0.02 = 2% por grau-dia) |

Para parar: fechar a janela preta (ou Ctrl+C).

---

## Forma 2 — Experiências completas

Duplo clique em **`correr_experiencias.bat`**. Faz duas coisas, por esta ordem:

1. Corre **todas as experiências** de `experiments/designs.py` (30 sementes cada) e grava os
   resultados em `experiments/results/<experiência>.csv` (uma linha por cenário × semente).
2. Corre o notebook `notebooks/02_experiments.ipynb`: testes estatísticos (ANOVA, Kruskal-Wallis,
   Tukey, testes emparelhados) e **figuras** em `notebooks/figures/*.png`.
   Para ver as tabelas, abrir o notebook (VS Code abre `.ipynb` diretamente).

| Experiência | Pergunta | Cenários |
|---|---|---|
Perguntas de investigação: **RQ1** comparação dos mecanismos de preços, **RQ2** poupança relativa,
**RQ3** flexibilidade, **RQ4** resiliência.

| Experiência | Pergunta | Cenários |
|---|---|---|
| `e1_pricing` | RQ1 mecanismos de preços (e RQ2 poupança vs % de PV) | 6 regras × PV 0/20/40/60/80/100 %, com entradas/saídas |
| `e1b_membership_threshold` | RQ1 robustez | 6 regras × poupança mínima 0/2/5 € |
| `e1c_pv_value` | RQ2 poupança e valor dos painéis | PV 0–100 % × comunidade com/sem bateria comunitária |
| `e2_storage` | RQ2 poupança com baterias | nenhuma / individual / comunitária × 50/100/200 kWh |
| `e2b_storage_pricing` | RQ1 × RQ2 preços com bateria | 5 regras, cada uma com bateria comunitária de 100 kWh |
| `e3_demand_response` | RQ3 flexibilidade | mid-market / SDR / dynamic × flexibilidade 0/0.1/0.2 |
| `e4_resilience` | RQ4 resiliência | 3 regimes de falhas × 3 armazenamentos × 20/30/50 casas |
| `e5_sensitivity` | robustez | cooperação, eficiência, preço de venda, regra da bateria, tarifa bi-horária, flexibilidade, temperatura |
| `e6_weather_temperature` | o tempo e a temperatura contam? | 10 anos de tempo × efeito da temperatura ligado/desligado |

### Opções extra (no terminal, dentro de `projeto_v1`)

```
correr_experiencias.bat e1_pricing e4_resilience   só estas experiências (e depois as figuras)
correr_experiencias.bat --workers 6                usar menos núcleos do processador
correr_experiencias.bat --figures-only             não corre nada, só refaz as figuras a partir dos CSV
```

### Mudar ou criar cenários

Os cenários estão em **`experiments/designs.py`**. Cada experiência é uma função que devolve
`{"nome do cenário": {parâmetros que mudam}}`. Os parâmetros possíveis são os de
`Community.__init__` em `model/model.py` (cada um tem um comentário a explicar). Os mais usados:

| Parâmetro | Valor por defeito | Significado |
|---|---|---|
| `n_households` | 30 | número de casas |
| `pv_share` | 0.4 | fração com painéis |
| `pricing` | `"mid_market"` | regra de preços |
| `storage_mode`, `storage_kwh` | `"none"`, 0 | armazenamento e total de kWh |
| `flexibility` | 0 | flexibilidade (demand response) |
| `cooperation` | 1.0 | probabilidade de oferecer o excedente à comunidade |
| `membership`, `initial_member_share`, `savings_threshold` | False, 1.0, 0 | entradas/saídas (limiar 0 €: entrar e sair é grátis nas comunidades reais) |
| `tariff` | `"simple"` | tarifa da rede: `"simple"` (ERSE 0,1711 €/kWh) ou `"bi_hourly"` (0,1143 vazio / 0,2045 fora de vazio) |
| `export_price` | 0.05 | preço de venda do excedente à rede (€/kWh) |
| `battery_income` | `"prosumers"` | quem recebe o dinheiro da bateria comunitária: quem a encheu, ou a comunidade (`"unallocated"`) |
| `outage_rate`, `outage_duration` | 4, (1, 8) | falhas por ano e duração (h) |
| `weather_year` | None | `None` = sorteado; ou um ano 2014–2023 |
| `heat_sensitivity`, `cool_sensitivity` | 0.02 | efeito da temperatura no consumo |

Exemplo — criar uma experiência nova: acrescentar a `designs.py`

```python
def tamanho():
    """Comunidade pequena vs grande, com bateria comunitária."""
    return {
        f"{n} casas": {"n_households": n, "storage_mode": "shared", "storage_kwh": 100}
        for n in [20, 50]
    }
```

e registá-la no dicionário `DESIGNS` no fim do ficheiro: `"tamanho": tamanho,`.
Depois: `correr_experiencias.bat tamanho`.

---

## Verificar que está tudo bem (opcional)

```
.venv\Scripts\python.exe -m pytest
```

Corre 50 testes (balanço de energia em todas as horas, poupança = redução da fatura da rede,
reprodutibilidade, baterias, falhas, temperatura, anos de tempo...). Demora ~4 min.

---

## Mapa do código

```
projeto_v1/
├── correr_visual.bat          FORMA 1: abre a simulação visual
├── correr_experiencias.bat    FORMA 2: corre todas as experiências + figuras
├── COMO_CORRER.md             este guia
├── README.md                  resumo do projeto (inglês)
├── requirements.txt           bibliotecas Python necessárias
├── app.py                     a visualização (Mesa + Solara): desenho da comunidade, gráficos, controlos
│
├── model/                     A SIMULAÇÃO
│   ├── model.py               Community: o "mundo". Lê os dados, sorteia o ano de tempo e as falhas,
│   │                          cria as casas, corre o ciclo de cada hora (step), calcula os KPIs
│   ├── agents.py              Household: cada casa (com ou sem PV). Constrói o seu consumo,
│   │                          usa a sua energia e bateria, oferece/pede à comunidade, decide
│   │                          a flexibilidade, guarda as suas contas e a fatura "sozinha"
│   ├── manager.py             CommunityManager: o gestor. Mercado local, regras de preço,
│   │                          bateria comunitária, faturas, previsão de preços
│   └── battery.py             Battery: carga/descarga com limites e perdas (casas e comunidade)
│
├── data/                      OS DADOS
│   ├── raw/                   downloads originais (PVGIS, perfil E-REDES), não mexer
│   └── processed/
│       ├── weather_porto.csv  sol (kWh por kWp) e temperatura, hora a hora, 2014–2023  ← usado
│       ├── load_btn_c.csv     perfil de consumo padrão (fração do consumo anual em cada hora) ← usado
│       └── pv_porto.csv       sol de 2023 (versão antiga; usado só para o calendário/horas)
│
├── scripts/                   PREPARAR OS DADOS (só se quiser descarregar de novo)
│   ├── get_weather.py         descarrega 2014–2023 do PVGIS -> weather_porto.csv
│   ├── get_pvgis.py           descarrega 2023 do PVGIS -> pv_porto.csv
│   └── prep_load.py           converte o Excel da E-REDES -> load_btn_c.csv
│
├── experiments/               AS EXPERIÊNCIAS
│   ├── designs.py             definição dos cenários de cada experiência (E1–E5)
│   ├── run_experiments.py     corre cenários × 30 sementes em paralelo -> results/*.csv
│   ├── run_all.py             FORMA 2 por dentro: run_experiments + notebook das figuras
│   ├── stats.py               funções de estatística (intervalos de confiança, ANOVA, Tukey, ...)
│   └── results/               resultados (um CSV por experiência)
│
├── notebooks/
│   ├── 01_data_check.ipynb    verificação dos dados e dos padrões (curva "duck", verão/inverno)
│   ├── 02_experiments.ipynb   estatística e figuras das experiências (corrido pela Forma 2)
│   └── figures/               as figuras (.png)
│
├── tests/test_model.py        os 37 testes de verificação
└── docs/
    ├── ODD.md                 documentação completa do modelo (protocolo ODD, v0.5)
    └── PROJECT_CONTEXT.md     contexto do projeto escrito pelo colega
```

### O que acontece quando se corre (resumo)

`Community(...)` prepara tudo (ano de tempo, casas, falhas, faturas de referência) →
`step()` é chamado 8760 vezes (1 por hora): casas calculam excedente/défice (`agents.py`) →
gestor faz o mercado e define o preço (`manager.py`) → bateria comunitária → rede e faturas →
regista tudo e verifica o balanço de energia → no fim, `kpis()` dá os resultados do ano.
Explicação detalhada: `../SIMULACAO_EXPLICADA.txt` (fora do repositório) e `docs/ODD.md`.
