from datetime import datetime

from scout import armazenamento
from scout.coleta import cvm
from scout.relatorio import site
from conftest import montar_zip_universo


def _base(con):
    cvm.carregar_zip(con, montar_zip_universo(), "inf_mensal_fii_2026.zip")
    armazenamento.gravar_cotacoes(
        con,
        "ALFA11",
        [("2026-01", 90.0, 90.0), ("2026-02", 100.0, 100.0)],
        100.0,
        "2026-02-17",
        "2026-02-18",
    )
    return con


def test_gerar_site_completo(con, tmp_path):
    _base(con)
    resumo = site.gerar(
        con, tmp_path / "site", com_cotacoes=False, agora=datetime(2026, 7, 18, 7, 0)
    )
    pasta = tmp_path / "site"
    assert resumo["paginas"] == 3
    assert (pasta / "index.html").exists()
    assert (pasta / "ALFA11.html").exists()
    assert (pasta / "BETA11.html").exists()
    assert (pasta / "apoie.html").exists()

    indice = (pasta / "index.html").read_text(encoding="utf-8")
    assert "3 fundos negociáveis" in indice
    assert 'href="ALFA11.html"' in indice
    assert "atualizado em 18/07/2026 07:00" in indice
    # busca client-side e rankings
    assert 'id="busca"' in indice
    assert "function filtrar" in indice
    assert "Rankings do dia" in indice
    assert "Maiores patrimônios" in indice
    assert "não recomendação" in indice
    # linha com dados de busca em minúsculas
    assert 'data-busca="alfa11 alfa fii shoppings"' in indice
    # botão de atualização manual + status ao vivo via API pública do GitHub
    assert "Atualizar agora" in indice
    assert "actions/workflows/site.yml" in indice
    assert "async function statusAtualizacao" in indice
    assert 'id="atu-barra"' in indice


def test_gerar_site_com_callback_de_progresso(con, tmp_path):
    _base(con)
    chamadas = []
    site.gerar(
        con,
        tmp_path / "site",
        com_cotacoes=False,
        ao_item=lambda fase, atual, total: chamadas.append((fase, atual, total)),
    )
    assert ("páginas", 1, 3) in chamadas
    assert ("páginas", 3, 3) in chamadas


def test_gerar_site_com_limite(con, tmp_path):
    _base(con)
    resumo = site.gerar(con, tmp_path / "site", com_cotacoes=False, limite=1)
    # só o maior fundo por PL (BETA) vira página
    assert resumo["paginas"] == 1
    assert (tmp_path / "site" / "BETA11.html").exists()
    assert not (tmp_path / "site" / "ALFA11.html").exists()


def test_paginas_do_site_tem_navegacao_e_sem_links_mortos(con, tmp_path):
    _base(con)
    site.gerar(con, tmp_path / "site", com_cotacoes=False, limite=2)
    # com limite=2 (maiores PLs: BETA e GAMA), ALFA11 fica fora do site
    assert not (tmp_path / "site" / "ALFA11.html").exists()
    pagina = (tmp_path / "site" / "BETA11.html").read_text(encoding="utf-8")
    # navegação: a marca no topo volta ao índice + salto por ticker no header
    assert 'class="brand" href="index.html"' in pagina
    assert 'id="ir-ticker"' in pagina
    assert "function irTicker" in pagina
    # header de marca visível (wordmark com o O verde)
    assert 'class="wordmark">SC<span class="brand-o">O</span>UT</span>' in pagina
    # ALFA11 é fundo irmão (mesmo administrador) mas não tem página: sem link morto
    assert 'href="ALFA11.html"' not in pagina
    assert "ALFA11" in pagina  # segue visível, como texto


def test_indice_tem_aviso_de_beta_dispensavel(con, tmp_path):
    _base(con)
    site.gerar(con, tmp_path / "site", com_cotacoes=False)
    indice = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'id="aviso-beta"' in indice
    assert "github.com/Ruamms/scout/issues" in indice
    assert "ruamms3@gmail.com" in indice
    # dispensável e lembrado entre visitas
    assert "scout-beta-visto" in indice
    assert "function fecharBeta" in indice


def test_indice_recolhe_tabela_grande(con, tmp_path, monkeypatch):
    _base(con)
    monkeypatch.setattr(site, "_VISIVEIS_DE_INICIO", 1)
    site.gerar(con, tmp_path / "site", com_cotacoes=False)
    indice = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    # só o maior fundo visível de início; o resto recolhido mas presente (a busca acha todos)
    assert indice.count('class="fundo-extra" hidden') == 2
    assert "Mostrar todos os 3 fundos" in indice
    assert "function mostrarTodos" in indice
    assert "hidden>Mostrar todos" not in indice  # botão visível


def test_indice_pequeno_ja_mostra_tudo(con, tmp_path):
    _base(con)
    site.gerar(con, tmp_path / "site", com_cotacoes=False)
    indice = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    # 3 fundos <= limite: nenhuma linha recolhida e o botão nasce escondido
    assert 'class="fundo-extra"' not in indice
    assert "hidden>Mostrar todos" in indice


def test_relatorio_local_nao_tem_navegacao_de_site(con):
    from scout import analise
    from scout.relatorio import html as relatorio_html

    _base(con)
    completo = analise.montar_completo(con, "alfa11")
    pagina = relatorio_html.gerar(completo)  # sem `publicados` = relatório avulso
    assert "todos os fundos</a>" not in pagina
    assert 'id="ir-ticker"' not in pagina


def test_pagina_do_fundo_no_site_tem_pares_via_varredura(con, tmp_path):
    _base(con)
    site.gerar(con, tmp_path / "site", com_cotacoes=False)
    pagina = (tmp_path / "site" / "ALFA11.html").read_text(encoding="utf-8")
    # pares do segmento calculados a partir da varredura pré-computada
    assert "Pares do segmento" in pagina
    assert 'href="BETA11.html"' in pagina
