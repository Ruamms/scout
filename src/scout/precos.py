"""Resolvedor único de preço de um ativo, por tipo.

A ideia (desenho do usuário): cada posição dentro de um ETF tem um TIPO
(ação, FII, ETF, renda fixa, exterior, cripto). Para reprecificar a carteira
"a preço de hoje", basta perguntar a este resolvedor o preço atual de cada
ativo — e cada tipo pluga na sua fonte:

- Ação / FII / ETF  -> já temos preço diário (fechamento D-1) em `cotacoes_meta`
  (COTAHIST da B3, codbdi 02/12/14). Acende HOJE.
- Título público federal -> PU oficial do MERCADO SECUNDÁRIO da ANBIMA
  (ms{AAMMDD}.txt, público, diário, sem autenticação) — cobre TODOS os
  vencimentos (o Tesouro Direto só tem os de varejo). A chave é
  (Código SELIC, vencimento), exatamente o que o CDA informa (CD_SELIC+DT_VENC).
- Debêntures / Exterior / Cripto -> ainda sem preço POR ATIVO; retorna None e a
  posição fica no valor informado à CVM. Quando a fonte existir, é só adicionar
  um ramo aqui — nada mais no resto do código muda ("deixa tudo pronto").

Nunca inventa preço: se não há fonte, é None.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

from . import armazenamento

_TICKER_ACAO = re.compile(r"^[A-Z]{4}\d{1,2}$")  # PETR4, VALE3, ITUB4…
_URL_ANBIMA = "https://www.anbima.com.br/informacoes/merc-sec/arqs/ms{d:%y%m%d}.txt"
_cache_anbima: dict | None = None  # {(cd_selic, venc_iso): {pu, titulo, data}} — 1 download por run


def _baixar_anbima(dia: date) -> bytes | None:
    import urllib.error
    import urllib.request

    try:
        requisicao = urllib.request.Request(
            _URL_ANBIMA.format(d=dia), headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            return resposta.read()
    except (urllib.error.URLError, OSError):
        return None


def _pu_titulos_publicos(hoje: date | None = None) -> dict:
    """PU indicativo da ANBIMA por (código SELIC, vencimento ISO). Tenta o dia
    mais recente e recua até 5 dias (fim de semana/feriado). Falhou tudo =
    dicionário vazio — as posições ficam no valor do CDA (nunca inventa)."""
    global _cache_anbima
    if _cache_anbima is not None:
        return _cache_anbima
    hoje = hoje or date.today()
    tabela: dict = {}
    for recuo in range(6):
        conteudo = _baixar_anbima(hoje - timedelta(days=recuo))
        if not conteudo:
            continue
        for linha in conteudo.decode("latin-1", "replace").splitlines():
            partes = linha.split("@")
            # Titulo@Data Referencia@Codigo SELIC@Data Base@Data Vencimento@...@PU@...
            if len(partes) < 9 or not partes[2].strip().isdigit():
                continue
            venc = partes[4].strip()  # AAAAMMDD
            if len(venc) != 8:
                continue
            try:
                pu = float(partes[8].replace(".", "").replace(",", "."))
            except ValueError:
                continue
            ref = partes[1].strip()
            tabela[(partes[2].strip(), f"{venc[:4]}-{venc[4:6]}-{venc[6:8]}")] = {
                "pu": pu,
                "titulo": partes[0].strip(),
                "data": f"{ref[:4]}-{ref[4:6]}-{ref[6:8]}" if len(ref) == 8 else "",
            }
        if tabela:
            break
    _cache_anbima = tabela
    return tabela


def ticker_para_preco(posicao: dict) -> str | None:
    """O ticker que usamos para buscar preço: o alvo já resolvido (FII/ETF pelo
    CNPJ do emissor) ou o próprio código quando é uma ação (CD_ATIVO da B3)."""
    alvo = posicao.get("ticker_alvo")
    if alvo:
        return alvo
    codigo = (posicao.get("codigo") or "").strip().upper()
    if _TICKER_ACAO.match(codigo):
        return codigo
    return None


def preco_por_ticker(con: sqlite3.Connection, ticker: str) -> dict | None:
    """{preco, cotado_em} do fechamento oficial mais recente, ou None."""
    meta = armazenamento.cotacao_meta(con, ticker)
    if meta is None or meta["preco_atual"] is None:
        return None
    return {"preco": meta["preco_atual"], "cotado_em": meta["cotado_em"]}


def reprecificar_posicoes(
    con: sqlite3.Connection, posicoes: list[dict]
) -> tuple[list[dict], dict]:
    """Enriquece cada posição com `preco_hoje`, `cotado_em` e `valor_hoje`
    (quantidade × preço, quando temos a quantidade). Devolve (posições, resumo),
    onde o resumo traz a COBERTURA: quanto da carteira (pelo peso do CDA) tem
    preço de hoje na nossa base."""
    enriquecidas: list[dict] = []
    peso_com_preco = 0.0
    valor_hoje_total = 0.0
    tem_algum_valor = False
    for posicao in posicoes:
        ticker = ticker_para_preco(posicao)
        cotacao = preco_por_ticker(con, ticker) if ticker else None
        nome_novo = None
        if cotacao is None:
            codigo = (posicao.get("codigo") or "").strip().upper()
            vencimento = posicao.get("vencimento")
            if codigo.startswith("TPF") and vencimento:
                titulo = _pu_titulos_publicos().get((codigo[3:], vencimento))
                if titulo:
                    cotacao = {"preco": titulo["pu"], "cotado_em": titulo["data"]}
                    # a ANBIMA dá o NOME do título (NTN-B, LTN…) que o CDA não traz
                    nome_novo = (
                        f"{titulo['titulo']} (venc. {vencimento[8:10]}/{vencimento[5:7]}/{vencimento[:4]})"
                    )
        quantidade = posicao.get("quantidade")
        valor_hoje = (
            cotacao["preco"] * quantidade if (cotacao and quantidade) else None
        )
        enriquecidas.append(
            {
                **posicao,
                **({"nome": nome_novo} if nome_novo else {}),
                "preco_hoje": cotacao["preco"] if cotacao else None,
                "cotado_em": cotacao["cotado_em"] if cotacao else None,
                "valor_hoje": valor_hoje,
            }
        )
        if cotacao:
            peso_com_preco += posicao.get("pct") or 0.0
        if valor_hoje is not None:
            valor_hoje_total += valor_hoje
            tem_algum_valor = True
    resumo = {
        "cobertura_pct": round(peso_com_preco, 1),  # % do peso da carteira com preço de hoje
        "valor_hoje_total": valor_hoje_total if tem_algum_valor else None,
    }
    return enriquecidas, resumo
