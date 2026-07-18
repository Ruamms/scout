"""Camada qualitativa: LLM local (Ollama) lê o relatório gerencial.

Princípio inegociável do projeto: a IA NUNCA produz números — ela recebe
os indicadores e red flags já calculados como contexto e só interpreta o
TEXTO do relatório, citando os trechos que sustentam cada fato.

Roda 100% local via Ollama (http://localhost:11434) — custo zero de token
e nenhum dado sai da máquina.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

URL_OLLAMA = os.environ.get("FATO_OLLAMA_URL", "http://localhost:11434")
MODELO_PADRAO = os.environ.get("FATO_MODELO_IA", "qwen2.5:14b")
_MAX_CARACTERES = 24_000  # ~6k tokens de relatório; o que passar disso é cortado

PROMPT_SISTEMA = (
    "Você é um extrator de fatos de relatórios gerenciais de fundos imobiliários "
    "brasileiros. Regras invioláveis:\n"
    "1. Extraia APENAS fatos que estão escritos no relatório — nunca invente, "
    "nunca calcule números novos, nunca extrapole.\n"
    "2. Para cada fato, cite o trecho do relatório que o sustenta, entre aspas.\n"
    "3. NUNCA dê opinião de investimento, recomendação de compra/venda ou "
    "previsão. Fatos, não dicas.\n"
    "4. Priorize: mudanças na carteira (compra/venda de ativos), obras e "
    "reformas, vacância e inadimplência comentadas, renegociações de contrato, "
    "alavancagem/dívidas, eventos societários, riscos citados pela gestão.\n"
    "5. Se o texto do relatório conectar algum fato aos indicadores fornecidos "
    "no contexto, aponte a conexão.\n"
    "6. Responda em português, em tópicos curtos (máximo 8), do mais para o "
    "menos importante. Termine com uma linha 'O que observar em seguida:' com "
    "no máximo 2 pontos factuais a acompanhar."
)


def disponivel() -> bool:
    try:
        with urllib.request.urlopen(f"{URL_OLLAMA}/api/tags", timeout=5):
            return True
    except (urllib.error.URLError, OSError):
        return False


def modelos_instalados() -> list[str]:
    try:
        with urllib.request.urlopen(f"{URL_OLLAMA}/api/tags", timeout=5) as resposta:
            dados = json.load(resposta)
        return [modelo["name"] for modelo in dados.get("models", [])]
    except (urllib.error.URLError, OSError):
        return []


def extrair_texto_pdf(caminho: Path, max_paginas: int = 40) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho))
    paginas = [pagina.extract_text() or "" for pagina in leitor.pages[:max_paginas]]
    texto = "\n".join(paginas).strip()
    if len(texto) > _MAX_CARACTERES:
        texto = texto[:_MAX_CARACTERES] + "\n[... relatório truncado para a análise ...]"
    return texto


def analisar_relatorio(
    texto_relatorio: str,
    contexto_fundo: str,
    modelo: str | None = None,
    ao_progresso=None,
) -> str:
    """Envia o relatório + contexto determinístico ao modelo local.

    A resposta vem em STREAMING: em máquinas onde o modelo não cabe todo
    na GPU, o processamento do prompt pode levar minutos — com stream a
    conexão nunca fica ociosa e dá para mostrar progresso
    (`ao_progresso(n_trechos)` é chamado a cada pedaço recebido).
    """
    modelo = modelo or MODELO_PADRAO
    corpo = json.dumps(
        {
            "model": modelo,
            "stream": True,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": PROMPT_SISTEMA},
                {
                    "role": "user",
                    "content": (
                        "CONTEXTO (calculado por código a partir de dados oficiais — "
                        f"use apenas para conectar fatos, não recalcule):\n{contexto_fundo}\n\n"
                        f"RELATÓRIO GERENCIAL (texto extraído do PDF):\n{texto_relatorio}"
                    ),
                },
            ],
        }
    ).encode("utf-8")
    requisicao = urllib.request.Request(
        f"{URL_OLLAMA}/api/chat",
        data=corpo,
        headers={"Content-Type": "application/json"},
    )
    pedacos: list[str] = []
    # timeout por LEITURA: o primeiro token só chega depois do modelo processar
    # o prompt inteiro, o que pode demorar bastante em GPU pequena
    with urllib.request.urlopen(requisicao, timeout=1800) as resposta:
        for linha in resposta:
            if not linha.strip():
                continue
            evento = json.loads(linha)
            trecho = evento.get("message", {}).get("content", "")
            if trecho:
                pedacos.append(trecho)
                if ao_progresso:
                    ao_progresso(len(pedacos))
            if evento.get("done"):
                break
    return "".join(pedacos).strip()


def contexto_do_raiox(raiox) -> str:
    """Resume o RaioX determinístico em texto para o modelo."""
    linhas = [
        f"Fundo: {raiox.ticker} — {raiox.nome} ({raiox.classificacao})",
        f"Selo: {raiox.selo.rotulo}" if raiox.selo else "",
        "Indicadores: "
        + "; ".join(
            f"{linha.nome} {linha.atual} (12m: {linha.doze_meses})"
            for linha in raiox.indicadores
        ),
    ]
    if raiox.red_flags:
        linhas.append(
            "Alertas disparados: "
            + " | ".join(f"{flag.titulo}: {flag.evidencia}" for flag in raiox.red_flags)
        )
    else:
        linhas.append("Nenhum alerta disparado pelas regras.")
    return "\n".join(filtro for filtro in linhas if filtro)
