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

    # --- DFC (fluxo de caixa, método indireto): D&A para o EBITDA ---
    # O código não é padronizado (varia entre 6.01.01.02/03/04/05/06…), então
    # casamos por TEXTO dentro dos ajustes operacionais (6.01.01.xx): a
    # depreciação/amortização/exaustão que é somada de volta ao lucro. As
    # "amortizações" de 6.02/6.03 (empréstimos, debêntures, arrendamentos) NÃO
    # entram — são fluxo de financiamento, não D&A.
    for cd, linha in _rows("DFC_MI_con"):
        conta = linha["CD_CONTA"]
        ds = (linha.get("DS_CONTA") or "").lower()
        if conta.startswith("6.01.01.") and ("deprecia" in ds or "amortiza" in ds or "exaust" in ds):
            val = _num(linha["VL_CONTA"]) * _escala(linha.get("ESCALA_MOEDA"))
            alvo = dados.setdefault(cd, {})
            alvo["da"] = alvo.get("da", 0.0) + val

    return dados


def extrair_meta_ano(conteudo: bytes, cod_cvms: set[int]) -> dict[int, dict]:
    """Metadados societários do MESMO zip DFP (matéria-prima das red flags do A3):
    entrega (DT_RECEB) e versão (>1 = reapresentado), composição do capital
    (ações integralizadas + tesouraria) e o RELATÓRIO DO AUDITOR — o tipo vem
    estruturado da própria CVM (TP_RELAT_AUD: Sem Ressalva/Com Ressalva/Adverso/
    Negativa de Opinião) e o texto alimenta a detecção de continuidade."""
    import re

    from .. import parecer as modulo_parecer

    zf = zipfile.ZipFile(io.BytesIO(conteudo))

    def _ler(nome: str):
        if nome not in zf.namelist():
            return
        with zf.open(nome) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")

    meta_csv = next((n for n in zf.namelist() if re.fullmatch(r"dfp_cia_aberta_\d{4}\.csv", n)), None)
    if meta_csv is None:
        return {}

    dados: dict[int, dict] = {}
    cod_por_cnpj: dict[str, int] = {}
    for linha in _ler(meta_csv):
        try:
            cd = int(linha["CD_CVM"])
        except (ValueError, KeyError, TypeError):
            continue
        if cd not in cod_cvms:
            continue
        versao = int(linha.get("VERSAO") or 1)
        alvo = dados.setdefault(cd, {"versao": 0})
        if versao >= alvo["versao"]:  # fica a versão vigente (a maior)
            alvo["versao"] = versao
            alvo["dt_receb"] = (linha.get("DT_RECEB") or "").strip() or None
        cod_por_cnpj[linha.get("CNPJ_CIA") or ""] = cd

    sufixo = meta_csv.replace("dfp_cia_aberta_", "").replace(".csv", "")
    capital_versao: dict[int, int] = {}
    for linha in _ler(f"dfp_cia_aberta_composicao_capital_{sufixo}.csv"):
        cd = cod_por_cnpj.get(linha.get("CNPJ_CIA") or "")
        if cd is None:
            continue
        versao = int(linha.get("VERSAO") or 1)
        if versao < capital_versao.get(cd, 0):
            continue
        capital_versao[cd] = versao
        alvo = dados.setdefault(cd, {"versao": versao})
        alvo["acoes_total"] = _num(linha.get("QT_ACAO_TOTAL_CAP_INTEGR"))
        alvo["acoes_tesouro"] = _num(linha.get("QT_ACAO_TOTAL_TESOURO"))

    parecer_versao: dict[int, int] = {}
    textos: dict[int, list[str]] = {}
    for linha in _ler(f"dfp_cia_aberta_parecer_{sufixo}.csv"):
        if "Auditor Independente" not in (linha.get("TP_PARECER_DECL") or ""):
            continue  # declarações de diretoria/conselho fiscal não são o parecer
        if "Declara" in (linha.get("TP_PARECER_DECL") or ""):
            continue  # "Declaração dos Diretores sobre o Relatório do Auditor"
        cd = cod_por_cnpj.get(linha.get("CNPJ_CIA") or "")
        if cd is None:
            continue
        versao = int(linha.get("VERSAO") or 1)
        if versao < parecer_versao.get(cd, 0):
            continue
        if versao > parecer_versao.get(cd, 0):
            textos[cd] = []  # versão mais nova zera o texto acumulado
        parecer_versao[cd] = versao
        alvo = dados.setdefault(cd, {"versao": versao})
        tipo = (linha.get("TP_RELAT_AUD") or "").strip()
        if tipo:
            alvo["parecer_tipo"] = tipo
        textos.setdefault(cd, []).append(linha.get("TXT_PARECER_DECL") or "")

    for cd, partes in textos.items():
        texto = " ".join(partes)
        resultado = modulo_parecer.classificar(texto)
        alvo = dados[cd]
        alvo["parecer_continuidade"] = 1 if resultado.get("continuidade") else 0
        if resultado.get("continuidade"):
            # a evidência tem que ser a FRASE DA CONTINUIDADE (não a da opinião,
            # que diz "apresentam adequadamente" e contradiz o alerta)
            alvo["parecer_trecho"] = modulo_parecer.trecho_continuidade(texto)[:300] or None

    return dados


