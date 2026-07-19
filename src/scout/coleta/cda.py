"""Composição da carteira dos ETFs — dataset CDA da CVM (mensal).

O CDA dos fundos de índice tem arquivo próprio (`cda_fie_AAAAMM.csv`) com as
posições da carteira e o PL. Duas funções aqui:

1. gravar a composição por GRUPO de ativo (Renda Fixa, Ações, Exterior, Cotas
   de Fundos) — alimenta o Misto/Híbrido dinâmico e o painel do ETF;
2. o VERIFICADOR de classificação: compara a composição real com a
   `classificacao_scout` da curadoria (dados/classificacao_etfs.csv) e aponta
   divergências — carteira muda, classificação envelhece, o dado avisa.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from .. import armazenamento

URL = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{ano}{mes:02d}.zip"
_HEADERS = {"User-Agent": "Mozilla/5.0 (scout)"}

# TP_APLIC -> grupo (linguagem do investidor). O que não está aqui é ignorado
# no denominador (valores a receber/pagar, futuros, passivos).
GRUPOS = {
    "Ações": "Ações",
    "Ações e outros TVM cedidos em empréstimo": "Ações",
    "Certificado ou recibo de depósito de valores mobiliários": "Ações",
    "Títulos Públicos": "Renda Fixa",
    "Debêntures": "Renda Fixa",
    "Operações Compromissadas": "Renda Fixa",
    "Disponibilidades": "Renda Fixa",
    "Depósitos a prazo e outros títulos de IF": "Renda Fixa",
    "Títulos de Crédito Privado": "Renda Fixa",
    "Obrigações por ações e outros TVM recebidos em empréstimo": "Renda Fixa",
    "Investimento no Exterior": "Exterior",
    "Brazilian Depository Receipt - BDR": "Exterior",
    "Fundos Offshore": "Exterior",
    "Cotas de Fundos": "Cotas de Fundos",
}

# classificação nossa -> regra de coerência com a carteira (grupo, mínimo %)
_REGRAS_COERENCIA = {
    "Renda Fixa": ("Renda Fixa", 80.0),
    "Ações Brasil": ("Ações", 70.0),
    "FIIs (índice)": ("Cotas de Fundos", 70.0),
    # internacionais/cripto/commodities vivem em "Exterior" (BDR, offshore,
    # investimento no exterior) — a regra é não ter muita coisa local
    "Ações Internacionais": ("Exterior", 60.0),
    "Cripto": ("Exterior", 60.0),
    "Commodities": ("Exterior", 40.0),
}


def _baixar_mes(ano: int, mes: int) -> bytes | None:
    try:
        requisicao = urllib.request.Request(URL.format(ano=ano, mes=mes), headers=_HEADERS)
        with urllib.request.urlopen(requisicao, timeout=600) as resposta:
            return resposta.read()
    except (urllib.error.URLError, OSError):
        return None


def extrair_carteiras(conteudo: bytes, cnpjs: set[str]) -> tuple[dict, dict, str]:
    """({cnpj: {grupo: pct}}, {cnpj: pl}, competencia) do arquivo cda_fie."""
    posicoes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pls: dict[str, float] = {}
    competencia = ""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        membro = next((n for n in zf.namelist() if n.startswith("cda_fie_") and "CONFID" not in n), None)
        if membro is None:
            return {}, {}, ""
        with zf.open(membro) as fh:
            leitor = csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";")
            for linha in leitor:
                cnpj = armazenamento.so_digitos(linha.get("CNPJ_FUNDO_CLASSE") or linha.get("CNPJ_FUNDO"))
                if cnpj not in cnpjs:
                    continue
                competencia = (linha.get("DT_COMPTC") or "")[:7] or competencia
                try:
                    pls[cnpj] = float(linha.get("VL_PATRIM_LIQ") or 0) or pls.get(cnpj, 0)
                except ValueError:
                    pass
                grupo = GRUPOS.get((linha.get("TP_APLIC") or "").strip())
                if grupo is None:
                    continue
                try:
                    valor = float(linha.get("VL_MERC_POS_FINAL") or 0)
                except ValueError:
                    continue
                if valor > 0:
                    posicoes[cnpj][grupo] += valor
    composicao = {}
    for cnpj, grupos in posicoes.items():
        total = sum(grupos.values())
        if total > 0:
            composicao[cnpj] = {grupo: 100 * valor / total for grupo, valor in grupos.items()}
    return composicao, pls, competencia


def carregar_classificacoes(raiz: Path | None = None) -> dict[str, dict]:
    """dados/classificacao_etfs.csv -> {cnpj: {ticker, classificacao_scout, ...}}."""
    caminho = (raiz or Path(".")) / "dados" / "classificacao_etfs.csv"
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        return {
            armazenamento.so_digitos(linha["cnpj"]): linha
            for linha in csv.DictReader(fh, delimiter=";")
        }


def verificar(composicao: dict[str, dict[str, float]], classificacoes: dict[str, dict]) -> list[dict]:
    """Divergências entre a carteira real e a classificação da curadoria."""
    divergencias = []
    for cnpj, grupos in composicao.items():
        classificado = classificacoes.get(cnpj)
        if not classificado:
            continue
        classe = (classificado.get("classificacao_scout") or "").strip()
        regra = _REGRAS_COERENCIA.get(classe)
        if regra is None:
            continue
        grupo_esperado, minimo = regra
        pct = grupos.get(grupo_esperado, 0.0)
        resumo = " · ".join(f"{g} {p:.0f}%" for g, p in sorted(grupos.items(), key=lambda kv: -kv[1]))
        if pct >= minimo:
            continue
        # situações especiais que NÃO são erro de curadoria:
        if classe != "Renda Fixa" and grupos.get("Renda Fixa", 0) >= 95:
            tipo, motivo = "atenção", "carteira ~100% renda fixa — provável fundo novo em captação"
        elif grupos.get("Cotas de Fundos", 0) >= 60 and grupo_esperado != "Cotas de Fundos":
            tipo, motivo = "atenção", "exposição via cotas de outro fundo — conferir o fundo-alvo manualmente"
        else:
            tipo = "divergência"
            motivo = f"{grupo_esperado} em {pct:.0f}% (esperado ≥ {minimo:.0f}% para '{classe}')"
        divergencias.append(
            {
                "ticker": (classificado.get("ticker") or "").strip() or cnpj,
                "tipo": tipo,
                "classificacao_scout": classe,
                "carteira": resumo,
                "motivo": motivo,
            }
        )
    return divergencias


def atualizar_composicao(
    con: sqlite3.Connection,
    hoje: date | None = None,
    ao_progredir=None,
    raiz: Path | None = None,
) -> str | None:
    """1x por mês: baixa o CDA mais recente disponível (M-1, M-2 ou M-3),
    grava composição+PL dos ETFs e roda o verificador de classificação."""
    hoje = hoje or date.today()
    cnpjs = {linha[0] for linha in con.execute("SELECT cnpj FROM etfs")}
    if not cnpjs:
        return None
    candidatos = []
    ano, mes = hoje.year, hoje.month
    for _ in range(3):
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
        candidatos.append((ano, mes))
    carregados = {linha[0] for linha in con.execute("SELECT arquivo FROM cargas")}
    alvo = next(
        ((a, m) for a, m in candidatos if f"cda_fi_{a}{m:02d}.zip" not in carregados), None
    )
    if alvo is None:
        return None  # o mais recente já está carregado
    conteudo = None
    for ano, mes in candidatos:
        if f"cda_fi_{ano}{mes:02d}.zip" in carregados:
            break  # não regride para um mês mais antigo que o já carregado
        conteudo = _baixar_mes(ano, mes)
        if conteudo:
            break
    if not conteudo:
        return "CDA (carteiras de ETF) indisponível no momento — usando o cache local"
    composicao, pls, competencia = extrair_carteiras(conteudo, cnpjs)
    for cnpj, grupos in composicao.items():
        con.execute("DELETE FROM etf_carteira WHERE cnpj = ? AND competencia = ?", (cnpj, competencia))
        con.executemany(
            "INSERT INTO etf_carteira (cnpj, competencia, grupo, pct) VALUES (?, ?, ?, ?)",
            [(cnpj, competencia, grupo, pct) for grupo, pct in grupos.items()],
        )
    con.executemany(
        "INSERT OR REPLACE INTO etf_pl (cnpj, competencia, pl) VALUES (?, ?, ?)",
        [(cnpj, competencia, pl) for cnpj, pl in pls.items()],
    )
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, ?)",
        (f"cda_fi_{ano}{mes:02d}.zip", hoje.isoformat()),
    )
    con.commit()

    divergencias = verificar(composicao, carregar_classificacoes(raiz))
    destino = armazenamento.diretorio_dados() / "etf_divergencias.csv"
    if divergencias:
        with destino.open("w", encoding="utf-8-sig", newline="") as fh:
            escritor = csv.DictWriter(
                fh,
                fieldnames=["ticker", "tipo", "classificacao_scout", "carteira", "motivo"],
                delimiter=";",
            )
            escritor.writeheader()
            escritor.writerows(sorted(divergencias, key=lambda d: (d["tipo"], d["ticker"])))
    else:
        destino.unlink(missing_ok=True)
    duras = sum(1 for d in divergencias if d["tipo"] == "divergência")
    brandas = len(divergencias) - duras
    mensagem = (
        f"carteiras de ETF ({competencia}): {len(composicao)} fundos · "
        + (
            f"⚠ {duras} divergências e {brandas} pontos de atenção — revisar {destino}"
            if divergencias
            else "classificações coerentes com as carteiras"
        )
    )
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
