"""Cotações oficiais da B3 — arquivos históricos COTAHIST.

Fonte pública e documentada (Série Histórica de Cotações da B3), sem chave
e sem termos de uso restritivos: a base certa para um site público. Um
arquivo cobre TODOS os papéis do pregão de uma vez — nada de uma requisição
por ticker.

O COTAHIST traz preço NOMINAL (fechamento oficial). A B3 publica o arquivo
MENSAL só depois do mês fechar — o mês corrente vem dos arquivos DIÁRIOS
(COTAHIST_DDDMMAAAA, ~0,5 MB), que garantem o preço D-1. Os ajustes são
calculados aqui, de forma auditável:
- FII/ETF: desdobramento pelo mesmo algoritmo do ajuste de VP (salto >2,5x);
  proventos estimados por cota (DY informado à CVM × VP ajustado);
- ação: eventos societários REAIS da B3 (desdobramento/grupamento/bonificação)
  e dividendos/JCP declarados — nunca por salto de preço (queda forte num mês
  viraria split falso).
Tudo ancorado no preço atual.
"""

from __future__ import annotations

import io
import re
import sqlite3
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import date, datetime, timedelta

from .. import armazenamento, series

URL_ARQUIVO = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/{nome}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (scout)"}
ANO_INICIAL = 2011  # cobre o histórico que o site sempre exibiu

_CODNEG_FII = re.compile(r"[A-Z]{4}11")
_CODNEG_ACAO = re.compile(r"[A-Z]{4}(3|4|5|6|11)")  # ON/PN/PNA/PNB/unit


def nome_anual(ano: int) -> str:
    return f"COTAHIST_A{ano}.ZIP"


def nome_mensal(ano: int, mes: int) -> str:
    return f"COTAHIST_M{mes:02d}{ano}.ZIP"


def nome_diario(dia: date) -> str:
    return f"COTAHIST_D{dia.day:02d}{dia.month:02d}{dia.year}.ZIP"


def _dia_do_diario(nome: str) -> date:
    # COTAHIST_DddmmAAAA.ZIP -> dd em [10:12], mm em [12:14], AAAA em [14:18]
    return date(int(nome[14:18]), int(nome[12:14]), int(nome[10:12]))


def _baixar(nome: str, tentativas: int = 3) -> bytes:
    ultimo_erro: Exception | None = None
    url = URL_ARQUIVO.format(nome=nome)
    for tentativa in range(tentativas):
        try:
            requisicao = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(requisicao, timeout=600) as resposta:
                return resposta.read()
        except (urllib.error.URLError, OSError) as erro:
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(5 * (tentativa + 1) ** 2)
    raise ultimo_erro


# códigos BDI que nos interessam:
# 02 = ação do lote padrão · 12 = FII · 14 = ETF/cotas de fundo (renda variável)
CODBDIS = ("02", "12", "14")


def extrair_pregoes(
    conteudo: bytes, codbdis: tuple[str, ...] = CODBDIS
) -> dict[str, list[tuple[str, float, float]]]:
    """{ticker: [(dia AAAA-MM-DD, fechamento, volume R$), ...]} dos papéis.

    Registro tipo 01, códigos BDI de interesse (02 = ação, 12 = FII, 14 = ETF)
    e código de negociação padrão (XXXX11 para cotas; XXXX3/4/5/6/11 para
    ações — direitos e recibos ficam fora).
    Layout posicional oficial: PREULT em [108:121], VOLTOT em [170:188] (V99).
    """
    pregoes: dict[str, list[tuple[str, float, float]]] = {}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            for bruta in io.TextIOWrapper(fh, encoding="latin-1"):
                if not bruta.startswith("01") or bruta[10:12] not in codbdis:
                    continue
                codneg = bruta[12:24].strip()
                padrao = _CODNEG_ACAO if bruta[10:12] == "02" else _CODNEG_FII
                if not padrao.fullmatch(codneg):
                    continue
                dia = f"{bruta[2:6]}-{bruta[6:8]}-{bruta[8:10]}"
                fechamento = int(bruta[108:121]) / 100
                if fechamento <= 0:
                    continue
                try:
                    volume = int(bruta[170:188]) / 100
                except ValueError:
                    volume = 0.0
                pregoes.setdefault(codneg, []).append((dia, fechamento, volume))
    return pregoes


