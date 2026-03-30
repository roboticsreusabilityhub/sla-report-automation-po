import streamlit as st
import pandas as pd
import os
import pickle
import time
from dotenv import load_dotenv

# Your custom imports
from models.IssueCauser import IssueCauser
from models.text_anonmyzation_handler import TextAnonmizationHandler
from enums.LanugageEnum import LanguageEnum
from models.chunker import Chunker
from models.sla_automation_report_analyzer import SLAAutomationReportAnalyzer

st.set_page_config(page_title="SLA Validation Suite", page_icon="⚖️", layout="wide")
load_dotenv()
display_cached_results_delay = 3

# --- DISK CACHE CONFIG ---
DISK_CACHE_DIR = ".disk_cache"
os.makedirs(DISK_CACHE_DIR, exist_ok=True)

def get_disk_cache_path(file_name, model_name):
    safe_name = "".join([c if c.isalnum() else "_" for c in file_name])
    return os.path.join(DISK_CACHE_DIR, f"{model_name}_{safe_name}.pkl")

def get_ticket_id_from_file_name(file_name):
    return os.path.basename(file_name).split(".")[0]

@st.cache_resource
def init_handlers():
    anon_handler = TextAnonmizationHandler(
        language_endpoint=os.getenv("LANGUAGE_ENDPOINT"),
        language_key=os.getenv("LANGUAGE_KEY")
    )
    chunker = Chunker(default_size=5000)
    return anon_handler, chunker, os.getenv("OPENAI_API_KEY")

anon_handler, chunker, openai_api_key = init_handlers()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Global Settings")
    selected_lang = st.selectbox("Log Language", [LanguageEnum.GERMAN, LanguageEnum.ENGLISH])
    
    st.divider()
    if st.button("🧹 Clear All Caches"):
        st.session_state.clear()
        for f in os.listdir(DISK_CACHE_DIR):
            os.remove(os.path.join(DISK_CACHE_DIR, f))
        st.rerun()

def render_analysis_page(model_name, file_name):
    st.subheader(f"🚀 Running via Model: {model_name}")

    st.markdown("### 🔍 Section 1: Causer Analysis")
    uploaded_log = st.file_uploader(f"Upload Log", type=["rep", "txt"], key=f"log_{model_name}")
    
    if uploaded_log:
        file_id = f"{model_name}_{uploaded_log.name}"
        cache_path = get_disk_cache_path(uploaded_log.name, model_name)
        active_data = None
        
        if file_id in st.session_state:
            with st.spinner("Retrieving from session..."):
                time.sleep(display_cached_results_delay)
                active_data = st.session_state[file_id]
                st.toast(f"Loaded from Session State", icon="⚡")
        elif os.path.exists(cache_path):
            with st.spinner("Restoring from disk cache..."):
                time.sleep(display_cached_results_delay)
                with open(cache_path, "rb") as f:
                    active_data = pickle.load(f)
                st.session_state[file_id] = active_data 
                st.toast(f"Loaded from Disk Cache", icon="📦")

        if st.button(f"Analyze / Refresh {model_name}", type="primary", key=f"btn_{model_name}"):
            with st.status("Running Analysis...", expanded=True) as status:
                raw_bytes = uploaded_log.getvalue()
                                
                log_text = ''
                # log_text = raw_bytes.decode("cp1252")
   
              
                # Try UTF-8 FIRST (modern standard)
                try:
                    log_text = raw_bytes.decode("utf-8")
                    print("Decoded using utf-8")

                except UnicodeDecodeError:
                    try:
                        log_text = raw_bytes.decode("cp1252")
                        print("Decoded using cp1252")

                    except UnicodeDecodeError:
                        log_text = raw_bytes.decode("iso-8859-1", errors="replace")
                        print("Decoded using iso-8859-1 with replacement")

                if not log_text:
                    st.error("Failed to decode file characters.")
                    st.stop()

                # Always write as UTF-8
                with open("example.txt", "w", encoding="utf-8") as file:
                     file.write(log_text)


                print("RAW BYTES AROUND UMLAUT:")
                print(raw_bytes[:300])

                print("DECODED TEXT PREVIEW:")
                print(log_text[:300])


        
            
           

                st.write("🛡️ Redacting PII...")
                chunks = chunker.chunk_by_size(size=5000, text=log_text)
                anon_chunks = [anon_handler.anonmyze_text_entity_redaction(c, selected_lang) for c in chunks if c.strip()]
                full_anon = "\n".join(anon_chunks)
 
                
                st.write("🤖 Querying LLM...")
                llm_chunks = chunker.chunk_recursive(full_anon, 450000, overlap=1000)
                analyzer = SLAAutomationReportAnalyzer(api_key=openai_api_key, chunks=llm_chunks, model_name=model_name)
                res = analyzer.get_issue_causer() 
                
                active_data = {
                    "anon": full_anon, 
                    "data": res,
                    "maps": anon_handler.placeholder_to_entityName_map.copy(),
                }
                
                st.session_state[file_id] = active_data
                with open(cache_path, "wb") as f:
                    pickle.dump(active_data, f)
                
                status.update(label="Analysis Complete!", state="complete")

        if active_data:
            anon_handler.placeholder_to_entityName_map = active_data['maps']
            res_data: IssueCauser = active_data["data"] 
            
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 2, 2])
            with c1:
                st.info("**1. Masked Logs**")
                st.text_area("PII Removed", active_data["anon"], height=250, key=f"txt_{file_id}")
            with c2:
                st.info("**2. Causer (Masked)**")
                st.code(res_data.finalCauserEntity or "None")
            with c3:
                st.info("**3. Causer (Real)**")
                if res_data.finalCauserEntity:
                    real_name = anon_handler.getEntityNameFromAnonmyzedValue(res_data.finalCauserEntity)
                    st.success(f"**{real_name}**")
                else:
                    st.warning("Not identified")
            with c4:
                st.info("**4. Evidence (De-anon)**")
                clean_evidence = anon_handler.deanonmyize_text(res_data.evidence) if res_data.evidence else ""
                st.write(clean_evidence)
            with c5:
                st.info("**5. Exact Logs**")
                raw_logs = ', '.join(res_data.exactLogs) if res_data.exactLogs else ""
                clean_logs = anon_handler.deanonmyize_text(raw_logs)
                st.write(clean_logs)

    st.divider()
    st.markdown(f"### ⏳ Section 2: Pending Times ({model_name})")

    if uploaded_log:    
        ai_validated_file = './output/'+file_name
        ticket_id = get_ticket_id_from_file_name(uploaded_log.name)
        
        if os.path.exists(ai_validated_file):
            df = pd.read_excel(ai_validated_file)
            required_col = 'TA-Ticketnr.'
            if required_col in df.columns:
                df_filtered = df[df[required_col].astype(str).str.strip() == str(ticket_id).strip()]
                if not df_filtered.empty:
                    st.dataframe(df_filtered, use_container_width=True, hide_index=True)
                else:
                    st.info(f"No tickets processed in the {model_name} tab yet.")
            else:
                st.error(f"Excel missing column: {required_col}")

# --- RENDER TABS ---
tab1 = st.tabs(["📊 gpt-4.1"])
with tab1:
    render_analysis_page("gpt-4.1","Action_Output_PendingTimes.xlsx")