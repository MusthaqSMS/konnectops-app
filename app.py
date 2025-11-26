# app.py — chunk 1 of 4
"""
KonnectOps Mobile — Updated with:
- Admin login
- Unified AI (Google Gemini primary -> Groq fallback)
- Groq model updated to 'llama-3.3-70b-versatile'
- Gemini safe default 'gemini-2.0-flash'
- All original features preserved
Note: Option A selected — embed API keys here (replace placeholders).
"""

# -------------------------
# IMPORTS
# -------------------------
import streamlit as st
import google.generativeai as genai
import pandas as pd
import time
import logging
import requests
import base64
import json
import os
from functools import lru_cache
from urllib.parse import quote_plus
import streamlit.components.v1 as components
from typing import Optional
from io import BytesIO
import re

# Optional cloud libs
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    BOTO3_AVAILABLE = True
except Exception:
    BOTO3_AVAILABLE = False

try:
    from google.cloud import storage as gcs_storage
    from google.oauth2 import service_account
    GCS_AVAILABLE = True
except Exception:
    GCS_AVAILABLE = False

# -------------------------
# ADMIN CREDENTIALS & API KEYS (Option A: embed here)
# Replace values below with your real keys and secure credentials.
# -------------------------
ADMIN_USERNAME = "admin"               # change this
ADMIN_PASSWORD = "Konnect@2024"        # change this
GOOGLE_API_KEY = "AIzaSyD_xRXkmB4fDjly_9eud5D1orqGcbacQoc"    # <-- paste your Google Generative AI key here
GROQ_API_KEY = "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"      # <-- paste your Groq API key here

# -------------------------
# LOGGING & PAGE CONFIG
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("konnectops")

