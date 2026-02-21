import streamlit as st
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import tempfile
import os

st.set_page_config(page_title="🛡️ Vistor.IA Pro", layout="wide")
st.title("🛡️ Vistor.IA Pro - Inteligência em Vistoria")

api_key = st.sidebar.text_input("Insira sua Gemini API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        
        # --- DIAGNÓSTICO DE MODELO ---
        # Listamos os modelos que sua chave realmente pode acessar
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Tentamos selecionar o melhor disponível na hierarquia
        if 'models/gemini-1.5-flash' in available_models:
            target_model = 'gemini-1.5-flash'
        elif 'models/gemini-1.5-pro' in available_models:
            target_model = 'gemini-1.5-pro'
        elif 'models/gemini-pro-vision' in available_models:
            target_model = 'gemini-pro-vision'
        else:
            target_model = available_models[0] if available_models else None

        if target_model:
            st.sidebar.success(f"Conectado ao modelo: {target_model}")
            model = genai.GenerativeModel(target_model)
            
            uploaded_files = st.file_uploader("Fotos da vistoria", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

            if uploaded_files and st.button("🚀 Efetuar Análise Técnica"):
                resultados_texto = ""
                for uploaded_file in uploaded_files:
                    img_pil = Image.open(uploaded_file)
                    st.image(img_pil, width=300, caption=uploaded_file.name)
                    
                    prompt = "Aja como Engenheiro Perito. Identifique cômodo, material, estado (🟢🟡🔴) e patologias em tabela."
                    
                    try:
                        with st.spinner(f"Analisando com {target_model}..."):
                            response = model.generate_content([prompt, img_pil])
                            st.markdown(response.text)
                            resultados_texto += f"\n\nIMAGEM: {uploaded_file.name}\n" + response.text
                    except Exception as e:
                        st.error(f"Erro na análise de {uploaded_file.name}: {e}")
                
                st.session_state['resultado'] = resultados_texto
        else:
            st.error("Nenhum modelo de IA disponível para esta chave.")

    except Exception as e:
        st.error(f"Erro de autenticação ou conexão: {e}")
        st.info("Verifique se sua chave no AI Studio está ativa.")
else:
    st.info("Obtenha sua chave em: https://aistudio.google.com/app/apikey")
