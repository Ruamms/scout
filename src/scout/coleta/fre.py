"""Coleta do FRE (Formulário de Referência) — dados abertos da CVM.

O FRE é o documento mais rico e menos lido do mercado. A parte ESTRUTURADA
(sem IA) já entrega dois blocos que ninguém mostra de graça:
- administradores: quem manda (conselho/diretoria/fiscal) com cargo, profissão,
  desde quando está na casa, nº de mandatos, % de presença nas reuniões, se foi
  eleito pelo controlador e o resumo de experiência declarado;
- transações com partes relacionadas: com quem a empresa faz negócio "em casa"
  (parte, relação, objeto, montante, saldo, juros).

Processos judiciais (seção 4.3+) NÃO vêm estruturados — ficam para a leitura
por IA do PDF (nuance registrada em docs/ACOES.md). Zip anual leve (~7 MB).
"""

from __future__ import annotations

import csv
import io
import sqlite3
import zipfile
from datetime import date

URL_FRE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _baixar(ano: int) -> bytes | None:
    import urllib.error
    import urllib.request

    try:
        requisicao = urllib.request.Request(URL_FRE.format(ano=ano), headers=_HEADERS)
        with urllib.request.urlopen(requisicao, timeout=180) as resposta:
            return resposta.read()
    except (urllib.error.URLError, OSError):
        return None


def _num(valor) -> float | None:
    """O FRE usa PONTO como decimal (3973062.88) — float direto primeiro;
    o formato pt-BR (1.234,56) fica só de fallback (senão 100×-a o valor)."""
    if valor in (None, ""):
        return None
    texto = str(valor).strip()
    try:
        return float(texto)
    except ValueError:
        try:
            return float(texto.replace(".", "").replace(",", "."))
        except ValueError:
            return None


