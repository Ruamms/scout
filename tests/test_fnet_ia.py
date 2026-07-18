import json

import pytest

from scout import armazenamento, ia
from scout.coleta import fnet


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


def test_garantir_fatos_relevantes_baixa_e_e_idempotente(con, tmp_path, monkeypatch):
    downloads = []
    monkeypatch.setattr(fnet, "listar", lambda cnpj, quantidade=30: _DOCUMENTOS)
    monkeypatch.setattr(
        fnet, "baixar", lambda id_fnet: downloads.append(id_fnet) or _pdf_minimo()
    )
    documentos = fnet.garantir_fatos_relevantes(con, "11.111.111/0001-11", destino=tmp_path)
    assert [meta["id"] for _, meta in documentos] == [120]
    assert documentos[0][0].exists()
    assert downloads == [120]
    # segunda chamada: cache, sem novo download
    fnet.garantir_fatos_relevantes(con, "11.111.111/0001-11", destino=tmp_path)
    assert downloads == [120]


def test_analisar_fatos_relevantes_monta_prompt(monkeypatch):
    import io
    import urllib.request

    capturado = {}
    fluxo = json.dumps({"message": {"content": "• lido"}, "done": True}).encode()

    def _urlopen(requisicao, timeout=None):
        capturado["corpo"] = json.loads(requisicao.data)
        return io.BytesIO(fluxo)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    saida = ia.analisar_fatos_relevantes(
        [("18/06/2026", "texto do fato A"), ("01/05/2026", "texto do fato B")],
        "CONTEXTO Y",
        modelo="teste:1b",
    )
    assert saida == "• lido"
    corpo = capturado["corpo"]
    assert "Fato Relevante" in corpo["messages"][0]["content"]  # prompt específico
    assert "nunca invente" in corpo["messages"][0]["content"]
    usuario = corpo["messages"][1]["content"]
    assert "CONTEXTO Y" in usuario
    assert "entregue em 18/06/2026" in usuario and "texto do fato A" in usuario
    assert "entregue em 01/05/2026" in usuario and "texto do fato B" in usuario


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
    from scout import analise
    from scout.coleta import cvm

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    contexto = ia.contexto_do_raiox(raiox)
    assert "TSTE11" in contexto
    assert "Indicadores:" in contexto
    assert "Selo:" in contexto


def test_cli_ia_fluxo_completo(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
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
    caminho_fato = tmp_path / "120.pdf"
    caminho_fato.write_bytes(_pdf_minimo("Comunicado sobre venda de ativo " * 20))
    monkeypatch.setattr(
        modulo_fnet,
        "garantir_fatos_relevantes",
        lambda con_, cnpj, quantidade=3, destino=None: [(caminho_fato, _DOCUMENTOS[2])],
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_fatos_relevantes",
        lambda fatos, ctx, modelo=None, ao_progresso=None: "• comunicado resumido",
    )
    resultado = CliRunner().invoke(app, ["ia", "tste11"])
    assert resultado.exit_code == 0, resultado.output
    assert "Leitura do relatório gerencial" in resultado.output
    assert "fato citado" in resultado.output
    assert "Fatos relevantes recentes" in resultado.output
    assert "comunicado resumido" in resultado.output
    assert "Não é recomendação" in resultado.output


def test_cli_ia_sem_fatos_pula_comunicados(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
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
    resultado = CliRunner().invoke(app, ["ia", "tste11", "--sem-fatos"])
    assert resultado.exit_code == 0, resultado.output
    assert "Fatos relevantes recentes" not in resultado.output


def test_leituras_salvar_carregar(tmp_path):
    from datetime import datetime

    from scout import leituras

    dados = leituras.montar(
        "tste11",
        "teste:1b",
        _DOCUMENTOS[1],
        "leitura do relatório",
        [_DOCUMENTOS[2]],
        "leitura dos fatos",
        agora=datetime(2026, 7, 18, 23, 0),
    )
    caminho = leituras.salvar(tmp_path / "leituras", dados)
    assert caminho.name == "TSTE11.json"
    todas = leituras.carregar_todas(tmp_path / "leituras")
    assert todas["TSTE11"]["relatorio"]["id"] == 150
    assert todas["TSTE11"]["fatos"]["ids"] == [120]
    assert leituras.carregar(tmp_path / "leituras", "tste11")["modelo"] == "teste:1b"


def test_cli_ia_lote_incremental(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30: _DOCUMENTOS)
    caminho_pdf = tmp_path / "doc.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Relatorio para o lote " * 50))
    monkeypatch.setattr(
        modulo_fnet, "_garantir_documento", lambda con_, cnpj, doc, destino: caminho_pdf
    )
    chamadas = []
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda texto, ctx, modelo=None, ao_progresso=None: chamadas.append("rel") or "L",
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_fatos_relevantes",
        lambda fatos, ctx, modelo=None, ao_progresso=None: chamadas.append("fatos") or "F",
    )
    pasta = tmp_path / "leituras"

    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert resultado.exit_code == 0, resultado.output
    assert "1 lidos, 0 já em dia" in resultado.output
    assert chamadas == ["rel", "fatos"]
    assert (pasta / "TSTE11.json").exists()

    # segunda rodada: mesmo documento no FNET -> nada a fazer
    resultado2 = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert "0 lidos, 1 já em dia" in resultado2.output
    assert chamadas == ["rel", "fatos"]  # a IA não foi chamada de novo


def test_cli_ia_sem_ollama_orienta_instalacao(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_ia, "disponivel", lambda: False)
    resultado = CliRunner().invoke(app, ["ia", "tste11"])
    assert resultado.exit_code == 1
    assert "winget install Ollama.Ollama" in resultado.output
