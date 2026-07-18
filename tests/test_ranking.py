import io
import zipfile

import pytest

from fato_relevante import analise, ranking
from fato_relevante.coleta import cvm


def _zip_universo(ano: int = 2026) -> bytes:
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
def base(con):
    cvm.carregar_zip(con, _zip_universo(), "inf_mensal_fii_2026.zip")
    return con


def test_varrer_exclui_fundo_inativo(base):
    resumos = ranking.varrer(base)
    nomes = {r.nome for r in resumos}
    assert "MORTO FII" not in nomes
    assert {"ALFA FII", "BETA FII", "GAMA FII"} <= nomes


def test_ranking_por_pl_ordena(base):
    resultado = ranking.montar(base, por="pl", top=2)
    assert [r.nome for r in resultado.linhas] == ["BETA FII", "GAMA FII"]
    assert "patrimônio líquido" in resultado.descricao


def test_ranking_filtra_segmento(base):
    resultado = ranking.montar(base, por="pl", segmento="shopping")
    assert all("Shoppings" == r.segmento for r in resultado.linhas)


def test_ranking_sem_alertas_filtra_por_selo(base):
    todos = ranking.montar(base, por="pl", top=10)
    assert todos.total_avaliado == 3  # universo ativo, antes dos filtros
    sem_alertas = ranking.montar(base, por="pl", top=10, sem_alertas=True)
    assert len(sem_alertas.linhas) < len(todos.linhas)
    # com 6 meses de histórico, todos têm selo "insuficiente" -> ninguém passa
    assert sem_alertas.linhas == []
    assert "sem alertas de atenção ou graves" in sem_alertas.filtros


def test_ranking_exclui_sem_ticker_por_padrao(base):
    import sqlite3

    base.execute(
        "UPDATE informes_gerais SET isin = NULL WHERE cnpj = '22.222.222/0001-22'"
    )
    base.commit()
    negociaveis = ranking.montar(base, por="pl", top=10)
    assert all(linha.ticker for linha in negociaveis.linhas)
    todos = ranking.montar(base, por="pl", top=10, apenas_negociaveis=False)
    assert len(todos.linhas) == len(negociaveis.linhas) + 1


def test_ranking_criterio_invalido(base):
    with pytest.raises(ValueError):
        ranking.montar(base, por="xpto")


def test_cli_ranking(base, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fato_relevante.cli import app

    monkeypatch.setenv("FATO_DATA_DIR", str(tmp_path))
    resultado = CliRunner().invoke(app, ["ranking", "--por", "pl", "--top", "3"])
    assert resultado.exit_code == 0
    assert "BETA FII" in resultado.output
    # a frase pode quebrar de linha no terminal estreito; checa a palavra-chave
    assert "recomendação" in resultado.output


def test_pares_do_segmento_no_raio_x(base):
    raiox = analise.montar_raio_x(base, "alfa11")
    assert raiox is not None
    nomes = [par.nome for par in raiox.pares]
    assert "BETA FII" in nomes  # mesmo segmento
    assert all("GAMA" not in nome for nome in nomes)  # segmento diferente fica fora
    assert raiox.pares_media["n"] == 2  # ALFA + BETA no segmento


def test_html_com_secao_pares(base):
    from fato_relevante.relatorio import html as relatorio_html

    completo = analise.montar_completo(base, "alfa11")
    pagina = relatorio_html.gerar(completo)
    assert "Pares do segmento" in pagina
    assert 'href="BETA11.html"' in pagina
    assert "média do segmento" in pagina
