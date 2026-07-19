"""Coleta dos informes mensais de FII dos dados abertos da CVM.

Fonte: https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/
Um ZIP por ano (2016+), cada um com os CSVs geral, complemento e
ativo_passivo (separador ';', encoding latin-1).
"""

from __future__ import annotations

import csv
import io
import sqlite3
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import date

URL_BASE = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/"
URL_BASE_TRIMESTRAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/"
# cadastro vivo de todos os fundos: gestora e administrador por CNPJ
URL_REGISTRO = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
ANO_INICIAL = 2016
DIAS_FRESCOR_REGISTRO = 7  # cadastro muda devagar; 1 download por semana basta

# A Resolução CVM 175 renomeou colunas a partir de 2024; este mapa
# normaliza os dois vocabulários para o antigo.
_RENOMEIA = {
    "CNPJ_Fundo_Classe": "CNPJ_Fundo",
    "Nome_Fundo_Classe": "Nome_Fundo",
}


def nome_arquivo(ano: int) -> str:
    return f"inf_mensal_fii_{ano}.zip"


def nome_arquivo_trimestral(ano: int) -> str:
    return f"inf_trimestral_fii_{ano}.zip"


def _baixar_url(url: str, tentativas: int = 3) -> bytes:
    """Download com retry: a CVM tem janelas de indisponibilidade curtas
    (madrugadas/fins de semana) que não devem derrubar uma atualização."""
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=120) as resposta:
                return resposta.read()
        except (urllib.error.URLError, OSError) as erro:
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(5 * (tentativa + 1) ** 2)  # 5s, depois 20s
    raise ultimo_erro


def baixar(ano: int) -> bytes:
    return _baixar_url(URL_BASE + nome_arquivo(ano))


def baixar_trimestral(ano: int) -> bytes:
    return _baixar_url(URL_BASE_TRIMESTRAL + nome_arquivo_trimestral(ano))


def anos_pendentes(
    con: sqlite3.Connection, hoje: date, nomeador: Callable[[int], str] = nome_arquivo
) -> list[int]:
    """Anos a baixar: os que faltam + os 2 últimos (informes chegam com atraso)."""
    carregados = {linha[0] for linha in con.execute("SELECT arquivo FROM cargas")}
    return [
        ano
        for ano in range(ANO_INICIAL, hoje.year + 1)
        if nomeador(ano) not in carregados or ano >= hoje.year - 1
    ]


def atualizar(
    con: sqlite3.Connection,
    hoje: date | None = None,
    ao_progredir: Callable[[str], None] | None = None,
) -> list[str]:
    hoje = hoje or date.today()
    resumo = []
    for ano in anos_pendentes(con, hoje):
        arquivo = nome_arquivo(ano)
        gerais, complementos = carregar_zip(con, baixar(ano), arquivo)
        mensagem = f"{arquivo}: {gerais} informes gerais, {complementos} complementos"
        resumo.append(mensagem)
        if ao_progredir:
            ao_progredir(mensagem)
    for ano in anos_pendentes(con, hoje, nome_arquivo_trimestral):
        arquivo = nome_arquivo_trimestral(ano)
        imoveis, resultados = carregar_zip_trimestral(con, baixar_trimestral(ano), arquivo)
        mensagem = f"{arquivo}: {imoveis} imóveis, {resultados} resultados"
        resumo.append(mensagem)
        if ao_progredir:
            ao_progredir(mensagem)
    mensagem_registro = atualizar_registro(con, hoje)
    if mensagem_registro:
        resumo.append(mensagem_registro)
        if ao_progredir:
            ao_progredir(mensagem_registro)
    return resumo


def atualizar_registro(con: sqlite3.Connection, hoje: date | None = None) -> str | None:
    """Baixa o cadastro de fundos da CVM (gestora/administrador) se o local
    tiver mais de DIAS_FRESCOR_REGISTRO dias. Retorna a mensagem de progresso,
    ou None quando não havia nada a fazer."""
    from .. import armazenamento

    hoje = hoje or date.today()
    meta = armazenamento.cadastro_meta(con)
    if meta and meta["atualizado_em"]:
        idade = (hoje - date.fromisoformat(meta["atualizado_em"][:10])).days
        if idade < DIAS_FRESCOR_REGISTRO:
            return None
    total = carregar_registro(con, _baixar_url(URL_REGISTRO), hoje)
    return f"registro de fundos (cadastro CVM): {total} FIIs com gestora/administrador"


