"""Ações A1 — modelo emissor→papéis (coleta/empresas.py)."""

from datetime import date

import pytest

from scout import armazenamento
from scout.coleta import empresas

# payloads reais (probe de 20/07/2026), enxugados
COMPOSICAO_IBXX = [
    {"cod": "PETR3", "asset": "PETROBRAS", "type": "ON", "part": "4,0"},
    {"cod": "PETR4", "asset": "PETROBRAS", "type": "PN", "part": "4,5"},
    {"cod": "ABEV3", "asset": "AMBEV S/A", "type": "ON", "part": "2,548"},
]
BUSCA_PETROBRAS = {
    "results": [
        {
            "codeCVM": "916986",
            "issuingCompany": "ACPE",
            "tradingName": "ACU PETROLEO",
            "companyName": "AÇU PETROLEO S.A.",
            "segment": "Não Classificados",
        },
        {
            "codeCVM": "9512",
            "issuingCompany": "PETR",
            "tradingName": "PETROBRAS",
            "companyName": "PETROLEO BRASILEIRO S.A. PETROBRAS",
            "segment": "N2",
        },
    ]
}
DETALHE_PETR = {
    "issuingCompany": "PETR",
    "companyName": "PETROLEO BRASILEIRO S.A. PETROBRAS",
    "cnpj": "33000167000101",
    "code": "PETR4",
    "codeCVM": "9512",
    "industryClassification": "Petróleo. Gás e Biocombustíveis / Exploração. Refino e Distribuição",
    "otherCodes": [
        {"code": "PETR3", "isin": "BRPETRACNOR9"},
        {"code": "PETR4", "isin": "BRPETRACNPR6"},
        {"code": "PETR-DEB62", "isin": "BRPETRDBS092"},
    ],
    "status": "A",
}
BUSCA_AMBEV = {
    "results": [
        {
            "codeCVM": "23264",
            "issuingCompany": "ABEV",
            "tradingName": "AMBEV S/A",
            "companyName": "AMBEV S.A.",
            "segment": "",
        }
    ]
}
DETALHE_ABEV = {
    "issuingCompany": "ABEV",
    "companyName": "AMBEV S.A.",
    "cnpj": "7526557000100",
    "code": "ABEV3",
    "codeCVM": "23264",
    "industryClassification": "Consumo não Cíclico / Bebidas / Cervejas e Refrigerantes",
    "otherCodes": [{"code": "ABEV3", "isin": "BRABEVACNOR1"}],
    "status": "A",
}
CADASTRO_CVM = {
    "33000167000101": {"setor": "Petróleo e Gás", "situacao": "ATIVO", "auditor": "KPMG"},
    "07526557000100": {"setor": "Bebidas e Fumo", "situacao": "ATIVO", "auditor": "PWC"},
}


def _mock_fontes(monkeypatch):
    buscas = {"PETROBRAS": BUSCA_PETROBRAS, "AMBEV S/A": BUSCA_AMBEV}
    detalhes = {"9512": DETALHE_PETR, "23264": DETALHE_ABEV}
    chamadas = {"detalhes": 0}

    monkeypatch.setattr(empresas, "composicao_ibrx", lambda indice="IBXX": COMPOSICAO_IBXX)
    monkeypatch.setattr(empresas.time, "sleep", lambda _s: None)

    def _chamar(url_base, endpoint, parametros):
        if endpoint == "GetInitialCompanies":
            return buscas.get(parametros["company"], {"results": []})
        if endpoint == "GetDetail":
            chamadas["detalhes"] += 1
            return detalhes[str(parametros["codeCVM"])]
        raise AssertionError(endpoint)

    monkeypatch.setattr(empresas, "_chamar", _chamar)
    monkeypatch.setattr(empresas, "carregar_cadastro_cvm", lambda: CADASTRO_CVM)
    monkeypatch.setattr(empresas, "eventos_do_emissor", lambda radical: ([], []))
    monkeypatch.setattr(empresas, "proventos_do_emissor", lambda nome: [])
    return chamadas


def test_papeis_do_detalhe_filtra_debentures():
    papeis = empresas.papeis_do_detalhe(DETALHE_PETR, "PETR")
    assert papeis == [
        ("PETR3", "BRPETRACNOR9", "ON"),
        ("PETR4", "BRPETRACNPR6", "PN"),
    ]