def gravar_pregoes(
    con: sqlite3.Connection,
    pregoes: dict[str, list[tuple[str, float, float]]],
    mesclar: bool = False,
) -> int:
    """Agrega por mês (fechamento do último pregão; volume = SOMA do mês).

    Com `mesclar` (arquivos DIÁRIOS), soma no acumulado existente do mês em
    vez de substituir — cada arquivo diário só entra uma vez (guard `cargas`)."""
    linhas = []
    for ticker, dias in pregoes.items():
        por_mes: dict[str, tuple[str, float]] = {}
        volume_mes: dict[str, float] = {}
        pregoes_mes: dict[str, int] = {}
        for registro in sorted(dias):
            dia, fechamento = registro[0], registro[1]
            volume = registro[2] if len(registro) > 2 else 0.0
            mes = dia[:7]
            por_mes[mes] = (dia, fechamento)
            volume_mes[mes] = volume_mes.get(mes, 0.0) + volume
            pregoes_mes[mes] = pregoes_mes.get(mes, 0) + 1
        for competencia, (dia, fechamento) in por_mes.items():
            linhas.append(
                (ticker, competencia, fechamento, dia, volume_mes[competencia], pregoes_mes[competencia])
            )
    if mesclar:
        for ticker, competencia, fechamento, dia, volume, npregoes in linhas:
            existente = con.execute(
                "SELECT fechamento, dia, volume, pregoes FROM cotacoes_b3"
                " WHERE ticker = ? AND competencia = ?",
                (ticker, competencia),
            ).fetchone()
            if existente is not None:
                volume += existente["volume"] or 0.0
                npregoes += existente["pregoes"] or 0
                if str(existente["dia"] or "") > dia:  # já temos pregão mais novo
                    fechamento, dia = existente["fechamento"], existente["dia"]
            con.execute(
                "INSERT OR REPLACE INTO cotacoes_b3"
                " (ticker, competencia, fechamento, dia, volume, pregoes) VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, competencia, fechamento, dia, volume, npregoes),
            )
    else:
        con.executemany(
            """
            INSERT OR REPLACE INTO cotacoes_b3
                (ticker, competencia, fechamento, dia, volume, pregoes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            linhas,
        )
    con.commit()
    return len(linhas)


def arquivos_pendentes(con: sqlite3.Connection, hoje: date) -> list[str]:
    """Anuais dos anos completos que faltam + mensais dos meses FECHADOS do
    ano corrente + DIÁRIOS do mês corrente (a B3 só publica o mensal depois
    do mês fechar; o preço D-1 vem dos diários). Quando o mensal sai, ele
    substitui o mês acumulado dos diários (autocorreção na virada)."""
    carregados = {linha[0] for linha in con.execute("SELECT arquivo FROM cargas")}
    pendentes = [
        nome_anual(ano) for ano in range(ANO_INICIAL, hoje.year) if nome_anual(ano) not in carregados
    ]
    for mes in range(1, hoje.month):
        nome = nome_mensal(hoje.year, mes)
        if nome not in carregados:
            pendentes.append(nome)
    dia = date(hoje.year, hoje.month, 1)
    while dia <= hoje:
        if dia.weekday() < 5 and nome_diario(dia) not in carregados:
            pendentes.append(nome_diario(dia))
        dia += timedelta(days=1)
    return pendentes


def atualizar(
    con: sqlite3.Connection,
    hoje: date | None = None,
    ao_progredir: Callable[[str], None] | None = None,
) -> list[str]:
    hoje = hoje or date.today()
    resumo = []
    for nome in arquivos_pendentes(con, hoje):
        diario = nome.startswith("COTAHIST_D")
        try:
            pregoes = extrair_pregoes(_baixar(nome))
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                # ainda não publicado (diário de hoje sai à noite; mensal sai
                # depois do fechamento) ou feriado sem pregão — diários de
                # dias passados não voltam a ser tentados
                if diario and _dia_do_diario(nome) < hoje:
                    con.execute(
                        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, 'indisponivel')",
                        (nome,),
                    )
                    con.commit()
                continue
            raise
        total = gravar_pregoes(con, pregoes, mesclar=diario)
        con.execute(
            "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, datetime('now'))",
            (nome,),
        )
        con.commit()
        mensagem = f"{nome}: {total} cotações mensais de {len(pregoes)} papéis"
        resumo.append(mensagem)
        if ao_progredir:
            ao_progredir(mensagem)
    if resumo:
        tickers = recalcular_derivadas(con)
        mensagem = f"cotações ajustadas (desdobramento + proventos) para {tickers} tickers"
        resumo.append(mensagem)
        if ao_progredir:
            ao_progredir(mensagem)
    return resumo


def garantir_mes_corrente(con: sqlite3.Connection, agora: datetime | None = None) -> str | None:
    """Busca o que falta (diários do mês corrente; o mensal recém-publicado
    na virada) no máximo 1x/dia. Retorna aviso quando a rede falhar."""
    agora = agora or datetime.now()
    carga = con.execute(
        "SELECT carregado_em FROM cargas WHERE arquivo = 'COTAHIST_DIA'"
    ).fetchone()
    if carga and str(carga[0])[:10] == agora.strftime("%Y-%m-%d"):
        return None
    try:
        atualizar(con, hoje=agora.date())
        con.execute(
            "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES ('COTAHIST_DIA', ?)",
            (agora.isoformat(timespec="seconds"),),
        )
        con.commit()
        return None
    except Exception:
        return "sem conexão com a B3 — usando o cache local de cotações"


def recalcular_derivadas(con: sqlite3.Connection, agora: datetime | None = None) -> int:
    """Reconstrói a tabela `cotacoes` (a que a análise lê) a partir do
    nominal da B3: fechamento ajustado por desdobramento + série de retorno
    total (proventos estimados pelos informes CVM), ancorada no preço atual."""
    agora = agora or datetime.now()
    atualizado_em = agora.isoformat(timespec="seconds")
    tickers = [
        linha[0] for linha in con.execute("SELECT DISTINCT ticker FROM cotacoes_b3")
    ]
    acoes = {linha[0] for linha in con.execute("SELECT ticker FROM papeis")}
    for ticker in tickers:
        linhas = con.execute(
            "SELECT competencia, fechamento, dia FROM cotacoes_b3 WHERE ticker = ? ORDER BY competencia",
            (ticker,),
        ).fetchall()
        bruta = [(linha["competencia"], linha["fechamento"]) for linha in linhas]
        if ticker in acoes:
            # ação: ajuste por eventos REAIS da B3 (nunca por salto de preço —
            # queda forte num mês viraria desdobramento falso) e proventos
            # declarados (dividendos/JCP) em R$ por ação
            eventos = _eventos_da_acao(con, ticker)
            ajustada_split = _ajustada_por_eventos(bruta, eventos)
            proventos = _proventos_acao_por_mes(con, ticker, eventos)
        else:
            ajustada_split = series.ajustada_por_evento_de_cotas(bruta)
            proventos = _proventos_por_mes(con, ticker)
        total = _retorno_total(ajustada_split, proventos)
        candles = [
            (competencia, fechamento, total.get(competencia, fechamento))
            for competencia, fechamento in ajustada_split
        ]
        ultimo = linhas[-1]
        # série 100% B3: derruba resíduos de fontes anteriores (Yahoo) do ticker
        con.execute("DELETE FROM cotacoes WHERE ticker = ?", (ticker,))
        armazenamento.gravar_cotacoes(
            con, ticker, candles, ultimo["fechamento"], ultimo["dia"], atualizado_em
        )
    return len(tickers)


def _eventos_da_acao(con: sqlite3.Connection, ticker: str) -> list[tuple[str, float]]:
    """(competência do evento, fator de QUANTIDADE) dos eventos societários
    reais da B3 — desdobramento/bonificação/grupamento."""
    return [
        (str(linha["data"])[:7], linha["fator"])
        for linha in con.execute(
            "SELECT data, fator FROM acao_eventos WHERE ticker = ? AND fator > 0 ORDER BY data",
            (ticker,),
        )
    ]


def _fator_acumulado(competencia: str, eventos: list[tuple[str, float]]) -> float:
    """Produto dos fatores de quantidade dos eventos POSTERIORES ao mês."""
    fator = 1.0
    for comp_evento, fator_qtd in eventos:
        if comp_evento > competencia:
            fator *= fator_qtd
    return fator


def _ajustada_por_eventos(
    bruta: list[tuple[str, float]], eventos: list[tuple[str, float]]
) -> list[tuple[str, float]]:
    """Fechamento ajustado: o preço anterior a um evento é dividido pelo
    fator de quantidade (split 2x → metade; grupamento 100:1 → ×100)."""
    return [
        (competencia, fechamento / _fator_acumulado(competencia, eventos))
        for competencia, fechamento in bruta
    ]


def _proventos_acao_por_mes(
    con: sqlite3.Connection, ticker: str, eventos: list[tuple[str, float]]
) -> dict[str, float]:
    """Dividendos/JCP declarados (R$ por ação) somados por competência da
    data "com", na MESMA base ajustada dos preços."""
    proventos: dict[str, float] = {}
    for linha in con.execute(
        "SELECT data_com, valor FROM acao_proventos WHERE ticker = ? AND valor > 0",
        (ticker,),
    ):
        competencia = str(linha["data_com"])[:7]
        valor = linha["valor"] / _fator_acumulado(competencia, eventos)
        proventos[competencia] = proventos.get(competencia, 0.0) + valor
    return proventos


def _proventos_por_mes(con: sqlite3.Connection, ticker: str) -> dict[str, float]:
    """Rendimento estimado por cota (R$) por competência, na base de cotas
    atual: DY mensal informado à CVM × VP/cota ajustado."""
    fundo = armazenamento.resolver_fundo(con, ticker)
    if fundo is None:
        return {}
    serie = armazenamento.serie_complemento(con, fundo.cnpj)
    vp_ajustada = series.serie_vp_ajustada(serie)
    return {
        linha["competencia"]: linha["dy_mes"] * vp_ajustada[linha["competencia"]]
        for linha in serie
        if series.dy_valido(linha["dy_mes"]) and vp_ajustada.get(linha["competencia"])
    }


def _retorno_total(
    ajustada_split: list[tuple[str, float]], proventos: dict[str, float]
) -> dict[str, float]:
    """Série de retorno total (preço + proventos reinvestidos), ancorada no
    último ponto = preço atual. Para trás: adj[t-1] = adj[t] × f[t-1] / (f[t] + prov[t])."""
    total: dict[str, float] = {}
    seguinte: tuple[str, float, float] | None = None  # (competencia, fech, adj)
    for competencia, fechamento in reversed(ajustada_split):
        if seguinte is None:
            valor = fechamento
        else:
            comp_seguinte, fech_seguinte, adj_seguinte = seguinte
            base = fech_seguinte + proventos.get(comp_seguinte, 0.0)
            valor = adj_seguinte * fechamento / base if base > 0 else fechamento
        total[competencia] = valor
        seguinte = (competencia, fechamento, valor)
    return total
