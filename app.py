import io
import json
import re
import time
import hashlib
from datetime import datetime

import streamlit as st
from PIL import Image

import google.generativeai as genai

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm


APP_TITLE = "VistorIA Pro"
APP_SUBTITLE = "Desenvolvido por Bruno Leandro Nenevê"
DEFAULT_MAX_IMAGE_SIDE = 1280
DEFAULT_JPEG_QUALITY = 85

# Se existir no repo, mostramos no app e colocamos no PDF
LOGO_PATH = "assets/logo.png"

# Timezone desejado
TZ_NAME = "America/Sao_Paulo"


# -----------------------
# Session State helpers
# -----------------------
def ensure_state():
    if "report" not in st.session_state:
        st.session_state.report = None
    if "analise_pronta" not in st.session_state:
        st.session_state.analise_pronta = False


def reset_report():
    st.session_state.report = None
    st.session_state.analise_pronta = False


# -----------------------
# Timezone helper
# -----------------------
def now_local_str():
    """
    Tenta usar America/Sao_Paulo. Se não houver tzdata no ambiente, cai para now() local do servidor.
    """
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        return datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        # fallback (pode ficar UTC em ambientes cloud)
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -----------------------
# Model discovery (estrutura anterior - evita 404)
# -----------------------
def discover_models(api_key: str) -> tuple[list[str], str | None]:
    genai.configure(api_key=api_key)
    available = [
        m.name
        for m in genai.list_models()
        if hasattr(m, "supported_generation_methods")
        and m.supported_generation_methods
        and "generateContent" in m.supported_generation_methods
    ]
    # prioridade sugerida por você
    preferred = ["models/gemini-1.5-flash", "models/gemini-1.5-pro"]
    target = next((m for m in preferred if m in available), available[0] if available else None)
    return available, target


# -----------------------
# Image utils
# -----------------------
def image_to_optimized_jpeg_bytes(pil_img: Image.Image, max_side=DEFAULT_MAX_IMAGE_SIDE, quality=DEFAULT_JPEG_QUALITY) -> bytes:
    img = pil_img.convert("RGB")
    w, h = img.size
    scale = min(max_side / max(w, h), 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# -----------------------
# Status mapping (UI + PDF)
# -----------------------
STATUS_MAP = {
    "verde": ("🟢", "Bom"),
    "amarelo": ("🟡", "Regular"),
    "vermelho": ("🔴", "Ruim"),
    "nao_identificavel": ("⚪", "Não identificável"),
}


def format_status(value: str) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    dot, label = STATUS_MAP.get(v, ("⚪", v))
    return f"{dot} {label}"


# -----------------------
# Prompt + JSON parsing
# -----------------------
def build_prompt() -> str:
    # mantém o backend em verde/amarelo/vermelho,
    # mas a UI/PDF converte em Bom/Regular/Ruim com bolinhas.
    return """
Você é um perito em vistoria visual de imóveis analisando UMA foto.

Retorne APENAS um JSON válido (sem markdown, sem texto fora do JSON), com este esquema:

{
  "comodo_ou_area": "string (ex: sala, cozinha, fachada, banheiro, garagem, área externa...)",
  "itens": [
    {
      "elemento": "string (ex: parede, piso, teto, janela, porta, bancada, revestimento...)",
      "material_acabamento": "string ou null",
      "estado_conservacao": "verde|amarelo|vermelho|nao_identificavel",
      "patologias_ou_observacoes": ["string", "..."]
    }
  ],
  "observacoes_gerais": "string",
  "confianca": 0.0
}

Regras:
- Se não der para identificar com segurança, use "nao_identificavel" e/ou null.
- "confianca" deve ser um número entre 0 e 1.
- Seja objetivo e técnico, sem inventar.
""".strip()


def extract_json(text: str):
    raw = (text or "").strip()

    try:
        return json.loads(raw), True, raw
    except Exception:
        pass

    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate), True, raw
        except Exception:
            return None, False, raw

    return None, False, raw


# -----------------------
# Gemini call
# -----------------------
def analyze_image_with_gemini(api_key: str, model_name: str, image_bytes: bytes) -> tuple[dict | None, bool, str]:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    prompt = build_prompt()
    pil_img = Image.open(io.BytesIO(image_bytes))

    resp = model.generate_content([prompt, pil_img])
    text = getattr(resp, "text", "") or ""
    obj, ok, raw = extract_json(text)
    return obj, ok, raw


