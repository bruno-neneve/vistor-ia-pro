import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
import os

# 1. Configuração de Título e Layout
st.set_page_config(page_title="🛡️ Vistor.IA Pro", layout="wide")
st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria") 

# 2. Entrada da API Key na Barra Lateral
api_key = st.sidebar.text_input("Insira sua Gemini API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        
        # Tentativa de inicialização usando o nome estável do modelo
        # Se o Flash não estiver disponível, o erro será capturado no bloco try/except abaixo
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 3. Interface de Upload
        uploaded_files = st.file_uploader("Arraste ou selecione as fotos da vistoria", 
                                        accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

        if uploaded_files:
            if st.button("🚀 Efetuar Análise Técnica"):
                resultados_texto = ""
                
                for uploaded_file in uploaded_files:
                    # Preparação da imagem para processamento
                    img_pil = Image.open(uploaded_file)
                    st.image(img_pil, width=300, caption=f"Arquivo: {uploaded_file.name}")
                    
                    # Instrução do Sistema (Lógica de Engenharia Diagnóstica)
                    prompt = """Aja como Engenheiro Civil Perito. Identifique o cômodo. 
                    Gere uma tabela Markdown com: Elemento, Material, Estado (🟢, 🟡, 🔴), 
                    Diagnóstico Técnico e Idade Aparente. Determine o Padrão (Baixo/Médio/Alto)."""
                    
                    # Chamada da API com tratamento de erro multimodal
                    try:
                        with st.spinner(f"Analisando {uploaded_file.name}..."):
                            # Envio da imagem para o Gemini 1.5 Flash
                            response = model.generate_content([prompt, img_pil])
                            st.markdown(response.text)
                            resultados_texto += f"\n\nIMAGEM: {uploaded_file.name}\n" + response.text
                    except Exception as e:
                        st.error(f"Erro na análise de {uploaded_file.name}: {e}")

                # Armazenamento seguro dos resultados para exportação
                st.session_state['resultado_vistoria'] = resultados_texto

            # 4. Geração de PDF em Modo Paisagem
            if 'resultado_vistoria' in st.session_state and st.session_state['resultado_vistoria']:
                if st.button("📄 Gerar Relatório PDF (Paisagem)"):
                    try:
                        pdf = FPDF(orientation='L', unit='mm', format='A4')
                        pdf.add_page()
                        pdf.set_font("helvetica", "B", 16)
                        pdf.cell(0, 10, "Relatório de Vistoria Técnica - Vistor.IA Pro", ln=1, align='C')
                        pdf.ln(10)
                        
                        pdf.set_font("helvetica", size=10)
                        # Limpeza de caracteres especiais para evitar conflitos no PDF simples
                        texto_limpo = st.session_state['resultado_vistoria'].encode('latin-1', 'replace').decode('latin-1')
                        texto_pdf = texto_limpo.replace('🟢','[BOM]').replace('🟡','[REGULAR]').replace('🔴','[CRITICO]')
                        
                        pdf.multi_cell(0, 5, txt=texto_pdf)
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            pdf.output(tmp.name)
                            with open(tmp.name, "rb") as f:
                                st.download_button("📥 Baixar Relatório Técnico", 
                                                 data=f, 
                                                 file_name="relatorio_vitoria_pro.pdf",
                                                 mime="application/pdf")
                    except Exception as pdf_error:
                        st.error(f"Erro ao gerar PDF: {pdf_error}")
                        
    except Exception as config_error:
        st.error(f"Erro de conexão com a API: {config_error}")
else:
    st.info("Obtenha sua chave gratuita em: https://aistudio.google.com/app/apikey")
