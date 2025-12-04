import streamlit as st
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes
import google.generativeai as genai
import openai
from anthropic import Anthropic

# Google Cloud Auth
from google.cloud import storage
from google.oauth2 import service_account

# PDF generation
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

# Поддержка локального файла .env (чтобы работало на твоем компе)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="Christmas Bomb v7.1 🎄", page_icon="🎅", layout="wide", initial_sidebar_state="expanded")

# --- 1. УМНАЯ СИСТЕМА ПАРОЛЕЙ ---
# Функция достает секрет либо из облака, либо из твоего файла .env
def get_secret(key_name):
    # 1. Сначала ищем в Streamlit Cloud Secrets
    if key_name in st.secrets:
        return st.secrets[key_name]
    # 2. Если нет - ищем в локальных переменных (.env)
    return os.getenv(key_name)

# --- 2. КОНФИГУРАЦИЯ ---
PROJECT_ID = "chatgpt-409111"
REGION = "us-east1"
INSTANCE_NAME = "lakf-ai"
DB_USER = "postgres"
DB_PASS = "admin"
DB_NAME = "christmas_bomb"

# Собираем ключи для AI
API_KEYS = {
    "Google Gemini 2.0": get_secret("GEMINI_KEY"),
    "OpenAI GPT-4o": get_secret("OPENAI_KEY"),
    "Claude 3.5 Sonnet": get_secret("CLAUDE_KEY"),
    "DeepSeek V3": get_secret("DEEPSEEK_KEY"),
    "Moonshot (Kimi)": get_secret("MOONSHOT_KEY"),
    "Groq Llama 3": get_secret("GROQ_KEY")
}

# --- 3. АВТОРИЗАЦИЯ GOOGLE (САМОЕ ВАЖНОЕ) ---
def get_gcp_auth():
    # Если мы в облаке и там прописан JSON-ключ:
    if "gcp_service_account" in st.secrets:
        # Превращаем TOML конфиг обратно в объект ключа
        return service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
    # Если мы дома - возвращаем None.
    # Библиотека Google сама найдет твои локальные настройки gcloud login.
    return None

# --- 4. ПОДКЛЮЧЕНИЯ (С учетом авторизации) ---
@st.cache_resource
def get_resources():
    creds = get_gcp_auth() # Ключ для облака или None для дома
    
    # 1. Подключение к БД
    def getconn():
        return Connector(credentials=creds).connect(
            f"{PROJECT_ID}:{REGION}:{INSTANCE_NAME}",
            "pg8000", user=DB_USER, password=DB_PASS, db=DB_NAME, ip_type=IPTypes.PUBLIC
        )
    engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)
    
    # 2. Подключение к Бакету
    st_client = storage.Client(credentials=creds, project=PROJECT_ID)
    
    return engine, st_client

try:
    pool, storage_client = get_resources()
except Exception as e:
    st.error(f"Ошибка подключения: {e}")
    st.stop()

# --- 5. ФУНКЦИИ ПРИЛОЖЕНИЯ ---

# Телепортация файлов из облака
def download_bytes_from_gcs(gcs_link):
    if not gcs_link: return None
    try:
        path = gcs_link.replace("gs://", "")
        bucket_name, blob_name = path.split("/", 1)
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        stream = io.BytesIO()
        blob.download_to_file(stream)
        stream.seek(0)
        return stream
    except Exception: return None

# Мозги AI
def get_ai_brain(model_name, prompt):
    key = API_KEYS.get(model_name)
    if not key: return "Error: API Key not found! Check secrets."
    
    try:
        if "Gemini" in model_name:
            genai.configure(api_key=key)
            return genai.GenerativeModel('gemini-2.0-flash').generate_content(prompt).text
        elif "Claude" in model_name:
            c = Anthropic(api_key=key)
            return c.messages.create(model="claude-3-opus-20240229", max_tokens=2500, messages=[{"role":"user","content":prompt}]).content[0].text
        else: # OpenAI / Deepseek / Groq / Kimi
            base = None
            model_id = "gpt-4o"
            
            if "DeepSeek" in model_name: base="https://api.deepseek.com"; model_id="deepseek-chat"
            elif "Groq" in model_name: base="https://api.groq.com/openai/v1"; model_id="llama3-8b-8192"
            elif "Moonshot" in model_name: base="https://api.moonshot.cn/v1"; model_id="moonshot-v1-8k"
            
            c = openai.OpenAI(api_key=key, base_url=base)
            return c.chat.completions.create(model=model_id, messages=[{"role":"user","content":prompt}]).choices[0].message.content
            
    except Exception as e: return f"Brain Error: {e}"

# Форматирование текста
def clean_md(text):
    text = text.replace('\n', '<br/>')
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'##\s+(.*?)<br/>', r'<font size="14"><b>\1</b></font><br/>', text)
    return text

