"""Executa o JavaScript real das calculadoras (via Node) e confere a matemática.

Os demais testes garantem que as calculadoras existem e vêm pré-preenchidas;
este garante que a CONTA está certa: o script é extraído da página gerada e
rodado num DOM mínimo, e os resultados são comparados com valores derivados
de forma independente (fórmula fechada de juros compostos, não o mesmo loop).
"""

import json
import re
import shutil
import subprocess

import pytest

from scout import analise, armazenamento
from scout.coleta import cvm
from scout.relatorio import html as relatorio_html

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js não disponível para executar o JS"
)


def _pagina(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    armazenamento.gravar_cotacoes(
        con,
        "TSTE11",
        [("2026-01", 90.0, 90.0), ("2026-02", 100.0, 100.0)],
        100.0,
        "2026-02-17",
        "2026-02-18",
    )
    return relatorio_html.gerar(analise.montar_completo(con, "tste11"))


def _script_da_pagina(pagina):
    for bloco in pagina.split("<script>")[1:]:
        corpo = bloco.split("</script>")[0]
        if "function calcUmaCota" in corpo:
            return corpo
    raise AssertionError("script das calculadoras não encontrado na página")


_HARNESS = """
const els = {};
function el(id) {
  if (!els[id]) els[id] = { value: '', checked: false, textContent: '', innerHTML: '' };
  return els[id];
}
const document = { getElementById: el };
const RETRO = { '12 meses': { com: { Fundo: 10, CDI: 8 }, sem: { Fundo: 5 } } };

__SCRIPT__

el('uc-preco').value = '95.5';
el('uc-rend').value = '0.9';
calcUmaCota();

el('pa-inicial').value = '1000';
el('pa-mensal').value = '100';
el('pa-anos').value = '1';
el('pa-taxa').value = '1';
el('pa-reinvestir').checked = true;
calcAportes();
const com = {
  aportado: el('pa-aportado').textContent,
  final: el('pa-final').textContent,
  rendimentos: el('pa-rendimentos').textContent,
  renda: el('pa-renda').textContent,
};
el('pa-reinvestir').checked = false;
calcAportes();
const sem = {
  final: el('pa-final').textContent,
  rendimentos: el('pa-rendimentos').textContent,
  renda: el('pa-renda').textContent,
};

el('rt-valor').value = '1000';
el('rt-janela').value = '12 meses';
el('rt-reinvestir').checked = true;
calcRetro();

console.log(JSON.stringify({
  cotas: el('uc-cotas').textContent,
  investimento: el('uc-invest').textContent,
  com: com,
  sem: sem,
  retro: el('rt-resultado').innerHTML,
}));
"""


def _rodar(pagina, tmp_path):
    harness = _HARNESS.replace("__SCRIPT__", _script_da_pagina(pagina))
    arquivo = tmp_path / "harness.js"
    arquivo.write_text(harness, encoding="utf-8")
    saida = subprocess.run(
        ["node", str(arquivo)], capture_output=True, text=True, encoding="utf-8"
    )
    assert saida.returncode == 0, f"erro no Node: {saida.stderr}"
    return json.loads(saida.stdout)


def _numero(texto):
    """Extrai o inteiro de um texto formatado tipo 'R$ 2.395'."""
    return int(re.sub(r"\D", "", texto))


def test_matematica_das_calculadoras(con, zip_cvm, tmp_path):
    resultado = _rodar(_pagina(con, zip_cvm), tmp_path)

    # Uma cota por mês: ceil(95,50 / 0,90) = 107 cotas; 107 × R$ 95,50 ≈ R$ 10.219
    assert _numero(resultado["cotas"]) == 107
    assert _numero(resultado["investimento"]) == 10219

    # Projeção COM reinvestimento (1% a.m., 12 meses, aporte no fim do mês):
    # fórmula fechada: inicial·(1+i)^n + mensal·((1+i)^n − 1)/i
    fator = 1.01**12
    final = 1000 * fator + 100 * (fator - 1) / 0.01
    assert _numero(resultado["com"]["aportado"]) == 2200
    assert _numero(resultado["com"]["final"]) == round(final)
    assert _numero(resultado["com"]["rendimentos"]) == round(final - 2200)
    assert _numero(resultado["com"]["renda"]) == round(final * 0.01)

    # SEM reinvestimento: patrimônio = só o aportado; dividendos rendem sobre o
    # principal do mês: i·Σ(inicial + m·mensal) = 1%·(12·1000 + 100·66) = 186
    assert _numero(resultado["sem"]["final"]) == 2200
    assert _numero(resultado["sem"]["rendimentos"]) == 186
    assert _numero(resultado["sem"]["renda"]) == 22

    # E se eu tivesse investido: R$ 1.000 × (1+10%) no fundo e × (1+8%) no CDI
    assert "1.100" in resultado["retro"] and "1.080" in resultado["retro"]
    assert "no fundo" in resultado["retro"] and "no CDI" in resultado["retro"]


def test_calculadora_ignora_entrada_invalida(con, zip_cvm, tmp_path):
    pagina = _pagina(con, zip_cvm)
    harness = _HARNESS.replace("__SCRIPT__", _script_da_pagina(pagina)).replace(
        "el('uc-preco').value = '95.5';", "el('uc-preco').value = '0';"
    )
    arquivo = tmp_path / "harness_zero.js"
    arquivo.write_text(harness, encoding="utf-8")
    saida = subprocess.run(
        ["node", str(arquivo)], capture_output=True, text=True, encoding="utf-8"
    )
    assert saida.returncode == 0, f"erro no Node: {saida.stderr}"
    resultado = json.loads(saida.stdout)
    # preço 0 não pode virar conta maluca: mostra travessão
    assert resultado["cotas"] == "—"
    assert resultado["investimento"] == "—"
