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

# LOGO: prioridade é raiz do repo como você descreveu
LOGO_PATH = "logo.png"
LOGO_FALLBACK = "assets/logo.png"  # opcional se você quiser usar no futuro

TZ_NAME = "America/Sao_Paulo"


# -----------------------
# Utils: file existence
# -----------------------
def exists_file(path: str) -> bool:
    try:
        import os
        return os.path.exists(path) and os.path.isfile(path)
    except Exception:
        return False


def get_logo_path() -> str | None:
    if exists_file(LOGO_PATH):
        return LOGO_PATH
    if exists_file(LOGO_FALLBACK):
        return LOGO_FALLBACK
    return None


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
    Tenta usar America/Sao_Paulo (zoneinfo). Se não houver tzdata no ambiente, cai para now() do servidor.
    """
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        return datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
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
    preferred = ["models/gemini-2.5-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]
    target = next((m for m in preferred if m in available), available[0] if available else None)
    return available, target


# -----------------------
# Image utils
# -----------------------
def image_to_optimized_jpeg_bytes(
    pil_img: Image.Image,
    max_side=DEFAULT_MAX_IMAGE_SIDE,
    quality=DEFAULT_JPEG_QUALITY
) -> bytes:
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
    "verde": ("🟢", "Bom", colors.HexColor("#DCFCE7")),         # green-100
    "amarelo": ("🟡", "Regular", colors.HexColor("#FEF9C3")),   # yellow-100
    "vermelho": ("🔴", "Ruim", colors.HexColor("#FEE2E2")),     # red-100
    "nao_identificavel": ("⚪", "Não identificável", colors.HexColor("#F3F4F6")),  # gray-100
}


def format_status(value: str) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    dot, label, _bg = STATUS_MAP.get(v, ("⚪", v, colors.HexColor("#F3F4F6")))
    return f"{dot} {label}"


def status_bg(value: str):
    v = (value or "").strip().lower()
    return STATUS_MAP.get(v, ("", "", colors.HexColor("#F3F4F6")))[2]


# -----------------------
# Prompt + JSON parsing
# -----------------------
def build_prompt() -> str:
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

    # 1) JSON puro
    try:
        return json.loads(raw), True, raw
    except Exception:
        pass

    # 2) tenta extrair o primeiro bloco {...}
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
# PDF (ReportLab) – Moderno/Clean (3B)
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


def strip_md(s: str) -> str:
    if not s:
        return ""
    # remove **bold** simples
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    return s.strip()


def split_summary_sections(text: str) -> list[tuple[str, str]]:
    """
    Tenta quebrar o resumo em blocos. Funciona mesmo se vier como texto corrido.
    Retorna lista de (titulo, conteudo).
    """
    t = strip_md(text or "")
    if not t:
        return []

    # Heurísticas comuns no seu resumo
    keys = [
        "Principais Achados",
        "Pontos de Atenção",
        "Recomendações de Próximos Passos",
        "Limitações",
    ]

    # marca posições
    positions = []
    for k in keys:
        m = re.search(rf"{re.escape(k)}\s*:?", t, flags=re.IGNORECASE)
        if m:
            positions.append((m.start(), k))

    if not positions:
        return [("Resumo Geral", t)]

    positions.sort()
    sections = []
    for i, (start, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(t)
        block = t[start:end].strip()
        # remove o título do começo do bloco
        block = re.sub(rf"^{re.escape(key)}\s*:?\s*", "", block, flags=re.IGNORECASE).strip()
        sections.append((key, block))

    # Se tiver texto antes do primeiro título, guarda como introdução
    first_start = positions[0][0]
    intro = t[:first_start].strip()
    if intro:
        sections.insert(0, ("Resumo Geral", intro))

    return sections


def fit_image_preserve_aspect(img_bytes: bytes, max_w: float, max_h: float) -> RLImage:
    """
    Cria RLImage mantendo proporção, limitado por max_w e max_h.
    """
    pil = Image.open(io.BytesIO(img_bytes))
    w_px, h_px = pil.size
    aspect = h_px / max(w_px, 1)

    # tenta usar toda a largura e ajusta altura
    w = max_w
    h = w * aspect
    if h > max_h:
        h = max_h
        w = h / aspect

    rl = RLImage(io.BytesIO(img_bytes))
    rl.drawWidth = w
    rl.drawHeight = h
    return rl


def build_pdf_bytes(report: dict) -> bytes:
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title="Relatório de Vistoria",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=9.5, leading=12))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=8.5, leading=11))
    styles.add(ParagraphStyle(name="H1", parent=styles["Title"], fontSize=18, leading=22, spaceAfter=6))
    styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontSize=13.5, leading=18, spaceBefore=6, spaceAfter=6))
    styles.add(ParagraphStyle(name="H3", parent=styles["Heading3"], fontSize=11, leading=14, spaceBefore=6, spaceAfter=6))
    styles.add(ParagraphStyle(name="Muted", parent=styles["Normal"], textColor=colors.HexColor("#6B7280"), fontSize=9, leading=11))

    header = report.get("header", {})
    meta = report.get("meta", {})
    items = report.get("items", [])
    summary = report.get("summary", {})

    logo_path = get_logo_path()

    # Header / Footer callbacks
    def draw_header_footer(canvas, _doc):
        canvas.saveState()

        # header line
        canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
        canvas.setLineWidth(1)
        canvas.line(doc.leftMargin, A4[1] - doc.topMargin + 0.2 * cm, A4[0] - doc.rightMargin, A4[1] - doc.topMargin + 0.2 * cm)

        # footer
        canvas.setFont("Helvetica", 8)
        footer_left = f"{APP_TITLE} — {APP_SUBTITLE}"
        footer_right = f"Página {_doc.page}"
        y = doc.bottomMargin - 0.6 * cm

        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(doc.leftMargin, y, footer_left)
        canvas.drawRightString(A4[0] - doc.rightMargin, y, footer_right)

        canvas.restoreState()

    story = []

    # --- Top header block (logo + title + metadata)
    top_table = []
    if logo_path:
        try:
            lg = RLImage(logo_path)
            lg.drawWidth = 1.2 * cm
            lg.drawHeight = 1.2 * cm
            top_table.append([lg, Paragraph("Relatório de Vistoria (IA)", styles["H1"])])
        except Exception:
            top_table.append(["", Paragraph("Relatório de Vistoria (IA)", styles["H1"])])
    else:
        top_table.append(["", Paragraph("Relatório de Vistoria (IA)", styles["H1"])])

    t = Table(top_table, colWidths=[1.6 * cm, A4[0] - doc.leftMargin - doc.rightMargin - 1.6 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # metadata “cards”
    meta_rows = [
        ["Gerado em", safe_p(meta.get("generated_at", ""))],
        ["Modelo", safe_p(meta.get("model", ""))],
        ["Fotos", str(meta.get("n_images", ""))],
        ["Tempo", f"{meta.get('elapsed_s', '')}s" if meta.get("elapsed_s") is not None else ""],
        ["Fuso", safe_p(meta.get("timezone", TZ_NAME))],
    ]
    if header.get("cliente"):
        meta_rows.append(["Cliente", safe_p(header.get("cliente"))])
    if header.get("endereco"):
        meta_rows.append(["Endereço", safe_p(header.get("endereco"))])

    meta_tbl = Table(meta_rows, colWidths=[2.6 * cm, A4[0] - doc.leftMargin - doc.rightMargin - 2.6 * cm])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    usable_w = A4[0] - doc.leftMargin - doc.rightMargin

    # col widths: moderno e legível
    col_elemento = usable_w * 0.20
    col_material = usable_w * 0.33
    col_estado = usable_w * 0.14
    col_obs = usable_w * 0.33

    def P(text, style="Tiny"):
        return Paragraph(safe_p(text), styles[style])

    for idx, item in enumerate(items, start=1):
        story.append(Paragraph(f"Foto {idx}: {safe_p(item.get('filename', ''))}", styles["H3"]))
        story.append(Spacer(1, 4))

        img_bytes = item.get("image_bytes")
        if img_bytes:
            # preserva proporção e limita altura (para não “estourar” página)
            max_h = 9.0 * cm
            rl_img = fit_image_preserve_aspect(img_bytes, max_w=usable_w, max_h=max_h)
            story.append(rl_img)
            story.append(Spacer(1, 8))

        if item.get("parse_ok") and isinstance(item.get("json"), dict):
            data = item["json"]
            comodo = str(data.get("comodo_ou_area", "") or "")
            obs = str(data.get("observacoes_gerais", "") or "")
            conf = data.get("confianca", None)

            # “chips” de info
            info_line = f"<b>Cômodo/Área:</b> {safe_p(comodo)}"
            if conf is not None:
                info_line += f" &nbsp;&nbsp; <b>Confiança:</b> {safe_p(conf)}"
            story.append(Paragraph(info_line, styles["Small"]))
            if obs:
                story.append(Paragraph(f"<b>Observações gerais:</b> {safe_p(obs)}", styles["Small"]))
            story.append(Spacer(1, 6))

            itens = data.get("itens", []) or []
            table_data = [[P("Elemento", "Small"), P("Material/Acabamento", "Small"), P("Estado", "Small"), P("Patologias/Obs", "Small")]]

            # TableStyle com zebra + background por status
            ts = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]

            for r_i, it in enumerate(itens, start=1):
                patologias = it.get("patologias_ou_observacoes", [])
                if isinstance(patologias, list):
                    patologias_txt = "; ".join([str(p) for p in patologias if p])
                else:
                    patologias_txt = str(patologias) if patologias else ""

                estado_raw = it.get("estado_conservacao", "")
                estado_fmt = format_status(estado_raw)

                table_data.append([
                    P(str(it.get("elemento", "") or "")),
                    P(str(it.get("material_acabamento", "") or "")),
                    P(estado_fmt),
                    P(patologias_txt),
                ])

                # zebra
                if r_i % 2 == 0:
                    ts.append(("BACKGROUND", (0, r_i), (-1, r_i), colors.HexColor("#FAFAFA")))

                # destaca coluna estado com cor de fundo suave
                ts.append(("BACKGROUND", (2, r_i), (2, r_i), status_bg(estado_raw)))

            tbl = Table(
                table_data,
                colWidths=[col_elemento, col_material, col_estado, col_obs],
                repeatRows=1
            )
            tbl.setStyle(TableStyle(ts))
            story.append(tbl)

        else:
            story.append(Paragraph("<b>Falha ao estruturar JSON.</b> Retorno bruto:", styles["Small"]))
            story.append(Spacer(1, 4))
            raw = item.get("raw_text", "") or ""
            story.append(Paragraph(safe_p(raw[:3000]), styles["Tiny"]))

        if idx < len(items):
            story.append(PageBreak())

    # Resumo com blocos
    story.append(PageBreak())
    story.append(Paragraph("Resumo Geral", styles["H2"]))
    story.append(Spacer(1, 4))

    sections = split_summary_sections(summary.get("text", "") or "")
    for title, content in sections:
        if title != "Resumo Geral":
            story.append(Paragraph(title, styles["H3"]))
        # quebra em parágrafos simples
        content = strip_md(content)
        # separa linhas vazias em parágrafos
        parts = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        for p in parts:
            story.append(Paragraph(safe_p(p), styles["Small"]))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 6))

    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    return buf.getvalue()


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

    # ---- CSS (3A: tirar vermelho, deixar clean/azul)
    st.markdown("""
    <style>
    .stButton > button {
      border-radius: 10px !important;
      border: 1px solid rgba(0,0,0,0.08) !important;
      padding: 0.6rem 0.9rem !important;
    }
    .stButton > button[kind="primary"] {
      background: #2563EB !important;
      color: white !important;
      border: 1px solid #2563EB !important;
    }
    .stButton > button[kind="primary"]:hover {
      background: #1D4ED8 !important;
      border-color: #1D4ED8 !important;
    }
    .stButton > button[kind="secondary"] {
      background: #F3F4F6 !important;
      color: #111827 !important;
      border: 1px solid #E5E7EB !important;
    }
    .stButton > button[kind="secondary"]:hover {
      background: #E5E7EB !important;
    }
    </style>
    """, unsafe_allow_html=True)

    logo_path = get_logo_path()

    # Topo: título + autor + logo
    cols_top = st.columns([1, 8])
    with cols_top[0]:
        if logo_path:
            st.image(logo_path, width=64)
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

            max_side = st.number_input(
                "Tamanho máx. da imagem (px)",
                min_value=640, max_value=3000,
                value=DEFAULT_MAX_IMAGE_SIDE, step=64
            )
            jpeg_quality = st.number_input(
                "Qualidade JPEG",
                min_value=50, max_value=95,
                value=DEFAULT_JPEG_QUALITY, step=1
            )

            _submitted = st.form_submit_button("Salvar configurações")

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
