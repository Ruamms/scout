"""Coleta de documentos do FNET (B3): relatórios gerenciais e fatos relevantes.

API pública, sem chave. A pesquisa devolve JSON; o download devolve o PDF
direto. Os PDFs baixados ficam em `<dados>/documentos/<cnpj>/<id>.pdf` e o
índice vai para a tabela `documentos`.
"""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

from .. import armazenamento

URL_PESQUISA = (
    "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"
    "?d=0&s=0&l={quantidade}&o%5B0%5D%5BdataEntrega%5D=desc&cnpjFundo={cnpj}"
    "&idCategoriaDocumento=0&idTipoDocumento=0&idEspecieDocumento=0"
)
URL_DOWNLOAD = "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={id}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (scout)"}


def so_digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _abrir_com_retry(requisicao, timeout: int, tentativas: int = 3):
    """O FNET oscila (timeouts esporádicos); espera 5s/20s entre tentativas."""
    import time
    import urllib.error

    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            return urllib.request.urlopen(requisicao, timeout=timeout)
        except (urllib.error.URLError, OSError, TimeoutError) as erro:
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(5 * (tentativa + 1) ** 2)
    raise ultimo_erro


def listar(
    cnpj: str, quantidade: int = 30, timeout: int = 60, tentativas: int = 3
) -> list[dict]:
    """Documentos mais recentes do fundo no FNET (mais novo primeiro).

    `timeout`/`tentativas` são frouxos por padrão (leitura de UM fundo, robusta).
    Numa varredura em LOTE (etf_renda, 200+ fundos) convém passar valores curtos:
    a busca do FNET pendura para alguns CNPJs, e 60s×3 por fundo ruim trava a
    rodada inteira — melhor pular rápido e retomar na semana seguinte."""
    url = URL_PESQUISA.format(cnpj=so_digitos(cnpj), quantidade=quantidade)
    requisicao = urllib.request.Request(url, headers=_HEADERS)
    with _abrir_com_retry(requisicao, timeout=timeout, tentativas=tentativas) as resposta:
        dados = json.load(resposta)
    return [
        {
            "id": item.get("id"),
            "tipo": (item.get("tipoDocumento") or "").strip(),
            "categoria": (item.get("categoriaDocumento") or "").strip(),
            "data_entrega": (item.get("dataEntrega") or "").strip(),
        }
        for item in dados.get("data", [])
        if item.get("id")
    ]


def baixar(id_fnet: int, timeout: int = 180, tentativas: int = 3) -> bytes:
    """Download de um documento do FNET. Timeout frouxo por padrão (relatório
    gerencial em PDF é grande e lento). Numa varredura em LOTE, passe valores
    curtos: um download que pendura custa 180s×3 ≈ 9 min por documento."""
    requisicao = urllib.request.Request(
        URL_DOWNLOAD.format(id=id_fnet), headers=_HEADERS
    )
    with _abrir_com_retry(requisicao, timeout=timeout, tentativas=tentativas) as resposta:
        return resposta.read()


def ultimo_relatorio_gerencial(documentos: list[dict]) -> dict | None:
    for documento_ in documentos:
        if "relatório gerencial" in documento_["tipo"].lower():
            return documento_
    return None


def fatos_relevantes(documentos: list[dict], quantidade: int = 3) -> list[dict]:
    return [
        documento_
        for documento_ in documentos
        if documento_["categoria"].lower() == "fato relevante"
    ][:quantidade]


def ultima_demonstracao_financeira(documentos: list[dict]) -> dict | None:
    """DF anual mais recente — é nela que mora o parecer do auditor."""
    for documento_ in documentos:
        if "demonstra" in documento_["tipo"].lower() and "financeira" in documento_["tipo"].lower():
            return documento_
    return None


def comunicados_e_assembleias(documentos: list[dict], hoje=None) -> list[dict]:
    """Comunicados ao Mercado (até 2) e Assembleias (até 2) dos últimos 12
    meses, com um `rotulo` legível para o prompt e a página. Junto com os
    fatos relevantes, cobrem a notícia que não aparece nos informes."""
    from datetime import date, datetime

    hoje = hoje or date.today()

    def _recente(documento_: dict) -> bool:
        try:
            entrega = datetime.strptime(documento_["data_entrega"][:10], "%d/%m/%Y").date()
        except ValueError:
            return False
        return (hoje - entrega).days <= 365

    comunicados = [
        {**documento_, "rotulo": "Comunicado ao Mercado"}
        for documento_ in documentos
        if documento_["categoria"].lower() == "comunicado ao mercado" and _recente(documento_)
    ][:2]
    assembleias = [
        {**documento_, "rotulo": f"Assembleia {documento_['tipo']}".strip()}
        for documento_ in documentos
        if documento_["categoria"].lower() == "assembleia" and _recente(documento_)
    ][:2]
    return comunicados + assembleias


def garantir_relatorio(
    con: sqlite3.Connection, cnpj: str, destino: Path | None = None
) -> tuple[Path, dict] | None:
    """Garante o último relatório gerencial baixado; retorna (caminho, metadados).

    Idempotente: se o PDF do documento mais recente já está no disco, não
    vai à rede de novo para baixá-lo.
    """
    destino = destino or armazenamento.diretorio_dados() / "documentos"
    documentos = listar(cnpj)
    relatorio = ultimo_relatorio_gerencial(documentos)
    if relatorio is None:
        return None
    return _garantir_documento(con, cnpj, relatorio, destino), relatorio


def garantir_fatos_relevantes(
    con: sqlite3.Connection,
    cnpj: str,
    quantidade: int = 3,
    destino: Path | None = None,
) -> list[tuple[Path, dict]]:
    """Garante os últimos fatos relevantes baixados; retorna [(caminho, metadados)].

    Mesmo cache idempotente do relatório gerencial.
    """
    destino = destino or armazenamento.diretorio_dados() / "documentos"
    documentos = listar(cnpj)
    return [
        (_garantir_documento(con, cnpj, fato, destino), fato)
        for fato in fatos_relevantes(documentos, quantidade)
    ]


def _garantir_documento(
    con: sqlite3.Connection, cnpj: str, documento_: dict, destino: Path
) -> Path:
    registrado = armazenamento.documento(con, cnpj, documento_["id"])
    if registrado and registrado["arquivo"] and Path(registrado["arquivo"]).exists():
        return Path(registrado["arquivo"])

    conteudo = baixar(documento_["id"])
    pasta = destino / so_digitos(cnpj)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{documento_['id']}.pdf"
    caminho.write_bytes(conteudo)
    armazenamento.gravar_documento(
        con,
        cnpj,
        documento_["id"],
        documento_["tipo"],
        documento_["categoria"],
        documento_["data_entrega"],
        str(caminho),
    )
    return caminho
