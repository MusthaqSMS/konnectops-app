# app.py (chunk 1 of 4)
"""
KonnectOps Mobile — Full app (chunk 1 of 4)
Paste chunk 1, then 2, then 3, then 4 into a single app.py
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
import json
import os
from io import BytesIO
from typing import Optional

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

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("konnectops")

# Page config
st.set_page_config(page_title="KonnectOps Mobile", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")

# CSS - professional UI; content boxes ensure readability
st.markdown("""
<style>
.konnectops-root { font-family: "Segoe UI", sans-serif; color: #0b1720; }
.bg-section { min-height: 560px; background-position: center; background-size: cover; position: relative; padding: 36px 48px; }
.bg-section::before { content:''; position:absolute; inset:0; background: linear-gradient(180deg, rgba(6,18,33,0.18), rgba(255,255,255,0.02)); backdrop-filter: blur(2px); z-index:0; }
.content-box { position:relative; z-index:2; max-width:1200px; margin:auto; background: rgba(255,255,255,0.96); border-radius:12px; padding:22px; box-shadow:0 10px 40px rgba(2,12,34,0.08); }
.hero-title h1 { margin:0; color:#002D62; font-size:28px; }
.subtitle { color:#334155; margin-top:6px; font-size:14px; }
.stButton > button { background:#002D62 !important; color:#fff !important; border-radius:8px; padding:10px 14px; font-weight:600; }
@media (max-width:760px) { .bg-section { padding:18px 12px; } .content-box{ padding:16px; } .hero-title h1{ font-size:20px; } }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="konnectops-root">', unsafe_allow_html=True)

# Session state defaults
if "api_key" not in st.session_state: st.session_state.api_key = ""
if "model_name" not in st.session_state: st.session_state.model_name = None
if "available_models" not in st.session_state: st.session_state.available_models = []
if "bg_images" not in st.session_state: st.session_state.bg_images = {}
if "_last_cover_bytes" not in st.session_state: st.session_state._last_cover_bytes = None
if "gcs_credentials_json" not in st.session_state: st.session_state.gcs_credentials_json = None

# Cached model fetcher
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

def try_connect(key: str) -> Optional[str]:
    if not key:
        return None
    try:
        models = fetch_models_for_key(key)
    except Exception as e:
        logger.exception("Model discovery failed: %s", e)
        return None
    # pick first supporting model
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
        name = safe_name(models[0])
        st.session_state.available_models = [safe_name(x) for x in models if safe_name(x)]
        return name
    return None

def ask_ai(prompt: str) -> str:
    if not st.session_state.get("model_name"):
        return "Error: Offline (no model configured)."
    try:
        genai.configure(api_key=st.session_state.api_key)
        model = genai.GenerativeModel(st.session_state.model_name)
        out = model.generate_content(prompt)
        text = getattr(out, "text", None)
        if not text and isinstance(out, dict):
            text = out.get("text") or str(out)
        return text or str(out)
    except Exception as e:
        logger.exception("AI call failed: %s", e)
        st.session_state.last_ai_error = str(e)
        return f"Error: {e}"

# Image generation best-effort
def generate_cover_image_via_genai(prompt: str, size: str = "1200x628") -> Optional[bytes]:
    try:
        if hasattr(genai, "images") and hasattr(genai.images, "generate"):
            resp = genai.images.generate(model="image-alpha-001", prompt=prompt, size=size)
            b64 = None
            if hasattr(resp, "data"):
                item = resp.data[0]
                b64 = getattr(item, "b64_json", None) or (item.get("b64_json") if isinstance(item, dict) else None)
            elif isinstance(resp, list) and resp:
                item = resp[0]
                b64 = getattr(item, "b64_json", None) or (item.get("b64_json") if isinstance(item, dict) else None)
            else:
                b64 = getattr(resp, "b64_json", None) or (resp.get("b64_json") if isinstance(resp, dict) else None)
            if b64:
                return base64.b64decode(b64)
            return None
        return None
    except Exception as e:
        logger.warning("Image generation failed: %s", e)
        return None

# Cloud upload helpers
def upload_to_s3(bytes_data: bytes, bucket: str, object_name: str, region: str, access_key: str, secret_key: str) -> str:
    if not BOTO3_AVAILABLE:
        raise RuntimeError("boto3 not installed.")
    s3 = boto3.client("s3", region_name=region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    s3.put_object(Bucket=bucket, Key=object_name, Body=bytes_data, ACL="public-read", ContentType="image/jpeg")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{object_name}"

def upload_to_gcs(bytes_data: bytes, bucket_name: str, object_name: str, credentials_json: dict) -> str:
    if not GCS_AVAILABLE:
        raise RuntimeError("google-cloud-storage not installed.")
    credentials = service_account.Credentials.from_service_account_info(credentials_json)
    client = gcs_storage.Client(credentials=credentials, project=credentials.project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(bytes_data, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url

# Sidebar - API key + backgrounds + cloud config
with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Paste your Generative AI key (kept only for session).")
    api_key_input = st.text_input("Generative AI Key", type="password", value=st.session_state.api_key, key="sid_api_key")
    if api_key_input and api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        try:
            fetch_models_for_key.cache_clear()
        except Exception:
            pass

    st.markdown("---")
    st.subheader("Page backgrounds")
    st.write("Upload background images per tab (optional). Recommended 1200×700.")
    page_keys = ["Landing", "Content", "Images", "Calendar", "Utilities", "Blog", "Uploads", "Zoho"]
    for p in page_keys:
        uploaded = st.file_uploader(f"{p} background", type=["jpg","jpeg","png"], key=f"sid_bg_{p}")
        if uploaded:
            data = uploaded.read()
            b64 = base64.b64encode(data).decode()
            mime = uploaded.type or "image/jpeg"
            st.session_state.bg_images[p] = f"data:{mime};base64,{b64}"
            st.success(f"{p} background saved for session.")

    st.markdown("---")
    st.subheader("S3 / GCS (optional) for cover images")
    st.write("Provide either S3 or GCS details to enable direct upload from app.")
    st.text_input("S3 Access Key", key="sid_s3_access_key", value=st.session_state.get("s3_access_key",""))
    st.text_input("S3 Secret Key", type="password", key="sid_s3_secret_key", value=st.session_state.get("s3_secret_key",""))
    st.text_input("S3 Region", key="sid_s3_region", value=st.session_state.get("s3_region",""))
    st.text_input("S3 Bucket", key="sid_s3_bucket", value=st.session_state.get("s3_bucket",""))

    st.markdown("**GCS Service Account JSON** - paste full JSON (optional)")
    gcs_json_text = st.text_area("GCS JSON", key="sid_gcs_json")
    if gcs_json_text and (not st.session_state.gcs_credentials_json):
        try:
            parsed = json.loads(gcs_json_text)
            st.session_state.gcs_credentials_json = parsed
            st.success("GCS credentials saved for session.")
        except Exception:
            st.warning("Invalid JSON - please paste valid service account JSON.")

    st.markdown("---")
    st.write("Connected model:")
    st.write(st.session_state.model_name or "Not connected")

    if st.button("Logout / Clear", key="sid_logout"):
        st.session_state.clear()
        st.rerun()

# Attempt to connect if key present and model not configured
if st.session_state.api_key and not st.session_state.model_name:
    with st.spinner("Discovering models..."):
        model_id = try_connect(st.session_state.api_key)
        if model_id:
            st.session_state.model_name = model_id
            st.success(f"Connected: {model_id}")
            time.sleep(0.2)
            st.rerun()
        else:
            st.error("Could not connect with provided key. Please check key or network.")

# app.py (chunk 2 of 4)
"""
KonnectOps Mobile — chunk 2 of 4 (Landing / Content / Images / Calendar / Utilities)
Continue: paste after chunk 1
"""

# Helper to render a background-wrapped content card
def render_bg_section(page_name: str, inner_html: str):
    bg = st.session_state.bg_images.get(page_name, "")
    style = f"background-image: url('{bg}');" if bg else "background: linear-gradient(180deg,#f8fafc,#e9eef6);"
    st.markdown(f"<div class='bg-section' style=\"{style}\"><div class='content-box'>{inner_html}</div></div>", unsafe_allow_html=True)

# Header
st.markdown("<div style='padding:12px 20px'><span style='font-weight:700;color:#002D62;font-size:20px'>KonnectOps Mobile</span></div>", unsafe_allow_html=True)

# Tabs
tabs = st.tabs(["📄 Landing", "✍️ Content", "🎨 Images", "📅 Calendar", "🛠️ Utilities", "📝 Blog", "☁️ Uploads", "👨‍💻 Zoho"])

# === Landing Tab
with tabs[0]:
    render_bg_section("Landing", "<div class='hero-title'><h1>Developer Console — Landing Page Generator</h1><p class='subtitle'>Quickly replace names and generate SEO-ready HTML with preview and download.</p></div>")
    c1, c2 = st.columns(2)
    with c1:
        proj = st.text_input("Project Name", value="", key="landing_proj")
        loc = st.text_input("Location", value="", key="landing_loc")
        price = st.text_input("Price", value="", key="landing_price")
    with c2:
        old_txt = st.text_input("Old Name (to replace)", value="", key="landing_old")
        html_input = st.text_area("Paste HTML Template (use {PRICE}, {LOCATION}, {DESC})", height=200, key="landing_html")
    if st.button("Generate Landing Page", key="landing_generate"):
        if not html_input:
            st.warning("Paste your HTML first.")
        else:
            res = html_input.replace(old_txt or "", proj or "").replace("{PRICE}", price or "").replace("{LOCATION}", loc or "")
            if "{DESC}" in res:
                seo = ask_ai(f"Write 150 char SEO description for {proj} in {loc}.")
                if seo and not seo.lower().startswith("error"):
                    res = res.replace("{DESC}", seo)
                else:
                    res = res.replace("{DESC}", f"{proj} at {loc} - premium homes.")
            try:
                st.markdown("### Preview")
                components.html(res, height=420, scrolling=True)
            except Exception:
                st.warning("Preview may not render in some environments. You can still download the file.")
            st.download_button("Download HTML", data=res, file_name=f"{(proj or 'page').replace(' ','_')}.html", mime="text/html", key="landing_download")

# === Content Tab
with tabs[1]:
    render_bg_section("Content", "<div class='hero-title'><h1>Marketing Studio</h1><p class='subtitle'>Human-friendly marketing drafts — blog, social, email.</p></div>")
    ctype = st.selectbox("Content Type", ["Blog Post", "Instagram Carousel", "LinkedIn Post", "Client Email"], key="content_type")
    topic = st.text_input("Topic", value="", key="content_topic")
    tone = st.selectbox("Tone", ["Professional", "Conversational", "Persuasive"], index=1, key="content_tone")
    if st.button("Draft Content", key="content_generate"):
        if not topic.strip():
            st.warning("Please enter a topic.")
        else:
            with st.spinner("Writing..."):
                prompt = f"Act as a Senior Marketing Manager. Write a {ctype} in a {tone.lower()} tone about: {topic}."
                out = ask_ai(prompt)
                if out.lower().startswith("error"):
                    st.error(out)
                else:
                    st.code(out, language="text")

# === Images Tab
with tabs[2]:
    render_bg_section("Images", "<div class='hero-title'><h1>Image Prompt Studio</h1><p class='subtitle'>Generate detailed prompts for Midjourney/ DALL·E/ SD.</p></div>")
    desc = st.text_input("Image Concept", value="", key="img_desc")
    style = st.selectbox("Style", ["Photorealistic 8k", "Oil Painting", "Architectural render", "Flat vector"], key="img_style")
    if st.button("Generate Prompt", key="img_generate"):
        if not desc.strip():
            st.warning("Enter a concept.")
        else:
            prompt = f"Write a detailed image prompt for: {desc}. Style: {style}. Photorealistic, high detail."
            out = ask_ai(prompt)
            if out.lower().startswith("error"):
                st.error(out)
            else:
                st.code(out, language="text")

# === Calendar Tab
with tabs[3]:
    render_bg_section("Calendar", "<div class='hero-title'><h1>2026 Festivals</h1><p class='subtitle'>Plan campaigns around key dates.</p></div>")
    data = {"Date": ["Jan 14", "Jan 26", "Mar 04", "Mar 20", "Apr 14", "Aug 15", "Aug 26", "Sep 14", "Oct 20", "Nov 08", "Dec 25"],
            "Festival": ["Pongal", "Republic Day", "Holi", "Ramzan", "Tamil New Year", "Independence Day", "Onam", "Ganesh Chaturthi", "Ayudha Puja", "Diwali", "Christmas"]}
    st.table(pd.DataFrame(data))

# === Utilities Tab
with tabs[4]:
    render_bg_section("Utilities", "<div class='hero-title'><h1>Sales Utilities</h1><p class='subtitle'>WhatsApp links, EMI calc, translations.</p></div>")
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
        txt = st.text_area("Enter English text", value="Exclusive launch offer ending soon.", key="trans_text")
        if st.button("Translate to Tamil", key="trans_button"):
            out = ask_ai(f"Translate this real estate text to professional Tamil: '{txt}'")
            if out.lower().startswith("error"):
                st.error(out)
            else:
                st.code(out, language="text")

# app.py (chunk 3 of 4)
"""
KonnectOps Mobile — chunk 3 of 4 (Blog, Cover generation, Uploads)
"""

# === Blog Tab
with tabs[5]:
    render_bg_section("Blog", "<div class='hero-title'><h1>Home Konnect Blog Generator</h1><p class='subtitle'>Produce copy-paste markdown in Home Konnect format and generate cover prompts/images.</p></div>")

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
        # build prompt safely (no triple-quoted f-string)
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
            blog_md = ask_ai(prompt)
        if blog_md.lower().startswith("error"):
            st.error(blog_md)
        else:
            st.markdown("**Generated Blog (Markdown)** — copy-paste ready:")
            st.code(blog_md, language="markdown")
            blog_filename = f"{b_project.replace(' ','_')}_homekonnect_blog.md"
            st.download_button("Download Blog (Markdown)", data=blog_md, file_name=blog_filename, mime="text/markdown", key="download_blog_md")

    st.markdown("---")
    st.subheader("Cover Image — Prompt & Auto-generate")

    usps_list = [u.strip() for u in b_usps.split(",") if u.strip()]
    usps_short = "; ".join(usps_list[:4])
    image_prompt_text = (
        f"Blog cover image for a real estate project named '{b_project}' located in {b_location}. "
        f"Style: {cover_style}. Modern mid-rise apartment exterior at golden hour, landscaped foreground with families (silhouettes), "
        f"soft city background, clean space for title/logo overlay, subtle 'Home Konnect' watermark bottom-right, cinematic composition, vibrant yet natural colors, no recognizable faces, 1200x628. Include props that suggest: {usps_short}."
    )

    st.code(image_prompt_text, language="text")
    if st.button("Copy Prompt (manually)", key="copy_prompt"):
        st.write("Please copy the prompt from the box above and paste into your image generator (clipboard not available via server).")

    # Try auto-generate
    if st.button("Try Generate Cover Image (auto)", key="gen_cover_auto"):
        with st.spinner("Attempting image generation..."):
            img_bytes = generate_cover_image_via_genai(image_prompt_text, size="1200x628")
            if img_bytes:
                st.image(img_bytes, width=700, caption="Generated cover image")
                st.session_state._last_cover_bytes = img_bytes
                st.download_button("Download generated cover", data=img_bytes, file_name=f"{b_project.replace(' ','_')}_cover.jpg", mime="image/jpeg", key="download_auto_cover")
            else:
                st.warning("Automatic image generation not available in this environment. Use the prompt above in Midjourney / DALL·E / SD or upload an image below.")

    st.markdown("**Or upload your own cover image (JPEG / PNG)**")
    uploaded = st.file_uploader("Upload cover image", type=["jpg","jpeg","png"], key="upload_cover")
    if uploaded:
        data = uploaded.read()
        st.image(data, width=700, caption="Uploaded cover image")
        st.session_state._last_cover_bytes = data
        st.success("Cover image loaded into session. You can now upload it to cloud from Uploads tab.")

# === Uploads Tab (cloud uploads)
with tabs[6]:
    render_bg_section("Uploads", "<div class='hero-title'><h1>Uploads</h1><p class='subtitle'>Upload the last generated/ uploaded cover image to S3 or GCS for a public URL.</p></div>")
    if not st.session_state._last_cover_bytes:
        st.info("No cover image in session. Generate or upload an image in the Blog tab.")
    else:
        st.image(st.session_state._last_cover_bytes, width=600, caption="Selected image ready for upload")
        dest = st.selectbox("Upload destination", ["None", "AWS S3", "Google Cloud Storage"], key="upload_dest")
        if dest == "AWS S3":
            if not BOTO3_AVAILABLE:
                st.error("boto3 not installed in this environment. Install boto3 to use S3 uploads.")
            else:
                s3_bucket = st.text_input("S3 Bucket", key="upload_s3_bucket", value=st.session_state.get("sid_s3_bucket",""))
                s3_region = st.text_input("S3 Region", key="upload_s3_region", value=st.session_state.get("sid_s3_region",""))
                s3_key = st.text_input("S3 object key (e.g., blog/covers/mycover.jpg)", value=f"blog_covers/{int(time.time())}_{b_project.replace(' ','_')}.jpg", key="upload_s3_key")
                if st.button("Upload to S3", key="upload_s3_button"):
                    try:
                        access = st.session_state.get("sid_s3_access_key", "")
                        secret = st.session_state.get("sid_s3_secret_key", "")
                        url = upload_to_s3(st.session_state._last_cover_bytes, s3_bucket, s3_key, s3_region, access, secret)
                        st.success("Uploaded to S3.")
                        st.write("Public URL:", url)
                    except Exception as e:
                        st.error(f"S3 upload failed: {e}")
        elif dest == "Google Cloud Storage":
            if not GCS_AVAILABLE:
                st.error("google-cloud-storage not installed in this environment.")
            else:
                gcs_bucket = st.text_input("GCS Bucket", key="upload_gcs_bucket")
                gcs_key = st.text_input("GCS object name (e.g., blog/covers/mycover.jpg)", value=f"blog_covers/{int(time.time())}_{b_project.replace(' ','_')}.jpg", key="upload_gcs_key")
                if st.button("Upload to GCS", key="upload_gcs_button"):
                    try:
                        if not st.session_state.gcs_credentials_json:
                            st.error("GCS credentials JSON not found in sidebar. Paste service account JSON there.")
                        else:
                            url = upload_to_gcs(st.session_state._last_cover_bytes, gcs_bucket, gcs_key, st.session_state.gcs_credentials_json)
                            st.success("Uploaded to GCS.")
                            st.write("Public URL:", url)
                    except Exception as e:
                        st.error(f"GCS upload failed: {e}")
        else:
            st.info("Select an upload destination to proceed (S3 or GCS).")

# === Zoho Tab (part: Deluge script generator)
with tabs[7]:
    render_bg_section("Zoho", "<div class='hero-title'><h1>Zoho Deluge Scripting</h1><p class='subtitle'>Generate Deluge scripts for Zoho automations.</p></div>")
    req = st.text_area("Logic required (describe in plain English)", key="zoho_req")
    if st.button("Compile Deluge Script", key="zoho_compile"):
        if not req.strip():
            st.warning("Describe the logic you want.")
        else:
            with st.spinner("Generating Deluge script..."):
                out = ask_ai(f"Write Zoho Deluge script: {req}")
            if out.lower().startswith("error"):
                st.error(out)
            else:
                st.code(out, language="java")

# app.py (chunk 4 of 4)
"""
KonnectOps Mobile — chunk 4 of 4 (footer, diagnostics)
"""

st.markdown("---")

# Diagnostics (collapsed)
with st.expander("Diagnostics & last AI error", expanded=False):
    st.write("Model in session:", st.session_state.get("model_name"))
    st.write("Available models (sample):", st.session_state.get("available_models", [])[:10])
    if st.session_state.get("last_ai_error"):
        st.error("Last AI error:")
        st.write(st.session_state.last_ai_error)
    st.write("Session backgrounds:", list(st.session_state.get("bg_images", {}).keys()))
    if st.session_state._last_cover_bytes:
        st.write("There is a cover image in session memory (Uploads tab).")

# Close root div
st.markdown("</div>", unsafe_allow_html=True)
