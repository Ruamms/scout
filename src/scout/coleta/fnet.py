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


def _buscar_com_retry(requisicao, timeout: int, tentativas: int, consumir):
    """Abre E LÊ O CORPO dentro do mesmo retry. O FNET oscila (timeouts
    esporádicos) e o `timed out` costuma estourar no read() do corpo, não no
    open — se a leitura ficar fora do retry, um stall transitório vira erro
    definitivo mesmo o FNET voltando 2s depois. `consumir(resposta)` faz a
    leitura (json.load ou .read()). Espera 5s/20s entre tentativas e trata
    também IncompleteRead ('Stream has ended unexpectedly')."""
    import http.client
    import time
    import urllib.error

    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
                return consumir(resposta)
        except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException, EOFError) as erro:
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(5 * (tentativa + 1) ** 2)
    raise ultimo_erro


def _pdf_truncado(conteudo: bytes) -> bool:
    """Um PDF completo termina com o marcador %%EOF. Se começa como PDF mas não
    tem %%EOF perto do fim, o download veio truncado — o read() às vezes devolve
    bytes parciais sem lançar, e o fitz depois falha 'Stream has ended'."""
    return conteudo[:5] == b"%PDF-" and b"%%EOF" not in conteudo[-2048:]


def _arquivo_pdf_truncado(caminho: Path) -> bool:
    """Mesma checagem de %%EOF lendo só as bordas do arquivo em cache."""
    try:
        with open(caminho, "rb") as fh:
            head = fh.read(5)
            fh.seek(max(0, caminho.stat().st_size - 2048))
            cauda = fh.read()
    except OSError:
        return True
    return head == b"%PDF-" and b"%%EOF" not in cauda


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
    dados = _buscar_com_retry(requisicao, timeout=timeout, tentativas=tentativas, consumir=json.load)
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

    def _ler(resposta) -> bytes:
        conteudo = resposta.read()
        if _pdf_truncado(conteudo):  # download parcial: força mais uma tentativa
            raise EOFError("download de PDF truncado (sem %%EOF)")
        return conteudo

    return _buscar_com_retry(requisicao, timeout=timeout, tentativas=tentativas, consumir=_ler)


def ultimo_relatorio_gerencial(documentos: list[dict]) -> dict | None:
    for documento_ in documentos:
        if "relatório gerencial" in documento_["tipo"].lower():
            return documento_
    return None


def ultimo_regulamento(documentos: list[dict]) -> dict | None:
    """Regulamento mais recente do fundo (é onde mora a taxa de administração
    do ETF). A adaptação à Resolução CVM 175 fez muitos fundos re-arquivarem o
    regulamento em 2024/2025, então costuma estar entre os documentos recentes."""
    for documento_ in documentos:
        rotulo = f"{documento_['tipo']} {documento_['categoria']}".lower()
        if "regulamento" in rotulo:
            return documento_
    return None


def documentos_de_regulamento(documentos: list[dict]) -> list[dict]:
    """Docs que podem trazer a taxa do fundo, do mais provável ao menos. No
    regime 175 a taxa (a "Taxa Global") é fixada por CLASSE no Instrumento de
    Alteração do Regulamento — não no Regulamento em si — então ele vem primeiro;
    depois o Regulamento e a Constituição. Já vêm ordenados por data (mais novo
    primeiro), preservada dentro de cada nível."""

    def _rank(documento_: dict) -> int:
        rotulo = f"{documento_['tipo']} {documento_['categoria']}".lower()
        if "altera" in rotulo and "regulamento" in rotulo:
            return 0
        if "regulamento" in rotulo:
            return 1
        if "constitui" in rotulo:
            return 2
        return 9

    return sorted((d for d in documentos if _rank(d) < 9), key=_rank)


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
    con: sqlite3.Connection, cnpj: str, documento_: dict, destino: Path,
    timeout: int = 180, tentativas: int = 3,
) -> Path:
    registrado = armazenamento.documento(con, cnpj, documento_["id"])
    if registrado and registrado["arquivo"] and Path(registrado["arquivo"]).exists():
        cache = Path(registrado["arquivo"])
        if not _arquivo_pdf_truncado(cache):
            return cache
        # cache truncado (download parcial de uma rodada anterior, quando ainda
        # não validávamos): baixa de novo em vez de servir o arquivo corrompido

    conteudo = baixar(documento_["id"], timeout=timeout, tentativas=tentativas)
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
