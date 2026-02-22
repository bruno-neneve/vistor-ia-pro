import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
from datetime import datetime
import time

# 1. Configuração de Título e Identidade Visual
st.set_page_config(page_title="Vistor.IA Pro", layout="wide")

# Inicialização de Memória (Estado da Sessão) para os dados não sumirem
if 'analise_pronta' not in st.session_state:
    st.session_state.analise_pronta = False
    st.session_state.contexto_texto = ""
    st.session_state.resumo_texto = ""

# Layout do Topo com Logo e Título
col1, col2 = st.columns([1, 4])
with col1:
    try:
        # Tenta carregar a logo do seu repositório
        logo = Image.open("logo.png")
        st.image(logo, width=150)
    except:
        st.markdown("# 🛡️") # Fallback caso o arquivo logo.png não seja encontrado

with col2:
    st.title("Vistor.IA Pro - Inteligência em Vistoria")
    st.markdown("### By Bruno Leandro Nenevê")

# 2. Configurações na Sidebar
st.sidebar.header("📋 Dados da Inspeção")
nome_cliente = st.sidebar.text_input("Nome do Cliente", "IPOS")
endereco_imovel = st.sidebar.text_input("Endereço do Imóvel", "Exemplo, 1")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    try:
        # Configuração direta para economizar cota
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Interface de Upload
        uploaded_files = st.file_uploader("Selecione as fotos da vistoria", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

        if uploaded_files:
            if st.button("🚀 Gerar Laudo Técnico"):
                data_hoje = datetime.now().strftime("%d/%m/%Y")
                full_content = ""
                
                # Cabeçalho do Laudo no App
                st.markdown(f"**INSPEÇÃO VISUAL PRELIMINAR** | {data_hoje}")
                st.markdown(f"**Cliente:** {nome_cliente} | **Endereço:** {endereco_imovel}")
                
                for uploaded_file in uploaded_files:
                    st.divider()
                    st.subheader(f"📸 Arquivo: {uploaded_file.name}")
                    img = Image.open(uploaded_file)
                    st.image(img, width=450)
                    
                    # Prompt de Engenharia Refinado
                    prompt = """Aja como Engenheiro Perito Civil. 
                    1. Identifique o cômodo e escreva acima da tabela: 'Cômodo detectado: [NOME]'.
                    2. Gere uma tabela Markdown: Elemento | Material | Estado (🟢🟡🔴) | Patologias Identificadas.
                    3. Se não houver patologias, use APENAS o símbolo '-'.
                    4. Seja estritamente técnico e objetivo."""
                    
                    try:
                        with st.spinner(f"Analisando {uploaded_file.name}..."):
                            response = model.generate_content([prompt, img])
                            st.markdown(response.text)
                            full_content += f"\n\n--- IMAGEM: {uploaded_file.name} ---\n{response.text}"
                            # Pausa para respeitar o limite de requisições por minuto
                            time.sleep(2) 
                    except Exception as e:
                        st.error(f"Erro na análise de {uploaded_file.name}: {e}")

                # 3. Resumo Geral Consolidado
                st.divider()
                st.subheader("📝 Resumo Geral do Imóvel")
                try:
                    with st.spinner("Consolidando inteligência diagnóstica..."):
                        prompt_resumo = f"Com base nas análises acima, escreva um 'Resumo' técnico (não use a palavra Conclusão). Destaque o estado de conservação geral e padrão construtivo: \n{full_content}"
                        resumo = model.generate_content(prompt_resumo)
                        st.info(resumo.text)
                        
                        # Salva na memória da sessão para persistência
                        st.session_state.contexto_texto = full_content
                        st.session_state.resumo_texto = resumo.text
                        st.session_state.analise_pronta = True
                except:
                    st.warning("Cota de API atingida para o resumo final. O laudo parcial está disponível abaixo.")

        # 4. Exportação PDF (Só aparece se houver análise pronta)
        if st.session_state.analise_pronta:
            st.divider()
            if st.button("📄 Baixar Relatório PDF Profissional"):
                pdf = FPDF(orientation='L', unit='mm', format='A4')
                pdf.add_page()
                
                # Identidade do PDF
                pdf.set_font("Arial", "B", 16)
                pdf.set_text_color(0, 51, 102) # Azul Marinho
                pdf.cell(0, 10, "LAUDO TÉCNICO VISTOR.IA PRO", ln=1, align='C')
                
                pdf.set_font("Arial", size=10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 8, f"Cliente: {nome_cliente} | Data: {datetime.now().strftime('%d/%m/%Y')}", ln=1)
                pdf.cell(0, 8, f"Endereco: {endereco_imovel}", ln=1)
                pdf.ln(5)

                # Tratamento de conteúdo para o PDF
                texto_pdf = st.session_state.contexto_texto.replace('🟢','[BOM]').replace('🟡','[ALERTA]').replace('🔴','[CRITICO]')
                resumo_pdf = st.session_state.resumo_texto
                
                # Multi_cell para evitar que o texto saia da página
                pdf.multi_cell(0, 5, txt=texto_pdf.encode('latin-1', 'replace').decode('latin-1'))
                pdf.ln(10)
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, "RESUMO GERAL DO IMÓVEL:", ln=1)
                pdf.set_font("Arial", size=10)
                pdf.multi_cell(0, 5, txt=resumo_pdf.encode('latin-1', 'replace').decode('latin-1'))
                
                # Rodapé
                pdf.set_y(-15)
                pdf.set_font("Arial", "I", 8)
                pdf.cell(0, 10, f"Vistor.IA Pro - By Bruno Leandro Neneve", align='C')

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    pdf.output(tmp.name)
                    st.download_button(
                        label="📥 Clique para Salvar o Laudo",
                        data=open(tmp.name, "rb"),
                        file_name=f"Laudo_{nome_cliente}.pdf",
                        mime="application/pdf"
                    )

    except Exception as e:
        st.error(f"Erro de conexão ou Cota Excedida: {e}")
else:
    st.info("Insira sua Gemini API Key na barra lateral para começar.")
