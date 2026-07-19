"""Fundos listados na B3 — API pública `fundsListedProxy` (a mesma do site
"Fundos Listados" da B3, sem chave).

É a fonte do mapeamento ticker↔CNPJ dos ETFs: a listagem traz o radical e a
razão social; o detalhe traz o código de negociação (ex.: BOVA11) e o CNPJ.
`typeFund`: "ETF" = renda variável · "ETF-RF" = renda fixa (estes NÃO negociam
no COTAHIST — ver docs/ETFS.md) · "ETF-Cripto" = criptoativos.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import time
import urllib.request
from datetime import date, datetime

from .. import armazenamento

URL_BASE = "https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/{endpoint}/{token}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (scout)"}
TIPOS = ("ETF", "ETF-RF", "ETF-Cripto")
DIAS_FRESCOR = 7  # a lista de ETFs muda devagar; 1 refresh por semana basta


def _chamar(endpoint: str, parametros: dict) -> dict:
    token = base64.b64encode(json.dumps(parametros).encode()).decode()
    requisicao = urllib.request.Request(
        URL_BASE.format(endpoint=endpoint, token=token), headers=_HEADERS
    )
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return json.load(resposta)


def listar(tipo: str) -> list[dict]:
    """Todos os fundos listados de um tipo (paginado)."""
    fundos: list[dict] = []
    pagina = 1
    while True:
        dados = _chamar(
            "GetListFunds",
            {"language": "pt-br", "typeFund": tipo, "pageNumber": pagina, "pageSize": 100},
        )
        resultados = dados.get("results") or []
        fundos.extend(resultados)
        total_paginas = (dados.get("page") or {}).get("totalPages") or 1
        if pagina >= total_paginas:
            return fundos
        pagina += 1


def detalhar(id_fnet: int, radical: str, tipo: str) -> dict:
    """Detalhe do fundo: tradingCode (ticker), cnpj, administrador etc."""
    return _chamar(
        "GetDetailFund",
        {"language": "pt-br", "idFNET": str(id_fnet), "idCEM": radical, "typeFund": tipo},
    )


def atualizar_etfs(
    con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None
) -> str | None:
    """Sincroniza a tabela `etfs` (1x/semana): lista os dois tipos e busca o
    detalhe (ticker+CNPJ) só de quem ainda não temos — com pausa de cortesia."""
    hoje = hoje or date.today()
    listados = con.execute(
        "SELECT COUNT(*) FROM etfs WHERE listado IS NULL OR listado = 1"
    ).fetchone()[0]
    carga = con.execute(
        "SELECT carregado_em FROM cargas WHERE arquivo = 'ETFS_B3'"
    ).fetchone()
    # respeita o frescor semanal, MENOS quando não há ETF listado — aí re-sincroniza
    # para se auto-curar (foi assim que o site zerou os ETFs)
    if carga and carga[0] and listados > 0:
        idade = (hoje - date.fromisoformat(str(carga[0])[:10])).days
        if idade < DIAS_FRESCOR:
            return None

    conhecidos = {
        linha[0] for linha in con.execute("SELECT id_fnet FROM etfs WHERE ticker IS NOT NULL")
    }
    novos = 0
    na_listagem: set[int] = set()
    for tipo in TIPOS:
        for fundo in listar(tipo):
            id_fnet = fundo.get("id")
            radical = (fundo.get("acronym") or "").strip()
            if id_fnet:
                na_listagem.add(id_fnet)
            if not id_fnet or not radical or id_fnet in conhecidos:
                continue
            detalhe = detalhar(id_fnet, radical, tipo)
            time.sleep(0.25)  # educação com a fonte
            cnpj = armazenamento.so_digitos(detalhe.get("cnpj"))
            ticker = (detalhe.get("tradingCode") or "").strip().upper() or f"{radical}11"
            if not cnpj:
                continue
            con.execute(
                """
                INSERT OR REPLACE INTO etfs
                    (cnpj, ticker, radical, id_fnet, tipo_b3, denominacao, nome_pregao, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cnpj,
                    ticker,
                    radical,
                    id_fnet,
                    tipo,
                    (fundo.get("fundName") or "").strip() or None,
                    (fundo.get("tradingName") or "").strip() or None,
                    hoje.isoformat(),
                ),
            )
            novos += 1
    # quem sumiu da listagem foi deslistado: sai do site e do lote na hora.
    # Linhas de curadoria manual (sem id_fnet, ex.: XFIX11) nunca são mexidas.
    # SEGURANÇA: só deslista se a listagem veio SAUDÁVEL (perto do que já temos).
    # Uma resposta parcial/degradada da B3 (ex.: proxy inacessível do GitHub
    # Actions devolvendo poucos/zero resultados) marcaria quase tudo como
    # deslistado e zeraria os ETFs do site — foi o que aconteceu.
    ja_listados = con.execute(
        "SELECT COUNT(*) FROM etfs WHERE id_fnet IS NOT NULL AND (listado IS NULL OR listado = 1)"
    ).fetchone()[0]
    # saudável = trouxe pelo menos 80% do que já tínhamos; abaixo disso é fonte
    # degradada e não se deslista nada (senão zeraria o site num erro da B3)
    listagem_saudavel = len(na_listagem) >= int(0.8 * ja_listados)
    deslistados = 0
    if listagem_saudavel:
        for linha in con.execute(
            "SELECT cnpj, ticker, id_fnet, listado FROM etfs WHERE id_fnet IS NOT NULL"
        ).fetchall():
            esta = 1 if linha["id_fnet"] in na_listagem else 0
            if esta != (1 if linha["listado"] in (None, 1) else 0):
                con.execute("UPDATE etfs SET listado = ? WHERE cnpj = ?", (esta, linha["cnpj"]))
                if not esta:
                    deslistados += 1
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES ('ETFS_B3', ?)",
        (hoje.isoformat(),),
    )
    con.commit()
    total = con.execute(
        "SELECT COUNT(*) FROM etfs WHERE listado IS NULL OR listado = 1"
    ).fetchone()[0]
    mensagem = f"ETFs listados na B3: {total} no total ({novos} novos nesta rodada)"
    if not listagem_saudavel and ja_listados:
        mensagem += (
            f" · listagem parcial ({len(na_listagem)} de ~{ja_listados}) — "
            "deslistagem pulada por segurança"
        )
    if deslistados:
        mensagem += f" · {deslistados} saíram da listagem (deslistados)"
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
