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


def montar(
    ticker: str,
    modelo: str,
    relatorio_meta: dict,
    texto_relatorio: str,
    fatos_meta: list[dict],
    texto_fatos: str | None,
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
        "fatos": {
            "ids": [meta["id"] for meta in fatos_meta],
            "datas": [meta["data_entrega"][:10] for meta in fatos_meta],
            "texto": texto_fatos,
        },
    }
