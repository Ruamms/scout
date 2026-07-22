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


def test_ultima_demonstracao_financeira():
    docs = _DOCUMENTOS + [
        {"id": 400, "tipo": "Demonstrações Financeiras", "categoria": "Informes Periódicos", "data_entrega": "18/02/2026 10:00"},
        {"id": 300, "tipo": "Demonstrações Financeiras", "categoria": "Informes Periódicos", "data_entrega": "18/02/2025 10:00"},
    ]
    assert fnet.ultima_demonstracao_financeira(docs)["id"] == 400
    assert fnet.ultima_demonstracao_financeira(_DOCUMENTOS) is None


def test_comunicados_e_assembleias_selecao():
    from datetime import date

    docs = [
        {"id": 1, "tipo": "", "categoria": "Comunicado ao Mercado", "data_entrega": "10/07/2026 10:00"},
        {"id": 2, "tipo": "AGO", "categoria": "Assembleia", "data_entrega": "05/05/2026 10:00"},
        {"id": 3, "tipo": "AGE", "categoria": "Assembleia", "data_entrega": "03/03/2026 10:00"},
        {"id": 4, "tipo": "AGE", "categoria": "Assembleia", "data_entrega": "01/01/2026 10:00"},
        {"id": 5, "tipo": "", "categoria": "Comunicado ao Mercado", "data_entrega": "10/07/2024 10:00"},
        {"id": 6, "tipo": "Relatório Gerencial", "categoria": "Relatórios", "data_entrega": "10/07/2026 10:00"},
    ]
    selecionados = fnet.comunicados_e_assembleias(docs, hoje=date(2026, 7, 19))
    # 2 assembleias no máximo (a 3ª fica fora), comunicado velho (>12m) fica fora
    assert [d["id"] for d in selecionados] == [1, 2, 3]
    assert selecionados[0]["rotulo"] == "Comunicado ao Mercado"
    assert selecionados[1]["rotulo"] == "Assembleia AGO"
    assert selecionados[2]["rotulo"] == "Assembleia AGE"


def test_baixar_repete_quando_o_read_estoura(monkeypatch):
    """Regressão: o timeout do FNET estoura no read() do corpo, não no open.
    O retry TEM que cobrir a leitura — senão um stall transitório vira erro."""
    import time
    import urllib.request

    monkeypatch.setattr(time, "sleep", lambda *_: None)  # não espera o backoff
    leituras_read = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            leituras_read["n"] += 1
            if leituras_read["n"] == 1:
                raise TimeoutError("The read operation timed out")
            return b"%PDF-1.4\nconteudo ok\n%%EOF"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    assert fnet.baixar(150, timeout=1, tentativas=3) == b"%PDF-1.4\nconteudo ok\n%%EOF"
    assert leituras_read["n"] == 2  # 1ª falhou no read, 2ª deu certo


def test_baixar_repete_em_stream_truncado(monkeypatch):
    """'Stream has ended unexpectedly' via IncompleteRead (HTTPException, não
    OSError): também precisa ser repetido."""
    import http.client
    import time
    import urllib.request

    monkeypatch.setattr(time, "sleep", lambda *_: None)
    tentativas = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            tentativas["n"] += 1
            if tentativas["n"] == 1:
                raise http.client.IncompleteRead(b"parcial")
            return b"completo"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    assert fnet.baixar(1, timeout=1, tentativas=3) == b"completo"
    assert tentativas["n"] == 2


def test_baixar_repete_pdf_truncado(monkeypatch):
    """Download parcial (read() devolve bytes sem %%EOF, sem lançar): tem que
    ser repetido — senão vira PDF corrompido que o fitz não abre."""
    import time
    import urllib.request

    monkeypatch.setattr(time, "sleep", lambda *_: None)
    n = {"i": 0}
    completo = b"%PDF-1.4\ncorpo do documento\n%%EOF"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            n["i"] += 1
            return b"%PDF-1.4\ncorpo truncado sem fim" if n["i"] == 1 else completo

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    assert fnet.baixar(1, timeout=1, tentativas=3) == completo
    assert n["i"] == 2  # 1ª veio truncada, 2ª completa


