"""Camada qualitativa: LLM local (Ollama) lê o relatório gerencial.

Princípio inegociável do projeto: a IA NUNCA produz números — ela recebe
os indicadores e red flags já calculados como contexto e só interpreta o
TEXTO do relatório, citando os trechos que sustentam cada fato.

Roda 100% local via Ollama (http://localhost:11434) — custo zero de token
e nenhum dado sai da máquina.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

# pypdf é tagarela: PDFs malformados do FNET (xref quebrado, padding inválido)
# geram avisos de RECUPERAÇÃO ("Ignoring wrong pointing object", "Invalid
# padding bytes", "Adding missing padding") — o texto é extraído mesmo assim.
# Silenciamos esse ruído no log do lote, mantendo erros de verdade (ERROR+).
logging.getLogger("pypdf").setLevel(logging.ERROR)

URL_OLLAMA = os.environ.get("SCOUT_OLLAMA_URL", "http://localhost:11434")
MODELO_PADRAO = os.environ.get("SCOUT_MODELO_IA", "qwen2.5:14b")
# modelo de VISÃO (fallback só para relatórios escaneados/imagem): reaproveita o
# Ollama local. Precisa ser puxado à parte (ex.: `ollama pull llama3.2-vision`);
# se não estiver instalado, o escaneado apenas continua "pulado".
MODELO_VISAO_PADRAO = os.environ.get("SCOUT_MODELO_VISAO", "llama3.2-vision")
_MAX_CARACTERES = 24_000  # ~6k tokens de relatório; o que passar disso é cortado

PROMPT_SISTEMA = (
    "Você é um extrator de fatos de relatórios gerenciais de fundos imobiliários "
    "brasileiros. Regras invioláveis:\n"
    "1. Extraia APENAS fatos que estão escritos no relatório — nunca invente, "
    "nunca calcule números novos, nunca extrapole.\n"
    "2. Para cada fato, cite o trecho do relatório que o sustenta, entre aspas, "
    "seguido da página de onde veio no formato (p. N) — o texto traz marcadores "
    "[página N]; use o marcador mais próximo ACIMA do trecho citado. Se não der "
    "para determinar a página com certeza, omita-a em vez de estimar.\n"
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


def _paginas_fitz(caminho: Path, max_paginas: int) -> list[str]:
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(caminho)) as doc:
            return [doc[i].get_text() or "" for i in range(min(doc.page_count, max_paginas))]
    except Exception:
        return []


def _paginas_pypdf(caminho: Path, max_paginas: int) -> list[str]:
    try:
        from pypdf import PdfReader

        leitor = PdfReader(str(caminho))
        return [pagina.extract_text() or "" for pagina in leitor.pages[:max_paginas]]
    except Exception:
        return []


def _paginas_pdf(caminho: Path, max_paginas: int) -> list[str]:
    """Texto por página. PyMuPDF (fitz) é o principal — extrai bem melhor que o
    pypdf em relatórios (tabelas, colunas, fontes embutidas), o mesmo motivo da
    migração na leitura da taxa de ETF. Se o fitz vier curto (arquivo difícil),
    tenta o pypdf e fica com o que extraiu MAIS — maximiza a recuperação de PDFs
    que antes caíam como 'sem texto'. Nenhum dos dois faz OCR: PDF escaneado de
    verdade (só imagem) continua sem texto."""
    paginas = _paginas_fitz(caminho, max_paginas)
    if sum(len(p) for p in paginas) < 500:
        alternativa = _paginas_pypdf(caminho, max_paginas)
        if sum(len(p) for p in alternativa) > sum(len(p) for p in paginas):
            return alternativa
    return paginas


def extrair_texto_pdf(caminho: Path, max_paginas: int = 40) -> str:
    paginas = _paginas_pdf(caminho, max_paginas)
    # marcadores [página N]: permitem ao modelo citar a página de cada trecho,
    # para o leitor conferir no PDF original
    texto = "\n".join(
        f"[página {numero}]\n{conteudo}" for numero, conteudo in enumerate(paginas, start=1)
    ).strip()
    if len(texto) > _MAX_CARACTERES:
        texto = texto[:_MAX_CARACTERES] + "\n[... relatório truncado para a análise ...]"
    return texto


def analisar_relatorio(
    texto_relatorio: str,
    contexto_fundo: str,
    modelo: str | None = None,
    ao_progresso=None,
) -> str:
    """Envia o relatório + contexto determinístico ao modelo local."""
    conteudo = (
        "CONTEXTO (calculado por código a partir de dados oficiais — "
        f"use apenas para conectar fatos, não recalcule):\n{contexto_fundo}\n\n"
        f"RELATÓRIO GERENCIAL (texto extraído do PDF):\n{texto_relatorio}"
    )
    return _conversar(PROMPT_SISTEMA, conteudo, modelo, ao_progresso)


def modelo_visao_instalado(preferido: str | None = None) -> str | None:
    """Nome do modelo de visão instalado no Ollama, ou None. Casa por nome exato
    e por prefixo (as tags vêm como 'nome:latest'); se o preferido não estiver
    lá, aceita qualquer modelo com cara de visão (vision/vl/llava/minicpm-v…)."""
    preferido = preferido or MODELO_VISAO_PADRAO
    instalados = modelos_instalados()
    alvo = preferido.split(":")[0].lower()
    for modelo in instalados:
        if modelo == preferido or modelo.split(":")[0].lower() == alvo:
            return modelo
    marcas = ("vision", "-vl", "vl-", "llava", "minicpm-v", "moondream")
    for modelo in instalados:
        if any(marca in modelo.lower() for marca in marcas):
            return modelo
    return None


def _imagens_do_pdf(caminho: Path, max_paginas: int = 8, dpi: int = 150) -> list[str]:
    """Renderiza as primeiras páginas do PDF em PNG base64 (para o modelo de
    visão). Só as primeiras: imagem custa muito no contexto do modelo."""
    import base64

    try:
        import fitz  # PyMuPDF
    except Exception:
        return []
    imagens = []
    with fitz.open(str(caminho)) as doc:
        for i in range(min(doc.page_count, max_paginas)):
            pix = doc[i].get_pixmap(dpi=dpi)
            imagens.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    return imagens


def analisar_relatorio_imagem(
    caminho_pdf: Path,
    contexto_fundo: str,
    modelo: str | None = None,
    ao_progresso=None,
) -> str | None:
    """Lê um relatório ESCANEADO (PDF só-imagem) por um modelo de VISÃO local,
    seguindo as mesmas regras do texto. Retorna None quando não há modelo de
    visão instalado, quando o PDF não rende imagens, ou quando o Ollama falha —
    aí o chamador mantém o comportamento atual (pulado)."""
    modelo = modelo or modelo_visao_instalado()
    if not modelo:
        return None
    imagens = _imagens_do_pdf(caminho_pdf)
    if not imagens:
        return None
    conteudo = (
        "CONTEXTO (calculado por código a partir de dados oficiais — use apenas "
        f"para conectar fatos, não recalcule):\n{contexto_fundo}\n\n"
        "O RELATÓRIO GERENCIAL está nas IMAGENS anexas (PDF escaneado, sem texto "
        "selecionável). Leia o que está escrito nas imagens e siga as regras. "
        "Sem marcadores [página N]: cite o trecho e, se não tiver certeza da "
        "página, omita-a."
    )
    try:
        return _conversar(PROMPT_SISTEMA, conteudo, modelo, ao_progresso, imagens=imagens) or None
    except (urllib.error.URLError, OSError):
        return None


PROMPT_FATOS = (
    "Você é um extrator de fatos de comunicados oficiais de fundos imobiliários "
    "brasileiros — fatos relevantes, comunicados ao mercado e editais/atas de "
    "assembleia. Regras invioláveis:\n"
    "1. Para CADA documento fornecido, produza um bloco com: a data, um título "
    "de uma linha dizendo O QUE aconteceu, um resumo de 1 a 3 linhas e a "
    "citação do trecho-chave entre aspas — se o texto trouxer marcadores "
    "[página N], indique a página do trecho no formato (p. N).\n"
    "2. Relate APENAS o que está escrito — nunca invente, nunca calcule "
    "números novos, nunca extrapole consequências.\n"
    "3. NUNCA dê opinião de investimento ou recomendação. Fatos, não dicas.\n"
    "4. Se o texto do documento se conectar aos indicadores do contexto, "
    "aponte a conexão em uma frase.\n"
    "5. Responda em português, do documento mais recente para o mais antigo."
)


def analisar_comunicados(
    itens: list[tuple[str, str, str]],
    contexto_fundo: str,
    modelo: str | None = None,
    ao_progresso=None,
) -> str:
    """Lê comunicados oficiais de uma vez — `itens` = (rotulo, data, texto).
    Uma única chamada ao modelo para todos os documentos; o corte de 5000
    caracteres por documento mantém o total dentro do contexto de 16k."""
    blocos = "\n\n".join(
        f"=== {rotulo.upper()} entregue em {data} ===\n{texto[:5000]}"
        for rotulo, data, texto in itens
    )
    conteudo = (
        "CONTEXTO (calculado por código a partir de dados oficiais — "
        f"use apenas para conectar fatos, não recalcule):\n{contexto_fundo}\n\n"
        f"DOCUMENTOS:\n{blocos}"
    )
    return _conversar(PROMPT_FATOS, conteudo, modelo, ao_progresso)


def analisar_fatos_relevantes(
    fatos: list[tuple[str, str]],
    contexto_fundo: str,
    modelo: str | None = None,
    ao_progresso=None,
) -> str:
    """Compatibilidade: fatos relevantes (lista de (data_entrega, texto))."""
    return analisar_comunicados(
        [("Fato Relevante", data, texto) for data, texto in fatos],
        contexto_fundo,
        modelo,
        ao_progresso,
    )


def _conversar(
    prompt_sistema: str,
    conteudo_usuario: str,
    modelo: str | None,
    ao_progresso,
    imagens: list[str] | None = None,
) -> str:
    """Chamada ao Ollama em STREAMING: em máquinas onde o modelo não cabe
    todo na GPU, o processamento do prompt pode levar minutos — com stream
    a conexão nunca fica ociosa e dá para mostrar progresso
    (`ao_progresso(n_trechos)` é chamado a cada pedaço recebido). `imagens`
    (base64 PNG) anexa páginas ao modelo de visão para ler PDF escaneado."""
    modelo = modelo or MODELO_PADRAO
    mensagem_usuario: dict = {"role": "user", "content": conteudo_usuario}
    if imagens:
        mensagem_usuario["images"] = imagens
    corpo = json.dumps(
        {
            "model": modelo,
            "stream": True,
            # num_ctx: o padrão do modelo (32k) desperdiça VRAM — nossos prompts
            # nunca passam de ~10k tokens (relatório ≤24k chars, fatos ≤8k cada);
            # com 16k o cache de contexto encolhe e mais camadas cabem na GPU.
            # num_predict: TETO da resposta — nossas leituras são tópicos curtos
            # (≤1k tokens); sem o teto, um modelo em loop de repetição gera
            # PARA SEMPRE (caso real: 85 mil trechos, >1h preso num fundo)
            "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": 2048},
            "messages": [
                {"role": "system", "content": prompt_sistema},
                mensagem_usuario,
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
            if len(pedacos) > 6000:  # cinto e suspensório: servidor ignorou o num_predict
                raise RuntimeError(
                    "resposta do modelo fora de controle (loop de repetição) — abortada"
                )
    return "".join(pedacos).strip()


PROMPT_PROCESSOS = (
    "Você é um extrator de fatos da seção de PROCESSOS JUDICIAIS do Formulário "
    "de Referência (FRE) de companhias abertas brasileiras. Regras invioláveis:\n"
    "1. Extraia APENAS o que está escrito — nunca invente, nunca calcule, nunca "
    "extrapole.\n"
    "2. Para cada processo relevante, produza um tópico com: a NATUREZA "
    "(trabalhista/tributário/cível/ambiental/regulatório), o VALOR envolvido "
    "quando declarado, a CHANCE DE PERDA declarada pela companhia (provável/"
    "possível/remota) e um resumo de 1-2 linhas do objeto, citando um trecho "
    "curto entre aspas.\n"
    "3. NUNCA dê opinião sobre mérito, resultado provável ou impacto no preço.\n"
    "4. Priorize os maiores valores e o que a companhia marcou como provável.\n"
    "5. Responda em português, em tópicos (máximo 8), do maior para o menor "
    "valor. Se a seção declarar que não há processos relevantes, diga só isso."
)


def analisar_processos(
    texto_processos: str,
    contexto_empresa: str,
    modelo: str | None = None,
    ao_progresso=None,
) -> str:
    """Lê a seção 4.3+ do FRE (processos judiciais) — fatos com citação."""
    conteudo = (
        "CONTEXTO (calculado por código a partir de dados oficiais — use apenas "
        f"para conectar fatos, não recalcule):\n{contexto_empresa}\n\n"
        f"SEÇÃO DE PROCESSOS JUDICIAIS DO FRE (texto extraído do PDF):\n{texto_processos}"
    )
    return _conversar(PROMPT_PROCESSOS, conteudo, modelo, ao_progresso)


PROMPT_CLASSIFICAR = (
    "Você classifica ETFs brasileiros lendo APENAS os nomes das maiores "
    "posições da carteira. Escolha EXATAMENTE UMA das classes oferecidas — "
    "não invente classe nova, não calcule nada. Responda em uma única linha no "
    "formato: CLASSE | trecho citando a posição que decidiu. Se as posições não "
    "permitirem decidir com segurança, responda apenas: INDEFINIDO."
)


def classificar_etf(
    ticker: str,
    posicoes: list[dict],
    candidatas: list[str],
    modelo: str | None = None,
) -> tuple[str, str] | None:
    """Desempata a classe de um ETF pela LEITURA dos nomes das posições
    (ex.: 'ISHARES S&P 500' → Ações Internacionais; 'BITCOIN' → Cripto).

    É interpretação de TEXTO — a IA escolhe entre classes que o código já
    ofereceu, nunca inventa número nem classe. Retorna (classe, justificativa)
    ou None quando o modelo não decide ou não está disponível."""
    if not posicoes or not candidatas:
        return None
    lista = "\n".join(
        f"- {(p.get('nome') or '').strip()} ({(p.get('codigo') or '').strip()}) {p.get('pct', 0):.0f}%"
        for p in posicoes[:10]
    )
    conteudo = (
        f"ETF {ticker}. Classes possíveis: {', '.join(candidatas)}.\n"
        f"Maiores posições da carteira:\n{lista}"
    )
    try:
        resposta = _conversar(PROMPT_CLASSIFICAR, conteudo, modelo, None)
    except (urllib.error.URLError, OSError):
        return None
    if not resposta or "INDEFINIDO" in resposta.upper():
        return None
    # casa a classe pelo nome (mais longa primeiro: "Ações Internacionais"
    # antes de "Ações Brasil") e usa o texto após '|' como justificativa
    alvo = resposta.upper()
    for classe in sorted(candidatas, key=len, reverse=True):
        if classe.upper() in alvo:
            justificativa = resposta.split("|", 1)[1].strip() if "|" in resposta else resposta.strip()
            return classe, justificativa[:200]
    return None


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
