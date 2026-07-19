"""Indicadores fundamentais de ações — balanços padronizados da CVM (DFP).

A CVM publica as demonstrações em contas PADRONIZADAS (CD_CONTA), então dá para
calcular indicadores SEM parsear PDF. Dois modelos de DRE convivem no mesmo
dataset:
- comercial/industrial: 3.01 "Receita de Venda…", 3.03 Resultado Bruto,
  3.05 "Antes do Resultado Financeiro" (EBIT), lucro líquido em 3.11;
- instituição financeira (banco/seguradora): 3.01 "Receitas de Intermediação…",
  sem EBIT nesse sentido, lucro líquido em 3.09.
A extração aqui é robusta aos dois (lucro = o maior 3.xx antes do 3.99); as
métricas que não fazem sentido em banco (margem bruta, EBIT, dívida líquida)
ficam nulas e o setor é sinalizado (`setor_financeiro`). Bancos vêm depois
(decisão "métricas universais primeiro, setoriais depois").

Valores gravados em REAIS (a escala MIL/UNIDADE do arquivo já é aplicada).
"""

from __future__ import annotations

import csv
import io
import sqlite3
import urllib.error
import urllib.request
import zipfile
from datetime import date

from .. import armazenamento

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
_HEADERS = {"User-Agent": "Mozilla/5.0 (scout)"}
ANOS_HISTORICO = 4  # DFP dos últimos N anos completos

_CAMPOS = (
    "receita", "resultado_bruto", "ebit", "lucro_liquido",
    "ativo_total", "patrimonio_liquido", "caixa", "divida_bruta",
)


def _num(valor) -> float:
    try:
        return float(valor)
    except (ValueError, TypeError):
        return 0.0


def _escala(texto) -> float:
    return 1000.0 if (texto or "").strip().upper() == "MIL" else 1.0


