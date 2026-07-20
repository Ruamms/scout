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

# classificação nossa -> regra de coerência com a carteira (grupo, mínimo %).
# "Misto/Híbrido" fica de fora de propósito: a natureza dele é não ter grupo
# dominante — a composição é exibida, não policiada.
_REGRAS_COERENCIA = {
    "Renda Fixa": ("Renda Fixa", 80.0),
    "Ações Brasil": ("Ações", 70.0),
    "FIIs (índice)": ("Cotas de Fundos", 70.0),
    # internacionais/cripto/commodities/RF internacional vivem em "Exterior"
    # (BDR, offshore, investimento no exterior) — a regra é não ter muita coisa local
    "Ações Internacionais": ("Exterior", 60.0),
    "Renda Fixa Internacional": ("Exterior", 60.0),
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


def extrair_carteiras(conteudo: bytes, cnpjs: set[str]) -> tuple[dict, dict, str, dict]:
    """({cnpj: {grupo: pct}}, {cnpj: pl}, competencia, {cnpj: top posições})."""
    posicoes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    itens: dict[str, list[dict]] = defaultdict(list)
    pls: dict[str, float] = {}
    competencia = ""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        membro = next((n for n in zf.namelist() if n.startswith("cda_fie_") and "CONFID" not in n), None)
        if membro is None:
            return {}, {}, "", {}
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
                    codigo = (linha.get("CD_ATIVO") or "").strip().upper()
                    nome = (
                        (linha.get("DS_ATIVO") or "").strip()
                        or (linha.get("EMISSOR") or "").strip()
                        or codigo
                    )
                    if codigo or nome:
                        try:
                            quantidade = float(linha.get("QT_POS_FINAL") or 0)
                        except ValueError:
                            quantidade = 0.0
                        itens[cnpj].append(
                            {
                                "codigo": codigo,
                                "nome": nome,
                                "cnpj_emissor": armazenamento.so_digitos(linha.get("CPF_CNPJ_EMISSOR")),
                                "valor": valor,
                                "quantidade": quantidade,
                            }
                        )
    composicao = {}
    top_posicoes: dict[str, list[dict]] = {}
    for cnpj, grupos in posicoes.items():
        total = sum(grupos.values())
        if total <= 0:
            continue
        composicao[cnpj] = {grupo: 100 * valor / total for grupo, valor in grupos.items()}
        # posições homônimas se somam (mesmo papel em carteira e emprestado)
        agregadas: dict[tuple, dict] = {}
        for item in itens.get(cnpj, []):
            chave = (item["codigo"], item["nome"])
            if chave in agregadas:
                agregadas[chave]["valor"] += item["valor"]
                agregadas[chave]["quantidade"] += item.get("quantidade", 0.0)
            else:
                agregadas[chave] = dict(item)
        # carteira COMPLETA (todas as posições), maior peso primeiro. A página
        # destaca o top 10 e deixa o restante numa tabela expansível.
        completa = sorted(agregadas.values(), key=lambda i: -i["valor"])
        top_posicoes[cnpj] = [
            {**item, "pct": 100 * item["valor"] / total} for item in completa
        ]
    return composicao, pls, competencia, top_posicoes


def carregar_classificacoes(raiz: Path | None = None) -> dict[str, dict]:
    """dados/classificacao_etfs.csv -> {cnpj: {ticker, classificacao_scout, ...}}.

    Procura no repositório (curadoria editável) e, no executável PyInstaller,
    nos dados embutidos (sys._MEIPASS)."""
    import sys

    candidatos = [
        (raiz or Path(".")) / "dados" / "classificacao_etfs.csv",
        Path(__file__).resolve().parents[3] / "dados" / "classificacao_etfs.csv",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.insert(0, Path(meipass) / "dados" / "classificacao_etfs.csv")
    caminho = next((c for c in candidatos if c.exists()), None)
    if caminho is None:
        return {}
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        classificacoes = {
            armazenamento.so_digitos(linha["cnpj"]): linha
            for linha in csv.DictReader(fh, delimiter=";")
        }
    # overlay das reclassificações automáticas: a classe efetiva já reflete a
    # correção, e a metadata `reclassificado` alimenta o selo na página do ETF
    for cnpj, entrada in carregar_reclassificacoes(raiz).items():
        base = classificacoes.get(cnpj)
        nova = (entrada.get("classe_nova") or "").strip()
        if base is not None and nova:
            base["classificacao_scout"] = nova
            base["reclassificado"] = entrada
    return classificacoes


# segmento oficial da B3 -> classes Scout compatíveis (contradição = erro na certa)
_SEGMENTO_COMPATIVEL = {
    "ETF-RF": {"Renda Fixa", "Renda Fixa Internacional"},
    "ETF-Cripto": {"Cripto", "Misto/Híbrido"},
}


def verificar(composicao: dict[str, dict[str, float]], classificacoes: dict[str, dict]) -> list[dict]:
    """Divergências entre a carteira real e a classificação da curadoria."""
    divergencias = []
    # checagem independente de carteira: classe Scout vs segmento oficial B3
    for cnpj, classificado in classificacoes.items():
        classe = (classificado.get("classificacao_scout") or "").strip()
        segmento = (classificado.get("segmento_b3") or "").strip()
        compativeis = _SEGMENTO_COMPATIVEL.get(segmento)
        if classe and compativeis and classe not in compativeis:
            divergencias.append(
                {
                    "ticker": (classificado.get("ticker") or "").strip() or cnpj,
                    "tipo": "divergência",
                    "classificacao_scout": classe,
                    "carteira": f"segmento oficial B3: {segmento}",
                    "motivo": f"segmento B3 '{segmento}' é incompatível com a classe '{classe}'",
                }
            )
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


# --- reclassificação automática (aprovada pelo dono em 20/07/2026) ----------
# Quando a carteira real diverge DURAMENTE da classe declarada, o Scout corrige
# a classe sozinho — mas só quando o alvo é determinável, UMA vez por ETF (nunca
# re-rola) e sempre com rastro auditável. O grupo "Exterior" é ambíguo (ações
# intl/cripto/commodities/RF intl caem todos nele): resolve-se pelos NOMES das
# posições, primeiro por palavra-chave e, no que sobrar, pela IA local (que só
# LÊ os nomes — nunca inventa classe nem número).

_CANDIDATAS_EXTERIOR = [
    "Ações Internacionais",
    "Renda Fixa Internacional",
    "Cripto",
    "Commodities",
]

# nome/código da posição -> classe. A primeira lista que casar vence; "Ações
# Internacionais" fica por último por ser a mais genérica.
_PALAVRAS_POSICAO = [
    ("Cripto", ("BITCOIN", "ETHEREUM", "ETHER", "CRIPTO", "CRYPTO", "SOLANA",
                "HASHDEX", "BLOCKCHAIN", "WEB3", " BTC", " ETH ")),
    ("Commodities", ("GOLD", "OURO", "SILVER", "PRATA", "COMMODIT", "PETROLE",
                     "CRUDE", "BRENT", "URANI")),
    ("Renda Fixa Internacional", ("TREASURY", "T-BOND", "T BOND", "GOV BOND",
                                  " BOND", "TIPS", "FIXED INCOME", "AGG ")),
    ("Ações Internacionais", ("S&P", "SP 500", "SP500", "NASDAQ", "MSCI",
                              "DOW JONES", "RUSSELL", "EQUITY", "STOCK",
                              "ISHARES CORE", "STOXX", "FTSE")),
]

_CAMPOS_RECLASSIFICACAO = [
    "data", "cnpj", "ticker", "classe_anterior", "classe_nova", "origem", "motivo",
]


def _grupo_dominante(grupos: dict[str, float]) -> tuple[str, float]:
    if not grupos:
        return "", 0.0
    grupo = max(grupos, key=grupos.get)
    return grupo, grupos[grupo]


def _alvo_por_segmento(grupos: dict[str, float], segmento: str) -> str | None:
    if segmento == "ETF-RF":
        return "Renda Fixa Internacional" if grupos.get("Exterior", 0) >= 60 else "Renda Fixa"
    if segmento == "ETF-Cripto":
        return "Cripto"
    return None


def _alvo_por_grupo(grupos: dict[str, float]) -> tuple[str, str] | None:
    grupo, pct = _grupo_dominante(grupos)
    if grupo == "Renda Fixa" and pct >= 80:
        return "Renda Fixa", f"carteira {pct:.0f}% em renda fixa"
    if grupo == "Cotas de Fundos" and pct >= 70:
        return "FIIs (índice)", f"carteira {pct:.0f}% em cotas de fundos"
    if grupo == "Ações" and pct >= 70:
        return "Ações Brasil", f"carteira {pct:.0f}% em ações"
    return None


def _alvo_por_posicoes(posicoes: list[dict]) -> tuple[str, str] | None:
    for classe, palavras in _PALAVRAS_POSICAO:
        for pos in posicoes:
            texto = f" {(pos.get('nome') or '')} {(pos.get('codigo') or '')} ".upper()
            if any(palavra in texto for palavra in palavras):
                nome = (pos.get("nome") or pos.get("codigo") or "").strip()
                return classe, f"posição “{nome}” indica {classe.lower()}"
    return None


def _alvo_deterministico(
    classe_atual: str, grupos: dict[str, float], segmento: str, posicoes: list[dict]
) -> tuple[str, str] | None:
    """(classe_nova, motivo) por regra fixa/palavra-chave; None se for ambíguo
    (aí quem decide é a IA, ou fica para revisão manual)."""
    por_seg = _alvo_por_segmento(grupos, segmento)
    if por_seg and por_seg != classe_atual:
        return por_seg, f"segmento oficial da B3 é {segmento}"
    por_grupo = _alvo_por_grupo(grupos)
    if por_grupo and por_grupo[0] != classe_atual:
        return por_grupo
    if grupos.get("Exterior", 0) >= 60:  # ambíguo por natureza: tenta pelas posições
        por_pos = _alvo_por_posicoes(posicoes)
        if por_pos and por_pos[0] != classe_atual:
            return por_pos
    return None


def carregar_reclassificacoes(raiz: Path | None = None) -> dict[str, dict]:
    """{cnpj: última reclassificação} — junta o registro local (~/.scout) e o
    versionado (dados/reclassificacoes.csv); a entrada mais recente vence."""
    import sys

    entradas: dict[str, dict] = {}
    caminhos = [
        armazenamento.diretorio_dados() / "reclassificacoes.csv",
        (raiz or Path(".")) / "dados" / "reclassificacoes.csv",
        Path(__file__).resolve().parents[3] / "dados" / "reclassificacoes.csv",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        caminhos.append(Path(meipass) / "dados" / "reclassificacoes.csv")
    vistos: set[str] = set()
    for caminho in caminhos:
        try:
            chave = str(caminho.resolve())
        except OSError:
            continue
        if chave in vistos or not caminho.exists():
            continue
        vistos.add(chave)
        with caminho.open(encoding="utf-8-sig", newline="") as fh:
            for linha in csv.DictReader(fh, delimiter=";"):
                cnpj = armazenamento.so_digitos(linha.get("cnpj"))
                if not cnpj:
                    continue
                atual = entradas.get(cnpj)
                if atual is None or (linha.get("data") or "") >= (atual.get("data") or ""):
                    entradas[cnpj] = linha
    return entradas


def registrar_reclassificacao(
    cnpj: str, ticker: str, classe_anterior: str, classe_nova: str,
    origem: str, motivo: str, data: str,
) -> None:
    """Anexa a mudança ao rastro em ~/.scout/reclassificacoes.csv (append-only)."""
    caminho = armazenamento.diretorio_dados() / "reclassificacoes.csv"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists()
    with caminho.open("a", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=_CAMPOS_RECLASSIFICACAO, delimiter=";")
        if novo:
            escritor.writeheader()
        escritor.writerow(
            {
                "data": data, "cnpj": cnpj, "ticker": ticker,
                "classe_anterior": classe_anterior, "classe_nova": classe_nova,
                "origem": origem, "motivo": motivo,
            }
        )


def reclassificar(
    composicao: dict[str, dict[str, float]],
    top_posicoes: dict[str, list[dict]],
    classificacoes: dict[str, dict],
    hoje: date | None = None,
    usar_ia: bool | None = None,
    ao_progredir=None,
) -> list[dict]:
    """Corrige a classe dos ETFs cuja carteira diverge DURAMENTE da declarada.
    Decide UMA vez por ETF (quem já tem rastro é pulado), grava a mudança e
    devolve a lista do que mudou. A IA local só entra no ambíguo que sobra."""
    hoje = hoje or date.today()
    if usar_ia is None:
        from .. import ia
        usar_ia = ia.disponivel()
    ja = carregar_reclassificacoes()
    mudancas = []
    for cnpj, grupos in composicao.items():
        classificado = classificacoes.get(cnpj)
        if not classificado:
            continue
        classe_atual = (classificado.get("classificacao_scout") or "").strip()
        if not classe_atual or cnpj in ja:
            continue  # sem classe declarada, ou já reclassificado (decide uma vez)
        # é divergência DURA? reusa EXATAMENTE a lógica do verificador (pontos de
        # atenção — captação, cotas — não disparam reclassificação)
        if not any(
            d["tipo"] == "divergência"
            for d in verificar({cnpj: grupos}, {cnpj: classificado})
        ):
            continue
        posicoes = top_posicoes.get(cnpj, [])
        segmento = (classificado.get("segmento_b3") or "").strip()
        origem, resultado = "auto", _alvo_deterministico(classe_atual, grupos, segmento, posicoes)
        if resultado is None and usar_ia and grupos.get("Exterior", 0) >= 60:
            from .. import ia
            escolha = ia.classificar_etf(
                (classificado.get("ticker") or cnpj), posicoes, _CANDIDATAS_EXTERIOR
            )
            if escolha and escolha[0] != classe_atual:
                origem, resultado = "ia", escolha
        if resultado is None:
            continue  # não deu para determinar com segurança: fica para revisão manual
        classe_nova, motivo = resultado
        ticker = (classificado.get("ticker") or "").strip()
        registrar_reclassificacao(cnpj, ticker, classe_atual, classe_nova, origem, motivo, hoje.isoformat())
        mudancas.append(
            {"ticker": ticker or cnpj, "de": classe_atual, "para": classe_nova, "origem": origem, "motivo": motivo}
        )
        if ao_progredir:
            ao_progredir(f"reclassificado {ticker or cnpj}: {classe_atual} → {classe_nova} ({origem})")
    return mudancas


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
    composicao, pls, competencia, top_posicoes = extrair_carteiras(conteudo, cnpjs)
    for cnpj, grupos in composicao.items():
        con.execute("DELETE FROM etf_carteira WHERE cnpj = ? AND competencia = ?", (cnpj, competencia))
        con.executemany(
            "INSERT INTO etf_carteira (cnpj, competencia, grupo, pct) VALUES (?, ?, ?, ?)",
            [(cnpj, competencia, grupo, pct) for grupo, pct in grupos.items()],
        )
        con.execute("DELETE FROM etf_posicoes WHERE cnpj = ?", (cnpj,))
        con.executemany(
            """
            INSERT INTO etf_posicoes (cnpj, competencia, item, codigo, nome, cnpj_emissor, pct, quantidade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    cnpj, competencia, indice, item["codigo"], item["nome"],
                    item["cnpj_emissor"], item["pct"], item.get("quantidade"),
                )
                for indice, item in enumerate(top_posicoes.get(cnpj, []))
            ],
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

    classificacoes = carregar_classificacoes(raiz)
    # reclassificação autônoma ANTES do relatório: quem for corrigido some da
    # lista de divergências (agora está certo) e ganha rastro auditável
    mudancas = reclassificar(
        composicao, top_posicoes, classificacoes, hoje=hoje, ao_progredir=ao_progredir
    )
    if mudancas:
        classificacoes = carregar_classificacoes(raiz)  # recarrega com o overlay novo
    divergencias = verificar(composicao, classificacoes)
    # ETF listado na B3 sem linha na curadoria: aparece como "?" no site — apontar
    for linha in con.execute("SELECT cnpj, ticker FROM etfs"):
        if linha["cnpj"] not in classificacoes:
            divergencias.append(
                {
                    "ticker": linha["ticker"] or linha["cnpj"],
                    "tipo": "divergência",
                    "classificacao_scout": "",
                    "carteira": "—",
                    "motivo": "ETF listado na B3 sem linha na curadoria (dados/classificacao_etfs.csv)",
                }
            )
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
    prefixo = f"{len(mudancas)} reclassificados · " if mudancas else ""
    mensagem = (
        f"carteiras de ETF ({competencia}): {len(composicao)} fundos · "
        + prefixo
        + (
            f"⚠ {duras} divergências e {brandas} pontos de atenção — revisar {destino}"
            if divergencias
            else "classificações coerentes com as carteiras"
        )
    )
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
