from fato_relevante import cli


def test_entrada_ticker_simples(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        cli, "_exibir_raio_x", lambda ticker, html=False, interativo=False: chamadas.append((ticker, html))
    )
    assert cli._executar_entrada("hglg11") is True
    assert chamadas == [("hglg11", False)]


def test_entrada_com_prefixo_fato_e_html(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        cli, "_exibir_raio_x", lambda ticker, html=False, interativo=False: chamadas.append((ticker, html))
    )
    # exatamente o que o usuário digitou e não funcionava
    assert cli._executar_entrada("fato analisar KNCR11 --html") is True
    assert chamadas == [("KNCR11", True)]
    assert cli._executar_entrada("KNCR11 html") is True
    assert chamadas[-1] == ("KNCR11", True)


def test_entrada_atualizar(monkeypatch):
    chamadas = []
    monkeypatch.setattr(cli, "_executar_atualizacao", lambda con: chamadas.append("atualizou"))
    monkeypatch.setenv("FATO_DATA_DIR", "")
    import fato_relevante.armazenamento as arm

    class _ConFake:
        def close(self):
            pass

    monkeypatch.setattr(arm, "conectar", lambda diretorio=None: _ConFake())
    assert cli._executar_entrada("atualizar") is True
    assert cli._executar_entrada("fato atualizar") is True
    assert chamadas == ["atualizou", "atualizou"]


def test_entrada_ranking(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        cli,
        "_mostrar_ranking",
        lambda por, top=10, sem_alertas=False, segmento=None, incluir_nao_listados=False: chamadas.append(
            (por, sem_alertas)
        ),
    )
    assert cli._executar_entrada("ranking") is True
    assert cli._executar_entrada("ranking pvp sem-alertas") is True
    assert chamadas == [("dy", False), ("pvp", True)]


def test_entrada_sair():
    assert cli._executar_entrada("sair") is False
    assert cli._executar_entrada("fato exit") is False


def test_entrada_ia_sem_ticker_orienta(monkeypatch):
    chamadas = []
    monkeypatch.setattr(cli, "ia", lambda ticker, modelo=None: chamadas.append(ticker))
    assert cli._executar_entrada("ia") is True  # só orienta o uso
    assert chamadas == []
    assert cli._executar_entrada("ia hglg11") is True
    assert chamadas == ["hglg11"]
