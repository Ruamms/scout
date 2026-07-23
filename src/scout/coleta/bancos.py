"""Saúde dos BANCOS emissores de CDB — IF.data (BCB, olinda), R1 da Renda Fixa.

A unidade é o CONGLOMERADO PRUDENCIAL (TipoInstituicao=1): é nele que a
Basileia é apurada e é por ele que o FGC conta o teto de R$ 250 mil. O
cadastro filtra Tcb b1/b2 (bancos comerciais/múltiplos e de câmbio/investimento
— quem capta via CDB); consórcios, cooperativas e afins ficam fora do v1.

Dados por trimestre (formato longo NomeColuna/Saldo, pivotado aqui):
- Relatório 1 (Resumo): ativo, carteira de crédito, captações, PL, lucro;
- Relatório 5 (Informações de Capital): Capital Principal, PR e RWA —
  **Basileia = 100·PR/RWA** (calculada, determinística; o mínimo regulatório
  é 8% de PR/RWA + adicionais — a régua exata fica para as red flags do R2).

Achado do probe (23/07/2026): o serviço olinda oscila (HTTP 500 transiente) —
retry com espera resolve. Incremental por trimestre (marcador IFDATA_<anomes>).
"""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from datetime import date

BASE = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata/"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TRIMESTRES_HISTORICO = 12  # 3 anos: base das red flags de tendência (R2)

# NomeColuna do IF.data -> nossa coluna. Os nomes vêm com sufixos "(a)"/"(j)" e
# quebras de linha; o casamento é por PREFIXO do nome normalizado.
_COLUNAS = {
    "Ativo Total": "ativo",
    "Carteira de Crédito Classificada": "carteira",
    "Captações": "captacoes",
    "Patrimônio Líquido": "pl",
    "Lucro Líquido": "lucro",
    "Capital Principal para Comparação": "capital_principal",
    "Patrimônio de Referência para Comparação": "pr",
    "Ativos Ponderados pelo Risco": "rwa",
}


def _get(caminho: str, tentativas: int = 3) -> dict:
    """GET no olinda com retry — o serviço devolve 500 transiente com frequência."""
    ultimo: Exception | None = None
    for tentativa in range(tentativas):
        try:
            requisicao = urllib.request.Request(BASE + caminho, headers=_HEADERS)
            with urllib.request.urlopen(requisicao, timeout=300) as resposta:
                return json.load(resposta)
        except Exception as erro:  # noqa: BLE001
            ultimo = erro
            if tentativa < tentativas - 1:
                time.sleep(10 * (tentativa + 1))
    raise ultimo


def _trimestres(hoje: date, quantos: int) -> list[int]:
    """AAAAMM dos últimos fins de trimestre (o IF.data publica com ~90d de
    atraso — o mais recente pode não existir ainda; quem chama tolera vazio)."""
    anomes = []
    ano, mes = hoje.year, hoje.month
    mes = (mes - 1) // 3 * 3  # fim do trimestre anterior
    if mes == 0:
        ano, mes = ano - 1, 12
    for _ in range(quantos):
        anomes.append(ano * 100 + mes)
        mes -= 3
        if mes <= 0:
            ano, mes = ano - 1, 12
    return anomes


def cadastro(anomes: int) -> list[dict]:
    dados = _get(f"IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={anomes}&$top=100000&$format=json")
    return dados.get("value") or []


def valores(anomes: int, relatorio: str) -> list[dict]:
    dados = _get(
        "IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)"
        f"?@AnoMes={anomes}&@TipoInstituicao=1&@Relatorio='{relatorio}'&$top=200000&$format=json"
    )
    return dados.get("value") or []


def pivotar(linhas: list[dict], so_cod_inst: set[str] | None = None) -> dict[str, dict]:
    """{cod_inst: {coluna: saldo}} — casa o NomeColuna por prefixo (os nomes do
    IF.data têm sufixos de fórmula e quebras de linha)."""
    saida: dict[str, dict] = {}
    for linha in linhas:
        cod = str(linha.get("CodInst") or "")
        if not cod or (so_cod_inst is not None and cod not in so_cod_inst):
            continue
        nome_coluna = " ".join(str(linha.get("NomeColuna") or "").split())
        for prefixo, coluna in _COLUNAS.items():
            if nome_coluna.startswith(prefixo):
                try:
                    saida.setdefault(cod, {})[coluna] = float(linha.get("Saldo"))
                except (TypeError, ValueError):
                    pass
                break
    return saida


def atualizar_bancos(con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None) -> str | None:
    """Cadastro (b1/b2, conglomerado prudencial) + série trimestral de saúde.
    Incremental por trimestre; o mais recente é reverificado a cada rodada."""
    hoje = hoje or date.today()
    fila = _trimestres(hoje, TRIMESTRES_HISTORICO)
    carregados = {l[0] for l in con.execute("SELECT arquivo FROM cargas")}

    # cadastro: do trimestre mais recente que existir
    novos_cadastro = 0
    for anomes in fila:
        try:
            linhas = cadastro(anomes)
        except Exception:  # noqa: BLE001
            linhas = []
        if not linhas:
            continue
        for linha in linhas:
            tcb = (linha.get("Tcb") or "").strip().lower()
            if tcb not in ("b1", "b2"):
                continue  # v1 = bancos que captam CDB de varejo
            con.execute(
                "INSERT OR REPLACE INTO bancos (cod_inst, nome, tcb, segmento, uf, atualizado_em)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(linha.get("CodInst") or ""),
                    (linha.get("NomeInstituicao") or "").strip(),
                    tcb,
                    (linha.get("SegmentoTb") or linha.get("Sr") or "").strip() or None,
                    (linha.get("Uf") or "").strip() or None,
                    hoje.isoformat(),
                ),
            )
            novos_cadastro += 1
        con.commit()
        break
    if not novos_cadastro:
        return None  # IF.data fora do ar: fica para a próxima rodada

    bancos_v1 = {l[0] for l in con.execute("SELECT cod_inst FROM bancos")}
    trimestres_novos = 0
    for indice, anomes in enumerate(fila):
        marcador = f"IFDATA_{anomes}"
        if marcador in carregados and indice != 0:  # o mais recente sempre reverifica
            continue
        try:
            resumo = pivotar(valores(anomes, "1"), bancos_v1)
            capital = pivotar(valores(anomes, "5"), bancos_v1)
        except Exception:  # noqa: BLE001 — trimestre indisponível não derruba a carga
            continue
        if not resumo:
            continue
        for cod, campos in resumo.items():
            cap = capital.get(cod, {})
            pr, rwa = cap.get("pr"), cap.get("rwa")
            basileia = (100 * pr / rwa) if (pr is not None and rwa) else None
            con.execute(
                """
                INSERT OR REPLACE INTO bancos_tri
                    (cod_inst, anomes, ativo, carteira, captacoes, pl, lucro,
                     capital_principal, pr, rwa, basileia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cod, anomes,
                    campos.get("ativo"), campos.get("carteira"), campos.get("captacoes"),
                    campos.get("pl"), campos.get("lucro"),
                    cap.get("capital_principal"), pr, rwa, basileia,
                ),
            )
        con.execute(
            "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, ?)",
            (marcador, hoje.isoformat()),
        )
        con.commit()
        trimestres_novos += 1

    total = con.execute("SELECT COUNT(*) FROM bancos").fetchone()[0]
    tris = con.execute("SELECT COUNT(DISTINCT anomes) FROM bancos_tri").fetchone()[0]
    mensagem = f"bancos (IF.data): {total} emissores b1/b2, {tris} trimestres ({trimestres_novos} novos)"
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
