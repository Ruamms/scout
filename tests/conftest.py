import io
import zipfile

import pytest

from fato_relevante import armazenamento


def montar_zip_cvm(novo_schema: bool, ano: int = 2026) -> bytes:
    """ZIP mínimo no formato dos dados abertos da CVM, nos dois vocabulários."""
    cnpj_col = "CNPJ_Fundo_Classe" if novo_schema else "CNPJ_Fundo"
    nome_col = "Nome_Fundo_Classe" if novo_schema else "Nome_Fundo"
    geral = (
        f"{cnpj_col};Data_Referencia;Versao;{nome_col};Codigo_ISIN;"
        "Segmento_Atuacao;Tipo_Gestao;Quantidade_Cotas_Emitidas\n"
        f"11.111.111/0001-11;{ano}-01-01;1;FUNDO TESTE FII;BRTSTECTF004;Shoppings;Ativa;1000\n"
        f"11.111.111/0001-11;{ano}-02-01;1;FUNDO TESTE FII;BRTSTECTF004;Shoppings;Ativa;1100\n"
    )
    complemento = (
        f"{cnpj_col};Data_Referencia;Versao;Valor_Ativo;Patrimonio_Liquido;"
        "Cotas_Emitidas;Valor_Patrimonial_Cotas;Percentual_Rentabilidade_Patrimonial_Mes;"
        "Percentual_Dividend_Yield_Mes;Percentual_Amortizacao_Cotas_Mes;Total_Numero_Cotistas\n"
        f"11.111.111/0001-11;{ano}-01-01;1;1200000.50;1000000;1000;100.5;0.008;0.009;;500\n"
        f"11.111.111/0001-11;{ano}-02-01;1;1300000;1050000;1100;95.45;0.007;0.011;;520\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"inf_mensal_fii_geral_{ano}.csv", geral.encode("latin-1"))
        zf.writestr(f"inf_mensal_fii_complemento_{ano}.csv", complemento.encode("latin-1"))
    return buffer.getvalue()


@pytest.fixture()
def zip_cvm():
    return montar_zip_cvm


@pytest.fixture()
def con(tmp_path):
    conexao = armazenamento.conectar(tmp_path)
    yield conexao
    conexao.close()
