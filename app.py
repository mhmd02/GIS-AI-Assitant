import streamlit as st
import google.generativeai as genai
from groq import Groq
from openai import OpenAI
import os
from fpdf import FPDF
from PIL import Image

st.set_page_config(page_title="GIS Assistant", page_icon="🗺️", layout="wide")

SYSTEM_PROMPT_PRESETS = {
    "🌊 Spatial Analyst": "You are a specialized Spatial Analyst AI. Your role is to assist GIS engineers by explaining spatial statistics, suggesting appropriate spatial analyses, recommending geospatial data sources, and writing scripts (e.g., Python/ArcPy, PyQGIS, PostGIS, GEE). Always think spatially, and be rigorous about coordinate reference systems, topology, and geospatial algorithms.",
    "Custom": ""
}

PRESET_PROMPTS = [
    "Explain Moran's I and when to use it.",
    "Generate a Python script to create a 50m buffer around points in a GeoJSON.",
    "Analyze NDVI: what are typical thresholds for healthy vegetation?",
    "Extract all spatial features mentioned in this text as JSON. Text: 'A river flows through the park near the mountain peak'."
]

PROVIDERS = {
    "Gemini": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.5-flash-8b"],
    "Groq": ["llama3-8b-8192", "llama3-70b-8192", "mixtral-8x7b-32768", "gemma2-9b-it"],
    "OpenRouter": ["openai/gpt-4o-mini", "anthropic/claude-3-haiku", "meta-llama/llama-3-8b-instruct"]
}

if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_input" not in st.session_state:
    st.session_state.current_input = ""

def estimate_tokens(text: str) -> int:
    if not text: return 0
    return int(len(text.split()) * 1.3)

def clear_chat():
    st.session_state.messages = []

def get_markdown_export():
    md = "# GIS Assistant Chat Export\n\n"
    for m in st.session_state.messages:
        role = "User" if m["role"] == "user" else "Assistant"
        content = m["content"]
        if isinstance(content, list):
            content = "[Image attached]\n" + "".join([c for c in content if isinstance(c, str)])
        md += f"### {role}\n{content}\n\n"
    return md

def get_pdf_export():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=12)
    
    pdf.cell(200, 10, txt="GIS Assistant Chat Export", ln=True, align='C')
    pdf.ln(10)
    
    for m in st.session_state.messages:
        role = "User" if m["role"] == "user" else "Assistant"
        content = m["content"]
        if isinstance(content, list):
            content = "[Image attached]\n" + "".join([c for c in content if isinstance(c, str)])
        
        pdf.set_font("Helvetica", style='B', size=12)
        pdf.cell(0, 10, txt=role, ln=True)
        pdf.set_font("Helvetica", size=11)
        
        safe_content = content.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 8, txt=safe_content)
        pdf.ln(5)
        
    return pdf.output(dest='S').encode('latin-1')

def handle_preset_click(prompt):
    st.session_state.current_input = prompt

# --- UI Setup ---
with st.sidebar:
    st.title("⚙️ Settings")
    provider = st.selectbox("Provider", list(PROVIDERS.keys()))
    model = st.selectbox("Model", PROVIDERS[provider])
    api_key = st.text_input(f"{provider} API Key", type="password")
    
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    json_mode = st.checkbox("JSON Mode (Structured Output)")
    
    st.divider()
    preset = st.selectbox("System Prompt Persona", list(SYSTEM_PROMPT_PRESETS.keys()))
    if preset == "Custom":
        sys_prompt = st.text_area("System Prompt", "", height=150)
    else:
        sys_prompt = st.text_area("System Prompt", SYSTEM_PROMPT_PRESETS[preset], height=150)
    
    st.divider()
    image_file = None
    if provider == "Gemini":
        st.write("Image Input (Gemini Only)")
        image_file = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])

st.title("🗺️ AI GIS Assistant")

# Preset buttons
st.markdown("### Quick Prompts")
cols = st.columns(2)
for i, prompt in enumerate(PRESET_PROMPTS):
    if cols[i%2].button(prompt, use_container_width=True):
         st.session_state.current_input = prompt

