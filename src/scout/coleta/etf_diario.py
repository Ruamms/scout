"""Informe DIÁRIO dos ETFs (FNET) — cota patrimonial, PL fresco e cotistas.

Descoberta do probe (23/07/2026): todo ETF publica no FNET o "Informe Diário"
como XML estruturado (`urn:infdiario`) com a COTA PATRIMONIAL (VL_QUOTA), o
patrimônio líquido do dia (PATRIM_LIQ) e o número de cotistas (NR_COTST) —
é a peça que faltava para o PRÊMIO/DESCONTO (preço de mercado vs cota) e
para os cotistas dos ETFs (pendências do E2/E4).

Coleta diária no mesmo desenho do etf_renda: 1 listagem FNET por ETF +
download SÓ do informe mais recente que ainda não temos; rede em paralelo,
gravação em série; 2ª passada para as buscas que oscilarem.
"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import fnet

TIPO_DOCUMENTO = "informe diário"
TRABALHADORES = 8


def _numero(texto: str | None) -> float | None:
    """Números do informe vêm em pt-BR ('11163549113,66')."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extrair_informe(conteudo_xml: bytes) -> dict | None:
    """{data, vl_quota, patrim_liq, cotistas} do XML urn:infdiario, ou None."""
    try:
        raiz = ET.fromstring(conteudo_xml)
    except ET.ParseError:
        return None
    ns = {"d": "urn:infdiario"}
    competencia = (raiz.findtext(".//d:CAB_INFORM/d:DT_COMPT", namespaces=ns) or "").strip()
    if len(competencia) != 10:  # dd/mm/aaaa
        return None
    informe = raiz.find(".//d:LISTA_INFORM/d:INFORM", namespaces=ns)
    if informe is None:
        return None
    cotistas = _numero(informe.findtext("d:NR_COTST", namespaces=ns))
    return {
        "data": f"{competencia[6:10]}-{competencia[3:5]}-{competencia[:2]}",
        "vl_quota": _numero(informe.findtext("d:VL_QUOTA", namespaces=ns)),
        "patrim_liq": _numero(informe.findtext("d:PATRIM_LIQ", namespaces=ns)),
        "cotistas": int(cotistas) if cotistas is not None else None,
    }


def atualizar_diarios(
    con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None
) -> str | None:
    """1x/dia: o informe mais recente de cada ETF (o histórico nasce da coleta
    diária e engorda com o tempo — mesma honestidade do preço de RF)."""
    hoje = hoje or date.today()
    carga = con.execute(
        "SELECT carregado_em FROM cargas WHERE arquivo = 'ETF_DIARIO'"
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
        for linha in con.execute("SELECT cnpj, id_doc FROM etf_diario")
    )

    def _coletar(etf) -> tuple[dict, tuple | None, bool]:
        """SÓ REDE (thread-safe): lista os últimos docs e baixa o informe
        diário mais recente que ainda não temos."""
        try:
            documentos = fnet.listar(etf["cnpj"], quantidade=10, timeout=12, tentativas=1)
        except Exception:
            return etf, None, True
        diario = next(
            (d for d in documentos if d["tipo"].lower() == TIPO_DOCUMENTO), None
        )
        if diario is None or (etf["cnpj"], diario["id"]) in conhecidos:
            return etf, None, False
        try:
            informe = extrair_informe(fnet.baixar(diario["id"], timeout=30, tentativas=1))
        except Exception:
            return etf, None, True
        if informe is None:
            return etf, None, False
        return etf, (
            etf["cnpj"], informe["data"], informe["vl_quota"],
            informe["patrim_liq"], informe["cotistas"], diario["id"],
        ), False

    def _processar(lista: list, progresso: bool = True) -> tuple[int, list]:
        novos = 0
        falharam = []
        with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
            for feitos, (etf, linha, falhou) in enumerate(
                executor.map(_coletar, lista), start=1
            ):
                if falhou:
                    falharam.append(etf)
                elif linha:
                    con.execute(
                        "INSERT OR REPLACE INTO etf_diario "
                        "(cnpj, data, vl_quota, patrim_liq, cotistas, id_doc) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        linha,
                    )
                    con.commit()
                    novos += 1
                if progresso and ao_progredir and feitos % 25 == 0:
                    ao_progredir(f"informes diários de ETF: {feitos}/{len(lista)} varridos")
        return novos, falharam

    novos, falharam = _processar(etfs)
    if falharam:
        if ao_progredir:
            ao_progredir(f"informes diários: repetindo {len(falharam)} buscas que oscilaram")
        recuperados, _ = _processar(falharam, progresso=False)
        novos += recuperados
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES ('ETF_DIARIO', ?)",
        (hoje.isoformat(),),
    )
    con.commit()
    total = con.execute("SELECT COUNT(DISTINCT cnpj) FROM etf_diario").fetchone()[0]
    mensagem = f"informes diários de ETF: {novos} novos ({total} fundos com cota patrimonial)"
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