# -----------------------
# PDF (ReportLab) – melhorado
# -----------------------
def safe_p(text: str) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_pdf_bytes(report: dict) -> bytes:
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Relatório de Vistoria",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=9, leading=11))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="H1", parent=styles["Title"], fontSize=18, leading=22))
    styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontSize=14, leading=18))
    styles.add(ParagraphStyle(name="H3", parent=styles["Heading3"], fontSize=11, leading=14))

    story = []

    header = report.get("header", {})
    meta = report.get("meta", {})
    items = report.get("items", [])
    summary = report.get("summary", {})

    # Logo (se existir)
    if exists_file(LOGO_PATH):
        try:
            rl_logo = RLImage(LOGO_PATH)
            rl_logo.drawHeight = 1.2 * cm
            rl_logo.drawWidth = 1.2 * cm
            story.append(rl_logo)
            story.append(Spacer(1, 6))
        except Exception:
            pass

    story.append(Paragraph("Relatório de Vistoria (IA)", styles["H1"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>Gerado em:</b> {safe_p(meta.get('generated_at', ''))}", styles["Small"]))
    story.append(Paragraph(f"<b>Modelo:</b> {safe_p(meta.get('model', ''))}", styles["Small"]))
    story.append(Paragraph(f"<b>Fotos analisadas:</b> {safe_p(str(meta.get('n_images', '')))}", styles["Small"]))
    if meta.get("elapsed_s") is not None:
        story.append(Paragraph(f"<b>Tempo total:</b> {safe_p(str(meta.get('elapsed_s')))}s", styles["Small"]))
    story.append(Spacer(1, 8))

    if header.get("cliente"):
        story.append(Paragraph(f"<b>Cliente:</b> {safe_p(header.get('cliente'))}", styles["Small"]))
    if header.get("endereco"):
        story.append(Paragraph(f"<b>Endereço:</b> {safe_p(header.get('endereco'))}", styles["Small"]))
    story.append(Spacer(1, 10))

    # Larguras de coluna proporcionais ao conteúdo (evita “brancaverde” colado)
    usable_w = A4[0] - doc.leftMargin - doc.rightMargin
    col_elemento = usable_w * 0.20
    col_material = usable_w * 0.33
    col_estado = usable_w * 0.14
    col_obs = usable_w * 0.33

    def P(text, style="Tiny"):
        return Paragraph(safe_p(text), styles[style])

    for idx, item in enumerate(items, start=1):
        story.append(Paragraph(f"Foto {idx}: {safe_p(item.get('filename', ''))}", styles["H3"]))
        story.append(Spacer(1, 6))

        img_bytes = item.get("image_bytes")
        if img_bytes:
            img_io = io.BytesIO(img_bytes)
            rl_img = RLImage(img_io)
            # largura boa sem estourar
            rl_img.drawWidth = usable_w
            rl_img.drawHeight = (usable_w * 9) / 16  # aproximação
            story.append(rl_img)
            story.append(Spacer(1, 8))

        if item.get("parse_ok") and isinstance(item.get("json"), dict):
            data = item["json"]
            comodo = str(data.get("comodo_ou_area", "") or "")
            obs = str(data.get("observacoes_gerais", "") or "")
            conf = data.get("confianca", None)

            story.append(P(f"<b>Cômodo/Área:</b> {comodo}", "Small"))
            if conf is not None:
                story.append(P(f"<b>Confiança:</b> {conf}", "Small"))
            if obs:
                story.append(P(f"<b>Observações gerais:</b> {obs}", "Small"))
            story.append(Spacer(1, 6))

            itens = data.get("itens", []) or []
            table_data = [
                [P("Elemento", "Small"), P("Material/Acabamento", "Small"), P("Estado", "Small"), P("Patologias/Obs", "Small")]
            ]

            for it in itens:
                patologias = it.get("patologias_ou_observacoes", [])
                if isinstance(patologias, list):
                    patologias_txt = "; ".join([str(p) for p in patologias if p])
                else:
                    patologias_txt = str(patologias) if patologias else ""

                estado_fmt = format_status(it.get("estado_conservacao", ""))

                table_data.append([
                    P(str(it.get("elemento", "") or "")),
                    P(str(it.get("material_acabamento", "") or "")),
                    P(estado_fmt),
                    P(patologias_txt),
                ])

            tbl = Table(
                table_data,
                colWidths=[col_elemento, col_material, col_estado, col_obs],
                repeatRows=1
            )
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tbl)
        else:
            story.append(P("<b>Falha ao estruturar JSON.</b> Retorno bruto:", "Small"))
            story.append(Spacer(1, 4))
            raw = item.get("raw_text", "") or ""
            story.append(P(raw[:3000], "Tiny"))

        if idx < len(items):
            story.append(PageBreak())

    story.append(PageBreak())
    story.append(Paragraph("Resumo Geral", styles["H2"]))
    story.append(Spacer(1, 6))
    story.append(P(summary.get("text", "") or "", "Small"))

    doc.build(story)
    return buf.getvalue()


def exists_file(path: str) -> bool:
    try:
        import os
        return os.path.exists(path) and os.path.isfile(path)
    except Exception:
        return False


# -----------------------
# App UI
# -----------------------
def render_report(report: dict):
    header = report.get("header", {})
    meta = report.get("meta", {})
    summary = report.get("summary", {})

    st.subheader("Relatório")

    cols = st.columns(3)
    cols[0].metric("Fotos", meta.get("n_images", 0))
    cols[1].metric("Modelo", meta.get("model", "-"))
    cols[2].metric("Gerado em", meta.get("generated_at", "-"))

    if header.get("cliente") or header.get("endereco"):
        st.write(
            f"**Cliente:** {header.get('cliente','-')}  \n"
            f"**Endereço:** {header.get('endereco','-')}"
        )

    st.divider()

    for idx, item in enumerate(report.get("items", []), start=1):
        st.markdown(f"### Foto {idx} — {item.get('filename','')}")
        if item.get("image_bytes"):
            st.image(item["image_bytes"], use_container_width=True)

        if item.get("parse_ok") and isinstance(item.get("json"), dict):
            data = item["json"]
            st.write(f"**Cômodo/Área:** {data.get('comodo_ou_area','')}")
            st.write(f"**Confiança:** {data.get('confianca','')}")
            if data.get("observacoes_gerais"):
                st.write(f"**Observações gerais:** {data.get('observacoes_gerais','')}")

            itens = data.get("itens", []) or []
            if itens:
                table_rows = []
                for it in itens:
                    patologias = it.get("patologias_ou_observacoes", [])
                    if isinstance(patologias, list):
                        patologias_txt = "; ".join([str(p) for p in patologias if p])
                    else:
                        patologias_txt = str(patologias) if patologias else ""

                    table_rows.append({
                        "Elemento": it.get("elemento", ""),
                        "Material/Acabamento": it.get("material_acabamento", ""),
                        "Estado": format_status(it.get("estado_conservacao", "")),
                        "Patologias/Obs": patologias_txt,
                    })
                st.dataframe(table_rows, use_container_width=True)
        else:
            st.warning("Não foi possível estruturar a resposta em JSON. Exibindo retorno bruto.")
            st.code(item.get("raw_text", ""), language="text")

        st.divider()

    st.subheader("Resumo Geral")
    st.write(summary.get("text", ""))


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_state()

    # Topo: título + autor + logo (se existir)
    cols_top = st.columns([1, 8])
    with cols_top[0]:
        if exists_file(LOGO_PATH):
            st.image(LOGO_PATH, width=64)
    with cols_top[1]:
        st.title(APP_TITLE)
        st.caption(APP_SUBTITLE)
        st.caption("Análise de fotos de vistoria com Gemini + geração de relatório e PDF (ReportLab).")

    with st.sidebar:
        st.header("Configurações")

        with st.form("cfg_form", clear_on_submit=False):
            api_key = st.text_input("Google AI Studio API Key", type="password")
            cliente = st.text_input("Cliente (opcional)", value="")
            endereco = st.text_input("Endereço (opcional)", value="")

            max_side = st.number_input("Tamanho máx. da imagem (px)", min_value=640, max_value=3000, value=DEFAULT_MAX_IMAGE_SIDE, step=64)
            jpeg_quality = st.number_input("Qualidade JPEG", min_value=50, max_value=95, value=DEFAULT_JPEG_QUALITY, step=1)

            submitted = st.form_submit_button("Salvar configurações")

        st.divider()
        if st.button("🧹 Limpar", type="secondary"):
            reset_report()
            st.rerun()

    uploaded_files = st.file_uploader(
        "Selecione as fotos",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    # Descoberta + seleção do modelo (estrutura anterior)
    model_name = None
    available_models = []
    if api_key:
        try:
            available_models, target_model = discover_models(api_key)
            if available_models:
                # deixa selecionar manualmente (e o target entra como default)
                default_index = available_models.index(target_model) if target_model in available_models else 0
                model_name = st.selectbox("Modelo Gemini", options=available_models, index=default_index)
            else:
                st.warning("Nenhum modelo compatível com generateContent foi encontrado para esta chave.")
        except Exception as e:
            st.error(f"Falha ao listar modelos: {e}")

    run = st.button(
        "🚀 Iniciar análise",
        type="primary",
        disabled=(not api_key or not model_name or not uploaded_files),
    )

    if run:
        st.session_state.analise_pronta = False
        st.session_state.report = None

        started = time.time()
        items = []

        progress = st.progress(0)
        status = st.empty()

        for i, uf in enumerate(uploaded_files, start=1):
            try:
                status.info(f"Analisando imagem {i}/{len(uploaded_files)}: {uf.name}")

                pil = Image.open(uf)
                img_bytes = image_to_optimized_jpeg_bytes(pil, max_side=max_side, quality=jpeg_quality)
                img_hash = sha256_bytes(img_bytes)

                obj, ok, raw = analyze_image_with_gemini(api_key, model_name, img_bytes)

                items.append({
                    "filename": uf.name,
                    "image_bytes": img_bytes,
                    "image_hash": img_hash,
                    "json": obj,
                    "parse_ok": ok,
                    "raw_text": raw,
                })

            except Exception as e:
                items.append({
                    "filename": getattr(uf, "name", f"imagem_{i}"),
                    "image_bytes": None,
                    "image_hash": None,
                    "json": None,
                    "parse_ok": False,
                    "raw_text": f"Erro ao analisar esta imagem: {e}",
                })

            progress.progress(i / max(len(uploaded_files), 1))

        # Resumo geral
        summary_text = ""
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            compact = []
            for it in items:
                if it["parse_ok"] and isinstance(it["json"], dict):
                    compact.append(it["json"])
                else:
                    compact.append({"erro": True, "raw": (it.get("raw_text", "") or "")[:500]})

            resumo_prompt = """
Você receberá um conjunto de análises (estruturadas em JSON ou fallback).
Gere um RESUMO GERAL técnico, objetivo, em português, com:
- Principais achados (top 5)
- Pontos de atenção (se houver)
- Recomendações de próximos passos
- Limitações: inspeção visual por fotos, sem medições/ensaios

Retorne APENAS texto (sem JSON).
""".strip()

            resp = model.generate_content([resumo_prompt, json.dumps(compact, ensure_ascii=False)])
            summary_text = (getattr(resp, "text", "") or "").strip()
        except Exception as e:
            summary_text = f"Não foi possível gerar resumo geral automaticamente: {e}"

        ended = time.time()
        report = {
            "header": {
                "cliente": cliente.strip(),
                "endereco": endereco.strip(),
            },
            "meta": {
                "generated_at": now_local_str(),
                "model": model_name,
                "n_images": len(items),
                "elapsed_s": round(ended - started, 2),
                "timezone": TZ_NAME,
            },
            "items": items,
            "summary": {"text": summary_text},
        }

        st.session_state.report = report
        st.session_state.analise_pronta = True
        status.success("Análise concluída com sucesso!")

    # Sempre renderiza se pronto (evita “apagão”)
    if st.session_state.analise_pronta and st.session_state.report:
        render_report(st.session_state.report)

        try:
            pdf_bytes = build_pdf_bytes(st.session_state.report)
            st.download_button(
                "📄 Baixar PDF do Relatório",
                data=pdf_bytes,
                file_name="relatorio_vistoria.pdf",
                mime="application/pdf",
                type="primary",
            )
        except Exception as e:
            st.error(f"Falha ao gerar PDF: {e}")


if __name__ == "__main__":
    main()
