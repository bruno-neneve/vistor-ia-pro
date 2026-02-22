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
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm


APP_TITLE = "VistorIA Pro"
DEFAULT_MAX_IMAGE_SIDE = 1280
DEFAULT_JPEG_QUALITY = 85


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
# Cache models list
# -----------------------
@st.cache_data(show_spinner=False, ttl=3600)
def cached_list_models(api_key: str):
    genai.configure(api_key=api_key)
    models = []
    for m in genai.list_models():
        name = getattr(m, "name", "")
        if not name:
            continue
        # focar nos modelos de geração (gemini)
        if "gemini" in name.lower():
            models.append(name)
    return sorted(set(models))


def pick_default_model(model_names: list[str]) -> str:
    # tenta priorizar flash, depois pro
    lower = [m.lower() for m in model_names]
    for key in ["flash", "pro"]:
        for i, m in enumerate(lower):
            if key in m:
                return model_names[i]
    return model_names[0] if model_names else ""


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
# Prompt + JSON parsing
# -----------------------
def build_prompt() -> str:
    # Saída estruturada: mais confiável para UI e PDF
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
    """
    Tenta extrair JSON mesmo que o modelo envolva com texto extra.
    Retorna (obj, ok, raw).
    """
    raw = (text or "").strip()

    # 1) tenta JSON puro
    try:
        return json.loads(raw), True, raw
    except Exception:
        pass

    # 2) tenta achar primeiro bloco {...}
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
    # google-generativeai aceita PIL Image também, mas bytes JPEG tende a ser estável
    pil_img = Image.open(io.BytesIO(image_bytes))

    resp = model.generate_content([prompt, pil_img])
    text = getattr(resp, "text", "") or ""
    obj, ok, raw = extract_json(text)
    return obj, ok, raw


