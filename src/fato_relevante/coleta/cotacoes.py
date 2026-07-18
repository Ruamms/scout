"""Coleta de cotações (candles mensais) via API pública do Yahoo Finance.

Sem chave/cadastro: é a única fonte gratuita que funciona de primeira
para quem clonar o projeto. A camada é isolada de propósito — trocar de
provedor no futuro é reescrever só este arquivo.

A sincronização é preguiçosa e diária: `garantir_atualizada` só vai à
rede se a última sincronização do ticker não for de hoje; sem conexão,
a análise segue com o cache e um aviso.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import date, datetime, timezone

from .. import armazenamento

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=max&interval=1mo"
_HEADERS = {"User-Agent": "Mozilla/5.0 (fato-relevante)"}


def garantir_atualizada(con: sqlite3.Connection, ticker: str, hoje: date | None = None) -> str | None:
    """Sincroniza as cotações do ticker se necessário.

    Retorna None quando está tudo certo, ou uma mensagem de aviso para
    exibir ao usuário (cache antigo ou cotação indisponível).
    """
    ticker = ticker.strip().upper()
    hoje = hoje or date.today()
    meta = armazenamento.cotacao_meta(con, ticker)
    if meta is not None and meta["atualizado_em"] == hoje.isoformat():
        return None
    try:
        candles, preco_atual, cotado_em = buscar(ticker)
    except Exception:
        if meta is not None:
            return f"sem conexão com a fonte de cotações — usando cache de {_data_br(meta['cotado_em'])}"
        return "cotação de bolsa indisponível para este ticker (sem conexão ou ticker não listado)"
    armazenamento.gravar_cotacoes(con, ticker, candles, preco_atual, cotado_em, hoje.isoformat())
    return None


def buscar(ticker: str) -> tuple[list[tuple[str, float, float]], float, str]:
    url = URL.format(simbolo=f"{ticker}.SA")
    requisicao = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        dados = json.load(resposta)
    return extrair(dados)


def extrair(dados: dict) -> tuple[list[tuple[str, float, float]], float, str]:
    """Converte o JSON do Yahoo em (candles, preço atual, data do pregão).

    Cada candle é (competencia AAAA-MM, fechamento, fechamento_ajustado).
    O fechamento do Yahoo já vem ajustado por desdobramento; o ajustado
    inclui também proventos.
    """
    resultado = dados["chart"]["result"][0]
    timestamps = resultado["timestamp"]
    fechamentos = resultado["indicators"]["quote"][0]["close"]
    ajustados = resultado["indicators"].get("adjclose", [{}])[0].get("adjclose") or fechamentos

    candles = []
    for ts, fechamento, ajustado in zip(timestamps, fechamentos, ajustados):
        if fechamento is None:
            continue
        competencia = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
        candles.append((competencia, fechamento, ajustado))

    meta = resultado["meta"]
    preco_atual = meta["regularMarketPrice"]
    cotado_em = datetime.fromtimestamp(meta["regularMarketTime"], tz=timezone.utc).strftime("%Y-%m-%d")
    return candles, preco_atual, cotado_em


def _data_br(iso: str | None) -> str:
    if not iso or len(iso) < 10:
        return "?"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
