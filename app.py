import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
from datetime import datetime
import os

# 1. Configuração de Título e Identidade
st.set_page_config(page_title="Vistor.IA Pro", layout="wide")
st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria")
st.markdown("### By Bruno Leandro Nenevê") # Seu nome como subtítulo

# Configurações na Sidebar
st.sidebar.header("📋 Dados da Inspeção")
nome_cliente = st.sidebar.text_input("Nome do Cliente", "Consumidor Final")
endereco_imovel = st.sidebar.text_input("Endereço do Imóvel", "Não Informado")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    try:
        # PROTEÇÃO TÉCNICA: Força a rota v1 estável
        os.environ["GOOGLE_GENERATIVE_AI_NETWORK_ENDPOINT"] = "generativelanguage.googleapis.com"
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        uploaded_files = st.file_uploader("Selecione as fotos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

        if uploaded_files:
            if st.button("🚀 Gerar Laudo Técnico"):
                data_hoje = datetime.now().strftime("%d/%m/%Y")
                
                # Cabeçalho atualizado conforme sua solicitação
                header_text = f"""
                **INSPEÇÃO VISUAL PRELIMINAR - Vistor.IA Pro** **Data da Inspeção:** {data_hoje}  
                **Cliente:** {nome_cliente} | **Endereço:** {endereco_imovel}
                
                A presente análise baseia-se exclusivamente na imagem fornecida, não sendo possível realizar testes destrutivos, medições precisas, inspeção de áreas não visíveis ou verificação de aspectos de funcionalidade e desempenho que demandariam uma vistoria in loco. As classificações de estado (🟢🟡🔴) referem-se à condição aparente no momento da inspeção visual da imagem.
                """
                st.markdown(header_text)
                
                contexto_consolidado = ""
                
                for uploaded_file in uploaded_files:
                    st.divider()
                    st.subheader(f"📸 Arquivo: {uploaded_file.name}") # Nome do arquivo como título
                    img = Image.open(uploaded_file)
                    st.image(img, width=400)
                    
                    # Prompt Refinado (Itens 4 e 7)
                    prompt = """Aja como Engenheiro Perito Civil. 
                    1. Identifique o cômodo e escreva: 'Cômodo detectado: [NOME]'.
                    2. Gere uma tabela Markdown com: Elemento | Material | Estado (🟢🟡🔴) | Patologias Identificadas.
                    3. Na coluna Patologias, se não houver, use APENAS '-'. 
                    4. Não escreva conclusões individuais por imagem."""
                    
                    try:
                        with st.spinner(f"Analisando {uploaded_file.name}..."):
                            response = model.generate_content([prompt, img])
                            st.markdown(response.text)
                            contexto_consolidado += f"\nAnálise da {uploaded_file.name}:\n{response.text}\n"
                    except Exception as e:
                        st.error(f"Erro na análise de {uploaded_file.name}: {e}")

                # RESUMO FINAL (Item 3 e 6)
                st.divider()
                st.subheader("📝 Resumo Geral do Imóvel")
                with st.spinner("Consolidando inteligência..."):
                    prompt_resumo = f"Com base nas análises acima, escreva um 'Resumo' técnico (não use 'Conclusão'). Destaque o estado de conservação geral, padrão construtivo e cite patologias críticas mencionando o arquivo da imagem correspondente: \n{contexto_consolidado}"
                    resumo_final = model.generate_content(prompt_resumo)
                    st.info(resumo_final.text)
                    st.session_state['laudo_pdf'] = f"{header_text}\n\n{contexto_consolidado}\n\nRESUMO:\n{resumo_final.text}"

            # 5. Geração de PDF Estilizado
            if 'laudo_pdf' in st.session_state:
                if st.button("📄 Baixar Relatório PDF Profissional"):
                    pdf = FPDF(orientation='L', unit='mm', format='A4')
                    pdf.add_page()
                    pdf.set_font("helvetica", "B", 16)
                    pdf.set_text_color(0, 51, 102) # Azul Marinho
                    pdf.cell(0, 10, "LAUDO TÉCNICO VISTOR.IA PRO", ln=1, align='C')
                    
                    pdf.set_font("helvetica", size=10)
                    pdf.set_text_color(0, 0, 0)
                    texto_pdf = st.session_state['laudo_pdf'].encode('latin-1', 'replace').decode('latin-1')
                    texto_pdf = texto_pdf.replace('🟢','[BOM]').replace('🟡','[ALERTA]').replace('🔴','[CRITICO]')
                    pdf.multi_cell(0, 6, txt=texto_pdf)
                    
                    pdf.set_y(-15)
                    pdf.set_font("helvetica", "I", 8)
                    pdf.cell(0, 10, f"Gerado por Vistor.IA Pro - Perito Responsável: Bruno Leandro Nenevê - Página {pdf.page_no()}", align='C')

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        pdf.output(tmp.name)
                        st.download_button("📥 Clique aqui para salvar o PDF", data=open(tmp.name, "rb"), file_name=f"Laudo_{nome_cliente}.pdf")
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
else:
    st.info("Insira sua Gemini API Key para começar.")