# -----------------------
# PDF (ReportLab)
# -----------------------
def safe_p(text: str) -> str:
    # ReportLab Paragraph é tipo HTML-like; escapar minimamente
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
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Relatório de Vistoria",
    )
    styles = getSampleStyleSheet()
    story = []

    header = report.get("header", {})
    meta = report.get("meta", {})

    story.append(Paragraph("Relatório de Vistoria (IA)", styles["Title"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"<b>Gerado em:</b> {safe_p(meta.get('generated_at', ''))}", styles["Normal"]))
    story.append(Paragraph(f"<b>Modelo:</b> {safe_p(meta.get('model', ''))}", styles["Normal"]))
    story.append(Paragraph(f"<b>Fotos analisadas:</b> {safe_p(str(meta.get('n_images', '')))}", styles["Normal"]))
    story.append(Spacer(1, 10))

    if header.get("cliente"):
        story.append(Paragraph(f"<b>Cliente:</b> {safe_p(header.get('cliente'))}", styles["Normal"]))
    if header.get("endereco"):
        story.append(Paragraph(f"<b>Endereço:</b> {safe_p(header.get('endereco'))}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Seção por foto
    for idx, item in enumerate(report.get("items", []), start=1):
        story.append(Paragraph(f"<b>Foto {idx}:</b> {safe_p(item.get('filename', ''))}", styles["Heading3"]))
        story.append(Spacer(1, 6))

        # imagem
        img_bytes = item.get("image_bytes")
        if img_bytes:
            img_io = io.BytesIO(img_bytes)
            rl_img = RLImage(img_io)
            rl_img.drawHeight = 7.0 * cm
            rl_img.drawWidth = 12.0 * cm
            story.append(rl_img)
            story.append(Spacer(1, 10))

        # tabela de itens (se parse ok)
        if item.get("parse_ok") and isinstance(item.get("json"), dict):
            data = item["json"]
            comodo = data.get("comodo_ou_area", "")
            obs = data.get("observacoes_gerais", "")
            conf = data.get("confianca", None)

            story.append(Paragraph(f"<b>Cômodo/Área:</b> {safe_p(comodo)}", styles["Normal"]))
            if conf is not None:
                story.append(Paragraph(f"<b>Confiança:</b> {safe_p(conf)}", styles["Normal"]))
            if obs:
                story.append(Paragraph(f"<b>Observações gerais:</b> {safe_p(obs)}", styles["Normal"]))
            story.append(Spacer(1, 8))

            itens = data.get("itens", []) or []
            table_data = [["Elemento", "Material/Acabamento", "Estado", "Patologias/Obs"]]
            for it in itens:
                patologias = it.get("patologias_ou_observacoes", [])
                if isinstance(patologias, list):
                    patologias_txt = "; ".join([str(p) for p in patologias if p])
                else:
                    patologias_txt = str(patologias) if patologias else ""
                table_data.append([
                    safe_p(it.get("elemento", "")),
                    safe_p(it.get("material_acabamento", "")),
                    safe_p(it.get("estado_conservacao", "")),
                    safe_p(patologias_txt),
                ])

            tbl = Table(table_data, colWidths=[4.0*cm, 4.2*cm, 2.6*cm, 6.0*cm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
            ]))
            story.append(tbl)
        else:
            # fallback: imprime texto bruto
            story.append(Paragraph("<b>Falha ao estruturar JSON.</b> Abaixo, retorno bruto:", styles["Normal"]))
            story.append(Spacer(1, 6))
            raw = safe_p(item.get("raw_text", ""))
            story.append(Paragraph(raw[:2500], styles["Code"]))

        story.append(PageBreak())

    # Resumo
    summary = report.get("summary", {})
    story.append(Paragraph("Resumo Geral", styles["Heading2"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(safe_p(summary.get("text", "")), styles["Normal"]))

    doc.build(story)
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
            st.write(f"**Observações gerais:** {data.get('observacoes_gerais','')}")

            itens = data.get("itens", []) or []
            if itens:
                # tabela no app
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
                        "Estado": it.get("estado_conservacao", ""),
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

    st.title(APP_TITLE)
    st.caption("Análise de fotos de vistoria com Gemini + geração de relatório e PDF.")

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
        if st.button("🧹 Limpar laudo / Novo", type="secondary"):
            reset_report()
            st.rerun()

    # Upload
    uploaded_files = st.file_uploader(
        "Envie as fotos da vistoria (JPG/PNG)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    # Model selection
    model_name = ""
    if api_key:
        try:
            models = cached_list_models(api_key)
            if models:
                model_name = st.selectbox("Modelo Gemini", options=models, index=models.index(pick_default_model(models)))
            else:
                st.warning("Nenhum modelo Gemini encontrado para esta chave.")
        except Exception as e:
            st.error(f"Falha ao listar modelos: {e}")

    # Botão de análise
    colA, colB = st.columns([1, 3])
    with colA:
        run = st.button("🚀 Gerar Laudo Técnico", type="primary", disabled=(not api_key or not model_name or not uploaded_files))

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
                    "image_bytes": img_bytes,   # usado para re-render e PDF
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

        # Resumo geral (pede ao Gemini um resumo a partir dos JSONs)
        summary_text = ""
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            # monta um contexto compacto
            compact = []
            for it in items:
                if it["parse_ok"] and isinstance(it["json"], dict):
                    compact.append(it["json"])
                else:
                    compact.append({"erro": True, "raw": it.get("raw_text", "")[:500]})

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
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "model": model_name,
                "n_images": len(items),
                "elapsed_s": round(ended - started, 2),
            },
            "items": items,
            "summary": {"text": summary_text},
        }

        st.session_state.report = report
        st.session_state.analise_pronta = True
        status.success("Laudo gerado com sucesso!")

    # Sempre renderiza se pronto (resolve o “apagão”)
    if st.session_state.analise_pronta and st.session_state.report:
        render_report(st.session_state.report)

        # PDF em bytes (sem arquivo temporário)
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
