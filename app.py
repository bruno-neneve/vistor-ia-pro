import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
from datetime import datetime

# 1. Configuração e Identidade
st.set_page_config(page_title="Vistor.IA Pro", layout="wide")
st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria")
st.markdown("### By Bruno Leandro Nenevê")

# Dados na Sidebar
st.sidebar.header("📋 Dados da Inspeção")
nome_cliente = st.sidebar.text_input("Nome do Cliente", "IPOS")
endereco_imovel = st.sidebar.text_input("Endereço do Imóvel", "Exemplo, 1")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        
        # --- SOLUÇÃO DO ERRO 404: Autodescoberta do Nome do Modelo ---
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        target_model = None
        for m in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro-vision']:
            if m in available_models:
                target_model = m
                break
        
        if not target_model and available_models:
            target_model = available_models[0]

        if target_model:
            model = genai.GenerativeModel(target_model)
            st.sidebar.success(f"Conectado: {target_model}")
            
            uploaded_files = st.file_uploader("Selecione as fotos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

            if uploaded_files:
                if st.button("🚀 Gerar Laudo Técnico"):
                    data_hoje = datetime.now().strftime("%d/%m/%Y")
                    header_text = f"""**INSPEÇÃO VISUAL PRELIMINAR - Vistor.IA Pro** | **Data:** {data_hoje} | **Cliente:** {nome_cliente} | **Endereço:** {endereco_imovel}\n
A presente análise baseia-se exclusivamente na imagem fornecida, não sendo possível realizar testes destrutivos ou medições precisas. As classificações de estado (🟢🟡🔴) referem-se à condição aparente na imagem."""
                    
                    st.markdown(header_text)
                    contexto_consolidado = ""
                    
                    for uploaded_file in uploaded_files:
                        st.divider()
                        st.subheader(f"📸 Arquivo: {uploaded_file.name}")
                        img = Image.open(uploaded_file)
                        st.image(img, width=400)
                        
                        prompt = """Aja como Engenheiro Perito Civil. 
                        1. Identifique o cômodo e escreva acima da tabela: 'Cômodo detectado: [NOME]'.
                        2. Gere uma tabela Markdown: Elemento | Material | Estado (🟢🟡🔴) | Patologias Identificadas.
                        3. Se não houver patologias, use APENAS o símbolo '-'.
                        4. Não escreva conclusões individuais agora."""
                        
                        try:
                            with st.spinner(f"Analisando {uploaded_file.name}..."):
                                response = model.generate_content([prompt, img])
                                st.markdown(response.text)
                                contexto_consolidado += f"\nFoto {uploaded_file.name}:\n{response.text}\n"
                        except Exception as e:
                            st.error(f"Erro na imagem {uploaded_file.name}: {e}")

                    # Resumo Geral Consolidado
                    st.divider()
                    st.subheader("📝 Resumo Geral do Imóvel")
                    with st.spinner("Consolidando inteligência..."):
                        prompt_resumo = f"Escreva um 'Resumo' técnico final (não use a palavra Conclusão). Destaque conservação, padrão e cite patologias críticas encontradas: \n{contexto_consolidado}"
                        resumo_final = model.generate_content(prompt_resumo)
                        st.info(resumo_final.text)
                        st.session_state['laudo_pdf'] = f"{header_text}\n\n{contexto_consolidado}\n\nRESUMO GERAL:\n{resumo_final.text}"

                # Exportação PDF
                if 'laudo_pdf' in st.session_state:
                    if st.button("📄 Baixar Relatório PDF"):
                        pdf = FPDF(orientation='L', unit='mm', format='A4')
                        pdf.add_page()
                        pdf.set_font("helvetica", "B", 16)
                        pdf.set_text_color(0, 51, 102)
                        pdf.cell(0, 10, "LAUDO TÉCNICO VISTOR.IA PRO", ln=1, align='C')
                        
                        pdf.set_font("helvetica", size=10)
                        pdf.set_text_color(0, 0, 0)
                        texto_pdf = st.session_state['laudo_pdf'].encode('latin-1', 'replace').decode('latin-1')
                        texto_pdf = texto_pdf.replace('🟢','[BOM]').replace('🟡','[ALERTA]').replace('🔴','[CRITICO]')
                        pdf.multi_cell(0, 6, txt=texto_pdf)
                        
                        pdf.set_y(-15)
                        pdf.set_font("helvetica", "I", 8)
                        pdf.cell(0, 10, f"Vistor.IA Pro - Perito: Bruno Leandro Neneve - Pag. {pdf.page_no()}", align='C')

                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            pdf.output(tmp.name)
                            st.download_button("📥 Salvar PDF", data=open(tmp.name, "rb"), file_name=f"Laudo_{nome_cliente}.pdf")
        else:
            st.error("Nenhum modelo compatível encontrado para esta chave.")
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
else:
    st.info("Insira sua API Key para começar.")
