import streamlit as st
import os
import re
import base64
import wikipedia
from openai import OpenAI
from pydub import AudioSegment
from io import BytesIO
from pypdf import PdfReader
from docx import Document

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(page_title="Hinglish Podcast Generator", page_icon="🎙️")
st.title("🎙️ Any Doc to Hinglish Podcast")
st.markdown("Convert **Wikipedia, PDFs, Images, or Word Docs** into a fun, 2-minute Hinglish conversation.")

# Initialize Session State Variables (The Memory)
if "raw_content" not in st.session_state:
    st.session_state.raw_content = ""
if "script" not in st.session_state:
    st.session_state.initial_script = ""
    st.session_state.edited_script = ""
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None

# Sidebar
api_key = st.sidebar.text_input("Enter OpenAI API Key", type="password")
if not api_key:
    st.warning("Please enter your OpenAI API Key in the sidebar.")
    st.stop()

client = OpenAI(api_key=api_key)

# --- 2. TEXT EXTRACTION FUNCTIONS ---
def get_wiki_content(topic):
    """Fetches Wikipedia summary."""
    try:
        return wikipedia.summary(topic, sentences=15)
    except Exception as e:
        st.error(f"Error: {e}")
        return None

def get_pdf_text(uploaded_file):
    """Extracts text from uploaded PDF."""
    try:
        reader = PdfReader(uploaded_file)
        text = "".join([page.extract_text() or "" for page in reader.pages[:10]])
        return text
    except Exception as e:
        st.error(f"Error reading PDF '" + uploaded_file + "': {e}")
        return None

def get_docx_text(uploaded_file):
    """Extracts text from uploaded DOCX file."""
    try:
        doc = Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        st.error(f"Error reading Word Document '" + uploaded_file + "': {e}")
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
                {"role": "user", "content": [
                    {"type": "text", "text": "Extract text and summarize visual content."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ]}
            ],
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error analyzing image '" + uploaded_file + "': {e}")
        return None