# Metrics and Export
st.markdown("---")
m_col1, m_col2, m_col3, m_col4 = st.columns(4)
total_tokens = sum(
    estimate_tokens(m['content']) if isinstance(m['content'], str) 
    else estimate_tokens("".join([c for c in m['content'] if isinstance(c, str)])) 
    for m in st.session_state.messages
)
m_col1.metric("Approx. Tokens", f"~{total_tokens}")

with m_col2:
    if st.button("🗑️ Clear Chat"):
        clear_chat()
        st.rerun()

with m_col3:
    if st.session_state.messages:
        st.download_button("📥 Export Markdown", get_markdown_export(), "chat.md")
with m_col4:
    if st.session_state.messages:
        st.download_button("📥 Export PDF", get_pdf_export(), "chat.pdf")

st.markdown("---")

# Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if isinstance(msg["content"], list):
             for item in msg["content"]:
                 if isinstance(item, str):
                     st.write(item)
                 else:
                     st.image(item, width=300)
        else:
             st.write(msg["content"])

# Input processing
user_input = st.chat_input("Ask about GIS, Spatial Analysis, scripts...")
if st.session_state.current_input:
    user_input = st.session_state.current_input
    st.session_state.current_input = ""

if user_input:
    if not api_key:
        st.warning(f"Please enter your {provider} API Key in the sidebar.")
        st.stop()
        
    content_to_append = user_input
    image_obj = None
    
    if image_file and provider == "Gemini":
        image_obj = Image.open(image_file)
        content_to_append = [user_input, image_obj]
        
    st.session_state.messages.append({"role": "user", "content": content_to_append})
    
    with st.chat_message("user"):
        st.write(user_input)
        if image_obj:
            st.image(image_obj, width=300)
            
    with st.chat_message("assistant"):
        response_container = st.empty()
        full_response = ""
        
        try:
            if provider == "Gemini":
                genai.configure(api_key=api_key)
                generation_config = genai.types.GenerationConfig(
                    temperature=temperature,
                    response_mime_type="application/json" if json_mode else "text/plain"
                )
                gemini_model = genai.GenerativeModel(model_name=model, system_instruction=sys_prompt)
                
                formatted_history = []
                for m in st.session_state.messages[:-1]:
                    role = "user" if m["role"] == "user" else "model"
                    text = m["content"]
                    if isinstance(text, list): text = "".join([c for c in text if isinstance(c, str)])
                    formatted_history.append({"role": role, "parts": [text]})
                
                chat = gemini_model.start_chat(history=formatted_history)
                
                inputs = [user_input]
                if image_obj:
                    inputs.append(image_obj)
                    
                response = chat.send_message(inputs, stream=True, generation_config=generation_config)
                
                for chunk in response:
                    full_response += chunk.text
                    response_container.markdown(full_response + "▌")
                response_container.markdown(full_response)
                
            elif provider == "Groq":
                client = Groq(api_key=api_key)
                
                messages = [{"role": "system", "content": sys_prompt}]
                for m in st.session_state.messages:
                    content = m["content"] if isinstance(m["content"], str) else "".join([c for c in m["content"] if isinstance(c, str)])
                    messages.append({"role": m["role"], "content": content})
                
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                    
                stream = client.chat.completions.create(**kwargs)
                
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        response_container.markdown(full_response + "▌")
                response_container.markdown(full_response)
                
            elif provider == "OpenRouter":
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                )
                
                messages = [{"role": "system", "content": sys_prompt}]
                for m in st.session_state.messages:
                    content = m["content"] if isinstance(m["content"], str) else "".join([c for c in m["content"] if isinstance(c, str)])
                    messages.append({"role": m["role"], "content": content})
                    
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True
                }
                if json_mode:
                     kwargs["response_format"] = {"type": "json_object"}
                     
                stream = client.chat.completions.create(**kwargs)
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        response_container.markdown(full_response + "▌")
                response_container.markdown(full_response)
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
            full_response = "Sorry, I encountered an error."
            
        st.session_state.messages.append({"role": "assistant", "content": full_response})