def test_garantir_documento_rebaixa_cache_truncado(con, tmp_path, monkeypatch):
    """Cache truncado de uma rodada antiga não deve ser servido — re-baixa."""
    from scout import armazenamento

    cnpj = "11.111.111/0001-11"
    doc = {"id": 999, "tipo": "Relatório Gerencial", "categoria": "Relatórios", "data_entrega": "13/07/2026 19:00"}
    pasta = tmp_path / "docs"
    (pasta / fnet.so_digitos(cnpj)).mkdir(parents=True)
    ruim = pasta / fnet.so_digitos(cnpj) / "999.pdf"
    ruim.write_bytes(b"%PDF-1.4\ntruncado sem eof")  # sem %%EOF
    armazenamento.gravar_documento(
        con, cnpj, 999, doc["tipo"], doc["categoria"], doc["data_entrega"], str(ruim)
    )
    bom = b"%PDF-1.4\ncompleto\n%%EOF"
    chamou = {"n": 0}
    monkeypatch.setattr(
        fnet, "baixar",
        lambda id_fnet, timeout=180, tentativas=3: chamou.__setitem__("n", chamou["n"] + 1) or bom,
    )
    caminho = fnet._garantir_documento(con, cnpj, doc, pasta)
    assert chamou["n"] == 1  # cache truncado -> baixou de novo
    assert caminho.read_bytes() == bom


def test_garantir_fatos_relevantes_baixa_e_e_idempotente(con, tmp_path, monkeypatch):
    downloads = []
    monkeypatch.setattr(fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS)
    monkeypatch.setattr(
        fnet, "baixar", lambda id_fnet, timeout=180, tentativas=3: downloads.append(id_fnet) or _pdf_minimo()
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
    # prompt cobre os comunicados oficiais (fatos, comunicados, assembleias)
    assert "fatos relevantes" in corpo["messages"][0]["content"]
    assert "comunicados ao mercado" in corpo["messages"][0]["content"]
    assert "nunca invente" in corpo["messages"][0]["content"]
    usuario = corpo["messages"][1]["content"]
    assert "CONTEXTO Y" in usuario
    assert "entregue em 18/06/2026" in usuario and "texto do fato A" in usuario
    assert "entregue em 01/05/2026" in usuario and "texto do fato B" in usuario


def test_garantir_relatorio_baixa_e_e_idempotente(con, tmp_path, monkeypatch):
    downloads = []
    monkeypatch.setattr(fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS)
    monkeypatch.setattr(
        fnet, "baixar", lambda id_fnet, timeout=180, tentativas=3: downloads.append(id_fnet) or _pdf_minimo()
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
    # marcador de página: permite ao modelo citar a página de cada trecho
    assert texto.startswith("[página 1]")


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
    assert todas["TSTE11"]["comunicados"]["ids"] == [120]
    assert todas["TSTE11"]["comunicados"]["rotulos"] == ["Fato Relevante"]
    assert leituras.carregar(tmp_path / "leituras", "tste11")["modelo"] == "teste:1b"
    # formato legado ("fatos") continua legível para a incrementalidade
    assert leituras.ids_comunicados({"fatos": {"ids": [7, 8]}}) == {7, 8}
    assert leituras.ids_comunicados(todas["TSTE11"]) == {120}


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
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS)
    caminho_pdf = tmp_path / "doc.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Relatorio para o lote " * 50))
    monkeypatch.setattr(
        modulo_fnet, "_garantir_documento", lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: caminho_pdf
    )
    chamadas = []
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda texto, ctx, modelo=None, ao_progresso=None: chamadas.append("rel") or "L",
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_comunicados",
        lambda itens, ctx, modelo=None, ao_progresso=None: chamadas.append("fatos") or "F",
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

    # terceira rodada: surge um comunicado novo, mas o relatório é o mesmo ->
    # reaproveita a leitura do relatório e só lê os comunicados
    docs_com_novo = _DOCUMENTOS + [
        {"id": 300, "tipo": "", "categoria": "Comunicado ao Mercado", "data_entrega": "16/07/2026 12:00"}
    ]
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: docs_com_novo)
    resultado3 = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert "1 lidos" in resultado3.output
    assert chamadas == ["rel", "fatos", "fatos"]  # relatório NÃO foi relido
    leitura = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert leitura["relatorio"]["texto"] == "L"  # leitura original preservada
    assert 300 in leitura["comunicados"]["ids"]


