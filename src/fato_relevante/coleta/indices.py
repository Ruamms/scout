"""Coleta de índices de referência (CDI, IPCA) via API SGS do Banco Central.

Fonte oficial, gratuita e sem chave: https://api.bcb.gov.br
Valores são percentuais MENSAIS (ex.: 1.16 = 1,16% no mês).

IFIX: sem fonte pública programável hoje (Yahoo não tem histórico do
índice; Stooq exige desafio JS). Fica registrado como pendência.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import date

from .. import armazenamento

SERIES_SGS = {"CDI": 4391, "IPCA": 433}
URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial=01/01/2016"
)


def garantir_atualizados(con: sqlite3.Connection, hoje: date | None = None) -> str | None:
    """Sincroniza CDI e IPCA (1x/dia). Retorna aviso se ficou sem dado novo."""
    hoje = hoje or date.today()
    pendentes = [
        serie
        for serie in SERIES_SGS
        if (meta := armazenamento.indice_meta(con, serie)) is None
        or meta["atualizado_em"] != hoje.isoformat()
    ]
    if not pendentes:
        return None
    falhas = []
    for serie in pendentes:
        try:
            valores = buscar(serie)
        except Exception:
            falhas.append(serie)
            continue
        armazenamento.gravar_indice(con, serie, valores, hoje.isoformat())
    if falhas:
        tem_cache = all(armazenamento.serie_indice(con, serie) for serie in falhas)
        if tem_cache:
            return f"sem conexão com o Banco Central — usando cache de {'/'.join(falhas)}"
        return f"índices indisponíveis (sem conexão com o Banco Central): {'/'.join(falhas)}"
    return None


def buscar(serie: str) -> list[tuple[str, float]]:
    url = URL.format(codigo=SERIES_SGS[serie])
    requisicao = urllib.request.Request(url, headers={"User-Agent": "fato-relevante"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return extrair(json.load(resposta))


def extrair(dados: list[dict]) -> list[tuple[str, float]]:
    """Converte o JSON do SGS ([{'data': '01/MM/AAAA', 'valor': '1.16'}])."""
    valores = []
    for item in dados:
        data, valor = item.get("data", ""), item.get("valor", "")
        if len(data) < 10 or not valor:
            continue
        competencia = f"{data[6:10]}-{data[3:5]}"
        try:
            valores.append((competencia, float(valor)))
        except ValueError:
            continue
    return valores
