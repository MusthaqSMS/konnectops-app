# app.py
"""
KonnectOps Mobile — Professional UI with Background Images & SEO Tools
Deploy-ready for Streamlit Cloud
"""

import streamlit as st
import google.generativeai as genai
import pandas as pd
import time
import logging
from functools import lru_cache
from urllib.parse import quote_plus
import streamlit.components.v1 as components
import base64
from io import BytesIO
from typing import Optional

# Optional cloud libraries (they won't break deployment if unavailable)
try:
    import boto3
    BOTO3_AVAILABLE = True
except:
    BOTO3_AVAILABLE = False

try:
    from google.cloud import storage as gcs_storage
    from google.oauth2 import service_account
    GCS_AVAILABLE = True
except:
    GCS_AVAILABLE = False


# ==============================================
# LOGGING
# ==============================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("konnectops")


# ==============================================
# PAGE CONFIG
# ==============================================
st.set_page_config(
    page_title="KonnectOps Mobile",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ==============================================
# PROFESSIONAL UI CSS
# ==============================================
st.markdown(
    """
    <style>
    .konnectops-root { font-family: 'Segoe UI', sans-serif; color:#000; }
    .bg-section {
        min-height: 580px;
        background-size: cover;
        background-position: center;
        position: relative;
        padding: 36px 48px;
    }
    .bg-section::before {
        content:'';
        position:absolute;
        inset:0;
        background:rgba(0,0,0,0.25);
        backdrop-filter: blur(2px);
    }
    .content-box {
        position: relative;
        z-index: 10;
        background:rgba(255,255,255,0.95);
        padding:24px;
        border-radius:12px;
        max-width:1200px;
        margin:auto;
        box-shadow:0 10px 40px rgba(0,0,0,0.15);
    }
    .stButton > button {
        background:#002D62 !important;
        color:white !important;
        border-radius:8px;
        padding:10px 16px;
        font-weight:600;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown("<div class='konnectops-root'>", unsafe_allow_html=True)


# ==============================================
# SESSION STATE
# ==============================================
if "api_key" not in st.session_state: st.session_state.api_key = ""
if "model_name" not in st.session_state: st.session_state.model_name = None
if "bg_images" not in st.session_state: st.session_state.bg_images = {}
if "_last_cover_bytes" not in st.session_state: st.session_state._last_cover_bytes = None


# ==============================================
# MODEL DETECTION HELPERS
# ==============================================
@lru_cache(maxsize=1)
def fetch_models_for_key(key: str):
    genai.configure(api_key=key)
    return list(genai.list_models())


def supports_generation(model_obj):
    try:
        return "generateContent" in model_obj.supported_generation_methods
    except:
        return False


def try_connect(key):
    try:
        models = fetch_models_for_key(key)
        for m in models:
            if supports_generation(m):
                return m.name
        return models[0].name if models else None
    except Exception as e:
        logger.exception(e)
        return None


def ask_ai(prompt: str):
    """Universal AI response wrapper."""
    if not st.session_state.model_name:
        return "Error: Model not configured"

    try:
        genai.configure(api_key=st.session_state.api_key)
        model = genai.GenerativeModel(st.session_state.model_name)
        out = model.generate_content(prompt)
        return out.text or "Error: No text output"
    except Exception as e:
        logger.error(e)
        return f"Error: {e}"


# ==============================================
# SIDEBAR
# ==============================================
with st.sidebar:
    st.header("⚙️ Settings")
    api_key_in = st.text_input("Generative AI Key", type="password", value=st.session_state.api_key)
    if api_key_in != st.session_state.api_key:
        st.session_state.api_key = api_key_in

    st.subheader("Background Images (Optional)")
    pages = ["Landing", "Content", "Images", "Calendar", "Utilities", "Blog", "Uploads", "Zoho"]

    for p in pages:
        file = st.file_uploader(f"{p} Background", type=["png","jpg","jpeg"], key=f"bg_{p}")
        if file:
            b64 = base64.b64encode(file.read()).decode()
            st.session_state.bg_images[p] = f"data:image/jpeg;base64,{b64}"

    if st.button("Logout / Reset"):
        st.session_state.clear()
        st.rerun()


# ==============================================
# CONNECT MODEL AUTOMATICALLY
# ==============================================
if st.session_state.api_key and not st.session_state.model_name:
    with st.spinner("Connecting..."):
        model = try_connect(st.session_state.api_key)
        if model:
            st.session_state.model_name = model
            st.success(f"Connected to model: {model}")
            
        else:
            st.error("Invalid API key or no models available.")


# ==============================================
# LOGIN SCREEN
# ==============================================
if not st.session_state.model_name:
    st.markdown("<h2>🔐 KonnectOps Login</h2>", unsafe_allow_html=True)
    api = st.text_input("Paste API Key", type="password")
    if st.button("Unlock"):
        st.session_state.api_key = api
        st.rerun()
    st.stop()


# ==============================================
# HEADER
# ==============================================
st.markdown("<h1 style='color:#002D62;padding-left:12px;'>KonnectOps Mobile</h1>", unsafe_allow_html=True)


# ==============================================
# BACKGROUND SECTION WRAPPER
# ==============================================
def render_bg_section(page_name, inner_html):
    bg = st.session_state.bg_images.get(page_name, "")
    style = f"background-image:url('{bg}');" if bg else "background:#eceff4;"
    st.markdown(
        f"""
        <div class='bg-section' style="{style}">
            <div class='content-box'>
                {inner_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# ==============================================
# TABS
# ==============================================
tabs = st.tabs([
    "📄 Landing",
    "✍️ Content",
    "🎨 Images",
    "📅 Calendar",
    "🛠️ Utilities",
    "📝 Blog",
    "☁️ Uploads",
    "👨‍💻 Zoho"
])


# ==============================================
# TAB 1 — LANDING PAGE GENERATOR
# ==============================================
with tabs[0]:
    render_bg_section("Landing", "<h2>Landing Page Generator</h2>")

    c1, c2 = st.columns(2)
    with c1:
        proj = st.text_input("Project Name")
        loc = st.text_input("Location")
        price = st.text_input("Price")

    with c2:
        old_txt = st.text_input("Old Project Name (Replace)")
        html_input = st.text_area("Paste HTML Template", height=200)

    if st.button("Generate Landing Page"):
        if not html_input:
            st.warning("Paste an HTML template first")
        else:
            html_out = (
                html_input.replace(old_txt or "", proj or "")
                .replace("{LOCATION}", loc)
                .replace("{PRICE}", price)
            )

            if "{DESC}" in html_out:
                seo = ask_ai(f"Write a 150 character SEO meta description for {proj} in {loc}.")
                html_out = html_out.replace("{DESC}", seo)

            st.markdown("### Preview")
            components.html(html_out, height=400, scrolling=True)

            st.download_button("Download HTML", html_out, f"{proj}.html")


# ==============================================
# TAB 2 — MARKETING CONTENT GENERATOR
# ==============================================
with tabs[1]:
    render_bg_section("Content", "<h2>Marketing Studio</h2>")

    ctype = st.selectbox("Content Type", [
        "Blog Post", "Instagram Carousel", "LinkedIn Post", "Client Email"
    ])
    topic = st.text_input("Topic")

    if st.button("Generate Content"):
        if topic.strip():
            out = ask_ai(f"Write a professional {ctype} about: {topic}.")
            st.code(out)
        else:
            st.warning("Enter a topic.")


# ==============================================
# TAB 3 — IMAGE PROMPTS
# ==============================================
with tabs[2]:
    render_bg_section("Images", "<h2>Image Prompt Generator</h2>")

    desc = st.text_input("Image Concept")
    style = st.selectbox("Style", ["Photorealistic", "8K Render", "Architectural"])

    if st.button("Generate Prompt"):
        out = ask_ai(f"Write a Midjourney prompt for: {desc}. Style: {style}.")
        st.code(out)


# ==============================================
# TAB 4 — CALENDAR
# ==============================================
with tabs[3]:
    render_bg_section("Calendar", "<h2>2026 Festival Calendar</h2>")

    df = pd.DataFrame({
        "Date": ["Jan 14","Jan 26","Mar 04","Mar 20","Apr 14","Aug 15","Aug 26","Sep 14","Oct 20","Nov 08","Dec 25"],
        "Festival": ["Pongal","Republic Day","Holi","Ramzan","Tamil New Year","Independence Day","Onam","Ganesh Chaturthi","Ayudha Puja","Diwali","Christmas"]
    })

    st.table(df)


# ==============================================
# TAB 5 — UTILITIES
# ==============================================
with tabs[4]:
    render_bg_section("Utilities", "<h2>Sales Utilities</h2>")

    tool = st.radio("Choose Tool", [
        "WhatsApp Link Generator", "EMI Calculator", "Tamil Translator"
    ])

    if tool == "WhatsApp Link Generator":
        ph = st.text_input("Phone Number", "919876543210")
        msg = st.text_input("Message", "Hi, I am interested.")
        if st.button("Generate Link"):
            st.code(f"https://wa.me/{ph}?text={quote_plus(msg)}")

    elif tool == "EMI Calculator":
        loan = st.number_input("Loan Amount", value=5000000)
        rate = st.number_input("Interest Rate %", value=8.5)
        yrs = st.number_input("Years", value=20)

        if st.button("Calculate EMI"):
            r = rate / (12 * 100)
            n = yrs * 12
            emi = loan * r * ((1+r)**n) / (((1+r)**n)-1)
            st.success(f"₹ {int(emi):,} per month")

    else:
        text = st.text_area("English Text")
        if st.button("Translate to Tamil"):
            out = ask_ai(f"Translate to professional Tamil: {text}")
            st.code(out)


# ==============================================
# TAB 6 — HOME KONNECT BLOG GENERATOR
# ==============================================
with tabs[5]:
    render_bg_section("Blog", "<h2>Home Konnect Blog Generator</h2>")

    col1, col2 = st.columns([2,1])
    with col1:
        b_project = st.text_input("Project Name")
        b_location = st.text_input("Location")
        b_developer = st.text_input("Developer")
        b_usps = st.text_area("USPs (comma separated)")

    with col2:
        b_phone = st.text_input("Phone")
        b_email = st.text_input("Email")

    if st.button("Generate Blog"):
        prompt = (
            "You are a real estate content writer. Follow this EXACT structure:\n"
            "Title, Preview (with emojis), Introduction, Project Highlights with emojis, "
            "Location Advantages, Premium Specifications, Amenities with emojis, "
            "About Developer, Contact CTA, FAQ (5), SEO Meta Title & Description, Tags.\n\n"
            f"Project: {b_project}\n"
            f"Location: {b_location}\n"
            f"Developer: {b_developer}\n"
            f"USPs: {b_usps}\n"
            f"Phone: {b_phone}\n"
            f"Email: {b_email}\n\n"
            "Return pure Markdown only."
        )

        out = ask_ai(prompt)
        st.code(out, language="markdown")

    # Cover Prompt
    usps_short = ", ".join(b_usps.split(",")[:4])
    img_prompt = (
        f"Blog cover for {b_project} located in {b_location}. "
        f"Photorealistic 1200x628 modern apartment facade, landscaped greenery, "
        f"professional lighting, subtle family silhouettes. Highlight: {usps_short}."
    )

    st.subheader("Cover Image Prompt")
    st.code(img_prompt)


# ==============================================
# TAB 7 — UPLOADS
# ==============================================
with tabs[6]:
    render_bg_section("Uploads", "<h2>Image Uploads</h2>")

    up = st.file_uploader("Upload Image")
    if up:
        st.image(up.read(), caption="Uploaded Image", width=600)


# ==============================================
# TAB 8 — ZOHO DELUGE
# ==============================================
with tabs[7]:
    render_bg_section("Zoho", "<h2>Zoho Deluge Script Generator</h2>")

    logic = st.text_area("Describe the logic")
    if st.button("Generate Deluge Script"):
        out = ask_ai(f"Write a Zoho Deluge script that does the following: {logic}")
        st.code(out, language="java")


# END ROOT DIV
st.markdown("</div>", unsafe_allow_html=True)
