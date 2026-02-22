import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
from datetime import datetime
import os

# 1. Configuração de Título e Layout
st.set_page_config(page_title="Vistor.IA Pro", layout="wide")

# Exibição da Logo na Barra Lateral
if os.path.exists("logo.jpg"):
    st.sidebar.image("logo.jpg", use_column_width=True)

st.sidebar.header("📋 Dados da Inspeção")
st.sidebar.caption("By Bruno Leandro Nenevê")
nome_cliente = st.sidebar.text_input("Nome do Cliente", "Consumidor Final")
endereco_imovel = st.sidebar.text_input("Endereço do Imóvel", "Não Informado")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria")
st.markdown("---")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    uploaded_files = st.file_uploader("Selecione as fotos para o laudo", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

    if uploaded_files:
        if st.button("🚀 Gerar Laudo Técnico"):
            data_hoje = datetime.now().strftime("%d/%m/%Y")
            
            # Cabeçalho do App
            st.markdown(f"### INSPEÇÃO VISUAL PRELIMINAR - Vistor.IA Pro")
            st.write(f"**Cliente:** {nome_cliente} | **Data:** {data_hoje}")
            st.write(f"**Endereço:** {endereco_imovel}")
            
            contexto_consolidado = ""
            
            for uploaded_file in uploaded_files:
                st.subheader(f"📸 {uploaded_file.name}")
                img = Image.open(uploaded_file)
                st.image(img, width=450)
                
                prompt = """Aja como Engenheiro Perito Civil. Identifique o cômodo e escreva: 'Cômodo detectado: [NOME]'.
                Gere uma tabela Markdown com: Elemento | Material | Estado (🟢🟡🔴) | Diagnóstico/Patologia.
                Se não houver patologias, use apenas '-'. Ignore móveis e objetos pessoais."""
                
                with st.spinner(f"Analisando {uploaded_file.name}..."):
                    response = model.generate_content([prompt, img])
                    st.markdown(response.text)
                    contexto_consolidado += f"\n--- IMAGEM: {uploaded_file.name} ---\n{response.text}\n"

            # Resumo Geral
            st.divider()
            st.subheader("📝 Resumo e Conclusão do Perito")
            with st.spinner("Consolidando inteligência..."):
                prompt_resumo = f"Escreva um Resumo Final técnico: \n{contexto_consolidado}"
                resumo_final = model.generate_content(prompt_resumo)
                st.info(resumo_final.text)
                st.session_state['resumo'] = resumo_final.text
            
            # PDF Aprimorado com Logo
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.add_page()
            
            # Inserção da Logo no PDF se o arquivo existir
            if os.path.exists("logo.jpg"):
                pdf.image("logo.jpg", 10, 8, 25) # Posição x, y e largura 25mm
                pdf.set_x(40) # Afasta o texto da logo
            
            pdf.set_font("helvetica", "B", 16)
            pdf.cell(0, 10, "LAUDO TÉCNICO DE VISTORIA - VISTOR.IA PRO", ln=1)
            pdf.set_font("helvetica", size=10)
            pdf.cell(0, 10, f"Perito: Bruno Leandro Nenevê | Cliente: {nome_cliente} | Data: {data_hoje}", ln=1)
            pdf.ln(10)
            
            resumo_limpo = st.session_state['resumo'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 5, txt=f"RESUMO GERAL:\n{resumo_limpo}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                pdf.output(tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button("📥 Baixar Laudo Profissional (PDF)", data=f, file_name=f"Laudo_{nome_cliente}.pdf")
else:
    st.info("Insira sua chave para iniciar.")