st.set_page_config(page_title="KonnectOps Mobile", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")

# -------------------------
# STYLES & ROOT
# -------------------------
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
.konnectops-root { font-family: 'Segoe UI', sans-serif; color:#0b1720; }
.bg-section { min-height: 560px; background-size: cover; background-position: center; position: relative; padding: 34px 48px; }
.bg-section::before { content:''; position:absolute; inset:0; background: linear-gradient(180deg, rgba(6,18,33,0.18), rgba(255,255,255,0.02)); backdrop-filter: blur(2px); z-index:0; }
.content-box { position:relative; z-index:2; max-width:1200px; margin:auto; background: rgba(255,255,255,0.96); border-radius:12px; padding:22px; box-shadow:0 10px 40px rgba(2,12,34,0.08); }
.hero-title h1 { margin:0; color:#002D62; font-size:28px; }
.subtitle { color:#334155; margin-top:6px; font-size:14px; }
.stButton > button { background:#002D62 !important; color:white !important; border-radius:8px; padding:10px 14px; font-weight:600; }
.stTextInput>div>input, .stTextArea>div>textarea { font-size:15px !important; }
.mini-card { background: rgba(240,243,247,0.9); border-radius:10px; padding:10px; margin-bottom:10px; border:1px solid rgba(0,0,0,0.04); }
@media (max-width:760px) { .bg-section{padding:18px 12px;} .content-box{padding:16px;} .hero-title h1{font-size:20px;} }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="konnectops-root">', unsafe_allow_html=True)

# -------------------------
# SESSION STATE defaults
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "api_key" not in st.session_state:
    st.session_state.api_key = GOOGLE_API_KEY or "AIzaSyD_xRXkmB4fDjly_9eud5D1orqGcbacQoc"
if "groq_api_key" not in st.session_state:
    st.session_state.groq_api_key = GROQ_API_KEY or "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"
if "model_name" not in st.session_state:
    st.session_state.model_name = None
if "bg_images" not in st.session_state:
    st.session_state.bg_images = {}
if "_last_cover_bytes" not in st.session_state:
    st.session_state._last_cover_bytes = None
if "last_ai_error" not in st.session_state:
    st.session_state.last_ai_error = ""
if "available_models" not in st.session_state:
    st.session_state.available_models = []
if "s3_access_key" not in st.session_state:
    st.session_state.s3_access_key = ""
if "s3_secret_key" not in st.session_state:
    st.session_state.s3_secret_key = ""
if "s3_region" not in st.session_state:
    st.session_state.s3_region = ""
if "s3_bucket" not in st.session_state:
    st.session_state.s3_bucket = ""
if "gcs_credentials_json" not in st.session_state:
    st.session_state.gcs_credentials_json = None

# -------------------------
# MODEL & AI HELPERS
# -------------------------
@lru_cache(maxsize=1)
def fetch_models_for_key(key: str):
    genai.configure(api_key=key)
    return list(genai.list_models() or [])

def safe_name(obj):
    try:
        return getattr(obj, "name", None) or (obj.get("name") if isinstance(obj, dict) else None)
    except Exception:
        return None

def model_supports_generate(obj) -> bool:
    try:
        methods = getattr(obj, "supported_generation_methods", None)
        if methods is None and isinstance(obj, dict):
            methods = obj.get("supported_generation_methods", None)
        if not methods:
            return False
        return "generateContent" in methods or "generate" in methods
    except Exception:
        return False

def try_connect_google(key: str) -> Optional[str]:
    if not key:
        return None
    try:
        models = fetch_models_for_key(key)
    except Exception as e:
        logger.exception("Google model discovery failed: %s", e)
        return None
    for m in models:
        try:
            if model_supports_generate(m):
                name = safe_name(m)
                if name:
                    st.session_state.available_models = [safe_name(x) for x in models if safe_name(x)]
                    return name
        except Exception:
            continue
    if models:
        return safe_name(models[0])
    return None

# -------------------------
# Image generation helper (best-effort)
# -------------------------
def generate_cover_image_via_genai(prompt: str, size: str = "1200x628") -> Optional[bytes]:
    try:
        if hasattr(genai, "images") and hasattr(genai.images, "generate"):
            resp = genai.images.generate(model="image-alpha-001", prompt=prompt, size=size)
            b64 = None
            if hasattr(resp, "data"):
                item = resp.data[0]
                b64 = getattr(item, "b64_json", None) or (item.get("b64_json") if isinstance(item, dict) else None)
            elif isinstance(resp, dict):
                b64 = resp.get("b64_json") or resp.get("data", [{}])[0].get("b64_json")
            if b64:
                return base64.b64decode(b64)
        return None
    except Exception as e:
        logger.warning("Image generation failed: %s", e)
        return None

# -------------------------
# Unified AI engine: Gemini -> Groq -> fallback
# -------------------------
def ask_ai_gemini(prompt: str, timeout:int=30):
    """Call Google Gemini via google.generativeai. Return text or codes."""
    try:
        if not st.session_state.api_key:
            return "GEMINI_NO_KEY"
        genai.configure(api_key=st.session_state.api_key)
        model_name = st.session_state.model_name or try_connect_google(st.session_state.api_key)
        # Safer default model choice if discovery returns heavy preview:
        if model_name and "2.5" in model_name:
            # prefer a flash model if available
            model_name = "models/gemini-2.0-flash" if "gemini-2.0-flash" in (st.session_state.available_models or []) else model_name
        if not model_name:
            return "GEMINI_NO_MODEL"
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None)
        if text:
            return text
        return str(resp)
    except Exception as e:
        msg = str(e)
        st.session_state.last_ai_error = msg
        if re.search(r"quota|429|rate limit|exceeded", msg, re.IGNORECASE):
            return "GEMINI_QUOTA"
        return f"GEMINI_ERROR: {msg}"

def ask_ai_groq(prompt: str, timeout: int = 25):
    """Call Groq OpenAI-compatible endpoint."""
    key = st.session_state.groq_api_key
    if not key:
        return "GROQ_NO_KEY"
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",  # updated working model
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            js = resp.json()
            try:
                return js["choices"][0]["message"]["content"]
            except Exception:
                return str(js)
        if resp.status_code == 429:
            return "GROQ_QUOTA"
        # model decommission returns 400 with JSON message; bubble it up
        return f"GROQ_ERROR: {resp.status_code} {resp.text}"
    except Exception as e:
        return f"GROQ_ERROR: {e}"

def local_homekonnect_blog(project, location, developer, unitmix, usps, price_hint, possession, phone, email):
    """Local fallback markdown blog (Home Konnect style)."""
    usps_list = [u.strip() for u in (usps or "").split(",") if u.strip()]
    usps_lines = "\n".join([f"- {u}" for u in usps_list]) if usps_list else "- Family-friendly\n- Good connectivity\n- Value pricing"
    md = (
f"# {project} — {location} | {unitmix}\n\n"
f"**Preview:** 🏡 Discover **{project}** by {developer} — modern {unitmix} with family-friendly amenities. {price_hint}.\n\n"
"---\n\n"
"## Introduction\n\n"
f"{developer} presents {project}, a thoughtfully designed residential project in {location}. The project focuses on comfortable living, modern specifications and community-focused amenities.\n\n"
"---\n\n"
"## Project highlights / key features\n\n"
f"{usps_lines}\n- **Unit mix:** {unitmix}\n- **Possession:** {possession}\n\n"
"---\n\n"
"## Location advantages\n\n"
"- Close to schools, hospitals and retail.\n- Excellent road connectivity to major IT and commercial hubs.\n\n"
"---\n\n"
"## Premium specifications\n\n"
"- RCC framed structure, vitrified floors, branded CP fittings, granite kitchen counters.\n\n"
"---\n\n"
"## Amenities\n\n"
"- 🏊 Swimming pool\n- 🏋️ Gym\n- 🧒 Children’s play area\n- 🪑 Clubhouse\n\n"
"---\n\n"
"## About the developer\n\n"
f"**{developer}** — regional developer focusing on timely delivery and value-driven residential projects. Verify RERA and completed projects before booking.\n\n"
"---\n\n"
"## Contact information / Call to action\n\n"
f"**Call:** {phone}  \n**Email:** {email}  \n**WhatsApp:** https://wa.me/{phone}?text={quote_plus(f'Hi I am interested in {project}')}\n\n"
"---\n\n"
"## FAQ\n\n"
"**Q: Where is the project located?**  \nA: In the specified location; check developer for exact GPS pin.\n\n"
"**Q: What are typical unit sizes and price range?**  \nA: Contact sales for the latest price list.\n\n"
"**Q: Is the project RERA registered?**  \nA: Verify RERA number with developer.\n\n"
"**Q: What payment plans are available?**  \nA: Contact sales for current schemes.\n\n"
"**Q: Are there any offers?**  \nA: Offers change frequently; check with sales.\n\n"
"---\n\n"
f"**Meta Title:** {project} — {unitmix} in {location} | {developer}\n\n"
f"**Meta Description (150 chars):** {project} by {developer} in {location} — {unitmix}, family amenities, good connectivity.\n\n"
f"**Tags:** {project.lower().replace(' ','_')}, {location.lower().replace(' ','_')}, real_estate, {unitmix.replace(' ','_')}\n"
    )
    return md

def ask_ai_unified(prompt: str):
    """Try Gemini first, then Groq, then allow caller to fallback to local template."""
    res_gem = ask_ai_gemini(prompt)
    if res_gem and not res_gem.startswith("GEMINI_") and not res_gem.startswith("GEMINI_ERROR"):
        return res_gem

    res_groq = ask_ai_groq(prompt)
    if res_groq and not res_groq.startswith("GROQ_") and not res_groq.startswith("GROQ_ERROR"):
        return res_groq

    # Both failed
    err = f"ERROR_BOTH_PROVIDERS: Gemini-> {res_gem} | Groq-> {res_groq}"
    st.session_state.last_ai_error = err
    return err

# -------------------------
# Cloud upload helpers (S3/GCS)
# -------------------------
def upload_to_s3(bytes_data: bytes, bucket: str, object_name: str, region: str, access_key: str, secret_key: str) -> str:
    if not BOTO3_AVAILABLE:
        raise RuntimeError("boto3 not available")
    s3 = boto3.client("s3", region_name=region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    s3.put_object(Bucket=bucket, Key=object_name, Body=bytes_data, ACL="public-read", ContentType="image/jpeg")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{object_name}"

def upload_to_gcs(bytes_data: bytes, bucket_name: str, object_name: str, credentials_json: dict) -> str:
    if not GCS_AVAILABLE:
        raise RuntimeError("gcs lib not available")
    credentials = service_account.Credentials.from_service_account_info(credentials_json)
    client = gcs_storage.Client(credentials=credentials, project=credentials.project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(bytes_data, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url
# app.py — chunk 2 of 4
"""
Main layout: Header + Tabs 1-5
"""

# Helper: background card renderer
def render_bg_section(page_name: str, inner_html: str):
    bg = st.session_state.bg_images.get(page_name, "")
    style = f"background-image: url('{bg}');" if bg else "background: linear-gradient(180deg,#f8fafc,#e9eef6);"
    st.markdown(f"<div class='bg-section' style=\"{style}\"><div class='content-box'>{inner_html}</div></div>", unsafe_allow_html=True)

# ADMIN PANEL: sidebar (only visible to admin after login)
with st.sidebar:
    st.header("Admin Panel")
    st.caption("Only visible after admin login for this session.")
    # Keys: admin can paste keys here (overrides embedded)
    api_in = st.text_input("Google Gemini Key (optional, admin)", type="password", value=st.session_state.api_key or "", key="admin_google_key")
    if api_in and api_in != st.session_state.api_key:
        st.session_state.api_key = api_in
        mn = try_connect_google(st.session_state.api_key)
        if mn:
            st.session_state.model_name = mn
            st.success("Google model discovered: " + mn)
        else:
            st.warning("Google key saved — model discovery returned none or key lacks perms.")
    groq_in = st.text_input("Groq Key (optional, admin)", type="password", value=st.session_state.groq_api_key or "", key="admin_groq_key")
    if groq_in and groq_in != st.session_state.groq_api_key:
        st.session_state.groq_api_key = groq_in
        st.success("Groq key saved for session.")

    st.markdown("---")
    st.subheader("Page backgrounds")
    st.write("Upload background images per tab (optional). Recommended 1200×700.")
    page_keys = ["Landing", "Content", "Images", "Calendar", "Utilities", "Blog", "Uploads", "Zoho"]
    for p in page_keys:
        uploaded = st.file_uploader(f"{p} background", type=["jpg","jpeg","png"], key=f"admin_bg_{p}")
        if uploaded:
            data = uploaded.read()
            b64 = base64.b64encode(data).decode()
            mime = uploaded.type or "image/jpeg"
            st.session_state.bg_images[p] = f"data:{mime};base64,{b64}"
            st.success(f"{p} background saved for session.")

    st.markdown("---")
    st.subheader("Cloud upload settings (optional)")
    st.session_state.s3_access_key = st.text_input("S3 Access Key", value=st.session_state.s3_access_key or "", key="admin_s3_key")
    st.session_state.s3_secret_key = st.text_input("S3 Secret Key", type="password", value=st.session_state.s3_secret_key or "", key="admin_s3_secret")
    st.session_state.s3_region = st.text_input("S3 Region", value=st.session_state.s3_region or "", key="admin_s3_region")
    st.session_state.s3_bucket = st.text_input("S3 Bucket name", value=st.session_state.s3_bucket or "", key="admin_s3_bucket")

    st.markdown("**GCS Service Account JSON** (paste full JSON if using GCS)")
    gcs_text = st.text_area("GCS JSON", key="admin_gcs_json")
    if gcs_text:
        try:
            parsed = json.loads(gcs_text)
            st.session_state.gcs_credentials_json = parsed
            st.success("GCS credentials saved for session.")
        except Exception:
            st.warning("Invalid JSON — paste full service account JSON.")

    st.markdown("---")
    if st.button("Logout (admin)", key="admin_logout"):
        st.session_state.clear()
        st.rerun()

# -------------------------
# ADMIN LOGIN SCREEN (if not logged_in)
# -------------------------
if not st.session_state.logged_in:
    st.markdown("<div style='max-width:900px;margin:20px auto;'>", unsafe_allow_html=True)
    st.markdown("<h2>🔐 KonnectOps Admin Login</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Only administrators may access API keys and features.</p>", unsafe_allow_html=True)

    u = st.text_input("Username", key="login_username")
    p = st.text_input("Password", type="password", key="login_password")

    col_a, col_b = st.columns([1,1])
    with col_a:
        if st.button("Login", key="login_button"):
            if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                # If embedded keys present, activate them
                if GOOGLE_API_KEY:
                    st.session_state.api_key = GOOGLE_API_KEY
                    mn = try_connect_google(st.session_state.api_key)
                    if mn:
                        st.session_state.model_name = mn
                if GROQ_API_KEY:
                    st.session_state.groq_api_key = GROQ_API_KEY
                st.success("Login successful — API providers activated (if keys configured).")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Invalid username or password.")
    with col_b:
        st.write("If you didn't embed keys, paste them on the left Admin Panel after login.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# -------------------------
# MAIN HEADER
# -------------------------
st.markdown("<div style='padding:12px 18px'><span style='font-size:20px;color:#002D62;font-weight:700;'>KonnectOps Mobile</span></div>", unsafe_allow_html=True)

# -------------------------
# TABS (Main) - also includes Blog/Uploads/Zoho placeholders
# -------------------------
tabs = st.tabs(["📄 Landing", "✍️ Content", "🎨 Images", "📅 Calendar", "🛠️ Utilities", "📝 Blog", "☁️ Uploads", "👨‍💻 Zoho"])

# -------------------------
# TAB: Landing
# -------------------------
with tabs[0]:
    render_bg_section("Landing", "<div class='hero-title'><h1>Developer Console — Landing Page Generator</h1><p class='subtitle'>Quickly replace names and generate SEO-ready HTML with preview and download.</p></div>")
    c1, c2 = st.columns(2)
    with c1:
        proj = st.text_input("Project Name", value="TVS Emerald", key="landing_proj")
        loc = st.text_input("Location", value="Porur", key="landing_loc")
        price = st.text_input("Price", value="85L", key="landing_price")
    with c2:
        old_txt = st.text_input("Old Name (to replace)", value="Casagrand Flagship", key="landing_old")
        html_input = st.text_area("Paste HTML Template (use {PRICE}, {LOCATION}, {DESC})", height=200, key="landing_html")
    if st.button("Generate Landing Page", key="landing_generate"):
        if not html_input:
            st.warning("Paste your HTML first.")
        else:
            res = html_input.replace(old_txt or "", proj or "").replace("{PRICE}", price or "").replace("{LOCATION}", loc or "")
            if "{DESC}" in res:
                seo = ask_ai_unified(f"Write 150 char SEO description for {proj} in {loc}.")
                if seo and not seo.startswith("ERROR"):
                    res = res.replace("{DESC}", seo)
                else:
                    res = res.replace("{DESC}", f"{proj} in {loc} - premium homes.")
            try:
                st.markdown("### Preview")
                components.html(res, height=420, scrolling=True)
            except Exception:
                st.warning("Preview may not render on this platform. Download to view.")
            st.download_button("Download HTML", data=res, file_name=f"{(proj or 'page').replace(' ','_')}.html", mime="text/html", key="landing_download")

# -------------------------
# TAB: Content
# -------------------------
with tabs[1]:
    render_bg_section("Content", "<div class='hero-title'><h1>Marketing Studio</h1><p class='subtitle'>Human-friendly marketing drafts — blog, social, email.</p></div>")
    ctype = st.selectbox("Content Type", ["Blog Post", "Instagram Carousel", "LinkedIn Post", "Client Email"], key="content_type")
    topic = st.text_input("Topic", value="Why invest in OMR?", key="content_topic")
    tone = st.selectbox("Tone", ["Professional", "Conversational", "Persuasive"], index=1, key="content_tone")
    if st.button("Draft Content", key="content_generate"):
        if not topic.strip():
            st.warning("Enter a topic.")
        else:
            with st.spinner("Writing..."):
                prompt = f"Act as a Senior Marketing Manager. Write a professional {ctype} in a {tone.lower()} tone about: {topic}."
                out = ask_ai_unified(prompt)
            if out.startswith("ERROR_BOTH_PROVIDERS") or out.startswith("ERROR"):
                st.error("AI providers failed. Showing fallback sample.")
                sample = local_homekonnect_blog(project="Sample Project", location="Location", developer="Dev", unitmix="2 & 3 BHK", usps="Family-friendly, Connectivity", price_hint="", possession="", phone="919876543210", email="sales@example.com")
                st.code(sample, language="markdown")
            else:
                st.code(out, language="text")

# -------------------------
# TAB: Images
# -------------------------
with tabs[2]:
    render_bg_section("Images", "<div class='hero-title'><h1>Image Prompt Studio</h1><p class='subtitle'>Generate detailed prompts for Midjourney / DALL·E / SD.</p></div>")
    desc = st.text_input("Image Concept", value="Luxury living room with sea view", key="img_desc")
    style = st.selectbox("Style", ["Photorealistic 8k", "Architectural render", "Lifestyle"], key="img_style")
    if st.button("Generate Prompt", key="img_generate"):
        if not desc.strip():
            st.warning("Enter an image concept.")
        else:
            prompt = f"Write a detailed Midjourney prompt for: {desc}. Style: {style}. Photorealistic, high detail."
            out = ask_ai_unified(prompt)
            if out.startswith("ERROR_BOTH_PROVIDERS") or out.startswith("ERROR"):
                st.error("AI providers failed. Please try again later or use the prompt template manually.")
            else:
                st.code(out, language="text")

# -------------------------
# TAB: Calendar
# -------------------------
with tabs[3]:
    render_bg_section("Calendar", "<div class='hero-title'><h1>2026 Festivals</h1><p class='subtitle'>Plan campaigns around key dates.</p></div>")
    data = {
        "Date": ["Jan 14","Jan 26","Mar 04","Mar 20","Apr 14","Aug 15","Aug 26","Sep 14","Oct 20","Nov 08","Dec 25"],
        "Festival": ["Pongal","Republic Day","Holi","Ramzan","Tamil New Year","Independence Day","Onam","Ganesh Chaturthi","Ayudha Puja","Diwali","Christmas"]
    }
    st.table(pd.DataFrame(data))

# -------------------------
# TAB: Utilities
# -------------------------
with tabs[4]:
    render_bg_section("Utilities", "<div class='hero-title'><h1>Sales Utilities</h1><p class='subtitle'>WhatsApp links, EMI calculator, translations.</p></div>")
    tool = st.radio("Select Tool", ["WhatsApp Link Generator", "EMI Calculator", "Tamil Translator"], key="util_tool")
    if tool == "WhatsApp Link Generator":
        wa_num = st.text_input("Phone Number (with country code)", value="919876543210", key="wa_num")
        wa_msg = st.text_input("Message", value="Hi, I am interested in the OMR project.", key="wa_msg")
        if st.button("Create WhatsApp Link", key="wa_create"):
            if not wa_num.strip():
                st.warning("Enter phone number.")
            else:
                link = f"https://wa.me/{wa_num.strip()}?text={quote_plus(wa_msg)}"
                st.code(link)
                st.markdown(f"[Open Link]({link})")
    elif tool == "EMI Calculator":
        loan = st.number_input("Loan Amount (₹)", value=5_000_000, min_value=0, key="emi_loan")
        rate = st.number_input("Interest Rate (%)", value=8.5, min_value=0.0, key="emi_rate", format="%.3f")
        years = st.number_input("Tenure (Years)", value=20, min_value=1, key="emi_years")
        if st.button("Calculate EMI", key="emi_calc"):
            r = rate / (12 * 100)
            n = int(years * 12)
            emi = loan * r * ((1 + r) ** n) / (((1 + r) ** n) - 1) if r > 0 else loan / n
            st.success(f"Monthly EMI: ₹ {int(round(emi)):,}")
    else:
        txt = st.text_area("Enter English text to translate", value="Exclusive launch offer ending soon.", key="trans_text")
        if st.button("Translate to Tamil", key="trans_button"):
            out = ask_ai_unified(f"Translate this real estate text to professional Tamil: '{txt}'")
            if out.startswith("ERROR_BOTH_PROVIDERS") or out.startswith("ERROR"):
                st.error("Translation failed via AI providers. Please translate manually.")
            else:
                st.code(out, language="text")
# app.py — chunk 3 of 4
"""
Blog tab + Uploads + Zoho
"""

# -------------------------
# Tab: Blog (Home Konnect generator)
# -------------------------
with tabs[5]:
    render_bg_section("Blog", "<div class='hero-title'><h1>Home Konnect Blog Generator</h1><p class='subtitle'>Produce copy-paste markdown and cover prompts/images.</p></div>")

    b_col1, b_col2 = st.columns([2,1])
    with b_col1:
        b_project = st.text_input("Project Name", value="DRA Beena Clover", key="blog_project")
        b_location = st.text_input("Location (area, city)", value="Madambakkam (Near Selaiyur & East Tambaram)", key="blog_location")
        b_developer = st.text_input("Developer", value="DRA Housing", key="blog_developer")
        b_unitmix = st.text_input("Unit mix", value="2 BHK, 3 BHK", key="blog_unitmix")
        b_usps = st.text_area("Top 4 USPs (comma separated)", value="Close to Selaiyur, Family-friendly amenities, Value pricing, Good connectivity", key="blog_usps")
    with b_col2:
        b_price = st.text_input("Price hint", value="Starts from 45L", key="blog_price")
        b_poss = st.text_input("Possession", value="Check developer brochure", key="blog_poss")
        b_phone = st.text_input("Sales phone", value="919876543210", key="blog_phone")
        b_email = st.text_input("Sales email", value="sales@draexample.com", key="blog_email")
        cover_style = st.selectbox("Cover image style", ["Photorealistic exterior (golden hour)", "Lifestyle (residents silhouettes)", "Architectural render clean look"], key="cover_style")

    if st.button("Generate Blog (Home Konnect markdown)", key="blog_generate"):
        prompt = (
            "You are a professional real estate content writer. Produce a copy-paste ready markdown blog post following the Home Konnect blog structure EXACTLY:\n"
            "- Title (include project name, location and a USP)\n"
            "- Preview paragraph (short intro with emojis)\n"
            "- Introduction (developer & what makes the project special)\n"
            "- Project highlights / key features (H2, bullet points with emojis, unit sizes, USPs, nearby landmarks)\n"
            "- Location advantages (H2, proximity to IT hubs, schools, hospitals, transport)\n"
            "- Premium specifications (H2, floor plans, interiors, fittings, smart features)\n"
            "- Amenities (H2, listed with emojis)\n"
            "- About the developer (H2, reputation, years, notable projects, RERA check note)\n"
            "- Contact information / call to action (H2, phone clickable, whatsapp quick link, email)\n"
            "- FAQ section (H2, 5 common Q&A)\n"
            "- SEO Meta Title & Description (150 chars)\n"
            "- Tags (comma-separated, lower case)\n\n"
            f"Project name: {b_project}\n"
            f"Location: {b_location}\n"
            f"Developer: {b_developer}\n"
            f"Unit mix: {b_unitmix}\n"
            f"USPs: {b_usps}\n"
            f"Price hint: {b_price}\n"
            f"Possession: {b_poss}\n"
            f"Contact phone: {b_phone}\n"
            f"Contact email: {b_email}\n\n"
            "Tone: Helpful, local-market-savvy, professional, friendly.\n"
            "Length: long-form (~1200-1600 words), headings clear for scanning.\n"
            "Return ONLY the markdown content (no commentary)."
        )
        with st.spinner("Drafting blog..."):
            blog_md = ask_ai_unified(prompt)
        if blog_md.startswith("ERROR_BOTH_PROVIDERS") or blog_md.startswith("ERROR"):
            st.error("AI providers failed. Showing fallback blog you can copy-paste. To permanently fix, configure API keys or enable billing.")
            fallback_md = local_homekonnect_blog(
                project=b_project or "Project",
                location=b_location or "Location",
                developer=b_developer or "Developer",
                unitmix=b_unitmix or "2 & 3 BHK",
                usps=b_usps or "Family-friendly amenities, Good connectivity",
                price_hint=b_price or "Check price",
                possession=b_poss or "TBD",
                phone=b_phone or "919876543210",
                email=b_email or "sales@example.com"
            )
            st.code(fallback_md, language="markdown")
            st.download_button("Download fallback blog (md)", data=fallback_md, file_name=f"{(b_project or 'project').replace(' ','_')}_fallback_blog.md", mime="text/markdown", key="download_fallback_blog")
        else:
            st.markdown("**Generated Blog (Markdown)** — copy-paste ready:")
            st.code(blog_md, language="markdown")
            st.download_button("Download Blog (Markdown)", data=blog_md, file_name=f"{b_project.replace(' ','_')}_blog.md", mime="text/markdown", key="download_blog_md")

    # Cover prompt + generation
    st.markdown("---")
    usps_list = [u.strip() for u in b_usps.split(",") if u.strip()]
    usps_short = "; ".join(usps_list[:4])
    image_prompt_text = (
        f"Blog cover image for a real estate project named '{b_project}' located in {b_location}. "
        f"Style: {cover_style}. Modern mid-rise apartment exterior at golden hour, landscaped foreground with families (silhouettes), "
        f"soft city background, clean space for title/logo overlay, subtle 'Home Konnect' watermark bottom-right, cinematic composition, vibrant yet natural colors, no recognizable faces, 1200x628. Include props that suggest: {usps_short}."
    )
    st.subheader("Cover Image Prompt")
    st.code(image_prompt_text, language="text")
    if st.button("Copy Prompt (manually)", key="copy_prompt"):
        st.write("Please copy the prompt from the box above and paste into your image generator (clipboard not available via server).")

    if st.button("Try Generate Cover Image (auto)", key="gen_cover_auto"):
        with st.spinner("Attempting image generation..."):
            img_bytes = generate_cover_image_via_genai(image_prompt_text, size="1200x628")
            if img_bytes:
                st.image(img_bytes, width=700, caption="Generated cover image")
                st.session_state._last_cover_bytes = img_bytes
                st.download_button("Download generated cover", data=img_bytes, file_name=f"{b_project.replace(' ','_')}_cover.jpg", mime="image/jpeg", key="download_generated_cover")
            else:
                st.warning("Automatic image generation not available. Use the prompt above in Midjourney / DALL·E / SD or upload an image below.")

    st.markdown("**Or upload your own cover image (JPEG / PNG)**")
    uploaded = st.file_uploader("Upload cover image", type=["jpg","jpeg","png"], key="blog_upload_cover")
    if uploaded:
        data = uploaded.read()
        st.image(data, width=700, caption="Uploaded cover image")
        st.session_state._last_cover_bytes = data
        st.success("Cover image loaded into session. Use the Uploads tab to push to cloud storage.")

# -------------------------
# Tab: Uploads (Cloud)
# -------------------------
with tabs[6]:
    render_bg_section("Uploads", "<div class='hero-title'><h1>Uploads</h1><p class='subtitle'>Upload the last generated/uploaded cover image to S3 or GCS for a public URL.</p></div>")
    if not st.session_state._last_cover_bytes:
        st.info("No cover image in session. Generate or upload an image in the Blog tab.")
    else:
        st.image(st.session_state._last_cover_bytes, width=600, caption="Selected image ready for upload")
        dest = st.selectbox("Upload destination", ["None", "AWS S3", "Google Cloud Storage"], key="uploads_dest")
        if dest == "AWS S3":
            if not BOTO3_AVAILABLE:
                st.error("boto3 not installed. Install to enable S3 uploads.")
            else:
                s3_bucket = st.text_input("S3 Bucket", value=st.session_state.s3_bucket or "", key="uploads_s3_bucket")
                s3_region = st.text_input("S3 Region", value=st.session_state.s3_region or "", key="uploads_s3_region")
                s3_key = st.text_input("S3 object key (e.g., blog/covers/mycover.jpg)", value=f"blog_covers/{int(time.time())}_{(b_project or 'project').replace(' ','_')}.jpg", key="uploads_s3_key")
                if st.button("Upload to S3", key="upload_to_s3"):
                    try:
                        access = st.session_state.s3_access_key
                        secret = st.session_state.s3_secret_key
                        url = upload_to_s3(st.session_state._last_cover_bytes, s3_bucket, s3_key, s3_region, access, secret)
                        st.success("Uploaded to S3.")
                        st.write("Public URL:", url)
                    except Exception as e:
                        st.error(f"S3 upload failed: {e}")
        elif dest == "Google Cloud Storage":
            if not GCS_AVAILABLE:
                st.error("google-cloud-storage not installed. Install it to enable GCS uploads.")
            else:
                gcs_bucket = st.text_input("GCS Bucket", key="uploads_gcs_bucket")
                gcs_key = st.text_input("GCS object name", value=f"blog_covers/{int(time.time())}_{(b_project or 'project').replace(' ','_')}.jpg", key="uploads_gcs_key")
                if st.button("Upload to GCS", key="upload_to_gcs"):
                    try:
                        credentials_json = st.session_state.gcs_credentials_json
                        if not credentials_json:
                            st.error("GCS credentials not provided in admin sidebar.")
                        else:
                            url = upload_to_gcs(st.session_state._last_cover_bytes, gcs_bucket, gcs_key, credentials_json)
                            st.success("Uploaded to GCS.")
                            st.write("Public URL:", url)
                    except Exception as e:
                        st.error(f"GCS upload failed: {e}")

# -------------------------
# Tab: Zoho Deluge
# -------------------------
with tabs[7]:
    render_bg_section("Zoho", "<div class='hero-title'><h1>Zoho Deluge Scripting</h1><p class='subtitle'>Generate Deluge scripts for Zoho CRM automations.</p></div>")
    req = st.text_area("Logic Needed (describe in plain English)", key="zoho_req_area")
    if st.button("Compile Code", key="zoho_compile"):
        if not req.strip():
            st.warning("Enter the logic.")
        else:
            with st.spinner("Writing Deluge script..."):
                out = ask_ai_unified(f"Write Zoho Deluge script: {req}")
            if out.startswith("ERROR_BOTH_PROVIDERS") or out.startswith("ERROR"):
                st.error("AI providers failed. Please try again later.")
            else:
                st.code(out, language="java")
# app.py — chunk 4 of 4
"""
Diagnostics, footer, and finalization.
"""

st.markdown("---")
with st.expander("Diagnostics & last AI error", expanded=False):
    st.write("Logged in (admin):", st.session_state.logged_in)
    st.write("Google model:", st.session_state.model_name)
    st.write("Available models (sample):", st.session_state.available_models[:10])
    if st.session_state.last_ai_error:
        st.error("Last AI error:")
        st.write(st.session_state.last_ai_error)
    st.write("Session backgrounds keys:", list(st.session_state.bg_images.keys()))
    if st.session_state._last_cover_bytes:
        st.write("Cover image in session memory is available.")

st.markdown("</div>", unsafe_allow_html=True)

# -------------------------
# Quick usage note printed in app (non-essential)
# -------------------------
st.sidebar.markdown("**KonnectOps — Ready**  \nAdmin panel available. Use admin credentials to login and paste API keys if not embedded.")
