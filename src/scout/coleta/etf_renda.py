"""Proventos em dinheiro dos ETFs — a geração distribuidora.

A maioria dos ETFs reinveste tudo; os distribuidores anunciam cada provento
no FNET como documento ESTRUTURADO ("Aviso aos Cotistas - Estruturado /
Proventos em dinheiro"), um XML limpo com valor por cota, datas e até o
aviso de que o rendimento NÃO é isento de IR (diferente de FII).

Coleta diária: 1 listagem FNET por ETF + download apenas dos avisos novos.
A busca do FNET oscila (timeouts intermitentes), então a varredura é feita em
PARALELO — só a rede; as gravações no banco ficam em série (SQLite não é
thread-safe). Isso mantém a rodada em ~2 min mesmo com muitos ETFs, e escala
para as próximas classes de ativo.
"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .. import armazenamento
from . import fnet

TIPO_DOCUMENTO = "proventos em dinheiro"
TRABALHADORES = 8  # requisições FNET simultâneas na varredura (rede paralela)


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
    """1x/dia: varre o FNET de cada ETF atrás de avisos de proventos e baixa
    só os documentos que ainda não temos. Diário (não semanal) por escolha do
    dono: o download é incremental, então rodar todo dia mantém a base sempre
    em dia — melhor do que ficar até uma semana atrasado."""
    hoje = hoje or date.today()
    carga = con.execute(
        "SELECT carregado_em FROM cargas WHERE arquivo = 'ETF_PROVENTOS'"
    ).fetchone()
    if carga and str(carga[0])[:10] == hoje.isoformat():
        return None  # já rodou hoje
    etfs = [
        {"cnpj": linha["cnpj"], "ticker": linha["ticker"]}
        for linha in con.execute(
            "SELECT cnpj, ticker FROM etfs WHERE ticker IS NOT NULL AND ticker <> ''"
        )
    ]
    conhecidos = frozenset(
        (linha[0], linha[1])
        for linha in con.execute("SELECT cnpj, id_doc FROM etf_proventos")
    )

    def _coletar(etf) -> tuple[dict, list, bool]:
        """SÓ REDE (thread-safe — não toca no banco): busca os documentos do ETF
        e baixa os avisos novos. Retorna (etf, linhas_para_gravar, falhou_busca)."""
        try:
            # timeout curto na varredura em lote: a busca do FNET oscila e
            # pendura de forma intermitente; 60s×3 por fundo travava a rodada
            documentos = fnet.listar(etf["cnpj"], quantidade=40, timeout=12, tentativas=1)
        except Exception:
            return etf, [], True
        linhas = []
        for documento in documentos:
            if documento["tipo"].lower() != TIPO_DOCUMENTO:
                continue
            if (etf["cnpj"], documento["id"]) in conhecidos:
                continue
            try:
                # timeout curto também no download (o aviso é um XML pequeno)
                proventos = extrair_proventos(fnet.baixar(documento["id"], timeout=30, tentativas=1))
            except Exception:
                continue
            for provento in proventos:
                linhas.append(
                    (
                        etf["cnpj"],
                        documento["id"],
                        provento["ticker"] or etf["ticker"],
                        provento["data_base"],
                        provento["valor"],
                        provento["data_pagamento"],
                        1 if provento["isento"] else 0,
                    )
                )
        return etf, linhas, False

    def _processar(lista: list, progresso: bool = True) -> tuple[int, list]:
        """Coleta em PARALELO (pool de rede) e grava no banco na thread principal
        (SQLite não é thread-safe). Retorna (avisos novos, ETFs que oscilaram)."""
        novos = 0
        falharam = []
        with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
            for feitos, (etf, linhas, falhou) in enumerate(
                executor.map(_coletar, lista), start=1
            ):
                if falhou:
                    falharam.append(etf)
                elif linhas:
                    con.executemany(
                        "INSERT OR REPLACE INTO etf_proventos "
                        "(cnpj, id_doc, ticker, data_base, valor, data_pagamento, isento) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        linhas,
                    )
                    con.commit()  # incremental: Ctrl+C não perde o já baixado
                    novos += len(linhas)
                # progresso visível: sem isto a etapa parece "travada no 100%"
                if progresso and ao_progredir and feitos % 25 == 0:
                    ao_progredir(
                        f"proventos de ETF: {feitos}/{len(lista)} varridos"
                        f"{f' ({len(falharam)} a repetir)' if falharam else ''}"
                    )
        return novos, falharam

    novos, falharam = _processar(etfs)
    # 2ª passada só nos que a busca oscilou (o FNET costuma responder na repetição)
    if falharam:
        if ao_progredir:
            ao_progredir(f"proventos de ETF: repetindo {len(falharam)} buscas que oscilaram")
        recuperados, _ = _processar(falharam, progresso=False)
        novos += recuperados
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
