"""Proventos em dinheiro dos ETFs — a geração distribuidora.

A maioria dos ETFs reinveste tudo; os distribuidores anunciam cada provento
no FNET como documento ESTRUTURADO ("Aviso aos Cotistas - Estruturado /
Proventos em dinheiro"), um XML limpo com valor por cota, datas e até o
aviso de que o rendimento NÃO é isento de IR (diferente de FII).

Coleta semanal: 1 listagem FNET por ETF + download apenas dos avisos novos.
"""

from __future__ import annotations

import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import date

from .. import armazenamento
from . import fnet

DIAS_FRESCOR = 7
TIPO_DOCUMENTO = "proventos em dinheiro"


def extrair_proventos(conteudo_xml: bytes) -> list[dict]:
    """[{ticker, data_base, valor, data_pagamento, isento}] do XML do FNET."""
    try:
        raiz = ET.fromstring(conteudo_xml)
    except ET.ParseError:
        return []
    proventos = []
    for provento in raiz.iter("Provento"):
        ticker = (provento.findtext("CodNegociacao") or "").strip().upper()
        for rendimento in provento.iter("Rendimento"):
            try:
                valor = float(rendimento.findtext("ValorProvento") or 0)
            except ValueError:
                continue
            if valor <= 0:
                continue
            proventos.append(
                {
                    "ticker": ticker,
                    "data_base": (rendimento.findtext("DataBase") or "").strip(),
                    "valor": valor,
                    "data_pagamento": (rendimento.findtext("DataPagamento") or "").strip(),
                    "isento": (rendimento.findtext("RendimentoIsentoIR") or "").strip().lower() == "sim",
                }
            )
    return proventos


def atualizar_proventos(
    con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None
) -> str | None:
    """1x/semana: varre o FNET de cada ETF atrás de avisos de proventos e
    baixa só os documentos que ainda não temos."""
    hoje = hoje or date.today()
    carga = con.execute(
        "SELECT carregado_em FROM cargas WHERE arquivo = 'ETF_PROVENTOS'"
    ).fetchone()
    if carga and carga[0]:
        idade = (hoje - date.fromisoformat(str(carga[0])[:10])).days
        if idade < DIAS_FRESCOR:
            return None
    etfs = con.execute(
        "SELECT cnpj, ticker FROM etfs WHERE ticker IS NOT NULL AND ticker <> ''"
    ).fetchall()
    conhecidos = {
        (linha[0], linha[1])
        for linha in con.execute("SELECT cnpj, id_doc FROM etf_proventos")
    }

    def _varrer(etf) -> int | None:
        """Baixa os proventos NOVOS de um ETF. Retorna o nº de avisos gravados,
        ou None quando a busca do FNET falhou (candidato à repetição)."""
        try:
            # timeout curto na varredura em lote: a busca do FNET oscila e
            # pendura de forma intermitente; 60s×3 por fundo travava a rodada
            documentos = fnet.listar(etf["cnpj"], quantidade=40, timeout=12, tentativas=1)
        except Exception:
            return None
        novos_no_etf = 0
        for documento in documentos:
            if documento["tipo"].lower() != TIPO_DOCUMENTO:
                continue
            if (etf["cnpj"], documento["id"]) in conhecidos:
                continue
            try:
                # timeout curto também no download (o aviso de proventos é um
                # XML pequeno); um download pendurado não pode custar 9 min
                proventos = extrair_proventos(fnet.baixar(documento["id"], timeout=30, tentativas=1))
            except Exception:
                continue
            for provento in proventos:
                con.execute(
                    """
                    INSERT OR REPLACE INTO etf_proventos
                        (cnpj, id_doc, ticker, data_base, valor, data_pagamento, isento)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        etf["cnpj"],
                        documento["id"],
                        provento["ticker"] or etf["ticker"],
                        provento["data_base"],
                        provento["valor"],
                        provento["data_pagamento"],
                        1 if provento["isento"] else 0,
                    ),
                )
                novos_no_etf += 1
        # grava a cada ETF com novidade: Ctrl+C na varredura longa não perde o baixado
        if novos_no_etf:
            con.commit()
        return novos_no_etf

    novos = 0
    falharam = []
    for indice, etf in enumerate(etfs, start=1):
        resultado = _varrer(etf)
        if resultado is None:
            falharam.append(etf)
        else:
            novos += resultado
        time.sleep(0.3)  # SEMPRE (educação + evita throttling do FNET)
        # progresso visível: sem isto a etapa parece "travada no 100%"
        if ao_progredir and indice % 25 == 0:
            ao_progredir(
                f"proventos de ETF: {indice}/{len(etfs)} varridos"
                f"{f' ({len(falharam)} a repetir)' if falharam else ''}"
            )
    # 2ª passada só nos que a busca oscilou (o FNET costuma responder na repetição)
    if falharam:
        if ao_progredir:
            ao_progredir(f"proventos de ETF: repetindo {len(falharam)} buscas que oscilaram")
        for etf in falharam:
            resultado = _varrer(etf)
            if resultado:
                novos += resultado
            time.sleep(0.3)
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES ('ETF_PROVENTOS', ?)",
        (hoje.isoformat(),),
    )
    con.commit()
    distribuidores = con.execute(
        "SELECT COUNT(DISTINCT cnpj) FROM etf_proventos"
    ).fetchone()[0]
    mensagem = (
        f"proventos de ETF (FNET): {novos} avisos novos · {distribuidores} ETFs distribuem renda"
    )
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
