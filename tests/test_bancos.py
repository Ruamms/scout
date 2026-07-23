"""R1 Renda Fixa — coletor IF.data (bancos b1/b2 + série trimestral de saúde)."""

from datetime import date

from scout.coleta import bancos


def test_trimestres_anda_para_tras():
    # em jul/2026 o trimestre anterior fechado é jun/2026
    assert bancos._trimestres(date(2026, 7, 23), 5) == [202606, 202603, 202512, 202509, 202506]
    # em jan, volta para dez do ano anterior
    assert bancos._trimestres(date(2026, 1, 10), 2) == [202512, 202509]


def test_pivotar_casa_prefixo_e_filtra():
    linhas = [
        {"CodInst": "123", "NomeColuna": "Ativo Total", "Saldo": 100.0},
        {"CodInst": "123", "NomeColuna": "Patrimônio de Referência para Comparação com o RWA \n(e)", "Saldo": 12.0},
        {"CodInst": "123", "NomeColuna": "Ativos Ponderados pelo Risco (RWA) \n(j) = (f) + (g)", "Saldo": 80.0},
        {"CodInst": "999", "NomeColuna": "Ativo Total", "Saldo": 5.0},  # fora do escopo
        {"CodInst": "123", "NomeColuna": "Coluna Desconhecida", "Saldo": 1.0},
    ]
    p = bancos.pivotar(linhas, so_cod_inst={"123"})
    assert p == {"123": {"ativo": 100.0, "pr": 12.0, "rwa": 80.0}}


def test_atualizar_grava_b1_b2_e_basileia(con, monkeypatch):
    monkeypatch.setattr(bancos.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        bancos, "cadastro",
        lambda anomes: [
            {"CodInst": "111", "NomeInstituicao": "BANCO BOM S.A.", "Tcb": "b1", "SegmentoTb": "S3", "Uf": "SP"},
            {"CodInst": "222", "NomeInstituicao": "COOPERATIVA X", "Tcb": "n1", "SegmentoTb": "S5", "Uf": "PR"},
        ] if anomes == 202606 else [],
    )

    def _valores(anomes, relatorio):
        if anomes != 202606:
            return []
        if relatorio == "1":
            return [
                {"CodInst": "111", "NomeColuna": "Ativo Total", "Saldo": 1000.0},
                {"CodInst": "111", "NomeColuna": "Captações", "Saldo": 700.0},
                {"CodInst": "111", "NomeColuna": "Lucro Líquido", "Saldo": 10.0},
                {"CodInst": "222", "NomeColuna": "Ativo Total", "Saldo": 5.0},  # não é b1/b2
            ]
        if relatorio == "2":
            return [
                {"CodInst": "111", "NomeColuna": "Disponibilidades (a)", "Saldo": 30.0},
                {"CodInst": "111", "NomeColuna": "Aplicações Interfinanceiras de Liquidez (b)", "Saldo": 20.0},
                {"CodInst": "111", "NomeColuna": "Títulos e Valores Mobiliários (c)", "Saldo": 500.0},
            ]
        return [
            {"CodInst": "111", "NomeColuna": "Patrimônio de Referência para Comparação com o RWA \n(e)", "Saldo": 15.0},
            {"CodInst": "111", "NomeColuna": "Ativos Ponderados pelo Risco (RWA) \n(j)", "Saldo": 100.0},
        ]

    monkeypatch.setattr(bancos, "valores", _valores)
    mensagem = bancos.atualizar_bancos(con, hoje=date(2026, 9, 15))
    assert "1 emissores b1/b2" in mensagem
    banco = con.execute("SELECT * FROM bancos").fetchone()
    assert banco["nome"] == "BANCO BOM S.A." and banco["tcb"] == "b1"
    assert con.execute("SELECT COUNT(*) FROM bancos WHERE cod_inst='222'").fetchone()[0] == 0
    tri = con.execute("SELECT * FROM bancos_tri WHERE cod_inst='111'").fetchone()
    assert tri["anomes"] == 202606 and tri["captacoes"] == 700.0
    assert tri["basileia"] == 15.0  # 100·15/100 — calculada, não inventada
    assert tri["caixa"] == 50.0  # disp + interfin; TVM fica de fora de propósito


def test_ifdata_fora_do_ar_nao_quebra(con, monkeypatch):
    monkeypatch.setattr(bancos.time, "sleep", lambda _s: None)
    monkeypatch.setattr(bancos, "cadastro", lambda anomes: (_ for _ in ()).throw(OSError("500")))
    assert bancos.atualizar_bancos(con, hoje=date(2026, 9, 15)) is None
