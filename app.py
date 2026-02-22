import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
from datetime import datetime
import time

# 1. Configuração e Identidade Visual
st.set_page_config(page_title="Vistor.IA Pro", layout="wide")

# Inicialização de Memória (Estado da Sessão)
if 'analise_pronta' not in st.session_state:
    st.session_state.analise_pronta = False
    st.session_state.contexto_texto = ""
    st.session_state.resumo_texto = ""

# Layout do Topo com Logo e Título
col1, col2 = st.columns([1, 4])
with col1:
    try:
        # Carrega a logo que está no seu GitHub
        logo = Image.open("logo.png")
        st.image(logo, width=150)
    except:
        st.markdown("# 🛡️") 

with col2:
    st.title("Vistor.IA Pro - Inteligência em Vistoria")
    st.markdown(f"### By Bruno Leandro Nenevê")

# Dados na Sidebar
st.sidebar.header("📋 Dados da Inspeção")
nome_cliente = st.sidebar.text_input("Nome do Cliente", "IPOS")
endereco_imovel = st.sidebar.text_input("Endereço do Imóvel", "Exemplo, 1")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        # Autodescoberta para evitar erro 404
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target_model = next((m for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro'] if m in available_models), None)

        if target_model:
            model = genai.GenerativeModel(target_model)
            uploaded_files = st.file_uploader("Selecione as fotos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

            if uploaded_files:
                if st.button("🚀 Gerar Laudo Técnico"):
                    data_hoje = datetime.now().strftime("%d/%m/%Y")
                    full_content = ""
                    
                    st.markdown(f"**INSPEÇÃO VISUAL PRELIMINAR** | {data_hoje}")
                    
                    for uploaded_file in uploaded_files:
                        st.divider()
                        st.subheader(f"📸 Arquivo: {uploaded_file.name}")
                        img = Image.open(uploaded_file)
                        st.image(img, width=400)
                        
                        prompt = "Aja como Engenheiro Perito Civil. Identifique o cômodo e gere uma tabela Markdown: Elemento | Material | Estado (🟢🟡🔴) | Patologias Identificadas (use '-' se não houver)."
                        
                        try:
                            with st.spinner(f"Analisando {uploaded_file.name}..."):
                                response = model.generate_content([prompt, img])
                                st.markdown(response.text)
                                full_content += f"\n\n--- IMAGEM: {uploaded_file.name} ---\n{response.text}"
                                # Pequena pausa para evitar erro de quota (429)
                                time.sleep(1) 
                        except Exception as e:
                            st.error(f"Erro na imagem {uploaded_file.name}: {e}")

                    st.divider()
                    st.subheader("📝 Resumo Geral")
                    with st.spinner("Consolidando inteligência..."):
                        prompt_resumo = f"Resuma o estado geral e padrão construtivo baseado nestas análises: {full_content}"
                        resumo = model.generate_content(prompt_resumo)
                        st.info(resumo.text)
                        
                        # Salva na memória para não sumir ao baixar o PDF
                        st.session_state.contexto_texto = full_content
                        st.session_state.resumo_texto = resumo.text
                        st.session_state.analise_pronta = True

            # Exibição do botão de PDF apenas se houver análise
            if st.session_state.analise_pronta:
                st.divider()
                if st.button("📄 Baixar Relatório PDF Profissional"):
                    pdf = FPDF(orientation='L', unit='mm', format='A4')
                    pdf.add_page()
                    
                    # Estética do PDF
                    pdf.set_font("Arial", "B", 16)
                    pdf.set_text_color(0, 51, 102) # Azul Marinho
                    pdf.cell(0, 10, "LAUDO TÉCNICO DE VISTORIA - VISTOR.IA PRO", ln=1, align='C')
                    
                    pdf.set_font("Arial", size=10)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(0, 8, f"Cliente: {nome_cliente} | Data: {datetime.now().strftime('%d/%m/%Y')}", ln=1)
                    pdf.ln(5)

                    # Conteúdo do PDF limpo
                    texto_pdf = st.session_state.contexto_texto.replace('🟢','[BOM]').replace('🟡','[ALERTA]').replace('🔴','[CRITICO]')
                    resumo_pdf = st.session_state.resumo_texto
                    
                    # Adiciona conteúdo ao PDF tratando caracteres especiais
                    pdf.multi_cell(0, 5, txt=texto_pdf.encode('latin-1', 'replace').decode('latin-1'))
                    pdf.ln(10)
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, "RESUMO GERAL DO IMÓVEL:", ln=1)
                    pdf.set_font("Arial", size=10)
                    pdf.multi_cell(0, 5, txt=resumo_pdf.encode('latin-1', 'replace').decode('latin-1'))
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        pdf.output(tmp.name)
                        st.download_button("📥 Clique aqui para Salvar o Arquivo", data=open(tmp.name, "rb"), file_name=f"Laudo_{nome_cliente}.pdf")
    except Exception as e:
        st.error(f"Erro geral: {e}")
