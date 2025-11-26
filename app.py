# app.py
"""
KonnectOps Mobile — Professional UI with page backgrounds & readable content
Ready to upload to GitHub and deploy on Streamlit Cloud.

Notes:
- Paste your Google Generative AI key in the sidebar (kept only for the session).
- Optional: install boto3 / google-cloud-storage if you need S3 / GCS uploads.
- Tested for Streamlit 1.##+ and python 3.10+.
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

# Optional cloud libs (import only if available)
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

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("konnectops")

# ---------- Page config ----------
st.set_page_config(page_title="KonnectOps Mobile", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")

# ---------- Scoped CSS ----------
st.markdown(
    """
    <style>
    .konnectops-root { font-family: "Segoe UI", sans-serif; color: #000; }
    .bg-section { min-height: 580px; background-position: center; background-size: cover; background-repeat: no-repeat; position: relative; padding: 36px 48px; box-sizing: border-box; }
    .bg-section::before { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(12,20,32,0.30) 0%, rgba(255,255,255,0.05) 100%); pointer-events: none; z-index: 0; backdrop-filter: blur(2px); }
    .content-box { position: relative; z-index: 2; max-width: 1200px; margin: 18px auto; background: rgba(255,255,255,0.96); border-radius: 14px; padding: 22px; box-shadow: 0 12px 40px rgba(2,12,34,0.12); color: #0b1720; }
    .hero-title { display:flex; align-items:center; gap:12px; }
    .hero-title h1 { margin:0; font-size:28px; color:#002D62; }
    .subtitle { color:#334155; margin-top:6px; font-size:14px; }
    .stButton>button { background:#002D62 !important; color:white !important; border-radius:8px; padding:10px 14px; font-weight:600; }
    .stTextInput>div>input, .stTextArea>div>textarea { font-size:15px !important; }
    .mini-card { background: rgba(240,243,247,0.9); border-radius:10px; padding:10px; margin-bottom:10px; border:1px solid rgba(0,0,0,0.04); }
    @media (max-width: 760px) { .bg-section { padding: 18px 12px; } .content-box { padding: 16px; margin: 8px; } .hero-title h1 { font-size:22px; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="konnectops-root">', unsafe_allow_html=True)

# ---------- Session state ----------
if "api_key" not in st.session_state: st.session_state.api_key = ""
if "model_name" not in st.session_state: st.session_state.model_name = None
if "available_models" not in st.session_state: st.session_state.available_models = []
if "last_ai_error" not in st.session_state: st.session_state.last_ai_error = ""
if "bg_images" not in st.session_state: st.session_state.bg_images = {}
if "s3_access_key" not in st.session_state: st.session_state.s3_access_key = ""
if "s3_secret_key" not in st.session_state: st.session_state.s3_secret_key = ""
if "s3_region" not in st.session_state: st.session_state.s3_region = ""
if "gcs_credentials_json" not in st.session_state: st.session_state.gcs_credentials_json = ""

# ---------- Model helpers ----------
@lru_cache(maxsize=1)
def fetch_models_for_key(key: str):
    genai.configure(api_key=key)
    return list(genai.list_models() or [])

def safe_name(obj):
    try: return getattr(obj, "name", None) or (obj.get("name") if isinstance(obj, dict) else None)
    except: return None

def supports_gen(obj):
    try:
        methods = getattr(obj, "supported_generation_methods", None)
        if methods is None and isinstance(obj, dict): methods = obj.get("supported_generation_methods")
        return methods and ("generateContent" in methods or "generate" in methods)
    except:
        return False

def try_connect(key: str) -> Optional[str]:
    if not key: return None
    try:
        models = fetch_models_for_key(key)
    except Exception as e:
        logger.exception("Model fetch failed: %s", e)
        return None
    for m in models:
        if supports_gen(m):
            nm = safe_name(m)
            if nm:
                st.session_state.available_models = [safe_name(x) for x in models if safe_name(x)]
                return nm
    if models:
        nm = safe_name(models[0])
        st.session_state.available_models = [safe_name(x) for x in models if safe_name(x)]
        return nm
    return None

def ask_ai(prompt: str) -> str:
    if not st.session_state.get("model_name"): return "Error: Offline (no model configured)."
    try:
        model = genai.GenerativeModel(st.session_state.model_name)
        res = model.generate_content(prompt)
        text = getattr(res, "text", None) or (res.get("text") if isinstance(res, dict) else str(res))
        return text
    except Exception as e:
        st.session_state.last_ai_error = str(e)
        logger.exception("AI error: %s", e)
        return f"Error (AI): {e}"

# ---------- Image generation stub (best-effort) ----------
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
        logger.warning("Image generation via genai failed: %s", e)
        return None

# ---------- Cloud upload helpers ----------
def upload_to_s3(bytes_data: bytes, bucket: str, object_name: str, region: str, access_key: str, secret_key: str) -> str:
    if not BOTO3_AVAILABLE:
        raise RuntimeError("boto3 not available; install boto3 to use S3 uploads.")
    s3 = boto3.client("s3", region_name=region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    s3.put_object(Bucket=bucket, Key=object_name, Body=bytes_data, ACL="public-read", ContentType="image/jpeg")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{object_name}"

def upload_to_gcs(bytes_data: bytes, bucket_name: str, object_name: str, credentials_json: dict) -> str:
    if not GCS_AVAILABLE:
        raise RuntimeError("google-cloud-storage not available; install google-cloud-storage to use GCS uploads.")
    credentials = service_account.Credentials.from_service_account_info(credentials_json)
    client = gcs_storage.Client(credentials=credentials, project=credentials.project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(bytes_data, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Paste your Generative AI key (kept only for this session).")
    api_key_in = st.text_input("Generative AI Key", type="password", value=st.session_state.api_key)
    if api_key_in and api_key_in != st.session_state.api_key:
        st.session_state.api_key = api_key_in
        try:
            fetch_models_for_key.cache_clear()
        except: pass

    st.markdown("---")
    st.subheader("Page backgrounds")
    st.write("Upload a background image per tab (1200×700 recommended).")
    tab_names = ["Landing", "Content", "Images", "Calendar", "Utilities", "Blog", "Uploads", "Zoho"]
    for t in tab_names:
        uploaded = st.file_uploader(f"{t} background", type=["jpg","jpeg","png"], key=f"bg_{t}")
        if uploaded:
            img_bytes = uploaded.read()
            b64 = base64.b64encode(img_bytes).decode()
            mime = uploaded.type
            data_url = f"data:{mime};base64,{b64}"
            st.session_state.bg_images[t] = data_url
            st.success(f"{t} background saved for this session.")

    st.markdown("---")
    st.subheader("Cover image upload (optional)")
    st.write("Provide either AWS S3 or Google Cloud Storage details to enable direct upload (optional).")
    st.session_state.s3_access_key = st.text_input("S3 Access Key", value=st.session_state.s3_access_key)
    st.session_state.s3_secret_key = st.text_input("S3 Secret Key", type="password", value=st.session_state.s3_secret_key)
    st.session_state.s3_region = st.text_input("S3 Region (e.g., ap-south-1)", value=st.session_state.s3_region)
    s3_bucket = st.text_input("S3 Bucket Name", value="")

    st.write("GCS Service Account JSON (paste as full JSON)")
    gcs_json_text = st.text_area("GCS JSON", value="")
    if gcs_json_text.strip():
        try:
            import json
            st.session_state.gcs_credentials_json = json.loads(gcs_json_text)
        except Exception:
            st.warning("Invalid JSON — please paste valid GCS service account JSON.")

    st.markdown("---")
    st.write("Connected model:")
    st.write(st.session_state.model_name.split("/")[-1] if st.session_state.model_name else "Not connected")

    if st.button("Logout / Clear"):
        st.session_state.api_key = ""
        st.session_state.model_name = None
        st.session_state.available_models = []
        st.session_state.last_ai_error = ""
        st.session_state.bg_images = {}
        st.session_state.s3_access_key = ""
        st.session_state.s3_secret_key = ""
        st.session_state.s3_region = ""
        st.session_state.gcs_credentials_json = ""
        try:
            fetch_models_for_key.cache_clear()
        except: pass
        st.experimental_rerun()

# ---------- Connect attempt ----------
if st.session_state.api_key and not st.session_state.model_name:
    with st.spinner("Discovering available models..."):
        model_id = try_connect(st.session_state.api_key)
        if model_id:
            st.session_state.model_name = model_id
            st.success("Connected.")
            st.experimental_rerun()
        else:
            st.error("Model discovery failed. Check key or network.")

# ---------- Locked view ----------
if not st.session_state.model_name:
    default_bg = st.session_state.bg_images.get("Landing", "")
    style_bg = f"background-image: url('{default_bg}');" if default_bg else "background:#f1f5f9;"
    st.markdown(f"<div class='bg-section' style='{style_bg}'>"
                "<div class='content-box' style='max-width:620px;text-align:center;'>"
                "<i class='fa-solid fa-lock' style='font-size:42px;color:#002D62'></i>"
                "<h1 style='margin-top:10px;color:#002D62'>KonnectOps Login</h1>"
                "<p class='subtitle'>Secure Digital Operations Center</p>"
                "</div></div>", unsafe_allow_html=True)
    key_input = st.text_input("Paste key (kept this session)", type="password", label_visibility="visible")
    if st.button("Unlock Dashboard"):
        if key_input:
            st.session_state.api_key = key_input
            st.experimental_rerun()
        else:
            st.warning("Please paste your key.")
    st.stop()

# ---------- Main header ----------
st.markdown("<div style='padding:12px 24px'><span style='font-size:20px;color:#002D62;font-weight:700;'>KonnectOps Mobile</span></div>", unsafe_allow_html=True)

# ---------- Tabs ----------
tabs = st.tabs(["📄 Landing", "✍️ Content", "🎨 Images", "📅 Calendar", "🛠️ Utilities", "📝 Blog", "☁️ Uploads", "👨‍💻 Zoho"])

def render_tab_section(tab_key: str, inner_html: str):
    bg = st.session_state.bg_images.get(tab_key, "")
    if not bg:
        bg_style = "background: linear-gradient(180deg, #f8fafc 0%, #e9eef6 100%);"
    else:
        bg_style = f"background-image: url('{bg}');"
    html = f"""
    <div class="bg-section" style="{bg_style}">
      <div class="content-box">
        {inner_html}
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ---------- Landing ----------
with tabs[0]:
    inner = "<div class='hero-title'><h1>Developer Console — Landing Page Generator</h1></div><p class='subtitle'>Quickly replace names and generate SEO-ready HTML with preview and download.</p>"
    render_tab_section("Landing", inner)
    c1, c2 = st.columns(2)
    with c1:
        proj = st.text_input("Project Name", placeholder="TVS Emerald")
        loc = st.text_input("Location", placeholder="Porur")
        price = st.text_input("Price", placeholder="85L")
    with c2:
        old_txt = st.text_input("Old Name", value="Casagrand Flagship")
        html_input = st.text_area("Paste HTML Code", height=180, placeholder="<html>... use {PRICE}, {LOCATION}, {DESC}</html>")
    if st.button("Generate Page"):
        if not html_input:
            st.warning("Paste your HTML first.")
        else:
            res = html_input.replace(old_txt or "", proj or "").replace("{PRICE}", price or "").replace("{LOCATION}", loc or "")
            if "{DESC}" in res:
                seo = ask_ai(f"Write 150 char SEO description for {proj} in {loc}.")
                if not seo.lower().startswith("error"): res = res.replace("{DESC}", seo)
            try:
                st.markdown("**Preview**")
                components.html(res, height=420, scrolling=True)
            except Exception:
                st.warning("Preview might not render; download to view.")
            st.download_button("Download HTML", data=res, file_name=f"{proj or 'page'}.html", mime="text/html")

# ---------- Content ----------
with tabs[1]:
    header_html = "<div class='hero-title'><h1>Marketing Studio</h1></div><p class='subtitle'>Short, human-friendly marketing drafts — blog, social, email.</p>"
    render_tab_section("Content", header_html)
    ctype = st.selectbox("Content Type", ["Blog Post", "Instagram Carousel", "LinkedIn Post", "Client Email"])
    topic = st.text_input("Topic", placeholder="Why invest in OMR?")
    if st.button("Draft Content"):
        if not topic.strip():
            st.warning("Enter a topic.")
        else:
            out = ask_ai(f"Act as a Senior Marketing Manager. Write a professional {ctype} about: {topic}.")
            if out.lower().startswith("error"):
                st.error(out)
            else:
                st.code(out, language="text")

# ---------- Images ----------
with tabs[2]:
    header_html = "<div class='hero-title'><h1>Image Prompt Studio</h1></div><p class='subtitle'>Generate production-ready prompts for image tools.</p>"
    render_tab_section("Images", header_html)
    desc = st.text_input("Image Concept", placeholder="Luxury living room with sea view")
    style = st.selectbox("Style", ["Photorealistic 8k", "Architectural render", "Lifestyle"])
    if st.button("Generate Prompt"):
        if not desc.strip():
            st.warning("Enter an image concept.")
        else:
            out = ask_ai(f"Write a detailed Midjourney prompt for: {desc}. Style: {style}.")
            if out.lower().startswith("error"): st.error(out)
            else: st.code(out, language="text")

# ---------- Calendar ----------
with tabs[3]:
    header_html = "<div class='hero-title'><h1>Marketing Calendar — 2026 Festivals</h1></div><p class='subtitle'>Plan campaigns around key dates.</p>"
    render_tab_section("Calendar", header_html)
    data = {"Date": ["Jan 14", "Jan 26", "Mar 04", "Mar 20", "Apr 14", "Aug 15", "Aug 26", "Sep 14", "Oct 20", "Nov 08", "Dec 25"],
            "Festival": ["Pongal","Republic Day","Holi","Ramzan","Tamil New Year","Independence Day","Onam","Ganesh Chaturthi","Ayudha Puja","Diwali","Christmas"]}
    st.table(pd.DataFrame(data))

# ---------- Utilities ----------
with tabs[4]:
    header_html = "<div class='hero-title'><h1>Sales Utilities</h1></div><p class='subtitle'>WhatsApp links, EMI calculator, translations — quick tools.</p>"
    render_tab_section("Utilities", header_html)
    tool = st.radio("Tool:", ["WhatsApp Link Generator", "EMI Calculator", "Tamil Translator"], horizontal=True)
    if tool == "WhatsApp Link Generator":
        wa_num = st.text_input("Phone Number (with code)", "919876543210")
        wa_msg = st.text_input("Message", "Hi, I am interested in the OMR project.")
        if st.button("Create WhatsApp Link"):
            if not wa_num.strip(): st.warning("Enter phone number.")
            else:
                link = f"https://wa.me/{wa_num.strip()}?text={quote_plus(wa_msg)}"
                st.code(link)
                st.markdown(f"[Open link]({link})")
    elif tool == "EMI Calculator":
        loan = st.number_input("Loan Amount (₹)", value=5_000_000, min_value=0, format="%d")
        rate = st.number_input("Interest Rate (%)", value=8.5, format="%.3f")
        years = st.number_input("Tenure (Years)", value=20, min_value=1)
        if st.button("Calculate EMI"):
            r = rate / (12 * 100); n = int(years * 12)
            emi = loan * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
            st.success(f"Monthly EMI: ₹ {int(round(emi)):,}")
    else:
        txt_to_translate = st.text_area("Enter English Text", "Exclusive launch offer ending soon.")
        if st.button("Translate"):
            out = ask_ai(f"Translate this real estate text to professional Tamil: '{txt_to_translate}'")
            if out.lower().startswith("error"): st.error(out)
            else: st.code(out, language="text")

# ---------- Blog ----------
with tabs[5]:
    header_html = "<div class='hero-title'><h1>Blog — Home Konnect Generator</h1></div><p class='subtitle'>Generate copy-paste blog (Home Konnect format) and cover image prompts.</p>"
    render_tab_section("Blog", header_html)
    col1, col2 = st.columns([2, 1])
    with col1:
        b_project = st.text_input("Project Name", "DRA Beena Clover")
        b_location = st.text_input("Location", "Madambakkam (Near Selaiyur & East Tambaram)")
        b_developer = st.text_input("Developer", "DRA Housing")
        b_usps = st.text_area("USPs (comma separated)", "Close to Selaiyur, Family-friendly amenities, Value pricing, Good connectivity")
    with col2:
        b_price = st.text_input("Price hint", "Starts from 45L")
        b_poss = st.text_input("Possession", "Check developer brochure")
        b_phone = st.text_input("Sales phone", "919876543210")
        b_email = st.text_input("Sales email", "sales@draexample.com")
    if st.button("Generate Home Konnect blog (Markdown)"):
        prompt = f\"\"\"
You are a professional real estate content writer. Produce a copy-paste ready markdown blog post following the Home Konnect blog structure EXACTLY:
Title, Preview (with emojis), Introduction, Project highlights with emojis, Location advantages, Premium specifications, Amenities (with emojis), About the developer, Contact CTA (phone, whatsapp link), FAQ (5 Q&A), SEO Meta Title & 150-char description, tags.
Project: {b_project}
Location: {b_location}
Developer: {b_developer}
USPs: {b_usps}
Phone: {b_phone}
Email: {b_email}
Return only markdown content.
\"\"\"
        with st.spinner("Drafting blog..."):
            blog_md = ask_ai(prompt)
        if blog_md.lower().startswith("error"): st.error(blog_md)
        else:
            st.markdown("**Generated blog (Markdown)**")
            st.code(blog_md, language="markdown")
            st.download_button("Download blog (md)", data=blog_md, file_name=f"{b_project.replace(' ','_')}_blog.md", mime="text/markdown")
    st.markdown("---")
    st.subheader("Cover image prompt")
    usps_list = [u.strip() for u in b_usps.split(",") if u.strip()]
    usps_short = "; ".join(usps_list[:4])
    image_prompt = (f"Blog cover for '{b_project}' in {b_location}. Photorealistic 1200x628, modern mid-rise exterior at golden hour, "
                    f"landscaped foreground, safe family silhouettes, room for title overlay, no recognizable faces. Emphasize: {usps_short}.")
    st.code(image_prompt, language="text")
    if st.button("Try auto-generate cover image"):
        with st.spinner("Attempting to generate image via GenAI..."):
            img_bytes = generate_cover_image_via_genai(image_prompt, size="1200x628")
            if img_bytes:
                st.image(img_bytes, width=700, caption="Generated cover image")
                st.download_button("Download Cover Image", data=img_bytes, file_name=f"{b_project.replace(' ','_')}_cover.jpg", mime="image/jpeg")
                st.session_state["_last_cover_bytes"] = img_bytes
            else:
                st.warning("Auto-generation not available in this environment. Use the prompt above in an image tool or upload your own image.")
    st.markdown("**Or upload your own cover image (JPEG/PNG)**")
    uploaded = st.file_uploader("Upload cover image", type=["jpg", "jpeg", "png"])
    if uploaded:
        bytes_img = uploaded.read()
        st.image(bytes_img, width=700, caption="Uploaded cover image")
        st.session_state["_last_cover_bytes"] = bytes_img
        st.download_button("Download uploaded cover", data=bytes_img, file_name=f"{b_project.replace(' ','_')}_cover.jpg", mime="image/jpeg")

# ---------- Uploads ----------
with tabs[6]:
    header_html = "<div class='hero-title'><h1>Uploads</h1></div><p class='subtitle'>Upload generated cover images to S3 or GCS (optional).</p>"
    render_tab_section("Uploads", header_html)
    if "_last_cover_bytes" not in st.session_state:
        st.info("No cover image available yet. Generate or upload one in the Blog tab first.")
    else:
        img_bytes = st.session_state["_last_cover_bytes"]
        st.image(img_bytes, width=600, caption="Selected cover image ready for upload")
        dest = st.selectbox("Upload destination", ["None", "AWS S3", "Google Cloud Storage"])
        if dest == "AWS S3":
            if not BOTO3_AVAILABLE:
                st.error("boto3 not installed. Install boto3 to enable S3 uploads.")
            else:
                s3_bucket_in = st.text_input("S3 Bucket (to upload)", value="")
                s3_region_in = st.text_input("S3 Region", value=st.session_state.s3_region or "")
                s3_key_in = st.text_input("S3 object key (e.g., blog/covers/mycover.jpg)", value=f"blog_covers/{int(time.time())}_cover.jpg")
                if st.button("Upload to S3"):
                    try:
                        url = upload_to_s3(img_bytes, s3_bucket_in, s3_key_in, s3_region_in, st.session_state.s3_access_key, st.session_state.s3_secret_key)
                        st.success("Uploaded to S3.")
                        st.write("Public URL:", url)
                    except Exception as e:
                        st.error(f"S3 upload failed: {e}")
        elif dest == "Google Cloud Storage":
            if not GCS_AVAILABLE:
                st.error("google-cloud-storage not installed. Install google-cloud-storage to enable GCS uploads.")
            else:
                gcs_bucket_in = st.text_input("GCS Bucket (to upload)", value="")
                gcs_key_in = st.text_input("GCS object name (e.g., blog/covers/mycover.jpg)", value=f"blog_covers/{int(time.time())}_cover.jpg")
                if st.button("Upload to GCS"):
                    try:
                        if not st.session_state.gcs_credentials_json:
                            st.error("GCS credentials JSON not provided in sidebar. Paste service account JSON there.")
                        else:
                            url = upload_to_gcs(img_bytes, gcs_bucket_in, gcs_key_in, st.session_state.gcs_credentials_json)
                            st.success("Uploaded to GCS.")
                            st.write("Public URL:", url)
                    except Exception as e:
                        st.error(f"GCS upload failed: {e}")

# ---------- Zoho ----------
with tabs[7]:
    header_html = "<div class='hero-title'><h1>Zoho Deluge Scripting</h1></div><p class='subtitle'>Generate Deluge scripts for Zoho CRM automations.</p>"
    render_tab_section("Zoho", header_html)
    req = st.text_area("Logic Needed", "e.g. Update lead status when email opens")
    if st.button("Compile Code"):
        if not req.strip(): st.warning("Enter the logic.")
        else:
            out = ask_ai(f"Write Zoho Deluge script: {req}")
            if out.lower().startswith("error"): st.error(out)
            else: st.code(out, language="java")

# ---------- Diagnostics ----------
with st.expander("Diagnostics & last AI error", expanded=False):
    st.write("Model:", st.session_state.model_name)
    st.write("Available models:", st.session_state.available_models[:8])
    if st.session_state.last_ai_error:
        st.error("Last AI error:")
        st.write(st.session_state.last_ai_error)
    st.write("Session backgrounds keys:", list(st.session_state.bg_images.keys()))

st.markdown("</div>", unsafe_allow_html=True)
