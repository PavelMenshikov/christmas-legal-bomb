import streamlit as st
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes
import google.generativeai as genai
import openai
from anthropic import Anthropic
from dotenv import load_dotenv
from google.cloud import storage 
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors
from pypdf import PdfWriter, PdfReader
import io
import time
import os
import re


load_dotenv()


st.set_page_config(page_title="Christmas Bomb v6.0 (Secure) 🔒", page_icon="🎅", layout="wide", initial_sidebar_state="expanded")


PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION")
INSTANCE_NAME = os.getenv("INSTANCE_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

API_KEYS = {
    "Google Gemini 2.0": os.getenv("GEMINI_KEY"),
    "OpenAI GPT-4o": os.getenv("OPENAI_KEY"),
    "Claude 3.5 Sonnet": os.getenv("CLAUDE_KEY"),
    "DeepSeek V3": os.getenv("DEEPSEEK_KEY"),
    "Moonshot (Kimi)": os.getenv("MOONSHOT_KEY"),
    "Groq Llama 3": os.getenv("GROQ_KEY")
}

# --- STYLE (CHRISTMAS MODE) ---
st.markdown("""
    <style>
    /* ФОН - Зимний градиент */
    .stApp { background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); font-family: 'Verdana', sans-serif; }
    
    /* СНЕЖИНКИ */
    #snow-container { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 9999; }
    .snowflake { position: absolute; color: white; opacity: 0.9; text-shadow: 0 0 4px #bbb; animation: fall linear infinite; }
    @keyframes fall { to { transform: translateY(105vh); } }

    /* САЙДБАР */
    [data-testid="stSidebar"] { border-right: 4px solid #b71c1c; background-color: #fff; }
    
    /* КНОПКА ДЕТОНАЦИИ */
    .bomb-container button {
        background: linear-gradient(45deg, #d90429, #ef233c) !important;
        color: white !important;
        font-family: 'Arial Black', sans-serif !important;
        font-size: 26px !important;
        padding: 22px !important;
        border: 4px solid #fff !important;
        border-radius: 8px !important;
        box-shadow: 0 8px 15px rgba(217, 4, 41, 0.4) !important;
        text-transform: uppercase;
        width: 100%;
        transition: transform 0.1s;
    }
    .bomb-container button:hover { transform: scale(1.02); filter: brightness(1.1); }
    .bomb-container button:active { transform: scale(0.97); }

    /* ЗАГОЛОВКИ */
    h1 { color: #c1121f; font-weight: 900; text-transform: uppercase; }
    h2, h3 { color: #003049; }
    </style>
    
    <div id="snow-container"></div>
    <script>
    const box = document.getElementById('snow-container');
    for(let i=0; i<30; i++){
        let flake = document.createElement('div');
        flake.className = 'snowflake';
        flake.innerHTML = '❄';
        flake.style.left = Math.random()*100 + 'vw';
        flake.style.fontSize = (Math.random()*15+10) + 'px';
        flake.style.animationDuration = (Math.random()*5+4) + 's';
        flake.style.opacity = Math.random();
        box.appendChild(flake);
    }
    </script>
""", unsafe_allow_html=True)

@st.cache_resource
def get_db_connection():
    def getconn():
        return Connector().connect(f"{PROJECT_ID}:{REGION}:{INSTANCE_NAME}", "pg8000", user=DB_USER, password=DB_PASS, db=DB_NAME, ip_type=IPTypes.PUBLIC)
    return sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)

pool = get_db_connection()
storage_client = storage.Client(project=PROJECT_ID)

def download_from_cloud(gcs_link):
    """Качает файл из GCS в RAM"""
    if not gcs_link: return None
    try:
        path = gcs_link.replace("gs://", "")
        bucket, blob_name = path.split("/", 1)
        blob = storage_client.bucket(bucket).blob(blob_name)
        stream = io.BytesIO()
        blob.download_to_file(stream)
        stream.seek(0)
        return stream
    except Exception: return None

def get_ai_brain(model, prompt):
    key = API_KEYS.get(model)
    if not key: return "🚫 Error: API Key missing in .env file!"
    
    try:
        if "Gemini" in model:
            genai.configure(api_key=key)
            return genai.GenerativeModel('gemini-2.0-flash').generate_content(prompt).text
        elif "Claude" in model:
            c = Anthropic(api_key=key)
            return c.messages.create(model="claude-3-opus-20240229", max_tokens=2000, messages=[{"role":"user","content":prompt}]).content[0].text
        else:
            base = "https://api.deepseek.com" if "DeepSeek" in model else ("https://api.groq.com/openai/v1" if "Groq" in model else ("https://api.moonshot.cn/v1" if "Moonshot" in model else None))
            aim = "deepseek-chat" if "DeepSeek" in model else ("llama3-8b-8192" if "Groq" in model else ("moonshot-v1-8k" if "Moonshot" in model else "gpt-4o"))
            client = openai.OpenAI(api_key=key, base_url=base)
            return client.chat.completions.create(model=aim, messages=[{"role":"user","content":prompt}]).choices[0].message.content
    except Exception as e: return f"🔥 Brain Freeze: {e}"

def clean_md(text):
    text = text.replace('\n', '<br/>')
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'##\s+(.*?)<br/>', r'<font size="14"><b>\1</b></font><br/>', text)
    return text

