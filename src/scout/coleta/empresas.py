"""Empresas listadas (ações) — fundação do modelo emissor→papéis.

Uma EMPRESA emite N papéis (PETR → PETR3 ON, PETR4 PN); a página é da
empresa, não do ticker. Fontes (todas públicas, sem chave):

- `indexProxy/GetPortfolioDay` (B3): composição do IBrX-100 — o escopo v1
  (as 100 mais líquidas; qualidade > cobertura no início).
- `listedCompaniesProxy` (B3): `GetInitialCompanies` acha a empresa pelo
  nome de pregão; `GetDetail` traz codeCVM, CNPJ, segmento de listagem,
  setor B3 e TODOS os códigos de negociação (com ISIN) do emissor.
- CVM dados abertos `CIA_ABERTA/CAD`: setor de atividade, situação do
  registro e AUDITOR — casados por CNPJ.

O `codeCVM` é a chave que liga a B3 aos datasets estruturados da CVM
(DFP/ITR/FRE) usados nas fases seguintes.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import sqlite3
import time
import urllib.request
from datetime import date

from .. import armazenamento

URL_INDICE = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{token}"
URL_EMPRESAS = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/{endpoint}/{token}"
URL_CAD = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
_HEADERS = {"User-Agent": "Mozilla/5.0 (scout)"}
INDICE_ESCOPO = "IBXX"  # IBrX-100
DIAS_FRESCOR = 7  # composição de índice e cadastro mudam devagar

# sufixo do código de negociação -> tipo do papel (só estes entram; o
# GetDetail também lista debêntures e outros códigos que não são ações)
TIPOS_PAPEL = {"3": "ON", "4": "PN", "5": "PNA", "6": "PNB", "11": "UNT"}


def _chamar(url_base: str, endpoint: str, parametros: dict) -> dict:
    token = base64.b64encode(json.dumps(parametros).encode()).decode()
    requisicao = urllib.request.Request(
        url_base.format(endpoint=endpoint, token=token), headers=_HEADERS
    )
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return json.load(resposta)


def composicao_ibrx(indice: str = INDICE_ESCOPO) -> list[dict]:
    """Papéis do índice: [{cod, asset, type, part}, ...]."""
    token = base64.b64encode(
        json.dumps(
            {"language": "pt-br", "pageNumber": 1, "pageSize": 200, "index": indice, "segment": "1"}
        ).encode()
    ).decode()
    requisicao = urllib.request.Request(URL_INDICE.format(token=token), headers=_HEADERS)
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        dados = json.load(resposta)
    return dados.get("results") or []


def buscar_empresa(nome_pregao: str, radical: str) -> dict | None:
    """Acha a empresa na B3 pelo nome de pregão e confirma pelo radical."""
    dados = _chamar(
        URL_EMPRESAS,
        "GetInitialCompanies",
        {"language": "pt-br", "pageNumber": 1, "pageSize": 60, "company": nome_pregao.strip()},
    )
    for resultado in dados.get("results") or []:
        if (resultado.get("issuingCompany") or "").strip().upper() == radical:
            return resultado
    return None


def detalhar_empresa(cod_cvm: str) -> dict:
    """Detalhe: cnpj, otherCodes (todos os papéis com ISIN), setor B3."""
    return _chamar(URL_EMPRESAS, "GetDetail", {"codeCVM": str(cod_cvm), "language": "pt-br"})


def papeis_do_detalhe(detalhe: dict, radical: str) -> list[tuple[str, str, str]]:
    """(ticker, isin, tipo) só dos códigos que são ações/units do emissor."""
    papeis = []
    codigos = list(detalhe.get("otherCodes") or [])
    if not codigos and detalhe.get("code"):
        codigos = [{"code": detalhe["code"], "isin": ""}]
    for item in codigos:
        codigo = (item.get("code") or "").strip().upper()
        casamento = re.fullmatch(rf"{re.escape(radical)}(3|4|5|6|11)", codigo)
        if not casamento:
            continue  # debênture, recibo etc.
        papeis.append((codigo, (item.get("isin") or "").strip(), TIPOS_PAPEL[casamento.group(1)]))
    return papeis


def _numero_ptbr(texto: str | None) -> float:
    """'1.222.000,50' -> 1222000.5 (formato pt-BR das APIs da B3)."""
    limpo = (texto or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0


def _data_iso(texto: str | None) -> str:
    """'25/04/2008' -> '2008-04-25'."""
    partes = (texto or "").strip().split("/")
    if len(partes) != 3 or len(partes[2]) != 4:
        return ""
    return f"{partes[2]}-{partes[1]}-{partes[0]}"


def eventos_do_emissor(radical: str) -> tuple[list[dict], list[dict]]:
    """(stockDividends, cashDividends) do bloco 'eventos corporativos' da B3.

    Semântica do factor, validada com casos reais (PETR/VALE/IRBR/AMER):
    DESDOBRAMENTO e BONIFICACAO = PERCENTUAL de ações novas (100 = dobrou);
    GRUPAMENTO = razão direta da quantidade (<1; AMER 100:1 = 0,01).
    """
    dados = _chamar(
        URL_EMPRESAS,
        "GetListedSupplementCompany",
        {"issuingCompany": radical, "language": "pt-br"},
    )
    item = dados[0] if isinstance(dados, list) and dados else {}
    return (item.get("stockDividends") or [], item.get("cashDividends") or [])


def proventos_do_emissor(nome_pregao: str) -> list[dict]:
    """Histórico completo de dividendos/JCP do emissor (paginado)."""
    proventos: list[dict] = []
    pagina = 1
    while True:
        dados = _chamar(
            URL_EMPRESAS,
            "GetListedCashDividends",
            {
                "language": "pt-br",
                "pageNumber": pagina,
                "pageSize": 100,
                "tradingName": nome_pregao.strip(),
            },
        )
        proventos.extend(dados.get("results") or [])
        total_paginas = (dados.get("page") or {}).get("totalPages") or 1
        if pagina >= total_paginas:
            return proventos
        pagina += 1


def _fator_quantidade(label: str, factor_bruto: str | None) -> float | None:
    """Normaliza o factor da B3 para multiplicador de QUANTIDADE de ações."""
    fator = _numero_ptbr(factor_bruto)
    if fator <= 0:
        return None
    label = (label or "").strip().upper()
    if label in ("DESDOBRAMENTO", "BONIFICACAO", "BONIFICAÇÃO"):
        return 1 + fator / 100
    if label == "GRUPAMENTO":
        return fator
    return None  # rótulo desconhecido: melhor não ajustar do que ajustar errado


def _gravar_eventos_e_proventos(con: sqlite3.Connection, empresa: sqlite3.Row) -> None:
    """Eventos societários (por ISIN) e proventos (por tipo de papel)."""
    papeis = con.execute(
        "SELECT ticker, isin, tipo FROM papeis WHERE cod_cvm = ?", (empresa["cod_cvm"],)
    ).fetchall()
    por_isin = {p["isin"]: p["ticker"] for p in papeis if p["isin"]}
    por_tipo = {p["tipo"]: p["ticker"] for p in papeis}

    eventos, _dividendos_recentes = eventos_do_emissor(empresa["radical"])
    time.sleep(0.25)
    for evento in eventos:
        ticker = por_isin.get((evento.get("isinCode") or "").strip())
        data = _data_iso(evento.get("lastDatePrior"))
        fator = _fator_quantidade(evento.get("label"), evento.get("factor"))
        if not ticker or not data or fator is None:
            continue
        con.execute(
            "INSERT OR REPLACE INTO acao_eventos (ticker, data, label, fator) VALUES (?, ?, ?, ?)",
            (ticker, data, (evento.get("label") or "").strip().upper(), fator),
        )

    for provento in proventos_do_emissor(empresa["nome_pregao"]):
        ticker = por_tipo.get((provento.get("typeStock") or "").strip().upper())
        # neste endpoint o último dia "com" chama lastDatePriorEx (≠ eventos)
        data_com = _data_iso(provento.get("lastDatePriorEx"))
        # cotações antigas eram por lote (quotedPerShares=1000): normaliza p/ 1 ação
        base = _numero_ptbr(provento.get("quotedPerShares")) or 1.0
        valor = _numero_ptbr(provento.get("valueCash")) / base
        if not ticker or not data_com or valor <= 0:
            continue
        con.execute(
            "INSERT OR REPLACE INTO acao_proventos (ticker, data_com, label, valor) VALUES (?, ?, ?, ?)",
            (ticker, data_com, (provento.get("corporateAction") or "").strip().upper(), valor),
        )
    time.sleep(0.25)


def carregar_cadastro_cvm() -> dict[str, dict]:
    """CAD da CVM por CNPJ (só dígitos): setor, situação e auditor."""
    requisicao = urllib.request.Request(URL_CAD, headers=_HEADERS)
    with urllib.request.urlopen(requisicao, timeout=120) as resposta:
        texto = resposta.read().decode("latin-1")
    cias = {}
    for linha in csv.DictReader(io.StringIO(texto), delimiter=";"):
        cnpj = armazenamento.so_digitos(linha.get("CNPJ_CIA"))
        if cnpj:
            cias[cnpj] = {
                "setor": (linha.get("SETOR_ATIV") or "").strip(),
                "situacao": (linha.get("SIT") or "").strip(),
                "auditor": (linha.get("AUDITOR") or "").strip(),
            }
    return cias


def atualizar_empresas(
    con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None
) -> str | None:
    """Sincroniza `empresas`/`papeis` (1x/semana): composição do IBrX-100,
    detalhe B3 só de quem ainda não temos, cadastro CVM para todas."""
    hoje = hoje or date.today()
    carga = con.execute(
        "SELECT carregado_em FROM cargas WHERE arquivo = 'EMPRESAS_B3'"
    ).fetchone()
    if carga and carga[0]:
        idade = (hoje - date.fromisoformat(str(carga[0])[:10])).days
        if idade < DIAS_FRESCOR:
            return None

    composicao = composicao_ibrx()
    radicais_indice: dict[str, str] = {}  # radical -> nome de pregão
    for item in composicao:
        codigo = (item.get("cod") or "").strip().upper()
        casamento = re.match(r"([A-Z]{4})\d", codigo)
        if casamento:
            radicais_indice.setdefault(casamento.group(1), (item.get("asset") or "").strip())

    conhecidos = {
        linha["radical"]: linha["cod_cvm"]
        for linha in con.execute("SELECT radical, cod_cvm FROM empresas")
    }
    novos, sem_match = 0, []
    for radical, nome_pregao in radicais_indice.items():
        if radical in conhecidos:
            continue
        empresa = buscar_empresa(nome_pregao, radical)
        time.sleep(0.25)  # educação com a fonte
        if not empresa or not empresa.get("codeCVM"):
            sem_match.append(radical)
            continue
        cod_cvm = str(empresa["codeCVM"])
        detalhe = detalhar_empresa(cod_cvm)
        time.sleep(0.25)
        cnpj = armazenamento.so_digitos(detalhe.get("cnpj") or empresa.get("cnpj"))
        con.execute(
            """
            INSERT OR REPLACE INTO empresas
                (cod_cvm, cnpj, radical, nome, nome_pregao, setor_b3,
                 segmento_listagem, no_ibrx100, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                cod_cvm,
                cnpj,
                radical,
                (detalhe.get("companyName") or empresa.get("companyName") or "").strip(),
                (empresa.get("tradingName") or nome_pregao).strip(),
                (detalhe.get("industryClassification") or "").strip(),
                (empresa.get("segment") or "").strip(),
                hoje.isoformat(),
            ),
        )
        for ticker, isin, tipo in papeis_do_detalhe(detalhe, radical):
            con.execute(
                "INSERT OR REPLACE INTO papeis (ticker, cod_cvm, isin, tipo) VALUES (?, ?, ?, ?)",
                (ticker, cod_cvm, isin, tipo),
            )
        novos += 1

    # marca quem saiu do índice (escopo é dinâmico; a empresa fica na base)
    con.execute("UPDATE empresas SET no_ibrx100 = 0")
    for radical in radicais_indice:
        con.execute("UPDATE empresas SET no_ibrx100 = 1 WHERE radical = ?", (radical,))

    # cadastro CVM (setor de atividade, situação do registro, auditor)
    try:
        cias = carregar_cadastro_cvm()
    except Exception:  # noqa: BLE001 — sem rede na CVM, os campos ficam para a próxima
        cias = {}
    for linha in con.execute("SELECT cod_cvm, cnpj FROM empresas"):
        dados = cias.get(linha["cnpj"])
        if dados:
            con.execute(
                "UPDATE empresas SET setor_cvm = ?, situacao = ?, auditor = ? WHERE cod_cvm = ?",
                (dados["setor"], dados["situacao"], dados["auditor"], linha["cod_cvm"]),
            )

    # eventos societários + dividendos/JCP (base do ajuste e do retorno total)
    for empresa in con.execute("SELECT * FROM empresas WHERE no_ibrx100 = 1"):
        try:
            _gravar_eventos_e_proventos(con, empresa)
        except Exception:  # noqa: BLE001 — um emissor com erro não derruba a carga
            sem_match.append(f"{empresa['radical']} (eventos)")

    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES ('EMPRESAS_B3', ?)",
        (hoje.isoformat(),),
    )
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM empresas WHERE no_ibrx100 = 1").fetchone()[0]
    papeis = con.execute(
        "SELECT COUNT(*) FROM papeis WHERE cod_cvm IN (SELECT cod_cvm FROM empresas WHERE no_ibrx100 = 1)"
    ).fetchone()[0]
    mensagem = f"empresas do IBrX-100: {total} emissores, {papeis} papéis ({novos} novos)"
    if sem_match:
        mensagem += f" · sem match na B3: {', '.join(sorted(sem_match))}"
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