def test_atualizar_cria_emissores_e_papeis(con, monkeypatch):
    _mock_fontes(monkeypatch)
    mensagem = empresas.atualizar_empresas(con, hoje=date(2026, 7, 20))
    assert "2 emissores, 3 papéis" in mensagem

    petr = armazenamento.empresa_por_ticker(con, "petr4")
    assert petr["radical"] == "PETR"
    assert petr["cnpj"] == "33000167000101"
    assert petr["tipo_papel"] == "PN"
    assert petr["no_ibrx100"] == 1
    assert "Petróleo" in petr["setor_b3"]
    # cadastro CVM casado por CNPJ
    assert petr["situacao"] == "ATIVO"
    assert petr["auditor"] == "KPMG"

    # 1 emissor = N papéis: PETR3 e PETR4 apontam para a MESMA empresa
    assert armazenamento.empresa_por_ticker(con, "PETR3")["cod_cvm"] == petr["cod_cvm"]
    assert len(armazenamento.papeis_da_empresa(con, petr["cod_cvm"])) == 2


def test_atualizar_respeita_frescor_semanal(con, monkeypatch):
    chamadas = _mock_fontes(monkeypatch)
    empresas.atualizar_empresas(con, hoje=date(2026, 7, 20))
    assert chamadas["detalhes"] == 2
    # 3 dias depois: dentro do frescor, nem toca a rede
    assert empresas.atualizar_empresas(con, hoje=date(2026, 7, 23)) is None
    assert chamadas["detalhes"] == 2


def test_quem_sai_do_indice_perde_o_escopo_mas_fica_na_base(con, monkeypatch):
    _mock_fontes(monkeypatch)
    empresas.atualizar_empresas(con, hoje=date(2026, 7, 20))
    # semana seguinte: AMBEV saiu do índice
    monkeypatch.setattr(
        empresas, "composicao_ibrx", lambda indice="IBXX": COMPOSICAO_IBXX[:2]
    )
    empresas.atualizar_empresas(con, hoje=date(2026, 7, 27))
    assert armazenamento.empresa_por_ticker(con, "ABEV3")["no_ibrx100"] == 0
    assert len(armazenamento.empresas_listadas(con)) == 1
    assert len(armazenamento.empresas_listadas(con, so_ibrx=False)) == 2


def test_radical_sem_match_nao_derruba_a_carga(con, monkeypatch):
    _mock_fontes(monkeypatch)
    composicao = COMPOSICAO_IBXX + [{"cod": "XYZW3", "asset": "INEXISTENTE", "type": "ON"}]
    monkeypatch.setattr(empresas, "composicao_ibrx", lambda indice="IBXX": composicao)
    mensagem = empresas.atualizar_empresas(con, hoje=date(2026, 7, 20))
    assert "sem match na B3: XYZW" in mensagem
    assert len(armazenamento.empresas_listadas(con)) == 2


# --- eventos societários e proventos (fatia 2 do A1) ---

def test_fator_quantidade_normaliza_os_rotulos_da_b3():
    # semântica validada com casos reais: PETR 2008 (+100% = dobrou),
    # IRBR 2019 (+200% = triplicou), AMER 2024 (grupamento 100:1)
    assert empresas._fator_quantidade("DESDOBRAMENTO", "100,00000000000") == 2.0
    assert empresas._fator_quantidade("DESDOBRAMENTO", "200,00000000000") == 3.0
    assert empresas._fator_quantidade("BONIFICACAO", "5,00000000000") == 1.05
    assert empresas._fator_quantidade("GRUPAMENTO", "0,01000000000") == 0.01
    # rótulo desconhecido ou fator inválido: melhor não ajustar do que ajustar errado
    assert empresas._fator_quantidade("CISAO", "50") is None
    assert empresas._fator_quantidade("DESDOBRAMENTO", "") is None