def create_court_bundle(case_data, messages, attachments, lawyer_draft):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    h1 = ParagraphStyle('H1', parent=styles['Heading1'], fontSize=18, textColor=colors.darkred, alignment=TA_CENTER, spaceAfter=20)
    n = ParagraphStyle('N', parent=styles['Normal'], fontSize=11, leading=14, alignment=TA_JUSTIFY, spaceAfter=8)
    
    story = []
    
    story.append(Paragraph("NOTICE OF CLAIM & EVIDENCE BUNDLE", h1))
    story.append(Paragraph(f"<b>RE:</b> {case_data.issue_title}", n))
    story.append(Paragraph(f"<b>DATE:</b> {time.strftime('%d December %Y')}", n))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph(clean_md(lawyer_draft), n))
    story.append(Spacer(1, 30))
    story.append(Paragraph("Yours faithfully,<br/><b>Red Square Group Legal</b>", n))
    story.append(PageBreak())
    
    story.append(Paragraph("SCHEDULE 1: CORRESPONDENCE LOG", styles['Heading2']))
    for m in messages:
        story.append(Paragraph(f"<b>[{str(m.date_sent)[:10]}] From: {m.sender}</b>", n))
        snip = m.body_text[:600] + "..." if m.body_text else "No content."
        story.append(Paragraph(f"<i>Subj: {m.subject}</i><br/>{clean_md(snip)}", n))
        story.append(Spacer(1, 12))
    
    doc.build(story)
    buf.seek(0)
    
    merger = PdfWriter()
    merger.append(PdfReader(buf))
    
    count = 0
    for att in attachments:
        if att.filename.lower().endswith(".pdf") and att.gcs_path:
            pdf_data = download_from_cloud(att.gcs_path)
            if pdf_data:
                try:
                    merger.append(PdfReader(pdf_data))
                    count += 1
                except: pass
                
    out = io.BytesIO()
    merger.write(out)
    return out.getvalue(), count

if 'case_id' not in st.session_state: st.session_state.case_id = None

st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3706/3706290.png", width=70)
st.sidebar.title("Targets List")
model = st.sidebar.selectbox("Legal Engine:", list(API_KEYS.keys()))

with pool.connect() as conn:
    rows = conn.execute(sqlalchemy.text("SELECT * FROM cases ORDER BY id")).fetchall()

st.sidebar.write("---")
for r in rows:
    icon = "🔴" if r.risk_level=="High" else "🟡"
    if st.sidebar.button(f"{icon} {r.issue_title[:30]}...", key=f"c{r.id}"):
        st.session_state.case_id = r.id


st.title("CHRISTMAS BOMB v6.0 🎄")
st.markdown("<div style='text-align:center; color:#555;'>\"Secured. Encrypted. Ready to Litigate.\"</div>", unsafe_allow_html=True)

if st.session_state.case_id:
    cid = st.session_state.case_id
    with pool.connect() as conn:
        case = conn.execute(sqlalchemy.text("SELECT * FROM cases WHERE id=:id"), {"id":cid}).fetchone()
        msgs = conn.execute(sqlalchemy.text("SELECT * FROM messages WHERE case_id=:id ORDER BY date_sent"), {"id":cid}).fetchall()
        atts = conn.execute(sqlalchemy.text("SELECT * FROM attachments WHERE case_id=:id"), {"id":cid}).fetchall()

    st.success(f"**Target Locked:** {case.issue_title}")
    
    c1, c2 = st.columns([1.5, 1])
    
    with c1:
        st.info(case.summary)
        
        t1, t2 = st.tabs(["Evidence Log", "Cloud Files"])
        with t1:
            for m in msgs[:3]: st.text(f"{str(m.date_sent)[:10]} | {m.subject}")
            if len(msgs)>3: st.caption("...more loaded.")
        with t2:
            for a in atts:
                state = "✅ Cloud Link Active" if a.gcs_path else "⚠️ No link"
                st.write(f"📄 {a.filename} - {state}")

        st.write("##")
        st.markdown('<div class="bomb-container">', unsafe_allow_html=True)
        
        if st.button("💣 EXECUTE (GENERATE BUNDLE)", key="exe"):
            with st.spinner(f"Agent {model} is drafting the claim..."):
                prompt = f"""
                ACT AS A UK BARRISTER. WRITE A 'LETTER BEFORE ACTION'.
                REF: {case.issue_title}.
                FACTS: {case.summary}.
                TONE: Litigious, Formal, Urgent.
                Demand remedy in 14 days or Court proceedings follow.
                References: 'Schedule 1' (Log) and attached 'Exhibits'.
                """
                text = get_ai_brain(model, prompt)
                
                # Сборка
                pdf, n_files = create_court_bundle(case, msgs, atts, text)
                
                st.balloons()
                st.success(f"BUNDLE GENERATED! Merged {n_files} PDFs from Google Cloud.")
                st.download_button("📥 DOWNLOAD CLAIM PDF", pdf, f"CLAIM_{case.issue_title}.pdf", "application/pdf")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown("### 🤖 Strategy")
        q = st.text_input("Consult counsel:")
        if q:
            with st.spinner("Researching..."):
                ctx = f"Case: {case.issue_title}. User asks: {q}"
                st.info(get_ai_brain(model, ctx))

else:
    st.info("👈 Select a file from the secure vault.")