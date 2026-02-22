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
        # Carrega o arquivo logo.png presente na raiz do seu GitHub
        logo = Image.open("logo.png")
        st.image(logo, width=150)
    except:
        st.markdown("# 🛡️") 

with col2:
    st.title("Vistor.IA Pro - Inteligência em Vistoria")
    st.markdown("### By Bruno Leandro Nenevê") # Seu nome como subtítulo

# 2. Configurações na Sidebar
st.sidebar.header("📋 Dados da Inspeção")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        
        # --- SOLUÇÃO DO ERRO 404: Autodescoberta do Nome do Modelo ---
        # Listamos os modelos que sua chave permite usar para evitar erros de versão da API
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target_model = next((m for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro'] if m in available_models), None)

        if target_model:
            model = genai.GenerativeModel(target_model)
            st.sidebar.success(f"Conectado ao modelo: {target_model}")
            
            uploaded_files = st.file_uploader("Selecione as fotos da vistoria", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

            if uploaded_files:
                if st.button("🚀 Gerar Laudo Técnico"):
                    data_hoje = datetime.now().strftime("%d/%m/%Y")
                    header_text = f"**INSPEÇÃO PRELIMINAR - Vistor.IA Pro** \n\n"
                    metodologia = "A presente análise é gerada com uso de inteligência artificial. As classificações de estado (🟢🟡🔴) referem-se à condição aparente na imagem."
                    
                    st.markdown(header_text + metodologia)
                    full_content = ""
                    
                    for uploaded_file in uploaded_files:
                        st.divider()
                        st.subheader(f"📸 Arquivo: {uploaded_file.name}") # Nome do arquivo como título
                        img = Image.open(uploaded_file)
                        st.image(img, width=450)
                        
                        # Prompt de Engenharia Refinado conforme solicitado
                        prompt = """Aja como Engenheiro Perito Civil. 
                        1. Identifique o cômodo e escreva acima da tabela: 'Cômodo detectado: [NOME]'.
                        2. Gere uma tabela Markdown: Elemento | Material | Estado (🟢🟡🔴) | Patologias Identificadas.
                        3. Se não houver patologias, use APENAS o símbolo '-'.
                        4. Seja técnico e objetivo."""
                        
                        try:
                            with st.spinner(f"Analisando {uploaded_file.name}..."):
                                response = model.generate_content([prompt, img])
                                st.markdown(response.text)
                                full_content += f"\n\nIMAGEM: {uploaded_file.name}\n{response.text}"
                                # Pausa de 2 segundos para respeitar o limite de 20 requisições
                                time.sleep(2) 
                        except Exception as e:
                            st.error(f"Erro na imagem {uploaded_file.name}: {e}")

                    # 3. Resumo Geral Consolidado (Item 6 e 3 das melhorias)
                    st.divider()
                    st.subheader("📝 Resumo Geral")
                    try:
                        with st.spinner("Consolidando inteligência diagnóstica..."):
                            prompt_resumo = f"Escreva um 'Resumo' técnico final. Destaque o estado de conservação geral, padrão construtivo e cite patologias críticas vinculando ao nome do arquivo: \n{full_content}"
                            resumo = model.generate_content(prompt_resumo)
                            st.info(resumo.text)
                            
                            # Salva na memória da sessão para o app não "limpar" ao baixar o PDF
                            st.session_state.contexto_texto = full_content
                            st.session_state.resumo_texto = resumo.text
                            st.session_state.header_info = header_text + metodologia
                            st.session_state.analise_pronta = True
                    except:
                        st.warning("Cota de API atingida para o resumo final.")

            # 4. Exportação PDF Profissional (Persistente)
            if st.session_state.analise_pronta:
                st.divider()
                if st.button("📄 Baixar Relatório em PDF"):
                    pdf = FPDF(orientation='L', unit='mm', format='A4')
                    pdf.add_page()
                    
                    # Identidade Visual no PDF
                    pdf.set_font("Arial", "B", 16)
                    pdf.set_text_color(0, 51, 102) # Azul Marinho para autoridade
                    pdf.cell(0, 10, "LAUDO TÉCNICO VISTOR.IA PRO", ln=1, align='C')
                    
                    pdf.set_font("Arial", size=10)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(0, 8, f"Cliente: {nome_cliente} | Data: {datetime.now().strftime('%d/%m/%Y')}", ln=1)
                    pdf.cell(0, 8, f"Endereco: {endereco_imovel}", ln=1)
                    pdf.ln(5)

                    # Conteúdo do Laudo
                    # Substituição de emojis por texto para compatibilidade com o PDF simples
                    texto_pdf = st.session_state.contexto_texto.replace('🟢','[BOM]').replace('🟡','[ALERTA]').replace('🔴','[CRITICO]')
                    resumo_pdf = st.session_state.resumo_texto
                    
                    pdf.multi_cell(0, 5, txt=texto_pdf.encode('latin-1', 'replace').decode('latin-1'))
                    pdf.ln(10)
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, "RESUMO GERAL DO IMÓVEL:", ln=1)
                    pdf.set_font("Arial", size=10)
                    pdf.multi_cell(0, 5, txt=resumo_pdf.encode('latin-1', 'replace').decode('latin-1'))
                    
                    # Rodapé de Autoria
                    pdf.set_y(-15)
                    pdf.set_font("Arial", "I", 8)
                    pdf.cell(0, 10, f"Vistor.IA Pro - By Bruno Leandro Neneve - Pag. {pdf.page_no()}", align='C')

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        pdf.output(tmp.name)
                        st.download_button(
                            label="📥 Clique para Salvar o Laudo",
                            data=open(tmp.name, "rb"),
                            file_name=f"Laudo_{nome_cliente}.pdf",
                            mime="application/pdf"
                        )
        else:
            st.error("Nenhum modelo compatível encontrado. Verifique sua chave ou cota.")

    except Exception as e:
        st.error(f"Erro técnico: {e}")
else:
    st.info("Insira sua Gemini API Key na barra lateral para começar.")