def atualizar_auditores(con: sqlite3.Connection, hoje: date | None = None) -> int:
    """Histórico de auditores via FCA (Formulário Cadastral): cada linha traz o
    auditor com a JANELA de atuação (início/fim) — um ano de FCA cobre o
    histórico. Matéria-prima da regra 'troca frequente de auditor'."""
    import urllib.error
    import urllib.request

    from .. import armazenamento

    hoje = hoje or date.today()
    cnpj_para_cod = {
        armazenamento.so_digitos(l["cnpj"]): str(l["cod_cvm"])
        for l in con.execute("SELECT cnpj, cod_cvm FROM empresas WHERE no_ibrx100 = 1")
    }
    if not cnpj_para_cod:
        return 0
    total = 0
    for ano in (hoje.year, hoje.year - 1):  # o zip do ano corrente pode não existir ainda
        url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(requisicao, timeout=120) as resposta:
                conteudo = resposta.read()
        except (urllib.error.URLError, OSError):
            continue
        zf = zipfile.ZipFile(io.BytesIO(conteudo))
        nome = next((n for n in zf.namelist() if "auditor" in n.lower()), None)
        if nome is None:
            continue
        with zf.open(nome) as f:
            for linha in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"):
                cod = cnpj_para_cod.get(armazenamento.so_digitos(linha.get("CNPJ_Companhia") or ""))
                auditor = (linha.get("Auditor") or "").strip()
                if not cod or not auditor:
                    continue
                con.execute(
                    "INSERT OR REPLACE INTO auditores (cod_cvm, auditor, inicio, fim) VALUES (?, ?, ?, ?)",
                    (
                        cod, auditor,
                        (linha.get("Data_Inicio_Atuacao_Auditor") or "").strip() or None,
                        (linha.get("Data_Fim_Atuacao_Auditor") or "").strip() or None,
                    ),
                )
                total += 1
        con.commit()
        break  # o primeiro ano disponível já traz as janelas históricas
    return total


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
        for cod_cvm, meta in extrair_meta_ano(conteudo, cod_cvms).items():
            con.execute(
                """
                INSERT OR REPLACE INTO dfp_meta
                    (cod_cvm, ano, dt_receb, versao, acoes_total, acoes_tesouro,
                     parecer_tipo, parecer_continuidade, parecer_trecho)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(cod_cvm), ano,
                    meta.get("dt_receb"), meta.get("versao"),
                    meta.get("acoes_total"), meta.get("acoes_tesouro"),
                    meta.get("parecer_tipo"), meta.get("parecer_continuidade"),
                    meta.get("parecer_trecho"),
                ),
            )
        for cod_cvm, campos in dados.items():
            con.execute(
                """
                INSERT OR REPLACE INTO fundamentos
                    (cod_cvm, ano, receita, resultado_bruto, ebit, lucro_liquido,
                     ativo_total, patrimonio_liquido, caixa, divida_bruta, da, setor_financeiro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(cod_cvm), ano,
                    campos.get("receita"), campos.get("resultado_bruto"),
                    campos.get("ebit"), campos.get("lucro_liquido"),
                    campos.get("ativo_total"), campos.get("patrimonio_liquido"),
                    campos.get("caixa"), campos.get("divida_bruta"),
                    campos.get("da"),
                    campos.get("setor_financeiro", 0),
                ),
            )
        con.execute(
            "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, ?)",
            (marcador, hoje.isoformat()),
        )
        con.commit()
        novos_anos += 1

    # auditores (FCA): 1 download leve, incremental por ano — janelas de atuação
    marcador_fca = f"FCA_{hoje.year}"
    if marcador_fca not in carregados:
        try:
            registros = atualizar_auditores(con, hoje)
            if registros:
                con.execute(
                    "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, ?)",
                    (marcador_fca, hoje.isoformat()),
                )
                con.commit()
        except Exception:  # FCA fora do ar não derruba a carga da DFP
            pass

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
    ebit = v("ebit")
    da = v("da")
    financeiro = bool(v("setor_financeiro"))

    def pct(numerador, denominador):
        if numerador is None or not denominador:
            return None
        return 100 * numerador / denominador

    divida_liquida = None
    if not financeiro and divida is not None:
        divida_liquida = divida - (caixa or 0.0)

    # EBITDA = EBIT + D&A (não se aplica a banco/seguradora, que não têm EBIT)
    ebitda = (ebit + da) if (ebit is not None and da is not None and not financeiro) else None

    return {
        "margem_bruta": None if financeiro else pct(bruto, receita),
        "margem_liquida": pct(lucro, receita),
        "roe": pct(lucro, pl),
        "ebitda": ebitda,
        "margem_ebitda": pct(ebitda, receita),
        "divida_liquida": divida_liquida,
        "divida_liquida_pl": (divida_liquida / pl) if (divida_liquida is not None and pl) else None,
        "setor_financeiro": financeiro,
    }


