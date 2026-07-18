import io
import zipfile

from fato_relevante import analise, armazenamento
from fato_relevante.coleta import cvm


def _zip_dois_fundos(ano: int = 2026) -> bytes:
    """Dois fundos do mesmo administrador + um de outro."""
    geral = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Nome_Fundo_Classe;Codigo_ISIN;"
        "Segmento_Atuacao;Tipo_Gestao;Quantidade_Cotas_Emitidas;Nome_Administrador;CNPJ_Administrador\n"
        f"11.111.111/0001-11;{ano}-01-01;1;FUNDO TESTE FII;BRTSTECTF004;Shoppings;Ativa;1000;ADMIN EXEMPLO;99.999.999/0001-99\n"
        f"11.111.111/0001-11;{ano}-02-01;1;FUNDO TESTE FII;BRTSTECTF004;Shoppings;Ativa;1000;ADMIN EXEMPLO;99.999.999/0001-99\n"
        f"22.222.222/0001-22;{ano}-02-01;1;FUNDO IRMAO FII;BRIRMOCTF001;Logística;Passiva;2000;ADMIN EXEMPLO;99.999.999/0001-99\n"
        f"33.333.333/0001-33;{ano}-02-01;1;FUNDO ALHEIO FII;BRALHECTF002;Papel;Ativa;3000;OUTRO ADMIN;88.888.888/0001-88\n"
    )
    complemento = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Valor_Ativo;Patrimonio_Liquido;"
        "Cotas_Emitidas;Valor_Patrimonial_Cotas;Percentual_Rentabilidade_Patrimonial_Mes;"
        "Percentual_Dividend_Yield_Mes;Percentual_Amortizacao_Cotas_Mes;Total_Numero_Cotistas\n"
        f"11.111.111/0001-11;{ano}-01-01;1;1200000;1000000;1000;100.5;0.008;0.009;;500\n"
        f"11.111.111/0001-11;{ano}-02-01;1;1300000;1050000;1000;95.45;0.007;0.011;;520\n"
        f"22.222.222/0001-22;{ano}-02-01;1;900000;800000;2000;400;0.007;0.008;;5000\n"
        f"33.333.333/0001-33;{ano}-02-01;1;500000;400000;3000;133;0.007;0.008;;9000\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"inf_mensal_fii_geral_{ano}.csv", geral.encode("latin-1"))
        zf.writestr(f"inf_mensal_fii_complemento_{ano}.csv", complemento.encode("latin-1"))
    return buffer.getvalue()


def test_administrador_e_fundos_irmaos(con):
    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    admin = armazenamento.administrador_do_fundo(con, "11.111.111/0001-11")
    assert admin["administrador"] == "ADMIN EXEMPLO"
    irmaos = armazenamento.fundos_do_administrador(
        con, "99.999.999/0001-99", "11.111.111/0001-11"
    )
    assert [linha["nome"] for linha in irmaos] == ["FUNDO IRMAO FII"]  # o alheio fica fora


def test_raio_x_traz_fundos_irmaos_com_selo(con):
    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    assert raiox.administrador == "ADMIN EXEMPLO"
    assert len(raiox.fundos_irmaos) == 1
    irmao = raiox.fundos_irmaos[0]
    assert irmao.ticker == "IRMO11"  # derivado do ISIN BRIRMOCTF001
    assert irmao.selo is not None


def test_html_com_secao_administrador(con):
    from fato_relevante.relatorio import html as relatorio_html

    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    completo = analise.montar_completo(con, "tste11")
    pagina = relatorio_html.gerar(completo)
    assert "ADMIN EXEMPLO" in pagina
    assert 'href="IRMO11.html"' in pagina  # link cruzado para o relatório do irmão


def test_ticker_do_isin():
    assert analise._ticker_do_isin("BRHGLGCTF004") == "HGLG11"
    assert analise._ticker_do_isin(None) == ""
    assert analise._ticker_do_isin("XX") == ""


def test_migracao_adiciona_colunas_e_forca_recarga(tmp_path):
    import sqlite3

    # simula uma base antiga: informes_gerais sem as colunas de administrador
    caminho = tmp_path / "fato.db"
    velho = sqlite3.connect(caminho)
    velho.execute(
        "CREATE TABLE informes_gerais (cnpj TEXT, competencia TEXT, nome TEXT,"
        " segmento TEXT, tipo_gestao TEXT, isin TEXT, cotas_emitidas REAL,"
        " PRIMARY KEY (cnpj, competencia))"
    )
    velho.execute("CREATE TABLE cargas (arquivo TEXT PRIMARY KEY, carregado_em TEXT)")
    velho.execute("INSERT INTO cargas VALUES ('inf_mensal_fii_2020.zip', 'x')")
    velho.execute("INSERT INTO cargas VALUES ('inf_trimestral_fii_2020.zip', 'x')")
    velho.commit()
    velho.close()

    con = armazenamento.conectar(tmp_path)
    colunas = {linha[1] for linha in con.execute("PRAGMA table_info(informes_gerais)")}
    assert "administrador" in colunas and "cnpj_administrador" in colunas
    cargas = [linha[0] for linha in con.execute("SELECT arquivo FROM cargas")]
    # mensais precisam recarregar (para preencher o administrador); trimestral fica
    assert cargas == ["inf_trimestral_fii_2020.zip"]
    con.close()
