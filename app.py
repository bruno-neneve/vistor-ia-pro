import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
from datetime import datetime
import os

# 1. Configuração e Identidade Visual
st.set_page_config(page_title="Vistor.IA Pro", layout="wide")

# Inicialização de Memória (Estado da Sessão) para os dados não sumirem
if 'analise_pronta' not in st.session_state:
    st.session_state.analise_pronta = False
    st.session_state.contexto_texto = ""
    st.session_state.resumo_texto = ""
    st.session_state.header_info = ""

# Layout do Topo com Logo e Título
col1, col2 = st.columns([1, 4])
with col1:
    try:
        logo = Image.open("logo.png")
        st.image(logo, width=150)
    except:
        st.markdown("# 🛡️") # Fallback caso a logo dê erro

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
        
        # Autodescoberta do modelo (Evita erro 404)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target_model = next((m for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro'] if m in available_models), available_models[0] if available_models else None)

        if target_model:
            model = genai.GenerativeModel(target_model)
            uploaded_files = st.file_uploader("Selecione as fotos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

            # BOTÃO GERAR ANÁLISE
            if uploaded_files:
                if st.button("🚀 Gerar Laudo Técnico"):
                    data_hoje = datetime.now().strftime("%d/%m/%Y")
                    st.session_state.header_info = f"**INSPEÇÃO VISUAL PRELIMINAR** | {data_hoje}\n\n**Cliente:** {nome_cliente} | **Endereço:** {endereco_imovel}"
                    
                    full_content = ""
                    
                    # Container para exibição
                    with st.container():
                        st.markdown(st.session_state.header_info)
                        
                        for uploaded_file in uploaded_files:
                            st.divider()
                            st.subheader(f"📸 Arquivo: {uploaded_file.name}")
                            img = Image.open(uploaded_file)
                            st.image(img, width=450)
                            
                            prompt = """Aja como Engenheiro Perito Civil. 
                            1. Identifique o cômodo e escreva: 'Cômodo detectado: [NOME]'.
                            2. Gere uma tabela Markdown: Elemento | Material | Estado (🟢🟡🔴) | Patologias Identificadas.
                            3. Se não houver patologias, use APENAS '-'. 
                            4. Seja objetivo."""
                            
                            with st.spinner(f"Analisando {uploaded_file.name}..."):
                                response = model.generate_content([prompt, img])
                                st.markdown(response.text)
                                full_content += f"\n\n--- IMAGEM: {uploaded_file.name} ---\n{response.text}"

                        st.divider()
                        st.subheader("📝 Resumo Geral")
                        prompt_resumo = f"Resuma o estado de conservação e padrão geral do imóvel baseado nestas análises parciais: {full_content}"
                        resumo = model.generate_content(prompt_resumo)
                        st.info(resumo.text)
                        
                        # Salva tudo no estado da sessão
                        st.session_state.contexto_texto = full_content
                        st.session_state.resumo_texto = resumo.text
                        st.session_state.analise_pronta = True

            # EXIBIÇÃO PERSISTENTE E PDF (Isso impede que os dados sumam ao clicar em baixar)
            if st.session_state.analise_pronta:
                st.sidebar.success("✅ Laudo disponível para exportação")
                
                # Botão de Download
                pdf = FPDF(orientation='L', unit='mm', format='A4')
                pdf.add_page()
                
                # Título do PDF
                pdf.set_font("Arial", "B", 16)
                pdf.set_text_color(0, 51, 102) # Azul Marinho
                pdf.cell(0, 10, "LAUDO TÉCNICO DE VISTORIA - VISTOR.IA PRO", ln=1, align='C')
                
                # Dados do Cliente
                pdf.set_font("Arial", "B", 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 8, f"Cliente: {nome_cliente} | Data: {datetime.now().strftime('%d/%m/%Y')}", ln=1)
                pdf.cell(0, 8, f"Endereco: {endereco_imovel}", ln=1)
                pdf.ln(5)

                # Conteúdo do Laudo
                pdf.set_font("Arial", size=9)
                # Limpeza de caracteres para compatibilidade FPDF
                texto_pdf = st.session_state.contexto_texto.replace('🟢','[BOM]').replace('🟡','[ALERTA]').replace('🔴','[CRITICO]')
                texto_resumo = st.session_state.resumo_texto
                
                pdf.multi_cell(0, 5, txt=texto_pdf.encode('latin-1', 'replace').decode('latin-1'))
                pdf.ln(10)
                pdf.set_font("Arial", "B", 11)
                pdf.cell(0, 10, "RESUMO GERAL DO IMÓVEL:", ln=1)
                pdf.set_font("Arial", size=10)
                pdf.multi_cell(0, 5, txt=texto_resumo.encode('latin-1', 'replace').decode('latin-1'))
                
                pdf.set_y(-15)
                pdf.set_font("Arial", "I", 8)
                pdf.cell(0, 10, f"Vistor.IA Pro - By Bruno Leandro Neneve", align='C')

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    pdf.output(tmp.name)
                    st.download_button(
                        label="📄 Baixar Relatório PDF Profissional",
                        data=open(tmp.name, "rb"),
                        file_name=f"Laudo_{nome_cliente}.pdf",
                        mime="application/pdf"
                    )

    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
else:
    st.info("Insira sua Gemini API Key para começar.")