# --- 3. SCRIPT GENERATION ---
def generate_script(content_text):
    prompt = f"""
    You are a scriptwriter for a candid, funny Indian podcast. 
    Create a conversation between **Sayan** (energetic, cracks jokes) and **Sucheta** (smart, sarcastic).
    
    **Content Source:** 
    {content_text[:4000]}  # Limiting text length
    
    **CRITICAL INSTRUCTIONS:**
    1. **Language:** Hinglish (Hindi + English).
    2. **Fillers:** Use words like: "Umm...", "Achcha?", "Matlab...", "Arre yaar", "You know?", "Haa correct".
    3. **Laughter:** Write "Hahaha" or "Hehe" where appropriate.
    4. **Tone:** Natural, interruptive, casual.
    5. **Length:** Keep it around 250-300 words total.
    
    **Format:**
    Sayan: Dialogue...
    Sucheta: Dialogue...
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a creative scriptwriter."},
                  {"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# --- 4. AUDIO GENERATION ---
def generate_audio(script_text):
    lines = script_text.strip().split('\n')
    combined_audio = AudioSegment.empty()
    voice_map = {"Sayan": "onyx", "Suchi": "nova"}
    
    # Track if we actually generated any audio
    chunks_generated = 0

    progress_bar = st.progress(0)
    total_lines = len(lines)
    status_text = st.empty()
    
    for i, line in enumerate(lines):
        # Regex to find "Name: Text"
        match = re.match(r"^(Sayan|Suchi):\s*(.*)", line, re.IGNORECASE)
        if match:
            speaker, text = match.groups()
            clean_text = re.sub(r'\((.*?)\)', '', text).strip() # Remove (actions)

            if clean_text:
                status_text.text(f"Generating audio for {speaker}...")
                try:
                    response = client.audio.speech.create(
                        model="tts-1", voice=voice_map.get(speaker, "alloy"), input=clean_text
                    )
            # Debug: Check if OpenAI returned data
                    if not response.content:
                        st.error("OpenAI API returned empty audio content.")
                        continue

                    # Convert bytes to audio segment
                    audio_chunk = AudioSegment.from_file(BytesIO(response.content), format="mp3")
                    combined_audio += audio_chunk + AudioSegment.silent(duration=150) # 150ms pause
                    chunks_generated += 1

                except Exception as e:
                    # SHOW THE ERROR ON SCREEN
                    st.error(f"Error generating line {i}: {e}")
                    # If it's an ffmpeg error, stop immediately to warn user
                    if "ffmpeg" in str(e).lower() or "file not found" in str(e).lower():
                        st.error("🚨 CRITICAL ERROR: FFmpeg is missing. Please check packages.txt.")
                        return None

        if total_lines > 0: progress_bar.progress((i + 1) / total_lines)

        status_text.empty()
    
        if chunks_generated == 0:
            st.warning("No audio chunks were generated. Check the errors above.")
            return None
        
    return combined_audio

# --- 5. Main UI LOGIC WITH SESSION STATE ---

source_type = st.radio("Select Source:", ("Wikipedia Topic", "Upload Document", "Upload Image"))
raw_content = ""

# INPUT SECTION
if source_type == "Wikipedia Topic":
    topic = st.text_input("Enter Topic Name (e.g. Mumbai Indians)")
    if st.button("Fetch Wiki Data") and topic:
        with st.spinner("Searching Wikipedia for '" + topic + "'..."):
            # SAVE TO SESSION STATE
            st.session_state.raw_content = get_wiki_content(topic)
            st.session_state.initial_script = "" # Reset script if new content fetched
            st.session_state.edited_script = ""
            st.session_state.audio_bytes = None

elif source_type == "Upload Document (PDF/DOCX/TXT)":
    uploaded_file = st.file_uploader("Choose file", type=["pdf", "docx", "txt"])
    if uploaded_file:
        if st.button("Process Document"):
            with st.spinner("Extracting from document '" + uploaded_file + "'..."):
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                if ext == ".pdf": st.session_state.raw_content = get_pdf_text(uploaded_file)
                elif ext == ".docx": st.session_state.raw_content = get_docx_text(uploaded_file)
                elif ext == ".txt": st.session_state.raw_content = str(uploaded_file.read(), "utf-8")
                
                st.session_state.initial_script = ""
                st.session_state.edited_script = ""
                st.session_state.audio_bytes = None

elif source_type == "Upload Image":
    uploaded_file = st.file_uploader("Choose Image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        st.image(uploaded_file, caption="Uploaded Image", width=300)
        if st.button("Analyze Image"):
            with st.spinner("Analyzing Image '" + uploaded_file + "'..."):
                st.session_state.raw_content = get_image_analysis(uploaded_file)
                st.session_state.initial_script = ""
                st.session_state.edited_script = ""
                st.session_state.audio_bytes = None

# DISPLAY SECTION (Check Session State instead of local variable)
if st.session_state.raw_content:
    st.success("✅ Content Loaded")
    with st.expander("View Content"):
        st.write(st.session_state.raw_content)

    # --- Generate Podcast Button ---
    if st.button("🎙️ Generate Podcast"):
        # 1. Script Generation
        with st.spinner("Writing Script..."):
            st.session_state.initial_script = generate_script(st.session_state.raw_content)
            st.session_state.audio_bytes = None # Reset audio if script changes

    # 1. Show Script
    if st.session_state.initial_script:
        st.subheader("📝 Script")
        st.text_area("Script", st.session_state.initial_script, height=300)

    # 2. Edit Script Section
    if st.session_state.initial_script:
        st.subheader("📝 Edit Script")
        st.info("You can edit the dialogue below before generating audio. Add your own jokes!")

        # This Text Area captures the user's edits
        st.session_state.edited_script = st.text_area("Script Editor", value=st.session_state.initial_script, height=300, max_chars=4000, help="The script cannot exceed 4000 characters to manage audio generation costs.")
        
        # 3. Audio Generation
        if st.button("Generate Audio"):
            if not st.session_state.edited_script.strip():
                st.error("Script is empty!")
            else:
                with st.spinner("Synthesizing Audio..."):
                    final_audio = generate_audio(st.session_state.edited_script)

                    if final_audio: # Export to memory buffer
                        buffer = BytesIO()
                        final_audio.export(buffer, format="mp3")
                        st.session_state.audio_bytes = buffer.getvalue()

                        # PLAY AUDIO
                        if st.session_state.audio_bytes:
                            st.success("Podcast Generated Successfully!")
                            st.audio(st.session_state.audio_bytes, format="audio/mp3")
                            st.download_button("📥 Download MP3", st.session_state.audio_bytes, "podcast.mp3", "audio/mp3")
                        else: st.error("Failed to generate audio. Please check the error messages above.")
                    else: st.error("Failed to generate audio. Check API keys or script format.")