def carregar_registro(con: sqlite3.Connection, conteudo: bytes, hoje: date | None = None) -> int:
    """Grava do registro CVM apenas os fundos Tipo_Fundo = FII."""
    from .. import armazenamento

    hoje = hoje or date.today()
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        linhas = _ler_csv(zf, "registro_fundo")
    registros = [
        (
            armazenamento.so_digitos(linha.get("CNPJ_Fundo")),
            (linha.get("Denominacao_Social") or "").strip() or None,
            (linha.get("Situacao") or "").strip() or None,
            (linha.get("Administrador") or "").strip() or None,
            (linha.get("CNPJ_Administrador") or "").strip() or None,
            (linha.get("Gestor") or "").strip() or None,
            armazenamento.so_digitos(linha.get("CPF_CNPJ_Gestor")) or None,
            (linha.get("Tipo_Pessoa_Gestor") or "").strip() or None,
        )
        for linha in linhas
        if (linha.get("Tipo_Fundo") or "").strip().upper() in ("FII", "FIIM")
        and armazenamento.so_digitos(linha.get("CNPJ_Fundo"))
    ]
    return armazenamento.gravar_cadastro(con, registros, hoje.isoformat())


def carregar_zip(con: sqlite3.Connection, conteudo: bytes, arquivo: str) -> tuple[int, int]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        gerais = _ler_csv(zf, "geral")
        complementos = _ler_csv(zf, "complemento")
    n_gerais = _gravar_gerais(con, gerais)
    n_complementos = _gravar_complementos(con, complementos)
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, datetime('now'))",
        (arquivo,),
    )
    con.commit()
    return n_gerais, n_complementos


def carregar_zip_trimestral(
    con: sqlite3.Connection, conteudo: bytes, arquivo: str
) -> tuple[int, int]:
    """Carrega do informe trimestral os imóveis e o resultado contábil/financeiro."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        imoveis = _ler_csv(zf, "fii_imovel_2")
        resultados = _ler_csv(zf, "resultado_contabil_financeiro")
        try:
            inquilinos = _ler_csv(zf, "renda_acabado_inquilino")
        except ValueError:  # arquivo não existe nos anos mais antigos
            inquilinos = []
    n_imoveis = _gravar_imoveis(con, imoveis)
    n_resultados = _gravar_resultados(con, resultados)
    _gravar_setores(con, inquilinos)
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, datetime('now'))",
        (arquivo,),
    )
    con.commit()
    return n_imoveis, n_resultados


def _gravar_imoveis(con: sqlite3.Connection, linhas: list[dict]) -> int:
    total = 0
    for indice, linha in enumerate(linhas):
        chave = _chave(linha)
        if chave is None:
            continue
        nome = (linha.get("Nome_Imovel") or "").strip() or (
            linha.get("Endereco") or ""
        ).strip() or f"imóvel #{indice}"
        con.execute(
            """
            INSERT OR REPLACE INTO imoveis
                (cnpj, competencia, nome, endereco, area, vacancia, inadimplencia, pct_receita)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                *chave,
                nome,
                linha.get("Endereco") or None,
                _numero(linha.get("Area")),
                # vacância/inadimplência vêm como FRAÇÃO (1.0 = 100%);
                # Percentual_Receitas_FII vem como PERCENTUAL (0-100) — escala da CVM
                _numero(linha.get("Percentual_Vacancia")),
                _numero(linha.get("Percentual_Inadimplencia")),
                _numero(linha.get("Percentual_Receitas_FII")),
            ),
        )
        total += 1
    return total


def _gravar_setores(con: sqlite3.Connection, linhas: list[dict]) -> int:
    """Setor de atuação dos inquilinos por imóvel (% da receita do FII, fração)."""
    total = 0
    for indice, linha in enumerate(linhas):
        chave = _chave(linha)
        if chave is None:
            continue
        setor = (linha.get("Setor_Atuacao") or "").strip()
        if not setor or setor == "-":
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO setores_inquilinos
                (cnpj, competencia, item, imovel, setor, pct_receita_fii)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                *chave,
                indice,
                (linha.get("Nome_Imovel") or "").strip() or None,
                setor,
                _numero(linha.get("Percentual_Receitas_FII")),
            ),
        )
        total += 1
    return total


