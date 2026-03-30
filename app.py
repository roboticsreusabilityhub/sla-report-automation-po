import streamlit as st
import pandas as pd
import os
import pickle
import time
from dotenv import load_dotenv

# Your custom imports
from models.IssueCauser import IssueCauser
from models.text_anonmyzation_handler import TextAnonmizationHandler
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
    selected_lang = st.selectbox("Log Language", ["GERMAN", "ENGLISH"])
    
    st.divider()
    # if st.button("🧹 Clear All Caches"):
    #     st.session_state.clear()
    #     for f in os.listdir(DISK_CACHE_DIR):
    #         os.remove(os.path.join(DISK_CACHE_DIR, f))
    #     st.rerun()

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
        ai_validated_file = file_name
        ticket_id = get_ticket_id_from_file_name(uploaded_log.name)
        
        # if os.path.exists(ai_validated_file):

        data = [
        {
            "TA-Ticketnr.": "TA0000017322420",
            "Auszeit-ID": "AU0000018129283",
            "Grund": "keine Aktivitäten seitens Vodafone erforderlich/möglich",
            "Beginn der Auszeit+": "09.10.2024 10:54:14",
            "Ende der Auszeit+": "09.10.2024 13:00:00",
            "Dauer": "02:05:46",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "09.10.2024 10:54:14",
            "end_time": "09.10.2024 13:00:00",
            "rule_applied": "2",
            "description": "Customer was in a meeting and requested to be contacted again after 13:00.",
            "evidence": "Start Evidence: Herr Büttner ... befindet sich gerade im Meeting, so koennen wir erst ab 13:00 wieder zusammen sprechen. | End Evidence: Explicit time 'ab 13:00' in same log",
            "duration time": "02:05:46"
        },
        {
            "TA-Ticketnr.": "TA0000017322420",
            "Auszeit-ID": "AU0000018129601",
            "Grund": "keine Aktivitäten seitens Vodafone erforderlich/möglich",
            "Beginn der Auszeit+": "09.10.2024 13:16:29",
            "Ende der Auszeit+": "09.10.2024 17:16:30",
            "Dauer": "04:00:01",
            "Valid?": "No",
            "Action": "Fixed",
            "start_time": "09.10.2024 13:16:10",
            "end_time": "09.10.2024 18:00:00",
            "rule_applied": "2",
            "description": "Customer was reached, but is in a meeting and will call back after checking the modem reset. Handling is postponed at customer's request.",
            "evidence": "Start Evidence: Herr Büttner ist unter der Nummer 069/6773289155 erreicht. Er hat noch nicht geprueft, ob seitdem Modemreset eine Verbesserung gibt. Es sollte auch kein Reset bevor Absprache durchgefuehrt werden. Er hat gerade auch ein Meeting und meldet sich bei uns sobald es erledigt ist. | End Evidence: End of day fallback (no explicit time or valid event on same day)",
            "duration time": "04:43:50"
        },
        {
            "TA-Ticketnr.": "TA0000017322420",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "04.03.2025 13:22:27",
            "end_time": "05.03.2025 08:00:00",
            "rule_applied": "7",
            "description": "Customer stated they will test the line tomorrow, so ticket is pending for customer action.",
            "evidence": "Start Evidence: asp unter 069/6773289155< kd wird morgen testen | End Evidence: Customer said 'morgen' (tomorrow), so fallback to 08:00:00 next day",
            "duration time": "18:37:33"
        },
        {
            "TA-Ticketnr.": "TA0000017322420",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "05.03.2025 16:08:56",
            "end_time": "06.03.2025 11:57:17",
            "rule_applied": "7",
            "description": "Customer will perform a new speed test and provide feedback; pending until customer responds.",
            "evidence": "Start Evidence: [05.03.2025 16:08:56 | er wird einen neuen Speedtest machen und uns ein Feedback geben. TA bis dahin anhalten.] | End Evidence: [06.03.2025 11:57:17 | asp unter 0175/1854182 - speed tests war unter 200 Mbit]",
            "duration time": "19:48:21"
        },
        {
            "TA-Ticketnr.": "TA0000017508689",
            "Auszeit-ID": "AU0000018505794",
            "Grund": "Terminvereinbarung mit dem Kunden erfolgt. (TBK-LE)",
            "Beginn der Auszeit+": "25.07.2025 16:40:40",
            "Ende der Auszeit+": "28.07.2025 09:00:00",
            "Dauer": "2.680092592592592",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "25.07.2025 16:40:06",
            "end_time": "28.07.2025 08:00:00",
            "rule_applied": "2",
            "description": "Customer explicitly requested to be called back on Monday, causing a pending time until the next business day at 08:00.",
            "evidence": "Start Evidence: Frau Koch ist unter der Rufnummer 0172/2803780 erreichbar. sie teilet mit, dass besser am Montag sie zurueckzuruefen. | End Evidence: Fallback to 08:00:00 on requested day (Monday, 28.07.2025)",
            "duration time": "63:19:54"
        },
        {
            "TA-Ticketnr.": "TA0000017508689",
            "Auszeit-ID": "AU0000018326712",
            "Grund": "Kunde nicht erreichbar",
            "Beginn der Auszeit+": "12.03.2025 16:30:11",
            "Ende der Auszeit+": "13.03.2025 10:30:11",
            "Dauer": "18:00:00",
            "Valid?": "No",
            "Action": "Deleted",
            "start_time": "12.03.2025 16:30:11",
            "end_time": "13.03.2025 10:30:11",
            "rule_applied": "N/A",
            "description": "Kunde nicht erreichbar",
            "evidence": "N/A",
            "duration time": "18:00:00"
        },
        {
            "TA-Ticketnr.": "TA0000017595444",
            "Auszeit-ID": "AU0000018414147",
            "Grund": "Kunde nicht erreichbar",
            "Beginn der Auszeit+": "16.05.2025 11:46:27",
            "Ende der Auszeit+": "16.05.2025 15:17:22",
            "Dauer": "03:30:55",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "16.05.2025 11:46:27",
            "end_time": "16.05.2025 13:16:43",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone (Abschlussmeldung, erreicht: nicht erreicht), ticket cannot proceed until next successful contact.",
            "evidence": "Start Evidence: Grund: Abschlussmeldung ... erreicht: nicht erreicht | End Evidence: 16.05.2025 13:16:43 ... erreicht: erreicht",
            "duration time": "01:30:16"
        },
        {
            "TA-Ticketnr.": "TA0000017595444",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "19.05.2025 11:01:37",
            "end_time": "20.05.2025 08:00:00",
            "rule_applied": "7",
            "description": "Customer will test today and report back by tomorrow; ticket pending on customer feedback/testing.",
            "evidence": "Start Evidence: ... wird der Kunde heute den ganzen Tag testen und bis morgen sich bei mir melden ... | End Evidence: Fallback to 20.05.2025 08:00:00 (customer said 'bis morgen')",
            "duration time": "20:58:23"
        },
        {
            "TA-Ticketnr.": "TA0000017595444",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "23.05.2025 13:28:51",
            "end_time": "27.05.2025 09:38:52",
            "rule_applied": "7",
            "description": "Customer has not yet tested the instructions and needs more time until next week; ticket is on hold until customer responds.",
            "evidence": "Start Evidence: Herr Michael Kupsch ist unter 0203/30001202 erreicht. Er hat die Anweisungen noch nicht getestet und braucht noch Zeit bis naechste Woche. Dann wird er sich bei uns im Ticket anmelden. TA bis dahin offen unter Beobachtung. | End Evidence: Herr Kupsch unter 0203/30001202 erreicht und meint, dass mit dem Chat Bot scheint behoben zu sein aber er ist am Testen.",
            "duration time": "92:10:01"
        },
        {
            "TA-Ticketnr.": "TA0000017595444",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "03.06.2025 12:00:16",
            "end_time": "04.06.2025 08:00:00",
            "rule_applied": "2",
            "description": "Customer is not available today and will be back tomorrow; follow-up is scheduled for the next day.",
            "evidence": "Start Evidence: Herr Kupsch unter 0203/30001202 angerufen aber er ist erst morgen wieder im Hause. Wir melden uns bei ihm morgen wieder | End Evidence: Fallback to 08:00:00 on 04.06.2025 (customer said 'erst morgen wieder im Hause')",
            "duration time": "19:59:44"
        },
        {
            "TA-Ticketnr.": "TA0000017621989",
            "Auszeit-ID": "N/A",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "",
            "start_time": "",
            "end_time": "",
            "rule_applied": "",
            "description": "",
            "evidence": "",
            "duration time": ""
        },
        {
            "TA-Ticketnr.": "TA0000017641940",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "27.06.2025 16:22:30",
            "end_time": "27.06.2025 16:38:32",
            "rule_applied": "7",
            "description": "Pending for customer to provide call examples for troubleshooting.",
            "evidence": "Start Evidence: Wir benötigen mindestens 2 bis 3 Anrufbeispiele ... | End Evidence: 27.06.2025 16:38:32 AR_SERVER ... hier die gewünschten Callbeispiele",
            "duration time": "00:16:02"
        },
        {
            "TA-Ticketnr.": "TA0000017641940",
            "Auszeit-ID": "AU0000018470966",
            "Grund": "keine Aktivitäten seitens Vodafone erforderlich/möglich",
            "Beginn der Auszeit+": "27.06.2025 17:30:00",
            "Ende der Auszeit+": "30.06.2025 15:00:00",
            "Dauer": "2.895833333333333",
            "Valid?": "No",
            "Action": "Fixed",
            "start_time": "27.06.2025 17:30:34",
            "end_time": "01.07.2025 12:56:49",
            "rule_applied": "7",
            "description": "Pending for customer to provide Admin Center extracts as agreed.",
            "evidence": "Start Evidence: Herr Obser stellt und Montag Auszüge aus dem Admin Center zur Verfügung. Bis dahin kann Auszeit gesetzt werden. | End Evidence: 01.07.2025 12:56:49 AR_SERVER ... wie erbeten haben wir noch im Teams Admin Tool geschaut ...",
            "duration time": "91:26:15"
        },
        {
            "TA-Ticketnr.": "TA0000017641940",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "09.07.2025 12:40:00",
            "end_time": "09.07.2025 12:43:22",
            "rule_applied": "1",
            "description": "Pending due to customer not reachable for technician appointment.",
            "evidence": "Start Evidence: ASP unter beide RN nicht erreicht für Terminvereinbarung. | End Evidence: 09.07.2025 12:43:22 ali.magdy ... Herr Obser unter 01511/6112306 erreicht. KD ist mit Packet Recording einverstanden. Termin morgen ...",
            "duration time": "00:03:22"
        },
        {
            "TA-Ticketnr.": "TA0000017641940",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "14.07.2025 15:59:45",
            "end_time": "14.07.2025 16:20:54",
            "rule_applied": "2",
            "description": "Pending due to customer callback request for new appointment.",
            "evidence": "Start Evidence: Grund für Rückrufwunsch: Neue Terminvereinbarung für Aufzeichnung ... | End Evidence: 14.07.2025 16:20:54 ahmed.elesawy ... Einen neuen Termin haben wir vereinbart ...",
            "duration time": "00:21:09"
        },
        {
            "TA-Ticketnr.": "TA0000017641940",
            "Auszeit-ID": "AU0000018490829",
            "Grund": "Terminvereinbarung mit dem Kunden erfolgt. (TBK-LE)",
            "Beginn der Auszeit+": "14.07.2025 16:20:59",
            "Ende der Auszeit+": "15.07.2025 12:20:59",
            "Dauer": "20:00:00",
            "Valid?": "No",
            "Action": "Fixed",
            "start_time": "14.07.2025 16:22:47",
            "end_time": "15.07.2025 12:00:00",
            "rule_applied": "12",
            "description": "Pending for customer appointment for packet recording as agreed.",
            "evidence": "Start Evidence: Termin für ein Packet-Recording mit Kunde vereinbart für Morgen 15.07 von 11 bis 12 Uhr | End Evidence: End of agreed window (15.07.2025 12:00:00)",
            "duration time": "19:37:13"
        },
        {
            "TA-Ticketnr.": "TA0000017641940",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "16.07.2025 14:54:58",
            "end_time": "16.07.2025 17:00:00",
            "rule_applied": "7",
            "description": "Pending for customer to provide further test examples in agreed window.",
            "evidence": "Start Evidence: Wir würden heute zwischen 16:30 und 17:00 Uhr versuchen weitere Beispiele zu generieren ... | End Evidence: End of agreed window (16.07.2025 17:00:00)",
            "duration time": "02:05:02"
        },
        {
            "TA-Ticketnr.": "TA0000017664078",
            "Auszeit-ID": "N/A",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "",
            "start_time": "",
            "end_time": "",
            "rule_applied": "",
            "description": "",
            "evidence": "",
            "duration time": ""
        },
        {
            "TA-Ticketnr.": "TA0000017664078",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "05.08.2025 10:32:13",
            "end_time": "19.08.2025 08:00:00",
            "rule_applied": "2",
            "description": "Customer requested to keep the ticket open and will test internally, asking for follow-up only after 19 Aug.",
            "evidence": "Start Evidence: [05.08.2025 10:32:13 | Er hat gesagt, er moechte das Ticket bis 2 oder 3 Wochen so oeffen lassen. Er testet noch und passt was intern an. Wir warten auf eine Rueckmeldung von ihm erst bis 19 Aug.] | End Evidence: [Specific future day requested: 19 Aug, fallback to 08:00:00]",
            "duration time": "21:27:47"
        },
        {
            "TA-Ticketnr.": "TA0000017664078",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "19.08.2025 14:11:58",
            "end_time": "22.08.2025 08:00:00",
            "rule_applied": "7",
            "description": "Customer requested more time to test until Friday.",
            "evidence": "Start Evidence: [19.08.2025 14:11:58 | Er hat gesagt, er braucht noch Zeit bis Freitag. Er testet noch.] | End Evidence: [Freitag (22.08.2025) with no explicit hour, so 08:00:00]",
            "duration time": "17:48:02"
        },
        {
            "TA-Ticketnr.": "TA0000017664078",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "22.08.2025 12:17:18",
            "end_time": "22.08.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for function confirmation; ticket cannot proceed.",
            "evidence": "Start Evidence: [22.08.2025 12:17:18 | erreicht: nicht erreicht | Grund: Abschlussmeldung] | End Evidence: [22.08.2025 18:00:00 (End of day fallback, no successful interaction after 4 minutes)]",
            "duration time": "05:42:42"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018467405",
            "Grund": "Entstörung in Abstimmung mit Kunden auf späteren Zeitpunkt verschoben",
            "Beginn der Auszeit+": "25.06.2025 14:08:55",
            "Ende der Auszeit+": "26.06.2025 09:16:00",
            "Dauer": "19:07:05",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "25.06.2025 14:08:59",
            "end_time": "26.06.2025 14:00:00",
            "rule_applied": "9",
            "description": "Technician appointment window scheduled per customer request.",
            "evidence": "Start Evidence: [25.06.2025 14:08:59 | Wunsch-Termin einen Techniker beauftragt: am 26.06.2025 von 14:00 bis 20:00 Uhr] | End Evidence: [26.06.2025 14:00:00 (Window Start)]",
            "duration time": "23:51:01"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018469832",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "27.06.2025 08:22:57",
            "Ende der Auszeit+": "01.07.2025 10:00:00",
            "Dauer": "4.0673958333333333",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "27.06.2025 08:22:57",
            "end_time": "01.07.2025 10:00:00",
            "rule_applied": "11",
            "description": "SLA pause per agreement with customer; no troubleshooting required in this period.",
            "evidence": "Start Evidence: [27.06.2025 08:22:57 | Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.] | End Evidence: [01.07.2025 10:00:00 (Next explicit appointment/ETA)]",
            "duration time": "97:37:03"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018472482",
            "Grund": "Entstörung in Abstimmung mit Kunden auf späteren Zeitpunkt verschoben",
            "Beginn der Auszeit+": "01.07.2025 13:01:27",
            "Ende der Auszeit+": "01.07.2025 14:01:29",
            "Dauer": "01:00:02",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "01.07.2025 13:01:40",
            "end_time": "02.07.2025 08:00:00",
            "rule_applied": "9",
            "description": "Technician appointment window scheduled per customer request.",
            "evidence": "Start Evidence: [01.07.2025 13:01:40 | Wunsch-Termin einen Techniker beauftragt: am 02.07.2025 von 08:00 bis 14:00 Uhr] | End Evidence: [02.07.2025 08:00:00 (Window Start)]",
            "duration time": "18:58:20"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018472614",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "01.07.2025 14:01:30",
            "Ende der Auszeit+": "01.07.2025 14:41:49",
            "Dauer": "00:40:19",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "01.07.2025 14:03:49",
            "end_time": "02.07.2025 08:00:00",
            "rule_applied": "10",
            "description": "System ETA provided for next action.",
            "evidence": "Start Evidence: [01.07.2025 14:03:49 | ETA: 02.07.2025 08:00:00] | End Evidence: [02.07.2025 08:00:00 (ETA)]",
            "duration time": "17:56:11"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018474829",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "02.07.2025 20:33:19",
            "Ende der Auszeit+": "03.07.2025 18:00:00",
            "Dauer": "21:26:41",
            "Valid?": "No",
            "Action": "Kept",
            "start_time": "02.07.2025 20:33:58",
            "end_time": "03.07.2025 18:00:00",
            "rule_applied": "9",
            "description": "Technician appointment scheduled per customer request.",
            "evidence": "Start Evidence: [02.07.2025 20:33:58 | Grund: Terminvereinbarung | Kunde wurde kontaktiert. Termin vereinbart für:] | End Evidence: [03.07.2025 18:00:00 mit Techniker hat den Termin selbst abgestimmt]",
            "duration time": "21:26:02"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018476806",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "04.07.2025 10:08:47",
            "Ende der Auszeit+": "04.07.2025 10:10:08",
            "Dauer": "00:01:21",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "04.07.2025 10:09:56",
            "end_time": "04.07.2025 12:00:00",
            "rule_applied": "9",
            "description": "Technician appointment scheduled per customer request.",
            "evidence": "Start Evidence: [04.07.2025 10:09:56 | Grund: Terminvereinbarung | Kunde wurde kontaktiert. Termin vereinbart für:] | End Evidence: [04.07.2025 12:00:00 mit unter vorbehalt]",
            "duration time": "01:50:04"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018477052",
            "Grund": "Entstörung in Abstimmung mit Kunden auf späteren Zeitpunkt verschoben",
            "Beginn der Auszeit+": "04.07.2025 12:14:30",
            "Ende der Auszeit+": "08.07.2025 08:00:00",
            "Dauer": "3.823263888888889",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "04.07.2025 12:15:05",
            "end_time": "08.07.2025 08:00:00",
            "rule_applied": "9",
            "description": "Technician appointment window scheduled per customer request.",
            "evidence": "Start Evidence: [04.07.2025 12:15:05 | wir haben für Ihren Wunsch-Termin einen Techniker beauftragt: am 08.07.2025 von 08:00 bis 14:00 Uhr.] | End Evidence: [08.07.2025 08:00:00 (Window Start)]",
            "duration time": "91:44:55"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018495244",
            "Grund": "Entstörung in Abstimmung mit Kunden auf späteren Zeitpunkt verschoben",
            "Beginn der Auszeit+": "17.07.2025 17:40:19",
            "Ende der Auszeit+": "18.07.2025 14:00:00",
            "Dauer": "18:19:41",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "17.07.2025 17:40:26",
            "end_time": "18.07.2025 14:00:00",
            "rule_applied": "9",
            "description": "Technician appointment window scheduled per customer request.",
            "evidence": "Start Evidence: [17.07.2025 17:40:26 | wir haben für Ihren Wunsch-Termin einen Techniker beauftragt: am 18.07.2025 von 14:00 bis 20:00 Uhr.] | End Evidence: [18.07.2025 14:00:00 (Window Start)]",
            "duration time": "20:19:34"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018499210",
            "Grund": "Entstörung in Abstimmung mit Kunden auf späteren Zeitpunkt verschoben",
            "Beginn der Auszeit+": "21.07.2025 11:27:56",
            "Ende der Auszeit+": "22.07.2025 08:00:00",
            "Dauer": "20:32:04",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "21.07.2025 11:28:03",
            "end_time": "22.07.2025 08:00:00",
            "rule_applied": "9",
            "description": "Technician appointment window scheduled per customer request.",
            "evidence": "Start Evidence: [21.07.2025 11:28:03 | wir haben für Ihren Wunsch-Termin einen Techniker beauftragt: am 22.07.2025 von 08:00 bis 14:00 Uhr.] | End Evidence: [22.07.2025 08:00:00 (Window Start)]",
            "duration time": "20:31:57"
        },
        {
            "TA-Ticketnr.": "TA0000017642768",
            "Auszeit-ID": "AU0000018492227",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "15.07.2025 15:26:30",
            "Ende der Auszeit+": "16.07.2025 15:26:30",
            "Dauer": "1",
            "Valid?": "No",
            "Action": "Fixed",
            "start_time": "15.07.2025 15:24:31",
            "end_time": "22.07.2025 10:00:00",
            "rule_applied": "10",
            "description": "System ETA provided for technician arrival.",
            "evidence": "Start Evidence: [15.07.2025 15:24:31 | ETA: 22.07.2025 10:00:00] | End Evidence: [22.07.2025 10:00:00 (ETA)]",
            "duration time": "162:35:29"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "AU0000018531127",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "14.08.2025 13:56:45",
            "Ende der Auszeit+": "15.08.2025 09:27:48",
            "Dauer": "19:31:03",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "14.08.2025 13:56:27",
            "end_time": "15.08.2025 12:00:00",
            "rule_applied": "10",
            "description": "System delay with explicit ETA provided.",
            "evidence": "Start Evidence: [14.08.2025 13:56:27 ... ETA: 15.08.2025 12:00:00] | End Evidence: [ETA: 15.08.2025 12:00:00]",
            "duration time": "22:03:33"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "AU0000018531989",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "15.08.2025 09:27:49",
            "Ende der Auszeit+": "19.08.2025 12:00:00",
            "Dauer": "4.10568287037037",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "15.08.2025 09:26:06",
            "end_time": "19.08.2025 12:00:00",
            "rule_applied": "10",
            "description": "System delay with explicit ETA provided.",
            "evidence": "Start Evidence: [15.08.2025 09:26:06 ... ETA: 19.08.2025 12:00:00] | End Evidence: [ETA: 19.08.2025 12:00:00]",
            "duration time": "98:33:54"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "AU0000018540196",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "21.08.2025 08:39:56",
            "Ende der Auszeit+": "22.08.2025 12:00:00",
            "Dauer": "1.138935185185185",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "21.08.2025 08:38:54",
            "end_time": "22.08.2025 12:00:00",
            "rule_applied": "10",
            "description": "System delay with explicit ETA provided.",
            "evidence": "Start Evidence: [21.08.2025 08:38:54 ... ETA: 22.08.2025 12:00:00] | End Evidence: [ETA: 22.08.2025 12:00:00]",
            "duration time": "27:21:06"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "25.08.2025 09:39:11",
            "end_time": "25.08.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for final confirmation.",
            "evidence": "Start Evidence: [25.08.2025 09:39:11 ... erreicht: nicht erreicht] | End Evidence: [25.08.2025 18:00:00 (End of Day Fallback)]",
            "duration time": "08:20:49"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "AU0000018529639",
            "Grund": "Gemäß der Service Level Vereinbarung mit dem Kunden muß im ang. Zeitraum keine Entstörung stattfinden.",
            "Beginn der Auszeit+": "13.08.2025 13:52:39",
            "Ende der Auszeit+": "14.08.2025 12:00:00",
            "Dauer": "22:07:21",
            "Valid?": "Yes",
            "Action": "Kept",
            "start_time": "13.08.2025 13:52:39",
            "end_time": "14.08.2025 12:00:00",
            "rule_applied": "9",
            "description": "SLA Pause per customer agreement.",
            "evidence": "Start Evidence: [13.08.2025 13:52:39 ... Gemäß der Service Level Vereinbarung ...] | End Evidence: [14.08.2025 12:00:00 (Explicit Time)]",
            "duration time": "22:07:21"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "AU0000018512369",
            "Grund": "Kunde nicht erreichbar",
            "Beginn der Auszeit+": "30.07.2025 17:39:41",
            "Ende der Auszeit+": "31.07.2025 08:00:00",
            "Dauer": "14:20:19",
            "Valid?": "No",
            "Action": "Kept",
            "start_time": "30.07.2025 17:39:41",
            "end_time": "31.07.2025 08:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone; ticket could not proceed.",
            "evidence": "Start Evidence: [TA0000017694729 AU0000018512369 Kunde nicht erreichbar 30.07.2025 17:39:41] | End Evidence: [31.07.2025 08:00:00 (Explicit Time)]",
            "duration time": "14:20:19"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "27.08.2025 14:33:57",
            "end_time": "27.08.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for final confirmation; ticket could not proceed.",
            "evidence": "Start Evidence: [27.08.2025 14:33:57 Grund: Abschlussmeldung erreicht: nicht erreicht] | End Evidence: [Fallback to 18:00:00 (no valid phone contact outside 4 min window)]",
            "duration time": "03:26:03"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "28.08.2025 13:33:18",
            "end_time": "28.08.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for final confirmation; ticket could not proceed.",
            "evidence": "Start Evidence: [28.08.2025 13:33:18 Grund: Abschlussmeldung erreicht: nicht erreicht] | End Evidence: [Fallback to 18:00:00 (no valid phone contact outside 4 min window)]",
            "duration time": "04:26:42"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "29.08.2025 12:40:28",
            "end_time": "29.08.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for final confirmation; ticket could not proceed.",
            "evidence": "Start Evidence: [29.08.2025 12:40:28 Grund: Abschlussmeldung erreicht: nicht erreicht] | End Evidence: [Fallback to 18:00:00 (no valid phone contact outside 4 min window)]",
            "duration time": "05:19:32"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "01.09.2025 15:55:08",
            "end_time": "01.09.2025 17:17:58",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for final confirmation; ticket could not proceed.",
            "evidence": "Start Evidence: [01.09.2025 15:55:08 Grund: Abschlussmeldung erreicht: nicht erreicht] | End Evidence: [01.09.2025 17:17:58 Grund: Abschlussmeldung erreicht: erreicht]",
            "duration time": "01:22:50"
        },
        {
            "TA-Ticketnr.": "TA0000017694729",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "02.09.2025 10:16:31",
            "end_time": "02.09.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone for final confirmation; ticket could not proceed.",
            "evidence": "Start Evidence: [02.09.2025 10:16:31 Grund: Abschlussmeldung erreicht: nicht erreicht] | End Evidence: [Fallback to 18:00:00 (no valid phone contact outside 4 min window)]",
            "duration time": "07:43:29"
        },
        {
            "TA-Ticketnr.": "TA0000017666991",
            "Auszeit-ID": "AU0000018481797",
            "Grund": "Kunde nicht erreichbar",
            "Beginn der Auszeit+": "07.07.2025 20:35:44",
            "Ende der Auszeit+": "08.07.2025 09:00:00",
            "Dauer": "12:24:16",
            "Valid?": "Yes",
            "Action": "Fixed",
            "start_time": "07.07.2025 20:33:57",
            "end_time": "07.07.2025 18:00:00",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone, ticket pending until end of day.",
            "evidence": "Start Evidence: [07.07.2025 20:33:57 | erreicht: nicht erreicht] | End Evidence: [Fallback to 18:00:00 (End of Day)]",
            "duration time": "00:00:00"
        },
        {
            "TA-Ticketnr.": "TA0000017666991",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "08.07.2025 07:23:38",
            "end_time": "08.07.2025 07:25:13",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone; pending until next successful phone contact.",
            "evidence": "Start Evidence: [08.07.2025 07:23:38 | erreicht: nicht erreicht] | End Evidence: [08.07.2025 07:25:13 | erreicht: erreicht]",
            "duration time": "00:01:35"
        },
        {
            "TA-Ticketnr.": "TA0000017666991",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "09.07.2025 11:56:54",
            "end_time": "09.07.2025 12:03:59",
            "rule_applied": "7",
            "description": "Customer was asked to perform a network test and provide results; pending until customer provided the requested information.",
            "evidence": "Start Evidence: [09.07.2025 11:56:54 | Bitte führen Sie einen Netzwerktest durch, senden Sie uns einen Screenshot der Ergebnisse und hängen Sie es an das Ticket an.] | End Evidence: [09.07.2025 12:03:59 | Kunde teilt Zusatzinfo mit. Wie gewünscht. Anhang: ...network-test-highlights...]",
            "duration time": "00:07:05"
        },
        {
            "TA-Ticketnr.": "TA0000017666991",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "15.07.2025 08:15:38",
            "end_time": "15.07.2025 09:59:35",
            "rule_applied": "1",
            "description": "Customer was not reachable by phone, blocking further action until successful phone contact.",
            "evidence": "Start Evidence: [15.07.2025 08:15:38 | erreicht: nicht erreicht] | End Evidence: [15.07.2025 09:59:35 | erreicht: erreicht (phone)]",
            "duration time": "01:43:57"
        },
        {
            "TA-Ticketnr.": "TA0000017666991",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "16.07.2025 16:30:12",
            "end_time": "16.07.2025 18:00:00",
            "rule_applied": "7",
            "description": "Customer must test network at home or outside the company as requested.",
            "evidence": "Start Evidence: [16.07.2025 16:30:12 | Kunde muss im Heimnetz oder ausserhalb der Firma mal testen] | End Evidence: [Fallback to 18:00:00, no explicit end or customer response same day]",
            "duration time": "01:29:48"
        },
        {
            "TA-Ticketnr.": "TA0000017666991",
            "Auszeit-ID": "",
            "Grund": "",
            "Beginn der Auszeit+": "",
            "Ende der Auszeit+": "",
            "Dauer": "",
            "Valid?": "",
            "Action": "Added",
            "start_time": "22.07.2025 11:23:30",
            "end_time": "22.07.2025 18:00:00",
            "rule_applied": "7",
            "description": "Customer will test QOS and report back by end of day.",
            "evidence": "Start Evidence: [22.07.2025 11:23:30 | Kunde wird die QOS heute pruefen und bis Ende des Tags sich bei mir per Email melden] | End Evidence: [Fallback to 18:00:00, no explicit end or customer response same day]",
            "duration time": "06:36:30"
        }
        ]
        df = pd.DataFrame(data)
        # df = pd.read_excel(ai_validated_file)
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
render_analysis_page("gpt-4.1","Action_Output_PendingTimes.xlsx")