# Сборка Бомбы
def create_bomb_pdf(case_data, messages, attachments, lawyer_draft):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    normal_s = ParagraphStyle('N', parent=styles['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=14, spaceAfter=8)
    title_s = ParagraphStyle('T', parent=styles['Heading1'], fontSize=18, textColor=colors.firebrick, alignment=TA_CENTER, spaceAfter=20)
    
    story = []
    story.append(Paragraph("NOTICE OF CLAIM / LEGAL DEMAND", title_s))
    story.append(Paragraph(f"<b>DATE:</b> {time.strftime('%d December %Y')}<br/><b>REF CASE:</b> {case_data.issue_title}", normal_s))
    story.append(Spacer(1, 15))
    story.append(Paragraph(clean_md(lawyer_draft), normal_s))
    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>Red Square Group Legal Dept.</b>", normal_s))
    story.append(PageBreak())
    
    # Лог переписки
    story.append(Paragraph("SCHEDULE OF EVIDENCE", styles['Heading2']))
    for m in messages:
        head = f"<b>[{str(m.date_sent)[:10]}] {m.sender}</b>"
        txt = clean_md(m.body_text[:500] + "...") if m.body_text else "..."
        story.append(Paragraph(head, normal_s))
        story.append(Paragraph(f"<i>Subject: {m.subject}</i><br/>{txt}", normal_s))
        story.append(Spacer(1, 10))
    
    doc.build(story)
    buf.seek(0)
    
    # Мердж PDF из облака
    merger = PdfWriter()
    merger.append(PdfReader(buf))
    
    cnt = 0
    for att in attachments:
        if att.filename.lower().endswith('.pdf') and att.gcs_path:
            pdf_bytes = download_bytes_from_gcs(att.gcs_path)
            if pdf_bytes:
                try:
                    merger.append(PdfReader(pdf_bytes))
                    cnt += 1
                except: pass
                
    final = io.BytesIO()
    merger.write(final)
    return final.getvalue(), cnt

# --- UI STYLE ---
st.markdown("""
<style>
.stApp {background: #fdfdfd;}
.snowflake {color: #b0c4de; position: fixed; top: -10px; z-index: 9999; animation: fall linear infinite;}
@keyframes fall { to {transform: translateY(105vh);} }
[data-testid="stSidebar"] {border-right: 4px solid #b71c1c;}
.bomb-div button {
    background: radial-gradient(circle, #D90429 0%, #8D0801 100%) !important;
    color: white !important; font-size: 24px !important; font-weight: 800 !important;
    padding: 20px !important; border: 4px solid white !important; box-shadow: 0 5px 15px rgba(0,0,0,0.2) !important;
    width: 100%; transition: transform 0.1s; text-transform: uppercase;
}
.bomb-div button:hover {transform: scale(1.02); filter: brightness(1.1);}
</style>
<script>
for(let i=0;i<20;i++){
    let d=document.createElement('div');d.className='snowflake';d.innerHTML='❄';
    d.style.left=Math.random()*100+'vw';d.style.animationDuration=(Math.random()*3+3)+'s';d.style.opacity=Math.random();d.style.fontSize=(Math.random()*20+10)+'px';
    document.body.appendChild(d);
}
</script>
""", unsafe_allow_html=True)

# --- 6. MAIN LAYOUT ---
if 'case_id' not in st.session_state: st.session_state.case_id = None

st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3706/3706290.png", width=70)
st.sidebar.title("Target List")
sel_brain = st.sidebar.selectbox("Legal Brain:", list(API_KEYS.keys()))

with pool.connect() as conn:
    cases = conn.execute(sqlalchemy.text("SELECT * FROM cases ORDER BY id")).fetchall()

st.sidebar.write("---")
for c in cases:
    icon = "🔴" if c.risk_level=="High" else "🟡"
    if st.sidebar.button(f"{icon} {c.issue_title[:30]}...", key=c.id):
        st.session_state.case_id = c.id

st.title("CHRISTMAS BOMB v7.1 (HYBRID) 🎄")

if st.session_state.case_id:
    cid = st.session_state.case_id
    with pool.connect() as conn:
        case = conn.execute(sqlalchemy.text("SELECT * FROM cases WHERE id=:id"), {"id":cid}).fetchone()
        msgs = conn.execute(sqlalchemy.text("SELECT * FROM messages WHERE case_id=:id ORDER BY date_sent"), {"id":cid}).fetchall()
        atts = conn.execute(sqlalchemy.text("SELECT * FROM attachments WHERE case_id=:id"), {"id":cid}).fetchall()

    st.success(f"TARGET: **{case.issue_title}**")
    
    # RAG Context
    rag_context = ""
    for m in msgs:
        rag_context += f"DATE: {m.date_sent} | SENDER: {m.sender}\nCONTENT: {m.body_text[:1500]}\n---\n"
    safe_rag = rag_context[:50000]

    c1, c2 = st.columns([1.5, 1])
    
    with c1:
        st.info(f"{case.summary}")
        t1, t2 = st.tabs(["Logs", "Cloud Files"])
        with t1:
            for m in msgs[:3]: st.text(f"{str(m.date_sent)[:10]} | {m.subject}")
            if len(msgs)>3: st.caption("...more")
        with t2:
            for a in atts:
                st.write(f"📄 {a.filename} {'✅ Linked' if a.gcs_path else ''}")

        st.write("##")
        st.markdown('<div class="bomb-div">', unsafe_allow_html=True)
        if st.button("💣 BOMB!!!", key="run"):
            with st.spinner("Drafting & Merging Evidence..."):
                prompt = f"""
                ACT AS A UK BARRISTER. WRITE A LETTER BEFORE ACTION.
                REF: {case.issue_title}.
                FACTS: {case.summary}.
                EVIDENCE DATABASE:
                {safe_rag}
                INSTRUCTION: Cite specific emails and dates from database. Demand remedy in 14 days. TONE: Cold, Formal.
                """
                txt = get_ai_brain(sel_brain, prompt)
                pdf, n = create_bomb_pdf(case, msgs, atts, txt)
                
                st.balloons()
                st.success(f"DONE! {n} PDF files merged from Cloud.")
                st.download_button("📥 DOWNLOAD PDF", pdf, "Claim.pdf", "application/pdf")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown("### 🦌 Barrister Chat")
        u = st.text_input("Consult:")
        if u:
            with st.spinner("Thinking..."):
                ans = get_ai_brain(sel_brain, f"CASE:{case.issue_title}\nEVIDENCE:{safe_rag}\nQ:{u}")
                st.info(ans)
else:
    st.info("👈 Choose a target.")