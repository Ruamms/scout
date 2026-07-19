import io
import zipfile

from scout import analise, armazenamento
from scout.coleta import cvm


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
    from scout.relatorio import html as relatorio_html

    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    completo = analise.montar_completo(con, "tste11")
    pagina = relatorio_html.gerar(completo)
    assert "ADMIN EXEMPLO" in pagina
    assert 'href="IRMO11.html"' in pagina  # link cruzado para o relatório do irmão
    # o selo do irmão traz o MOTIVO no tooltip (fundo novo, 1 mês de histórico)
    assert 'title="Alertas: ' in pagina


def test_carregar_registro_filtra_fii_e_grava_gestora(con):
    from datetime import date

    from conftest import montar_zip_registro

    total = cvm.carregar_registro(con, montar_zip_registro(), hoje=date(2026, 7, 19))
    assert total == 3  # o FMIA fica fora
    cadastro = armazenamento.cadastro_do_fundo(con, "11.111.111/0001-11")
    assert cadastro["gestor"] == "GESTORA G"
    assert cadastro["cnpj_gestor"] == "88888888000188"
    assert cadastro["administrador"] == "ADMIN X"
    assert armazenamento.cadastro_meta(con)["atualizado_em"] == "2026-07-19"


def test_atualizar_registro_respeita_frescor(con, monkeypatch):
    from datetime import date

    from conftest import montar_zip_registro

    chamadas = []
    monkeypatch.setattr(
        cvm, "_baixar_url", lambda url: chamadas.append(url) or montar_zip_registro()
    )
    assert cvm.atualizar_registro(con, hoje=date(2026, 7, 19)) is not None
    assert cvm.atualizar_registro(con, hoje=date(2026, 7, 20)) is None  # fresco: não baixa
    assert cvm.atualizar_registro(con, hoje=date(2026, 7, 30)) is not None  # 11 dias: baixa
    assert len(chamadas) == 2


def test_raio_x_traz_gestora_e_fundos_da_gestora(con):
    from conftest import montar_zip_registro

    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    cvm.carregar_registro(con, montar_zip_registro())
    raiox = analise.montar_raio_x(con, "tste11")
    assert raiox.gestora == "GESTORA G"
    assert raiox.gestora_e_admin is False  # admin 99..., gestora 88...
    assert [irmao.ticker for irmao in raiox.fundos_gestora] == ["IRMO11"]


def test_html_secao_gestora(con):
    from conftest import montar_zip_registro
    from scout.relatorio import html as relatorio_html

    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    cvm.carregar_registro(con, montar_zip_registro())
    completo = analise.montar_completo(con, "tste11")
    pagina = relatorio_html.gerar(completo)
    assert "Gestora" in pagina
    assert "GESTORA G" in pagina
    assert "gere outros 1 FIIs" in pagina


def test_gestora_igual_admin_nao_duplica_secao(con):
    from scout.relatorio import html as relatorio_html

    cvm.carregar_zip(con, _zip_dois_fundos(), "inf_mensal_fii_2026.zip")
    # registro em que a gestora É o próprio administrador
    linhas = (
        "ID_Registro_Fundo;CNPJ_Fundo;Tipo_Fundo;Denominacao_Social;Situacao;"
        "CNPJ_Administrador;Administrador;Tipo_Pessoa_Gestor;CPF_CNPJ_Gestor;Gestor\n"
        "1;11111111000111;FII;FUNDO TESTE FII;Em Funcionamento Normal;"
        "99999999000199;ADMIN EXEMPLO;PJ;99999999000199;ADMIN EXEMPLO\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("registro_fundo.csv", linhas.encode("latin-1"))
    cvm.carregar_registro(con, buffer.getvalue())

    completo = analise.montar_completo(con, "tste11")
    assert completo.raiox.gestora_e_admin is True
    pagina = relatorio_html.gerar(completo)
    assert "que também é a gestora do fundo" in pagina
    assert "<h2>Gestora" not in pagina  # sem seção duplicada


def test_ticker_do_isin():
    assert analise._ticker_do_isin("BRHGLGCTF004") == "HGLG11"
    assert analise._ticker_do_isin(None) == ""
    assert analise._ticker_do_isin("XX") == ""


def test_migracao_adiciona_colunas_e_forca_recarga(tmp_path):
    import sqlite3

    # simula uma base antiga: informes_gerais sem as colunas de administrador
    caminho = tmp_path / "scout.db"
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
    cargas = {linha[0] for linha in con.execute("SELECT arquivo FROM cargas")}
    # mensais precisam recarregar (para preencher o administrador); trimestral fica;
    # o marcador COTAHIST_V2_ETFS é criado pela migração das cotações
    assert "inf_trimestral_fii_2020.zip" in cargas
    assert not any(arquivo.startswith("inf_mensal") for arquivo in cargas)
    con.close()
