import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile

# 1. Configuração de Título e Layout
st.set_page_config(page_title="🛡️ Vistor.IA Pro", layout="wide")
st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria") 

# 2. Entrada da API Key (A que você pegou no passo 1)
api_key = st.sidebar.text_input("Insira sua Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)
    # Recomendado: Gemini 1.5 Pro para análise de patologias
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # 3. Interface de Upload
    uploaded_files = st.file_uploader("Arraste ou selecione as fotos da vistoria", 
                                    accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

    if uploaded_files:
        if st.button("🚀 Efetuar Análise Técnica"): #
            resultados_texto = ""
            
            for uploaded_file in uploaded_files:
                img = Image.open(uploaded_file)
                st.image(img, width=300, caption=f"Arquivo: {uploaded_file.name}")
                
                # Instrução do Sistema (Sua lógica de engenharia)
                prompt = """Aja como Engenheiro Civil Perito. Identifique o cômodo. 
                Gere uma tabela Markdown com: Elemento, Material, Estado (🟢, 🟡, 🔴), 
                Diagnóstico Técnico e Idade Aparente. Determine o Padrão (Baixo/Médio/Alto)."""
                
                response = model.generate_content([prompt, img])
                st.markdown(response.text) # Exibição tabular
                resultados_texto += f"\n\nIMAGEM: {uploaded_file.name}\n" + response.text

            # 4. Geração de PDF em Modo Paisagem
            if st.button("📄 Gerar Relatório PDF (Paisagem)"):
                pdf = FPDF(orientation='L', unit='mm', format='A4') # 'L' = Landscape/Paisagem
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(200, 10, txt="Relatório de Vistoria - Bari Juriscan Remastered", ln=1, align='C')
                pdf.multi_cell(0, 10, txt=resultados_texto.replace('🟢','*').replace('🟡','!').replace('🔴','X'))
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    pdf.output(tmp.name)
                    st.download_button("Baixar PDF", data=open(tmp.name, "rb"), file_name="relatorio_vistoria.pdf")

else:

    st.info("Acesse https://aistudio.google.com/app/apikey para obter sua chave gratuita.")