def test_eventos_e_proventos_gravados_por_papel(con, monkeypatch):
    _mock_fontes(monkeypatch)
    monkeypatch.setattr(
        empresas,
        "eventos_do_emissor",
        lambda radical: (
            [
                {
                    "isinCode": "BRPETRACNOR9",
                    "label": "DESDOBRAMENTO",
                    "factor": "100,00000000000",
                    "lastDatePrior": "25/04/2008",
                },
                {  # ISIN que não é papel nosso (debênture): ignorado
                    "isinCode": "BRPETRDBS092",
                    "label": "DESDOBRAMENTO",
                    "factor": "100,0",
                    "lastDatePrior": "25/04/2008",
                },
            ],
            [],
        )
        if radical == "PETR"
        else ([], []),
    )
    monkeypatch.setattr(
        empresas,
        "proventos_do_emissor",
        lambda nome: [
            {
                "typeStock": "PN",
                "corporateAction": "JRS CAP PROPRIO",
                "valueCash": "0,35048636",
                "quotedPerShares": "1",
                "lastDatePriorEx": "01/06/2026",
            },
            {  # cotação antiga por lote de 1000: vira R$/ação
                "typeStock": "ON",
                "corporateAction": "DIVIDENDO",
                "valueCash": "500,00",
                "quotedPerShares": "1.000,00",
                "lastDatePriorEx": "10/03/2012",
            },
        ]
        if nome == "PETROBRAS"
        else [],
    )
    empresas.atualizar_empresas(con, hoje=date(2026, 7, 20))

    eventos = con.execute("SELECT * FROM acao_eventos ORDER BY ticker").fetchall()
    assert [(e["ticker"], e["data"], e["fator"]) for e in eventos] == [
        ("PETR3", "2008-04-25", 2.0)
    ]
    proventos = con.execute("SELECT * FROM acao_proventos ORDER BY data_com").fetchall()
    assert [(p["ticker"], p["data_com"], p["valor"]) for p in proventos] == [
        ("PETR3", "2012-03-10", 0.5),
        ("PETR4", "2026-06-01", 0.35048636),
    ]


def test_derivadas_de_acao_ajustam_por_evento_real_e_nao_por_salto(con):
    from scout.coleta import b3

    con.execute(
        "INSERT INTO empresas (cod_cvm, cnpj, radical, no_ibrx100) VALUES ('9512', '33000167000101', 'PETR', 1)"
    )
    con.execute("INSERT INTO papeis (ticker, cod_cvm, isin, tipo) VALUES ('PETR4', '9512', 'X', 'PN')")
    # split 2x com data "com" em fev: preço cai de 100 para 50 sem perda real
    con.execute(
        "INSERT INTO acao_eventos (ticker, data, label, fator) VALUES ('PETR4', '2026-02-10', 'DESDOBRAMENTO', 2.0)"
    )
    # dividendo de R$ 1/ação em março (base pós-split)
    con.execute(
        "INSERT INTO acao_proventos (ticker, data_com, label, valor) VALUES ('PETR4', '2026-03-05', 'DIVIDENDO', 1.0)"
    )
    for competencia, fech in [("2026-01", 100.0), ("2026-02", 50.0), ("2026-03", 49.0)]:
        con.execute(
            "INSERT INTO cotacoes_b3 (ticker, competencia, fechamento, dia) VALUES ('PETR4', ?, ?, ?)",
            (competencia, fech, f"{competencia}-28"),
        )
    con.commit()
    b3.recalcular_derivadas(con)

    serie = {
        linha["competencia"]: (linha["fechamento"], linha["fechamento_ajustado"])
        for linha in con.execute(
            "SELECT competencia, fechamento, fechamento_ajustado FROM cotacoes WHERE ticker = 'PETR4'"
        )
    }
    # jan ajustado para a base atual: 100/2 = 50 (split não é queda)
    assert serie["2026-01"][0] == 50.0
    # retorno total: março recebeu R$ 1 de dividendo -> fev ajustado > fev nominal
    assert serie["2026-03"][1] == 49.0  # âncora = preço atual
    assert serie["2026-02"][1] == pytest.approx(49.0 * 50.0 / (49.0 + 1.0))


def test_queda_forte_de_acao_nao_vira_split_falso(con):
    from scout.coleta import b3

    con.execute("INSERT INTO empresas (cod_cvm, cnpj, radical, no_ibrx100) VALUES ('1', '1', 'MGLU', 1)")
    con.execute("INSERT INTO papeis (ticker, cod_cvm, isin, tipo) VALUES ('MGLU3', '1', 'Y', 'ON')")
    # -60% num mês SEM evento societário: tem que continuar sendo queda
    for competencia, fech in [("2026-01", 10.0), ("2026-02", 4.0)]:
        con.execute(
            "INSERT INTO cotacoes_b3 (ticker, competencia, fechamento, dia) VALUES ('MGLU3', ?, ?, ?)",
            (competencia, fech, f"{competencia}-28"),
        )
    con.commit()
    b3.recalcular_derivadas(con)
    serie = {
        linha["competencia"]: linha["fechamento"]
        for linha in con.execute("SELECT competencia, fechamento FROM cotacoes WHERE ticker = 'MGLU3'")
    }
    assert serie["2026-01"] == 10.0  # nada de "ajuste" mascarando o tombo