def carregar_zip(con: sqlite3.Connection, conteudo: bytes, cnpj_para_cod: dict[str, str]) -> tuple[int, int]:
    """Grava administradores e partes relacionadas do zip FRE (última versão de
    cada companhia vence). Retorna (n_administradores, n_partes)."""
    from .. import armazenamento

    zf = zipfile.ZipFile(io.BytesIO(conteudo))

    def _ler(parcial: str):
        nome = next((n for n in zf.namelist() if parcial in n.lower()), None)
        if not nome:
            return
        with zf.open(nome) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")

    # última versão do FRE por companhia (o documento é reapresentável)
    def _versoes(parcial: str) -> dict[str, int]:
        maiores: dict[str, int] = {}
        for linha in _ler(parcial):
            cod = cnpj_para_cod.get(armazenamento.so_digitos(linha.get("CNPJ_Companhia") or ""))
            if cod is None:
                continue
            versao = int(linha.get("Versao") or 1)
            if versao > maiores.get(cod, 0):
                maiores[cod] = versao
        return maiores

    # documento FRE vigente por companhia (id + link do RAD): a porta de entrada
    # dos processos judiciais (seção 4.3+, PDF embutido — fre_processos.py)
    import re as _re

    meta_csv = next(
        (n for n in zf.namelist() if _re.fullmatch(r"fre_cia_aberta_\d{4}\.csv", n)), None
    )
    if meta_csv:
        docs_versao: dict[str, int] = {}
        for linha in _ler(meta_csv):
            cod = cnpj_para_cod.get(armazenamento.so_digitos(linha.get("CNPJ_CIA") or ""))
            if cod is None:
                continue
            versao = int(linha.get("VERSAO") or 1)
            if versao < docs_versao.get(cod, 0):
                continue
            docs_versao[cod] = versao
            try:
                id_doc = int(linha.get("ID_DOC") or 0)
            except ValueError:
                continue
            con.execute(
                "INSERT OR REPLACE INTO fre_docs (cod_cvm, id_doc, link, referencia) VALUES (?, ?, ?, ?)",
                (cod, id_doc, (linha.get("LINK_DOC") or "").strip() or None,
                 (linha.get("DT_REFER") or "").strip()[:10] or None),
            )

    n_adm = 0
    versoes = _versoes("administrador_membro")
    codigos_com_fre = set()
    for linha in _ler("administrador_membro"):
        cod = cnpj_para_cod.get(armazenamento.so_digitos(linha.get("CNPJ_Companhia") or ""))
        if cod is None or int(linha.get("Versao") or 1) != versoes.get(cod):
            continue
        nome = (linha.get("Nome") or "").strip()
        cargo = (linha.get("Cargo_Eletivo_Ocupado") or "").strip()
        if not nome:
            continue
        if cod not in codigos_com_fre:
            con.execute("DELETE FROM administradores WHERE cod_cvm = ?", (cod,))
            codigos_com_fre.add(cod)
        con.execute(
            """
            INSERT OR REPLACE INTO administradores
                (cod_cvm, nome, orgao, cargo, profissao, controlador, primeiro_mandato,
                 mandatos, presenca, experiencia, referencia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cod, nome,
                (linha.get("Orgao_Administracao") or "").strip() or None,
                cargo or None,
                (linha.get("Profissao") or "").strip() or None,
                1 if (linha.get("Eleito_Controlador") or "").strip().lower() in ("sim", "true", "1") else 0,
                (linha.get("Data_Inicio_Primeiro_Mandato") or "").strip()[:10] or None,
                _num(linha.get("Numero_Mandatos_Consecutivos")),
                _num(linha.get("Percentual_Participacao_Reunioes")),
                (linha.get("Experiencia_Profissional") or "").strip()[:600] or None,
                (linha.get("Data_Referencia") or "").strip()[:10] or None,
            ),
        )
        n_adm += 1

    n_partes = 0
    versoes_p = _versoes("transacao_parte")
    codigos_com_partes = set()
    for linha in _ler("transacao_parte"):
        cod = cnpj_para_cod.get(armazenamento.so_digitos(linha.get("CNPJ_Companhia") or ""))
        if cod is None or int(linha.get("Versao") or 1) != versoes_p.get(cod):
            continue
        parte = (linha.get("Parte_Relacionada") or "").strip()
        if not parte:
            continue
        if cod not in codigos_com_partes:
            con.execute("DELETE FROM partes_relacionadas WHERE cod_cvm = ?", (cod,))
            codigos_com_partes.add(cod)
        con.execute(
            """
            INSERT OR REPLACE INTO partes_relacionadas
                (cod_cvm, parte, relacao, objeto, montante, saldo, juros, data, referencia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cod, parte,
                (linha.get("Relacao_Emissor") or "").strip() or None,
                (linha.get("Objeto_Contrato") or "").strip()[:300] or None,
                _num(linha.get("Montante_Envolvido")),
                (linha.get("Saldo_Existente") or "").strip()[:60] or None,
                (linha.get("Taxa_Juros") or "").strip()[:60] or None,
                (linha.get("Data_Transacao") or "").strip()[:10] or None,
                (linha.get("Data_Referencia") or "").strip()[:10] or None,
            ),
        )
        n_partes += 1
    con.commit()
    return n_adm, n_partes


def atualizar(con: sqlite3.Connection, hoje: date | None = None, ao_progredir=None) -> str | None:
    """Baixa o FRE do ano corrente (fallback: anterior) para as empresas do
    escopo. Incremental por marcador anual — 1 download leve por ano."""
    from .. import armazenamento

    hoje = hoje or date.today()
    cnpj_para_cod = {
        armazenamento.so_digitos(l["cnpj"]): str(l["cod_cvm"])
        for l in con.execute("SELECT cnpj, cod_cvm FROM empresas")
    }
    if not cnpj_para_cod:
        return None
    carregados = {l[0] for l in con.execute("SELECT arquivo FROM cargas")}
    marcador = f"FRE_{hoje.year}"
    if marcador in carregados:
        return None
    total_adm = total_partes = 0
    for ano in (hoje.year, hoje.year - 1):
        conteudo = _baixar(ano)
        if not conteudo:
            continue
        n_adm, n_partes = carregar_zip(con, conteudo, cnpj_para_cod)
        total_adm += n_adm
        total_partes += n_partes
        break  # o primeiro ano disponível cobre as entregas vigentes
    if not total_adm and not total_partes:
        return None
    con.execute(
        "INSERT OR REPLACE INTO cargas (arquivo, carregado_em) VALUES (?, ?)",
        (marcador, hoje.isoformat()),
    )
    con.commit()
    mensagem = f"FRE: {total_adm} administradores e {total_partes} transações com partes relacionadas"
    if ao_progredir:
        ao_progredir(mensagem)
    return mensagem