def _gravar_resultados(con: sqlite3.Connection, linhas: list[dict]) -> int:
    total = 0
    for linha in linhas:
        chave = _chave(linha)
        if chave is None:
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO resultados_trimestrais
                (cnpj, competencia, resultado_financeiro, rendimentos_declarados,
                 lucro_contabil, resultado_acumulado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                *chave,
                _numero(linha.get("Resultado_Trimestral_Liquido_Financeiro")),
                _numero(linha.get("Rendimentos_Declarados")),
                _numero(linha.get("Lucro_Contabil")),
                _numero(linha.get("Resultado_Financeiro_Liquido_Acumulado")),
            ),
        )
        total += 1
    return total


def _ler_csv(zf: zipfile.ZipFile, sufixo: str) -> list[dict]:
    membro = next((n for n in zf.namelist() if sufixo in n), None)
    if membro is None:
        raise ValueError(f"CSV '{sufixo}' não encontrado no ZIP ({zf.namelist()})")
    with zf.open(membro) as fh:
        texto = io.TextIOWrapper(fh, encoding="latin-1")
        linhas = [_normalizar(linha) for linha in csv.DictReader(texto, delimiter=";")]
    # Grava na ordem: menor versão primeiro e, em empate, linhas com ISIN
    # por último — assim o REPLACE deixa vencer a informação mais completa.
    linhas.sort(key=lambda l: (_inteiro(l.get("Versao")), 1 if l.get("Codigo_ISIN") else 0))
    return linhas


def _normalizar(linha: dict) -> dict:
    return {_RENOMEIA.get(chave, chave): valor for chave, valor in linha.items() if chave}


def _gravar_gerais(con: sqlite3.Connection, linhas: list[dict]) -> int:
    total = 0
    for linha in linhas:
        chave = _chave(linha)
        if chave is None:
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO informes_gerais
                (cnpj, competencia, nome, segmento, tipo_gestao, isin, cotas_emitidas,
                 administrador, cnpj_administrador)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                *chave,
                linha.get("Nome_Fundo") or None,
                linha.get("Segmento_Atuacao") or None,
                linha.get("Tipo_Gestao") or None,
                linha.get("Codigo_ISIN") or None,
                _numero(linha.get("Quantidade_Cotas_Emitidas")),
                linha.get("Nome_Administrador") or None,
                linha.get("CNPJ_Administrador") or None,
            ),
        )
        total += 1
    return total


def _gravar_complementos(con: sqlite3.Connection, linhas: list[dict]) -> int:
    total = 0
    for linha in linhas:
        chave = _chave(linha)
        if chave is None:
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO informes_complemento
                (cnpj, competencia, valor_ativo, patrimonio_liquido, cotas_emitidas,
                 vp_cota, rentab_patrimonial_mes, dy_mes, amortizacao_mes, cotistas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                *chave,
                _numero(linha.get("Valor_Ativo")),
                _numero(linha.get("Patrimonio_Liquido")),
                _numero(linha.get("Cotas_Emitidas")),
                _numero(linha.get("Valor_Patrimonial_Cotas")),
                _numero(linha.get("Percentual_Rentabilidade_Patrimonial_Mes")),
                _numero(linha.get("Percentual_Dividend_Yield_Mes")),
                _numero(linha.get("Percentual_Amortizacao_Cotas_Mes")),
                _numero(linha.get("Total_Numero_Cotistas")),
            ),
        )
        total += 1
    return total


def _chave(linha: dict) -> tuple[str, str] | None:
    cnpj = (linha.get("CNPJ_Fundo") or "").strip()
    referencia = (linha.get("Data_Referencia") or "").strip()
    if not cnpj or len(referencia) < 7:
        return None
    return cnpj, referencia[:7]


def _numero(valor: str | None) -> float | None:
    if valor is None:
        return None
    valor = valor.strip()
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _inteiro(valor: str | None) -> int:
    try:
        return int(valor or 0)
    except ValueError:
        return 0