def _baixar(ano: int) -> bytes | None:
    try:
        req = urllib.request.Request(URL.format(ano=ano), headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read()
    except (urllib.error.URLError, OSError):
        return None


def extrair_ano(conteudo: bytes, cod_cvms: set[int]) -> dict[int, dict]:
    """{cod_cvm: {campos...}} de um zip DFP anual (só a coluna ÚLTIMO = o ano)."""
    zf = zipfile.ZipFile(io.BytesIO(conteudo))
    dados: dict[int, dict] = {}
    lucro_cod: dict[int, str] = {}

    def _rows(parcial: str):
        nome = next((n for n in zf.namelist() if parcial in n), None)
        if not nome:
            return
        with zf.open(nome) as f:
            for linha in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"):
                if linha.get("ORDEM_EXERC") != "ÚLTIMO":
                    continue
                try:
                    cd = int(linha["CD_CVM"])
                except (ValueError, KeyError, TypeError):
                    continue
                if cd in cod_cvms:
                    yield cd, linha

    # --- DRE: receita, resultado bruto, EBIT, lucro líquido ---
    for cd, linha in _rows("DRE_con"):
        conta = linha["CD_CONTA"]
        ds = linha.get("DS_CONTA") or ""
        val = _num(linha["VL_CONTA"]) * _escala(linha.get("ESCALA_MOEDA"))
        alvo = dados.setdefault(cd, {})
        if conta == "3.01":
            alvo["receita"] = val
            alvo["setor_financeiro"] = 1 if ("Intermedia" in ds or "Prêmios" in ds) else 0
        elif conta == "3.03":
            alvo["resultado_bruto"] = val
        elif conta == "3.05" and "Antes do Resultado Financeiro" in ds:
            alvo["ebit"] = val
        # lucro líquido = o maior código 3.xx de UM ponto, exceto 3.99 (EPS)
        if conta.startswith("3.") and conta.count(".") == 1 and conta != "3.99":
            if cd not in lucro_cod or conta > lucro_cod[cd]:
                lucro_cod[cd] = conta
                alvo["lucro_liquido"] = val

    # --- BPA: ativo total + caixa (caixa e equivalentes + aplicações) ---
    for cd, linha in _rows("BPA_con"):
        conta = linha["CD_CONTA"]
        val = _num(linha["VL_CONTA"]) * _escala(linha.get("ESCALA_MOEDA"))
        alvo = dados.setdefault(cd, {})
        if conta == "1":
            alvo["ativo_total"] = val
        elif conta in ("1.01.01", "1.01.02"):
            alvo["caixa"] = alvo.get("caixa", 0.0) + val

    # --- BPP: patrimônio líquido + dívida (empréstimos e financiamentos) ---
    for cd, linha in _rows("BPP_con"):
        conta = linha["CD_CONTA"]
        ds = (linha.get("DS_CONTA") or "").strip()
        val = _num(linha["VL_CONTA"]) * _escala(linha.get("ESCALA_MOEDA"))
        alvo = dados.setdefault(cd, {})
        if ds == "Patrimônio Líquido Consolidado":
            alvo["patrimonio_liquido"] = val
        elif conta in ("2.01.04", "2.02.01"):  # dívida onerosa (circ + não circ)
            alvo["divida_bruta"] = alvo.get("divida_bruta", 0.0) + val

    return dados


def atualizar(
    con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None
) -> str | None:
    """Baixa a DFP dos últimos anos das empresas do escopo (IBrX-100) e grava a
    série de balanços. Incremental por ano (marcador `DFP_<ano>`); o ano mais
    recente é sempre rebaixado (pode ser republicado/reapresentado)."""
    hoje = hoje or date.today()
    cod_cvms = {
        int(linha["cod_cvm"])
        for linha in con.execute("SELECT cod_cvm FROM empresas WHERE no_ibrx100 = 1")
        if str(linha["cod_cvm"]).isdigit()
    }
    if not cod_cvms:
        return None  # empresas ainda não sincronizadas (roda depois do A1)

    carregados = {linha[0] for linha in con.execute("SELECT arquivo FROM cargas")}
    anos = list(range(hoje.year - ANOS_HISTORICO, hoje.year))  # últimos N anos completos
    recente = anos[-1]
    novos_anos = 0
    for ano in anos:
        marcador = f"DFP_{ano}"
        if marcador in carregados and ano != recente:
            continue  # ano fechado já carregado (só o mais recente é rebaixado)
        conteudo = _baixar(ano)
        if not conteudo:
            continue
        dados = extrair_ano(conteudo, cod_cvms)
        for cod_cvm, campos in dados.items():
            con.execute(
                """
                INSERT OR REPLACE INTO fundamentos
                    (cod_cvm, ano, receita, resultado_bruto, ebit, lucro_liquido,
                     ativo_total, patrimonio_liquido, caixa, divida_bruta, setor_financeiro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(cod_cvm), ano,
                    campos.get("receita"), campos.get("resultado_bruto"),
                    campos.get("ebit"), campos.get("lucro_liquido"),
                    campos.get("ativo_total"), campos.get("patrimonio_liquido"),
                    campos.get("caixa"), campos.get("divida_bruta"),
                    campos.get("setor_financeiro", 0),
                ),
            )
        con.execute(
            "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, ?)",
            (marcador, hoje.isoformat()),
        )
        con.commit()
        novos_anos += 1

    empresas = con.execute("SELECT COUNT(DISTINCT cod_cvm) FROM fundamentos").fetchone()[0]
    mensagem = f"fundamentos (DFP): {empresas} empresas com balanço ({novos_anos} anos nesta rodada)"
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem


def indicadores(linha: sqlite3.Row | dict) -> dict:
    """Indicadores derivados de um ano de balanço (só os que dependem apenas do
    balanço; P/L, P/VP e DY entram com preço+ações no próximo passo). Cada um é
    None quando falta o dado — nunca um número inventado."""
    g = linha.__getitem__ if hasattr(linha, "keys") else linha.get

    def v(campo):
        try:
            return g(campo)
        except (KeyError, IndexError):
            return None

    receita = v("receita")
    lucro = v("lucro_liquido")
    pl = v("patrimonio_liquido")
    bruto = v("resultado_bruto")
    divida = v("divida_bruta")
    caixa = v("caixa")
    financeiro = bool(v("setor_financeiro"))

    def pct(numerador, denominador):
        if numerador is None or not denominador:
            return None
        return 100 * numerador / denominador

    divida_liquida = None
    if not financeiro and divida is not None:
        divida_liquida = divida - (caixa or 0.0)

    return {
        "margem_bruta": None if financeiro else pct(bruto, receita),
        "margem_liquida": pct(lucro, receita),
        "roe": pct(lucro, pl),
        "divida_liquida": divida_liquida,
        "divida_liquida_pl": (divida_liquida / pl) if (divida_liquida is not None and pl) else None,
        "setor_financeiro": financeiro,
    }
