"""Tipo do FII derivado da carteira oficial (CVM): classificador + parser."""

import io
import zipfile

from scout import armazenamento, tipo_fii
from scout.coleta import cvm


# --- classificador (função pura) --------------------------------------------

def test_papel_puro():
    assert tipo_fii.classificar(tijolo=0, papel=900, fof=0) == tipo_fii.PAPEL


def test_tijolo_puro():
    assert tipo_fii.classificar(tijolo=1000, papel=0, fof=0) == tipo_fii.TIJOLO


def test_fundo_de_fundos_domina():
    # fof >= 50% da base imobiliária vence, mesmo com tijolo/papel presentes
    assert tipo_fii.classificar(tijolo=30, papel=10, fof=60) == tipo_fii.FOF


def test_hibrido_quando_tijolo_e_papel_relevantes():
    # nenhum >= 70%, ambos >= 20%, fof < 50% -> híbrido
    assert tipo_fii.classificar(tijolo=55, papel=45, fof=0) == tipo_fii.HIBRIDO


def test_dominante_quando_nao_bate_limiar_de_hibrido():
    # papel 85% (>=70) -> Papel, mesmo com um pouco de tijolo
    assert tipo_fii.classificar(tijolo=15, papel=85, fof=0) == tipo_fii.PAPEL
    # papel só 10% (< 20) -> não é híbrido; vence o maior (tijolo)
    assert tipo_fii.classificar(tijolo=60, papel=10, fof=0) == tipo_fii.TIJOLO


def test_sem_base_imobiliaria_e_nao_classificado():
    # fundo só de caixa/liquidez (tudo em "outros") não tem como ser classificado
    assert tipo_fii.classificar(tijolo=0, papel=0, fof=0) is None


# --- parser do ativo_passivo (integração via carregar_zip) ------------------

def _zip_com_ativos(ano: int = 2026) -> bytes:
    """ZIP mínimo da CVM com geral + complemento + ativo_passivo (2 fundos:
    um de papel/CRI e um de tijolo)."""
    geral = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Nome_Fundo_Classe;Codigo_ISIN;"
        "Segmento_Atuacao;Tipo_Gestao;Quantidade_Cotas_Emitidas\n"
        f"11.111.111/0001-11;{ano}-06-01;1;FUNDO PAPEL FII;BRPAPECTF004;Outros;Ativa;1000\n"
        f"22.222.222/0001-22;{ano}-06-01;1;FUNDO TIJOLO FII;BRTIJOCTF004;Logística;Ativa;1000\n"
    )
    complemento = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Valor_Ativo;Patrimonio_Liquido;"
        "Cotas_Emitidas;Valor_Patrimonial_Cotas;Percentual_Rentabilidade_Patrimonial_Mes;"
        "Percentual_Dividend_Yield_Mes;Percentual_Amortizacao_Cotas_Mes;Total_Numero_Cotistas\n"
        f"11.111.111/0001-11;{ano}-06-01;1;1000;1000;1000;1;0;0;;10\n"
        f"22.222.222/0001-22;{ano}-06-01;1;1000;1000;1000;1;0;0;;10\n"
    )
    # papel: CRI 800 + LCI 100 (papel=900), caixa 100 (outros). Fundos_Renda_Fixa
    # é liquidez -> NÃO conta como FoF.
    ativo = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;CRI;LCI;Direitos_Bens_Imoveis;"
        "FII;Fundos_Renda_Fixa;Disponibilidades\n"
        f"11.111.111/0001-11;{ano}-06-01;1;800;100;0;0;500;100\n"
        f"22.222.222/0001-22;{ano}-06-01;1;0;0;950;0;0;50\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"inf_mensal_fii_geral_{ano}.csv", geral.encode("latin-1"))
        zf.writestr(f"inf_mensal_fii_complemento_{ano}.csv", complemento.encode("latin-1"))
        zf.writestr(f"inf_mensal_fii_ativo_passivo_{ano}.csv", ativo.encode("latin-1"))
    return buffer.getvalue()


def test_parser_soma_baldes_e_classifica(con):
    cvm.carregar_zip(con, _zip_com_ativos(), "inf_mensal_fii_2026.zip")

    papel = armazenamento.composicao_ativo(con, "11.111.111/0001-11")
    assert papel["papel"] == 900  # CRI 800 + LCI 100
    assert papel["tijolo"] == 0 and papel["fof"] == 0
    assert papel["outros"] == 600  # Fundos_Renda_Fixa 500 (liquidez) + caixa 100

    tijolo = armazenamento.composicao_ativo(con, "22.222.222/0001-22")
    assert tijolo["tijolo"] == 950

    tipos = armazenamento.tipos_fii(con)
    assert tipos["11.111.111/0001-11"] == tipo_fii.PAPEL
    assert tipos["22.222.222/0001-22"] == tipo_fii.TIJOLO


def test_carregar_zip_sem_ativo_passivo_nao_quebra(con, zip_cvm):
    # zip antigo/fixture sem o CSV ativo_passivo: ingestão segue sem erro
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    assert armazenamento.tipos_fii(con) == {}
