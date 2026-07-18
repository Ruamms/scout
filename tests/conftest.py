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


def montar_zip_trimestral(
    novo_schema: bool = True,
    ano: int = 2026,
    resultado_financeiro: str = "100000",
    rendimentos: str = "90000",
    vacancias: tuple[str, str] = ("0.10", "0.50"),
) -> bytes:
    cnpj_col = "CNPJ_Fundo_Classe" if novo_schema else "CNPJ_Fundo"
    imovel = (
        f"{cnpj_col};Data_Referencia;Versao;Classe;Nome_Imovel;Endereco;Area;"
        "Percentual_Vacancia;Percentual_Inadimplencia;Percentual_Receitas_FII\n"
        f"11.111.111/0001-11;{ano}-03-01;1;Classe;GALPAO A;Rua X, 1;1000;"
        f"{vacancias[0]};0.02;60\n"
        f"11.111.111/0001-11;{ano}-03-01;1;Classe;;Rua Y, 2;500;{vacancias[1]};;40\n"
    )
    resultado = (
        f"{cnpj_col};Data_Referencia;Versao;Resultado_Trimestral_Liquido_Financeiro;"
        "Rendimentos_Declarados;Lucro_Contabil\n"
        f"11.111.111/0001-11;{ano}-03-01;1;{resultado_financeiro};{rendimentos};80000\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"inf_trimestral_fii_imovel_{ano}.csv", imovel.encode("latin-1"))
        zf.writestr(
            f"inf_trimestral_fii_resultado_contabil_financeiro_{ano}.csv",
            resultado.encode("latin-1"),
        )
    return buffer.getvalue()


def montar_zip_universo(ano: int = 2026) -> bytes:
    """Três fundos ativos com DY/PL distintos + um inativo (parou em jan)."""
    geral_header = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Nome_Fundo_Classe;Codigo_ISIN;"
        "Segmento_Atuacao;Tipo_Gestao;Quantidade_Cotas_Emitidas;Nome_Administrador;CNPJ_Administrador\n"
    )
    compl_header = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Valor_Ativo;Patrimonio_Liquido;"
        "Cotas_Emitidas;Valor_Patrimonial_Cotas;Percentual_Rentabilidade_Patrimonial_Mes;"
        "Percentual_Dividend_Yield_Mes;Percentual_Amortizacao_Cotas_Mes;Total_Numero_Cotistas\n"
    )
    fundos = [
        ("11.111.111/0001-11", "ALFA FII", "BRALFACTF001", "Shoppings", "0.010", "1000000", "800"),
        ("22.222.222/0001-22", "BETA FII", "BRBETACTF001", "Shoppings", "0.006", "5000000", "9000"),
        ("33.333.333/0001-33", "GAMA FII", "BRGAMACTF001", "Logística", "0.008", "3000000", "50"),
    ]
    geral, compl = geral_header, compl_header
    for mes in range(1, 7):
        for cnpj, nome, isin, seg, dy, pl, cotistas in fundos:
            geral += f"{cnpj};{ano}-{mes:02d}-01;1;{nome};{isin};{seg};Ativa;1000;ADMIN X;99.999.999/0001-99\n"
            compl += f"{cnpj};{ano}-{mes:02d}-01;1;{pl};{pl};1000;100;0.005;{dy};;{cotistas}\n"
    # fundo inativo: só janeiro
    geral += f"44.444.444/0001-44;{ano}-01-01;1;MORTO FII;BRMRTOCTF001;Shoppings;Ativa;1000;ADMIN X;99.999.999/0001-99\n"
    compl += f"44.444.444/0001-44;{ano}-01-01;1;100;100;1000;100;0.005;0.005;;10\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"inf_mensal_fii_geral_{ano}.csv", geral.encode("latin-1"))
        zf.writestr(f"inf_mensal_fii_complemento_{ano}.csv", compl.encode("latin-1"))
    return buffer.getvalue()


@pytest.fixture()
def zip_cvm():
    return montar_zip_cvm


@pytest.fixture()
def zip_trimestral():
    return montar_zip_trimestral


@pytest.fixture()
def con(tmp_path):
    conexao = armazenamento.conectar(tmp_path)
    yield conexao
    conexao.close()
