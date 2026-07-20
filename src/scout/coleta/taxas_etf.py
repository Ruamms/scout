"""Taxa de administração de ETFs — curadoria com fonte (dados/taxas_etfs.csv).

Ao contrário do FII, o ETF (fundo de índice) NÃO entra no regime que publica
taxa de administração em dados abertos da CVM: ela não está no registro de
fundos, nem no cad_fi/extrato/lâmina, e a B3 também não expõe. A única fonte
oficial é o REGULAMENTO do fundo. Por isso a taxa de ETF é tratada como
curadoria: um número por ticker, sempre acompanhado da fonte (link do
regulamento) e da data em que foi conferido. Determinístico e auditável — o
Scout nunca inventa a taxa.

O arquivo pode ser pré-preenchido lendo o regulamento no FNET (proposta) e é
sempre revisado manualmente antes de entrar.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

# A taxa aparece como "taxa de administração ... X%" (regime antigo) OU como
# "Taxa Global / Taxa Máxima Global ... X%" (Resolução CVM 175, que fundiu
# administração+gestão+custódia numa taxa única). Captura o 1º percentual
# plausível depois da expressão. DETERMINÍSTICO (regex), nunca IA — o número sai
# do texto oficial do regulamento, e ainda assim entra como PROPOSTA para revisão.
_RE_TAXA_ADM = re.compile(
    r"taxa\s+(?:de\s+administra[çc][ãa]o|(?:m[áa]xima\s+)?global)"
    r"[^%]{0,180}?(\d{1,2}(?:[.,]\d{1,4})?)\s*%",
    re.IGNORECASE,
)


def extrair_taxa_regulamento(texto: str) -> dict | None:
    """Acha a taxa de administração (% a.a.) no texto de um regulamento.

    Retorna {taxa_adm_aa, trecho, confianca} ou None. Prefere o trecho que fala
    em "ano/a.a." (confiança alta); pula o que fala em "mês/mensal" (não vamos
    reportar taxa mensal como anual). É sempre uma PROPOSTA — quem confirma é o
    humano, olhando o trecho e a fonte."""
    if not texto:
        return None
    plano = " ".join(texto.split())
    candidatos: list[dict] = []
    for casamento in _RE_TAXA_ADM.finditer(plano):
        try:
            valor = float(casamento.group(1).replace(",", "."))
        except ValueError:
            continue
        if not 0 < valor <= 3:  # taxa de ETF fica bem abaixo de 3% a.a.
            continue
        cauda_curta = plano[casamento.end() : casamento.end() + 25].lower()
        if "mês" in cauda_curta or "mes" in cauda_curta or "mensal" in cauda_curta:
            continue  # taxa mensal (armadilha) — não confundir com a anual
        # "ao ano/a.a." costuma vir após o valor por extenso entre parênteses,
        # então a janela para confiança é mais larga que a de "mês"
        cauda_longa = plano[casamento.end() : casamento.end() + 70].lower()
        trecho = plano[casamento.start() : casamento.end() + 40].strip()
        confianca = "alta" if ("ano" in cauda_longa or "a.a" in cauda_longa) else "media"
        candidatos.append({"taxa_adm_aa": valor, "trecho": trecho, "confianca": confianca})
    if not candidatos:
        return None
    return next((c for c in candidatos if c["confianca"] == "alta"), candidatos[0])


_CAP_POR_RODADA = 20     # lê no máximo N regulamentos por rodada (FNET é lento)
_FRESCOR_DIAS = 90       # re-confere o regulamento de cada ETF a cada N dias
_CAMPOS = ["ticker", "taxa_adm_aa", "fonte", "verificado_em", "confianca"]


def _caminho_gravavel() -> Path | None:
    """O CSV de curadoria no repositório (gravável). None quando rodando do
    executável empacotado (dados embutidos são read-only) — a coleta só grava
    a partir do código-fonte."""
    caminho = Path(__file__).resolve().parents[3] / "dados" / "taxas_etfs.csv"
    return caminho if caminho.parent.exists() else None


def _ler_linhas(caminho: Path) -> dict[str, dict]:
    """{TICKER: linha} de tudo que já está no arquivo (achado, manual OU não achado)."""
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        return {
            (linha.get("ticker") or "").strip().upper(): linha
            for linha in csv.DictReader(fh, delimiter=";")
            if (linha.get("ticker") or "").strip()
        }


def _id_regulamento(fonte: str | None) -> str:
    """O id do regulamento fica embutido na fonte (…downloadDocumento?id=NNN).
    É o PARÂMETRO que diz se o documento mudou desde a última leitura."""
    achado = re.search(r"id=(\d+)", fonte or "")
    return achado.group(1) if achado else ""


def _dias_desde(iso: str | None) -> int:
    from datetime import date

    try:
        return (date.today() - date.fromisoformat((iso or "")[:10])).days
    except ValueError:
        return 10**6  # sem data válida -> tratado como muito antigo (re-confere)


def atualizar(con, ao_progredir=None) -> str | None:
    """Passo do `scout atualizar`: mantém dados/taxas_etfs.csv em dia lendo o
    REGULAMENTO no FNET. DOIS parâmetros decidem o que fazer:

    - QUANDO reconferir (frescor): só re-checa ETF cujo `verificado_em` tem mais
      de `_FRESCOR_DIAS` dias — evita bater no FNET toda rodada.
    - SE atualizar (mudança): o id do regulamento (embutido na `fonte`). Se o
      regulamento mais recente no FNET tem id DIFERENTE do gravado, o documento
      mudou -> re-lê e atualiza a taxa. Mesmo id -> só renova a data.

    NADA é eterno — nem `manual`: quando o regulamento MUDA (id novo) até a taxa
    manual é reavaliada (ela só vale enquanto o documento não muda). Se o novo regulamento
    não declarar a taxa mas já tínhamos uma, mantém a última conhecida (o regex
    pode ter falhado no PDF novo). Processa até `_CAP_POR_RODADA` por rodada;
    falha de rede não “queima” o ETF (retenta). Retorna None quando não há nada a
    fazer (e grava só do código-fonte)."""
    import csv as _csv
    import os
    from datetime import date

    from .. import armazenamento, ia
    from . import fnet

    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
        return None  # curadoria roda LOCAL; o CI usa o CSV commitado
    caminho = _caminho_gravavel()
    if caminho is None:
        return None

    linhas = _ler_linhas(caminho)
    hoje = date.today().isoformat()

    def _precisa(ticker: str) -> bool:
        linha = linhas.get(ticker)
        if linha is None:
            return True  # ETF novo, nunca lido
        # NADA é eterno — nem o manual. Ele também é reconferido pelo frescor; o
        # que o protege é o MESMO regulamento (tratado no loop: id igual -> mantém
        # o valor). Quando o documento muda, até a manual pode estar velha -> re-lê.
        return _dias_desde(linha.get("verificado_em")) >= _FRESCOR_DIAS

    tickers_etf = [
        (etf["ticker"].strip().upper(), etf)
        for etf in armazenamento.etfs_listados(con)
        if (etf["ticker"] or "").strip()
    ]
    fila = [(tk, etf) for tk, etf in tickers_etf if _precisa(tk)]
    restantes = max(0, len(fila) - _CAP_POR_RODADA)
    fila = fila[:_CAP_POR_RODADA]
    if not fila:
        return None

    achados = mudancas = 0
    for ticker, etf in fila:
        linha = linhas.get(ticker)
        try:
            documentos = fnet.listar(etf["cnpj"], quantidade=120, timeout=12, tentativas=2)
        except Exception:  # noqa: BLE001 — falha de rede não queima o ETF (retenta)
            continue
        candidatos = fnet.documentos_de_regulamento(documentos)
        if not candidatos:
            base = dict(linha) if linha else {
                "ticker": ticker, "taxa_adm_aa": "", "fonte": "", "confianca": "sem_regulamento"
            }
            base["verificado_em"] = hoje  # sem regulamento agora: mantém o que havia, renova a data
            linhas[ticker] = base
            continue
        id_atual = str(candidatos[0]["id"])  # âncora de versão = doc primário (a alteração, se houver)
        resolvido = linha and (linha.get("confianca") or "").strip().lower() not in (
            "", "nao_achou", "sem_regulamento"
        )
        # MESMO documento de antes e já resolvido -> não re-baixa, só renova a data
        if resolvido and _id_regulamento(linha.get("fonte")) == id_atual:
            linha["verificado_em"] = hoje
            linhas[ticker] = linha
            continue
        # documento novo (ou 1ª leitura, ou antes não achado): tenta os candidatos
        # (alteração -> regulamento -> constituição) até um trazer a taxa
        achado = usado = None
        for candidato in candidatos[:3]:
            try:
                pdf = fnet._garantir_documento(
                    con, etf["cnpj"], candidato,
                    armazenamento.diretorio_dados() / "documentos",
                    timeout=45, tentativas=2,
                )
                extraido = extrair_taxa_regulamento(ia.extrair_texto_pdf(pdf, max_paginas=60))
            except Exception:  # noqa: BLE001 — falhou nesse doc: tenta o próximo candidato
                continue
            usado = candidato
            if extraido:
                achado = extraido
                break
        if usado is None:
            continue  # todos os downloads falharam -> não marca (retenta depois)
        fonte = fnet.URL_DOWNLOAD.format(id=(usado if achado else candidatos[0])["id"])
        if achado:
            achados += 1
            if not linha or _numero(linha.get("taxa_adm_aa")) != achado["taxa_adm_aa"]:
                mudancas += 1
            linhas[ticker] = {
                "ticker": ticker,
                "taxa_adm_aa": f"{achado['taxa_adm_aa']:.2f}".replace(".", ","),
                "fonte": fonte,
                "verificado_em": hoje,
                "confianca": achado["confianca"],
            }
        elif linha and _numero(linha.get("taxa_adm_aa")) is not None:
            # novo regulamento não declarou a taxa, mas já tínhamos uma: mantém a
            # última conhecida (regex pode falhar no PDF novo), só renova a data
            linha["verificado_em"] = hoje
            linhas[ticker] = linha
        else:
            linhas[ticker] = {
                "ticker": ticker, "taxa_adm_aa": "", "fonte": fonte,
                "verificado_em": hoje, "confianca": "nao_achou",
            }

    with caminho.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = _csv.DictWriter(fh, fieldnames=_CAMPOS, delimiter=";", extrasaction="ignore")
        escritor.writeheader()
        for ticker in sorted(linhas):
            escritor.writerow({campo: (linhas[ticker].get(campo) or "") for campo in _CAMPOS})

    mensagem = (
        f"taxas de ETF (regulamento): {achados} achada(s), {mudancas} mudança(s)"
        + (f" · {restantes} p/ próxima rodada" if restantes else "")
    )
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem


def carregar(raiz: Path | None = None) -> dict[str, dict]:
    """dados/taxas_etfs.csv -> {TICKER: {taxa_adm_aa, fonte, verificado_em}}.

    Procura no repositório (curadoria editável) e, no executável PyInstaller,
    nos dados embutidos (sys._MEIPASS) — mesmo padrão da classificação."""
    candidatos = [
        (raiz or Path(".")) / "dados" / "taxas_etfs.csv",
        Path(__file__).resolve().parents[3] / "dados" / "taxas_etfs.csv",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.insert(0, Path(meipass) / "dados" / "taxas_etfs.csv")
    caminho = next((c for c in candidatos if c.exists()), None)
    if caminho is None:
        return {}
    taxas: dict[str, dict] = {}
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh, delimiter=";"):
            ticker = (linha.get("ticker") or "").strip().upper()
            valor = _numero(linha.get("taxa_adm_aa"))
            confianca = (linha.get("confianca") or "").strip().lower()
            # PORTEIRO (regra do dono): só vai pro site quem tem taxa numérica E
            # confiança preenchida. O que foi ACHADO no regulamento já vem com
            # confiança (alta/média) e entra direto; o que NÃO foi achado fica no
            # arquivo como "nao_achou"/"sem_regulamento" (sem taxa) até alguém
            # conferir e preencher manualmente.
            if not ticker or valor is None or confianca in ("", "nao_achou", "sem_regulamento"):
                continue
            taxas[ticker] = {
                "taxa_adm_aa": valor,
                "fonte": (linha.get("fonte") or "").strip(),
                "verificado_em": (linha.get("verificado_em") or "").strip(),
                "confianca": confianca,
            }
    return taxas


def _numero(valor: str | None) -> float | None:
    """Taxa em % a.a., aceitando vírgula ou ponto. Descarta o que não faz
    sentido: taxa de ETF fica tipicamente entre 0 e 3% a.a."""
    if valor is None:
        return None
    valor = valor.strip().replace(",", ".")
    if not valor:
        return None
    try:
        numero = float(valor)
    except ValueError:
        return None
    return numero if 0 <= numero <= 3 else None
