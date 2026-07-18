"""Página "Apoie o projeto": chave PIX + QR code (BR Code/EMV do BACEN).

O payload PIX estático é montado aqui mesmo (campos EMV + CRC16/CCITT-FALSE,
conforme o Manual de Padrões para Iniciação do PIX); o desenho do QR usa a
lib `qrcode` com saída SVG — página continua auto-contida.
"""

from __future__ import annotations

from pathlib import Path

CHAVE_PIX = "ruamms3@gmail.com"
NOME_RECEBEDOR = "Ruan Sampaio"
CIDADE = "BRASIL"
EMAIL_CONTATO = "ruamms3@gmail.com"
LINKEDIN = "https://www.linkedin.com/in/ruan-magalhaes-sampaio/"


def payload_pix(
    chave: str = CHAVE_PIX, nome: str = NOME_RECEBEDOR, cidade: str = CIDADE
) -> str:
    """PIX copia-e-cola (estático, sem valor definido)."""
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    corpo = (
        _campo("00", "01")            # payload format
        + _campo("26", conta)          # merchant account info (PIX)
        + _campo("52", "0000")         # merchant category
        + _campo("53", "986")          # moeda BRL
        + _campo("58", "BR")
        + _campo("59", nome[:25])
        + _campo("60", cidade[:15])
        + _campo("62", _campo("05", "***"))  # txid livre
        + "6304"
    )
    return corpo + _crc16(corpo)


def _campo(identificador: str, valor: str) -> str:
    return f"{identificador}{len(valor):02d}{valor}"


def _crc16(dados: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) em hexa maiúsculo."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return f"{crc:04X}"


def qr_svg(payload: str) -> str:
    import qrcode
    import qrcode.image.svg

    imagem = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=12)
    return imagem.to_string(encoding="unicode")


def salvar(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / "apoie.html"
    caminho.write_text(gerar(), encoding="utf-8")
    return caminho


def gerar() -> str:
    payload = payload_pix()
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Apoie o Fato Relevante</title>
<style>
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0b1017; color:#dbe3ec; font-family:system-ui,sans-serif; line-height:1.6; }}
.pagina {{ max-width:560px; margin:0 auto; padding:40px 20px; text-align:center; }}
.marca {{ color:#8b98a9; font-size:13px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-size:26px; margin:8px 0 14px; }}
p {{ color:#aeb9c7; }}
.qr {{ background:#fff; border-radius:14px; padding:14px; display:inline-block; margin:22px 0 10px; max-width:280px; }}
.qr svg {{ width:100%; height:auto; display:block; }}
.chave {{ font-size:17px; font-weight:700; background:#121a24; border:1px solid #1f2a38; border-radius:9px; padding:10px 16px; display:inline-block; margin:8px 0; }}
textarea {{ width:100%; background:#121a24; color:#8b98a9; border:1px solid #1f2a38; border-radius:9px; padding:10px; font-size:11px; margin-top:14px; resize:none; }}
button {{ background:#5eead4; color:#0b1017; border:0; border-radius:8px; padding:8px 18px; font-weight:700; cursor:pointer; margin-top:8px; }}
a {{ color:#5eead4; }}
.rodape {{ color:#66707d; font-size:12px; margin-top:30px; }}
</style>
</head>
<body>
<div class="pagina">
  <div class="marca">FATO RELEVANTE</div>
  <h1>☕ Apoie o projeto</h1>
  <p>O Fato Relevante é gratuito e de código aberto. Se ele te ajudou, qualquer
  contribuição via PIX ajuda a manter o projeto vivo — pagando os custos de
  infraestrutura e mantendo o site <b>sem anúncios</b>.</p>
  <div class="qr">{qr_svg(payload)}</div>
  <p>Chave PIX (e-mail):</p>
  <div class="chave">{CHAVE_PIX}</div>
  <p style="margin-top:14px">ou use o PIX copia-e-cola:</p>
  <textarea id="payload" rows="3" readonly onclick="this.select()">{payload}</textarea>
  <br><button onclick="navigator.clipboard.writeText(document.getElementById('payload').value).then(()=>this.textContent='Copiado!')">Copiar código PIX</button>
  <div class="rodape">
  Contato: <a href="mailto:{EMAIL_CONTATO}">{EMAIL_CONTATO}</a>{_link_linkedin()}<br>
  Projeto open source:
  <a href="https://github.com/Ruamms/fato-relevante">github.com/Ruamms/fato-relevante</a></div>
</div>
</body>
</html>
"""


def _link_linkedin() -> str:
    if not LINKEDIN:
        return ""
    return f' · <a href="{LINKEDIN}">LinkedIn</a>'
