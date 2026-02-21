import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile

# 1. Configuração de Título e Layout
st.set_page_config(page_title="🛡️ Vistor.IA Pro", layout="wide")
st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria") 

# 2. Entrada da API Key na Barra Lateral
api_key = st.sidebar.text_input("Insira sua Gemini API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        # Utilizamos o modelo Flash por ser mais estável para chaves novas e mais rápido
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 3. Interface de Upload
        uploaded_files = st.file_uploader("Arraste ou selecione as fotos da vistoria", 
                                        accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

        if uploaded_files:
            if st.button("🚀 Efetuar Análise Técnica"):
                resultados_texto = ""
                
                for uploaded_file in uploaded_files:
                    # Preparação da imagem
                    img_pil = Image.open(uploaded_file)
                    st.image(img_pil, width=300, caption=f"Arquivo: {uploaded_file.name}")
                    
                    # Instrução do Sistema (Sua lógica de engenharia pericial)
                    prompt = """Aja como Engenheiro Civil Perito. Identifique o cômodo. 
                    Gere uma tabela Markdown com: Elemento, Material, Estado (🟢, 🟡, 🔴), 
                    Diagnóstico Técnico e Idade Aparente. Determine o Padrão (Baixo/Médio/Alto)."""
                    
                    # Chamada da API com tratamento de erro robusto
                    try:
                        with st.spinner(f"Analisando {uploaded_file.name}..."):
                            response = model.generate_content([prompt, img_pil])
                            st.markdown(response.text)
                            resultados_texto += f"\n\nIMAGEM: {uploaded_file.name}\n" + response.text
                    except Exception as e:
                        st.error(f"Erro técnico na API para a imagem {uploaded_file.name}: {e}")

                # Armazena os resultados para o PDF
                st.session_state['resultado_vistoria'] = resultados_texto

            # 4. Geração de PDF em Modo Paisagem
            if 'resultado_vistoria' in st.session_state and st.session_state['resultado_vistoria']:
                if st.button("📄 Gerar Relatório PDF (Paisagem)"):
                    pdf = FPDF(orientation='L', unit='mm', format='A4')
                    pdf.add_page()
                    pdf.set_font("Arial", size=12)
                    pdf.cell(200, 10, txt="Relatório de Vistoria - Vistor.IA Pro", ln=1, align='C')
                    
                    # Limpeza de emojis para evitar erro no PDF básico
                    texto_pdf = st.session_state['resultado_vistoria'].replace('🟢','[BOM]').replace('🟡','[REGULAR]').replace('🔴','[CRITICO]')
                    pdf.multi_cell(0, 10, txt=texto_pdf)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        pdf.output(tmp.name)
                        st.download_button("Clique aqui para baixar seu PDF", 
                                         data=open(tmp.name, "rb"), 
                                         file_name="relatorio_vitoria_pro.pdf")
    except Exception as general_error:
        st.error(f"Erro de configuração: {general_error}")
else:
    st.info("Acesse https://aistudio.google.com/app/apikey para obter sua chave gratuita.")
