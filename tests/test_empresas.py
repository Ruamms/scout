"""Ações A1 — modelo emissor→papéis (coleta/empresas.py)."""

from datetime import date

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