def multiplos(preco, dividendos_12m, lucro, patrimonio_liquido, acoes_total) -> dict:
    """P/L, P/VP e DY (%) de um PAPEL, a partir do preço + ações em circulação
    (B3) + último balanço. LPA = lucro/ações, VPA = PL/ações. Cada um é None
    quando falta o dado ou não faz sentido — P/L só com lucro POSITIVO (empresa
    no prejuízo não tem P/L útil); nunca um número inventado."""
    lpa = (lucro / acoes_total) if (lucro is not None and acoes_total) else None
    vpa = (patrimonio_liquido / acoes_total) if (patrimonio_liquido is not None and acoes_total) else None
    return {
        "pl": (preco / lpa) if (preco and lpa and lpa > 0) else None,
        "pvp": (preco / vpa) if (preco and vpa and vpa > 0) else None,
        "dy": (100 * dividendos_12m / preco) if (preco and dividendos_12m is not None) else None,
    }


def multiplos_do_papel(con: sqlite3.Connection, ticker: str, hoje: date | None = None) -> dict:
    """Junta preço (fechamento D-1), ações em circulação, último balanço e os
    proventos dos últimos 12 meses para calcular P/L, P/VP e DY do ticker."""
    hoje = hoje or date.today()
    ticker = ticker.strip().upper()
    papel = con.execute("SELECT cod_cvm FROM papeis WHERE ticker = ?", (ticker,)).fetchone()
    if papel is None:
        return {"pl": None, "pvp": None, "dy": None}
    cod_cvm = papel["cod_cvm"]
    empresa = con.execute("SELECT acoes_total FROM empresas WHERE cod_cvm = ?", (cod_cvm,)).fetchone()
    balanco = con.execute(
        "SELECT lucro_liquido, patrimonio_liquido FROM fundamentos WHERE cod_cvm = ? ORDER BY ano DESC LIMIT 1",
        (cod_cvm,),
    ).fetchone()
    meta = armazenamento.cotacao_meta(con, ticker)
    return multiplos(
        preco=meta["preco_atual"] if meta else None,
        dividendos_12m=armazenamento.proventos_12m(con, ticker, hoje),
        lucro=balanco["lucro_liquido"] if balanco else None,
        patrimonio_liquido=balanco["patrimonio_liquido"] if balanco else None,
        acoes_total=empresa["acoes_total"] if empresa else None,
    )