def test_cli_ia_lote_marca_fundo_sem_relatorio_e_le_quando_aparece(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")
    # FNET só com documentos estruturados: relatório gerencial é opcional e este fundo não tem
    so_estruturados = [d for d in _DOCUMENTOS if d["tipo"] != "Relatório Gerencial"]
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: so_estruturados)
    pasta = tmp_path / "leituras"

    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta), "--sem-fatos"])
    assert resultado.exit_code == 0, resultado.output
    assert "sem relatório gerencial" in resultado.output
    marcador = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert marcador["sem_relatorio"] is True
    assert marcador["verificado_em"]
    # histórico permanente registra o desfecho de cada fundo
    historico = (pasta / "_historico.txt").read_text(encoding="utf-8")
    assert "TSTE11\tsem-relatorio" in historico
    assert "lote iniciado" in historico and "lote encerrado" in historico

    # o fundo publica um relatório gerencial depois: o marcador não trava a leitura
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS)
    caminho_pdf = tmp_path / "doc.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Relatorio para o lote " * 50))
    monkeypatch.setattr(
        modulo_fnet, "_garantir_documento", lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: caminho_pdf
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda texto, ctx, modelo=None, ao_progresso=None: "leitura ok",
    )
    resultado2 = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta), "--sem-fatos"])
    assert resultado2.exit_code == 0, resultado2.output
    assert "1 lidos" in resultado2.output
    leitura = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert leitura.get("sem_relatorio") is None
    assert leitura["relatorio"]["texto"] == "leitura ok"
    historico = (pasta / "_historico.txt").read_text(encoding="utf-8")
    assert "TSTE11\tlido" in historico


def test_cli_ia_lote_sem_relatorio_le_fatos_relevantes(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")
    # sem relatório gerencial, mas COM fato relevante publicado
    so_estruturados = [d for d in _DOCUMENTOS if d["tipo"] != "Relatório Gerencial"]
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: so_estruturados)
    caminho_pdf = tmp_path / "doc.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Fato relevante para o lote " * 30))
    monkeypatch.setattr(
        modulo_fnet, "_garantir_documento", lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: caminho_pdf
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_comunicados",
        lambda itens, ctx, modelo=None, ao_progresso=None: "fatos lidos pela ia",
    )
    pasta = tmp_path / "leituras"

    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert resultado.exit_code == 0, resultado.output
    assert "fatos/comunicados lidos" in resultado.output
    leitura = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert leitura["sem_relatorio"] is True
    assert leitura["comunicados"]["texto"] == "fatos lidos pela ia"
    assert leitura["comunicados"]["ids"] == [120]
    assert leitura["comunicados"]["rotulos"] == ["Fato Relevante"]
    historico = (pasta / "_historico.txt").read_text(encoding="utf-8")
    assert "sem-relatorio-fatos-lidos" in historico

    # segunda rodada: mesmo fato -> nada a refazer
    resultado2 = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert "0 lidos, 1 já em dia" in resultado2.output


