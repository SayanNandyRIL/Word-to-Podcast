import streamlit as st
import os
import re
import base64
import wikipedia
from openai import OpenAI
from pydub import AudioSegment
from io import BytesIO
from pypdf import PdfReader
from PIL import Image
from docx import Document

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(page_title="Hinglish Podcast Generator", page_icon="🎙️")

st.title("🎙️ Any Doc to Hinglish Podcast")
st.markdown("Convert **Wikipedia, PDFs, Images, or Word Docs** into a fun, 2-minute Hinglish conversation.")

# Sidebar for API Key
api_key = st.sidebar.text_input("Enter OpenAI API Key", type="password")

if not api_key:
    st.warning("Please enter your OpenAI API Key in the sidebar to proceed.")
    st.stop()

client = OpenAI(api_key=api_key)

# --- 2. TEXT EXTRACTION FUNCTIONS ---

def get_wiki_content(topic):
    """Fetches Wikipedia summary."""
    try:
        summary = wikipedia.summary(topic, sentences=15)
        return summary
    except Exception as e:
        st.error(f"Error fetching Wikipedia: {e}")
        return None

def get_pdf_text(uploaded_file):
    """Extracts text from uploaded PDF."""
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        # Limit to first 10 pages
        for page in reader.pages[:10]:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def get_docx_text(uploaded_file):
    """Extracts text from uploaded DOCX file."""
    try:
        doc = Document(uploaded_file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        st.error(f"Error reading Word Document: {e}")
        return None

def get_image_analysis(uploaded_file):
    """Uses GPT-4o Vision to extract/describe text in an image."""
    try:
        # Encode image to base64
        bytes_data = uploaded_file.getvalue()
        base64_image = base64.b64encode(bytes_data).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all the text and summarize the visual content of this image for a podcast script."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                }
            ],
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error analyzing image: {e}")
        return None

# --- 3. SCRIPT GENERATION ---

def generate_script(content_text):
    prompt = f"""
    You are a scriptwriter for a candid, funny Indian podcast. 
    Create a conversation between **Rahul** (energetic, cracks jokes) and **Priya** (smart, sarcastic).
    
    **Content Source:** 
    {content_text[:4000]}  # Limiting text length
    
    **CRITICAL INSTRUCTIONS:**
    1. **Language:** Hinglish (Hindi + English).
    2. **Fillers:** Use words like: "Umm...", "Achcha?", "Matlab...", "Arre yaar", "You know?", "Haa correct".
    3. **Laughter:** Write "Hahaha" or "Hehe" where appropriate.
    4. **Tone:** Natural, interruptive, casual.
    5. **Length:** Keep it around 250-300 words total.
    
    **Format:**
    Rahul: Dialogue...
    Priya: Dialogue...
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a creative scriptwriter."},
                  {"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# --- 4. AUDIO GENERATION ---

def generate_audio(script_text):
    # Parse the script
    lines = script_text.strip().split('\n')
    combined_audio = AudioSegment.empty()
    
    voice_map = {"Rahul": "onyx", "Priya": "nova"}

    progress_bar = st.progress(0)
    total_lines = len(lines)

    for i, line in enumerate(lines):
        # Regex to find "Name: Text"
        match = re.match(r"^(Rahul|Priya):\s*(.*)", line, re.IGNORECASE)
        if match:
            speaker, text = match.groups()
            clean_text = re.sub(r'\((.*?)\)', '', text).strip() # Remove (actions)
            
            if clean_text:
                voice = voice_map.get(speaker, "alloy")
                try:
                    response = client.audio.speech.create(
                        model="tts-1",
                        voice=voice,
                        input=clean_text
                    )
                    
                    audio_chunk = AudioSegment.from_file(BytesIO(response.content), format="mp3")
                    silence = AudioSegment.silent(duration=150) # 150ms pause
                    combined_audio += audio_chunk + silence
                    
                except Exception as e:
                    # st.warning(f"Skipped line: {e}")
                    pass
        
        # Update progress bar
        if total_lines > 0:
            progress_bar.progress((i + 1) / total_lines)

    return combined_audio

# --- 5. MAIN UI LOGIC ---

source_type = st.radio("Select Source Material:", ("Wikipedia Topic", "Upload Document (PDF/DOCX)", "Upload Image"))

raw_content = ""

if source_type == "Wikipedia Topic":
    topic = st.text_input("Enter Topic Name (e.g., MS Dhoni)")
    if st.button("Fetch Wiki Data") and topic:
        with st.spinner("Searching Wikipedia..."):
            raw_content = get_wiki_content(topic)
            if raw_content:
                st.success("✅ Content Found!")
                st.expander("View Content").write(raw_content)

elif source_type == "Upload Document (PDF/DOCX)":
    uploaded_file = st.file_uploader("Choose a file", type=["pdf", "docx", "txt"])
    
    if uploaded_file is not None:
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        
        with st.spinner("Extracting text..."):
            if file_ext == ".pdf":
                raw_content = get_pdf_text(uploaded_file)
            elif file_ext == ".docx":
                raw_content = get_docx_text(uploaded_file)
            elif file_ext == ".txt":
                raw_content = str(uploaded_file.read(), "utf-8")
                
            if raw_content:
                st.success(f"✅ Text Extracted from {uploaded_file.name}!")
                st.expander("View Extracted Text").write(raw_content[:1000] + "...")

elif source_type == "Upload Image":
    uploaded_file = st.file_uploader("Choose an Image", type=["jpg", "png", "jpeg"])
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Uploaded Image", width=300)
        with st.spinner("Analyzing Image with GPT-4o Vision..."):
            raw_content = get_image_analysis(uploaded_file)
            if raw_content:
                st.success("✅ Image Analyzed!")
                st.expander("View Analysis").write(raw_content)

# --- Generate Podcast Button ---
if raw_content:
    if st.button("🎙️ Generate Podcast"):
        
        # 1. Script Generation
        with st.spinner("🤖 Writing Hinglish Script (Wait for it...)..."):
            script = generate_script(raw_content)
            st.subheader("📝 Generated Script")
            st.text_area("Script", script, height=300)
        
        # 2. Audio Generation
        with st.spinner("🔊 Synthesizing Audio (This takes about 30-60s)..."):
            final_audio = generate_audio(script)
            
            # Export to memory buffer
            buffer = BytesIO()
            final_audio.export(buffer, format="mp3")
            
            st.audio(buffer, format="audio/mp3")
            
            # Download Button
            st.download_button(
                label="📥 Download MP3",
                data=buffer,
                file_name="hinglish_podcast.mp3",
                mime="audio/mp3"
            )