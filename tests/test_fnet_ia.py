import json

import pytest

from fato_relevante import armazenamento, ia
from fato_relevante.coleta import fnet


# --- helpers ---------------------------------------------------------------------


def _pdf_minimo(texto: str = "Relatorio gerencial de teste do fundo") -> bytes:
    """PDF de 1 página válido, com texto extraível, sem dependências."""
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        None,  # stream, montado abaixo
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    fluxo = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
    objetos[3] = b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream"

    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for indice, corpo in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += f"{indice} 0 obj\n".encode() + corpo + b"\nendobj\n"
    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n".encode()
    saida += b"0000000000 65535 f \n"
    for offset in offsets:
        saida += f"{offset:010d} 00000 n \n".encode()
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF"
    ).encode()
    return bytes(saida)


_DOCUMENTOS = [
    {"id": 200, "tipo": "Informe Mensal Estruturado", "categoria": "Informes Periódicos", "data_entrega": "15/07/2026 19:00"},
    {"id": 150, "tipo": "Relatório Gerencial", "categoria": "Relatórios", "data_entrega": "13/07/2026 19:34"},
    {"id": 120, "tipo": "", "categoria": "Fato Relevante", "data_entrega": "18/06/2026 18:58"},
    {"id": 100, "tipo": "Relatório Gerencial", "categoria": "Relatórios", "data_entrega": "11/06/2026 19:55"},
]


# --- fnet ------------------------------------------------------------------------


def test_so_digitos():
    assert fnet.so_digitos("11.728.688/0001-47") == "11728688000147"


def test_seleciona_relatorio_e_fatos():
    relatorio = fnet.ultimo_relatorio_gerencial(_DOCUMENTOS)
    assert relatorio["id"] == 150  # o mais recente, não o antigo
    fatos = fnet.fatos_relevantes(_DOCUMENTOS)
    assert [fato["id"] for fato in fatos] == [120]


def test_garantir_relatorio_baixa_e_e_idempotente(con, tmp_path, monkeypatch):
    downloads = []
    monkeypatch.setattr(fnet, "listar", lambda cnpj, quantidade=30: _DOCUMENTOS)
    monkeypatch.setattr(
        fnet, "baixar", lambda id_fnet: downloads.append(id_fnet) or _pdf_minimo()
    )
    caminho, meta = fnet.garantir_relatorio(con, "11.111.111/0001-11", destino=tmp_path)
    assert caminho.exists()
    assert caminho.name == "150.pdf"
    assert meta["data_entrega"].startswith("13/07/2026")
    assert downloads == [150]
    # segunda chamada: mesmo documento -> não baixa de novo
    caminho2, _ = fnet.garantir_relatorio(con, "11.111.111/0001-11", destino=tmp_path)
    assert caminho2 == caminho
    assert downloads == [150]


# --- ia --------------------------------------------------------------------------


def test_extrair_texto_pdf(tmp_path):
    caminho = tmp_path / "rel.pdf"
    caminho.write_bytes(_pdf_minimo("Vacancia do imovel X caiu no trimestre"))
    texto = ia.extrair_texto_pdf(caminho)
    assert "Vacancia do imovel X caiu" in texto


def test_analisar_relatorio_monta_chamada_ao_ollama(monkeypatch):
    capturado = {}

    import io
    import urllib.request

    fluxo = b"\n".join(
        json.dumps(evento).encode()
        for evento in (
            {"message": {"content": "• fato "}},
            {"message": {"content": "extraído"}},
            {"message": {"content": ""}, "done": True},
        )
    )

    def _urlopen(requisicao, timeout=None):
        capturado["url"] = requisicao.full_url
        capturado["corpo"] = json.loads(requisicao.data)
        return io.BytesIO(fluxo)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    progresso = []
    saida = ia.analisar_relatorio(
        "texto do relatório", "CONTEXTO X", modelo="teste:1b", ao_progresso=progresso.append
    )
    assert saida == "• fato extraído"
    assert progresso == [1, 2]  # um callback por trecho com conteúdo
    assert capturado["url"].endswith("/api/chat")
    corpo = capturado["corpo"]
    assert corpo["model"] == "teste:1b"
    assert corpo["stream"] is True
    assert "nunca invente" in corpo["messages"][0]["content"]
    assert "CONTEXTO X" in corpo["messages"][1]["content"]
    assert "texto do relatório" in corpo["messages"][1]["content"]


def test_contexto_do_raiox(con, zip_cvm):
    from fato_relevante import analise
    from fato_relevante.coleta import cvm

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    contexto = ia.contexto_do_raiox(raiox)
    assert "TSTE11" in contexto
    assert "Indicadores:" in contexto
    assert "Selo:" in contexto


def test_cli_ia_fluxo_completo(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fato_relevante import ia as modulo_ia
    from fato_relevante.cli import app
    from fato_relevante.coleta import cvm
    from fato_relevante.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("FATO_DATA_DIR", str(tmp_path))
    caminho_pdf = tmp_path / "150.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Texto longo do relatorio " * 50))
    monkeypatch.setattr(modulo_ia, "disponivel", lambda: True)
    monkeypatch.setattr(modulo_ia, "modelos_instalados", lambda: ["qwen2.5:14b"])
    monkeypatch.setattr(
        modulo_fnet,
        "garantir_relatorio",
        lambda con_, cnpj, destino=None: (caminho_pdf, _DOCUMENTOS[1]),
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda texto, ctx, modelo=None, ao_progresso=None: "• fato citado",
    )
    resultado = CliRunner().invoke(app, ["ia", "tste11"])
    assert resultado.exit_code == 0, resultado.output
    assert "Leitura do relatório gerencial" in resultado.output
    assert "fato citado" in resultado.output
    assert "Não é recomendação" in resultado.output


def test_cli_ia_sem_ollama_orienta_instalacao(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fato_relevante import ia as modulo_ia
    from fato_relevante.cli import app
    from fato_relevante.coleta import cvm

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("FATO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_ia, "disponivel", lambda: False)
    resultado = CliRunner().invoke(app, ["ia", "tste11"])
    assert resultado.exit_code == 1
    assert "winget install Ollama.Ollama" in resultado.output