def test_cli_ia_lote_parecer_do_auditor(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")

    df_ok = {"id": 400, "tipo": "Demonstrações Financeiras", "categoria": "Informes Periódicos", "data_entrega": "18/02/2026 10:00"}
    docs = _DOCUMENTOS + [df_ok]
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: docs)

    pdf_relatorio = tmp_path / "rel.pdf"
    pdf_relatorio.write_bytes(_pdf_minimo("Relatorio para o lote " * 50))
    pdf_df = tmp_path / "df.pdf"
    pdf_df.write_bytes(
        _pdf_minimo(
            "Em nossa opiniao, as demonstracoes apresentam adequadamente, "
            "em todos os aspectos relevantes, a posicao do Fundo. " * 10
        )
    )
    por_id = {400: pdf_df, 401: pdf_df}
    monkeypatch.setattr(
        modulo_fnet,
        "_garantir_documento",
        lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: por_id.get(doc["id"], pdf_relatorio),
    )
    chamadas = []
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda texto, ctx, modelo=None, ao_progresso=None: chamadas.append("rel") or "L",
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_comunicados",
        lambda itens, ctx, modelo=None, ao_progresso=None: chamadas.append("docs") or "F",
    )
    pasta = tmp_path / "leituras"

    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert resultado.exit_code == 0, resultado.output
    leitura = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert leitura["parecer"]["id"] == 400
    assert leitura["parecer"]["tipo"] == "sem_ressalva"
    assert chamadas == ["rel", "docs"]

    # segunda rodada: tudo em dia (parecer incluído)
    resultado2 = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert "0 lidos, 1 já em dia" in resultado2.output
    assert chamadas == ["rel", "docs"]

    # DF nova (id 401): parecer reprocessado SEM nenhuma chamada de IA
    pdf_df.write_bytes(
        _pdf_minimo(
            "Opiniao com ressalva. Exceto pelo assunto descrito, as demonstracoes "
            "apresentam adequadamente a posicao do Fundo. " * 10
        )
    )
    df_nova = {**df_ok, "id": 401, "data_entrega": "18/02/2027 10:00"}
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS + [df_nova])
    resultado3 = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert resultado3.exit_code == 0, resultado3.output
    leitura = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert leitura["parecer"]["id"] == 401
    assert leitura["parecer"]["tipo"] == "ressalva"
    assert leitura["parecer"]["grave"] is True
    assert chamadas == ["rel", "docs"]  # IA não foi chamada: relatório e comunicados reaproveitados
    assert leitura["relatorio"]["texto"] == "L"
    assert leitura["comunicados"]["texto"] == "F"


def test_cli_ia_lote_registra_erros_e_reprocessa_so_eles(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS)
    caminho_pdf = tmp_path / "doc.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Relatorio para o lote " * 50))
    monkeypatch.setattr(
        modulo_fnet, "_garantir_documento", lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: caminho_pdf
    )
    # primeira rodada: a IA explode -> fundo vai para a lista de erros
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("modelo caiu")),
    )
    pasta = tmp_path / "leituras"
    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta), "--sem-fatos"])
    assert resultado.exit_code == 0, resultado.output
    assert "1 com erro" in resultado.output
    erros = (pasta / "_erros.txt").read_text(encoding="utf-8")
    assert erros.startswith("TSTE11\t")
    assert "modelo caiu" in erros

    # segunda rodada com --apenas-erros: agora a IA funciona -> lê e limpa a lista
    monkeypatch.setattr(
        modulo_ia,
        "analisar_relatorio",
        lambda texto, ctx, modelo=None, ao_progresso=None: "leitura ok",
    )
    resultado2 = CliRunner().invoke(
        app, ["ia-lote", "--destino", str(pasta), "--sem-fatos", "--apenas-erros"]
    )
    assert resultado2.exit_code == 0, resultado2.output
    assert "Reprocessando apenas os 1 fundos" in resultado2.output
    assert "1 lidos" in resultado2.output
    assert (pasta / "TSTE11.json").exists()
    assert not (pasta / "_erros.txt").exists()  # rodada limpa apaga a lista


def test_cli_ia_lote_pdf_imagem_pula_sem_erro(con, zip_cvm, tmp_path, monkeypatch):
    """PDF só-imagem é TERMINAL: vira pulado (não erro), não entra em _erros.txt
    (senão --apenas-erros repetiria pra sempre) e grava o marcador ilegível."""
    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")
    monkeypatch.setattr(modulo_fnet, "listar", lambda cnpj, quantidade=30, timeout=60, tentativas=3: _DOCUMENTOS)
    caminho_pdf = tmp_path / "imagem.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("x"))
    monkeypatch.setattr(
        modulo_fnet, "_garantir_documento", lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: caminho_pdf
    )
    monkeypatch.setattr(modulo_ia, "extrair_texto_pdf", lambda caminho, **kw: "")  # imagem: sem texto
    pasta = tmp_path / "leituras"

    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta), "--sem-fatos"])
    assert resultado.exit_code == 0, resultado.output
    assert "0 com erro" in resultado.output
    assert "imagem/escaneado" in resultado.output
    assert not (pasta / "_erros.txt").exists()  # NÃO é erro
    leitura = json.loads((pasta / "TSTE11.json").read_text(encoding="utf-8"))
    assert leitura["relatorio"]["ilegivel"] is True
    assert leitura["relatorio"]["texto"] == ""
    historico = (pasta / "_historico.txt").read_text(encoding="utf-8")
    assert "TSTE11\tsem-texto" in historico


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
