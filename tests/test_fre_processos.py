"""Processos judiciais do FRE — extração do XML do RAD (valor + PDF embutido)."""

import base64
import io
import zipfile

from scout.coleta import fre_processos


def _pacote(valor="1234567.89", pdf=b"%PDF-1.4 conteudo"):
    xml = (
        "<?xml version='1.0'?><Fre>"
        "<ProcessosNaoSigilosos><NomeArquivoPdf>x.docx</NomeArquivoPdf>"
        f"<ImagemObjetoArquivoPdf>{base64.b64encode(pdf).decode()}</ImagemObjetoArquivoPdf>"
        "</ProcessosNaoSigilosos>"
        f"<ValorProvisionadoProcessosNaoSigilosos>{valor}</ValorProvisionadoProcessosNaoSigilosos>"
        "</Fre>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("004820FRE31-12-2026v1.xml", xml.encode("utf-8"))
    return buffer.getvalue()


def test_extrai_valor_e_pdf_embutido():
    dados = fre_processos.extrair_processos(_pacote())
    assert dados["valor_provisionado"] == 1234567.89  # ponto decimal, sem 100×
    assert dados["pdf"].startswith(b"%PDF-")


def test_anexo_que_nao_e_pdf_vira_none():
    dados = fre_processos.extrair_processos(_pacote(pdf=b"DOCX qualquer coisa"))
    assert dados["pdf"] is None  # só PDF de verdade; nunca grava lixo
    assert dados["valor_provisionado"] == 1234567.89


def test_cache_por_id_nao_rebaixa(tmp_path, monkeypatch):
    chamadas = {"n": 0}

    def _baixar(link, timeout=180, tentativas=3):
        chamadas["n"] += 1
        return _pacote()

    monkeypatch.setattr(fre_processos, "baixar_pacote", _baixar)
    caminho, valor = fre_processos.garantir_pdf_processos("http://rad/x", 158044, tmp_path)
    assert caminho.exists() and valor == 1234567.89 and chamadas["n"] == 1
    caminho2, valor2 = fre_processos.garantir_pdf_processos("http://rad/x", 158044, tmp_path)
    assert caminho2 == caminho and valor2 == 1234567.89
    assert chamadas["n"] == 1  # zip de 5 MB não é rebaixado (FRE é anual)
