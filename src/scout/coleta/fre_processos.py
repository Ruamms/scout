"""Processos judiciais do FRE (seção 4.3+) — a parte que NÃO é estruturada.

O FRE baixado do RAD/ENET é um zip com o formulário em XML. Os processos
vêm em DOIS níveis:
- `ValorProvisionadoProcessosNaoSigilosos`: um número ESTRUTURADO (sem IA);
- o detalhamento é um PDF EMBUTIDO em base64 (`ImagemObjetoArquivoPdf` dentro
  de `ProcessosNaoSigilosos`) — esse é o documento que a IA lê.

O download é pesado (~5 MB por empresa) e o FRE é anual: a extração é feita
sob demanda e cacheada por id do documento.
"""

from __future__ import annotations

import base64
import io
import re
import zipfile
from pathlib import Path

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def baixar_pacote(link_doc: str, timeout: int = 180, tentativas: int = 3) -> bytes:
    """Zip do FRE no RAD (o endpoint reseta conexão à toa: retry do fnet)."""
    import urllib.request

    from . import fnet

    link = link_doc.replace("http://", "https://")  # o http reseta a conexão
    requisicao = urllib.request.Request(link, headers=_HEADERS)
    return fnet._buscar_com_retry(
        requisicao, timeout=timeout, tentativas=tentativas, consumir=lambda r: r.read()
    )


def extrair_processos(pacote: bytes) -> dict:
    """{valor_provisionado, pdf} do XML do FRE. `pdf` = bytes do documento de
    processos não sigilosos (base64 decodificado), ou None quando a companhia
    não anexou. Nunca inventa: campo ausente = None."""
    zf = zipfile.ZipFile(io.BytesIO(pacote))
    nome = next((n for n in zf.namelist() if re.search(r"FRE.*\.xml$", n, re.IGNORECASE)), None)
    if nome is None:
        return {"valor_provisionado": None, "pdf": None}
    xml = zf.read(nome).decode("utf-8", "replace")

    valor = None
    encontro = re.search(
        r"<ValorProvisionadoProcessosNaoSigilosos>\s*([\d.,]+)\s*</ValorProvisionadoProcessosNaoSigilosos>",
        xml,
    )
    if encontro:
        bruto = encontro.group(1)
        try:
            # o XML usa ponto decimal; formato pt-BR só de fallback
            valor = float(bruto)
        except ValueError:
            try:
                valor = float(bruto.replace(".", "").replace(",", "."))
            except ValueError:
                valor = None

    pdf = None
    bloco = re.search(
        r"<ProcessosNaoSigilosos>.*?<ImagemObjetoArquivoPdf>\s*([A-Za-z0-9+/=\s]+?)\s*"
        r"</ImagemObjetoArquivoPdf>",
        xml,
        flags=re.DOTALL,
    )
    if bloco:
        try:
            candidato = base64.b64decode("".join(bloco.group(1).split()))
            if candidato[:5] == b"%PDF-":
                pdf = candidato
        except Exception:  # base64 corrompido: fica sem o anexo, nunca quebra
            pdf = None
    return {"valor_provisionado": valor, "pdf": pdf}


def garantir_pdf_processos(
    link_doc: str, id_doc: int, destino: Path
) -> tuple[Path | None, float | None]:
    """(caminho do PDF de processos, valor provisionado) com cache por id do
    FRE — o zip de ~5 MB só é baixado quando o documento muda (FRE é anual)."""
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"fre_processos_{id_doc}.pdf"
    marcador_valor = destino / f"fre_processos_{id_doc}.valor"
    if caminho.exists() or marcador_valor.exists():
        valor = None
        if marcador_valor.exists():
            try:
                valor = float(marcador_valor.read_text(encoding="ascii") or "nan")
            except ValueError:
                valor = None
        return (caminho if caminho.exists() else None), valor

    dados = extrair_processos(baixar_pacote(link_doc))
    if dados["pdf"]:
        caminho.write_bytes(dados["pdf"])
    marcador_valor.write_text(
        "" if dados["valor_provisionado"] is None else repr(dados["valor_provisionado"]),
        encoding="ascii",
    )
    return (caminho if dados["pdf"] else None), dados["valor_provisionado"]
