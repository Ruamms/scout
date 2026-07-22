"""Leituras por IA persistidas em arquivos versionáveis.

As leituras são geradas localmente (Ollama) e commitadas no repositório em
`leituras/<TICKER>.json`; o site (GitHub Actions) apenas as exibe. O `id`
do documento no FNET é a chave da incrementalidade: relatório já lido não
é lido de novo.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PASTA_PADRAO = "leituras"


def carregar_todas(pasta: Path) -> dict[str, dict]:
    """{ticker: leitura} de todos os JSONs da pasta (ignora inválidos)."""
    leituras: dict[str, dict] = {}
    if not pasta.is_dir():
        return leituras
    for arquivo in sorted(pasta.glob("*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if dados.get("ticker"):
            leituras[dados["ticker"]] = dados
    return leituras


def carregar(pasta: Path, ticker: str) -> dict | None:
    arquivo = pasta / f"{ticker.upper()}.json"
    if not arquivo.exists():
        return None
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def salvar(pasta: Path, dados: dict) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{dados['ticker'].upper()}.json"
    arquivo.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return arquivo


def _bloco_comunicados(docs_meta: list[dict], texto: str | None) -> dict:
    """Bloco de comunicados lidos (fatos relevantes, comunicados ao mercado,
    assembleias) — o `rotulo` diz o que cada documento é."""
    return {
        "ids": [meta["id"] for meta in docs_meta],
        "datas": [meta["data_entrega"][:10] for meta in docs_meta],
        "rotulos": [meta.get("rotulo", "Fato Relevante") for meta in docs_meta],
        "texto": texto,
    }


def bloco_comunicados_lido(leitura: dict | None) -> dict | None:
    """Bloco de comunicados de uma leitura existente, normalizado — aceita o
    formato novo (`comunicados`) e o legado (`fatos`)."""
    if not leitura:
        return None
    bloco = leitura.get("comunicados") or leitura.get("fatos")
    if not bloco:
        return None
    ids = bloco.get("ids", [])
    return {
        "ids": ids,
        "datas": bloco.get("datas", []),
        "rotulos": bloco.get("rotulos", ["Fato Relevante"] * len(ids)),
        "texto": bloco.get("texto"),
    }


def ids_comunicados(leitura: dict | None) -> set:
    """Ids dos comunicados já lidos (formato novo ou legado)."""
    bloco = bloco_comunicados_lido(leitura)
    return set(bloco["ids"]) if bloco else set()


def montar_sem_relatorio(
    ticker: str,
    docs_meta: list[dict] = (),
    texto_docs: str | None = None,
    modelo: str | None = None,
    agora: datetime | None = None,
) -> dict:
    """Marcador para fundo SEM relatório gerencial no FNET (documento opcional
    — muitos fundos nunca publicam um). Persistido para a página explicar por
    que não há leitura do relatório; fatos relevantes, comunicados e
    assembleias, quando existem, são lidos mesmo assim e viajam junto.
    Reverificado a cada rodada do lote."""
    agora = agora or datetime.now()
    dados = {
        "ticker": ticker.upper(),
        "sem_relatorio": True,
        "verificado_em": agora.isoformat(timespec="seconds"),
        "comunicados": _bloco_comunicados(docs_meta, texto_docs),
    }
    if modelo and texto_docs:
        dados["modelo"] = modelo
    return dados


def montar_relatorio_ilegivel(
    ticker: str,
    relatorio_meta: dict,
    docs_meta: list[dict] = (),
    texto_docs: str | None = None,
    modelo: str | None = None,
    agora: datetime | None = None,
) -> dict:
    """Marcador para relatório gerencial que EXISTE mas é imagem/escaneado (sem
    texto extraível). Não é erro (repetir não muda o PDF) nem 'sem relatório'
    (ele existe) — guarda o id e `ilegivel` para a página não mostrar leitura
    falsa (o render só exibe quando há `texto`) e os comunicados/parecer, quando
    dá, são lidos mesmo assim."""
    agora = agora or datetime.now()
    dados = {
        "ticker": ticker.upper(),
        "gerada_em": agora.isoformat(timespec="seconds"),
        "relatorio": {
            "id": relatorio_meta["id"],
            "data_entrega": relatorio_meta["data_entrega"],
            "texto": "",
            "ilegivel": True,
        },
        "comunicados": _bloco_comunicados(docs_meta, texto_docs),
    }
    if modelo:
        dados["modelo"] = modelo
    return dados


def montar(
    ticker: str,
    modelo: str,
    relatorio_meta: dict,
    texto_relatorio: str,
    docs_meta: list[dict],
    texto_docs: str | None,
    agora: datetime | None = None,
) -> dict:
    agora = agora or datetime.now()
    return {
        "ticker": ticker.upper(),
        "modelo": modelo,
        "gerada_em": agora.isoformat(timespec="seconds"),
        "relatorio": {
            "id": relatorio_meta["id"],
            "data_entrega": relatorio_meta["data_entrega"],
            "texto": texto_relatorio,
        },
        "comunicados": _bloco_comunicados(docs_meta, texto_docs),
    }


def anexar_snapshot(dados: dict, snapshot: dict | None, existente: dict | None) -> dict:
    """Grava o retrato do fundo NO MOMENTO da leitura e preserva o retrato da
    leitura anterior quando o relatório muda — a matéria-prima do "histórico
    entre relatórios" (fato comparado, nunca validação de previsão)."""
    if snapshot:
        dados["retrato"] = snapshot
    if not existente or not existente.get("retrato"):
        return dados
    relatorio_anterior = (existente.get("relatorio") or {}).get("id")
    relatorio_novo = (dados.get("relatorio") or {}).get("id")
    if relatorio_anterior and relatorio_novo and relatorio_anterior != relatorio_novo:
        dados["anterior"] = {
            "gerada_em": existente.get("gerada_em", ""),
            "relatorio_data": (existente.get("relatorio") or {}).get("data_entrega", ""),
            **existente["retrato"],
        }
    elif existente.get("anterior"):
        dados["anterior"] = existente["anterior"]  # mantém o histórico já capturado
    return dados
