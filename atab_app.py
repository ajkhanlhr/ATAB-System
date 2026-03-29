import streamlit as st
import sqlite3
import pypdf
from docx import Document
import google.generativeai as genai
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime

# --- PROFESSIONAL UI CONFIG ---
st.set_page_config(page_title="ATAB System", page_icon="🎓", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stButton>button {width: 100%; border-radius: 5px; height: 3em; background-color: #0e1117; color: white;}
    </style>
    """, unsafe_allow_html=True)

# 1. BRAIN CONFIG
api_key = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=api_key)

# 2. DATABASE INIT (Version-Independent Storage)
def init_db():
    conn = sqlite3.connect('atab_memory.db', check_same_thread=False)
    c = conn.cursor()
    # Student Info Archive (Stores everyone permanently)
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (roll_no TEXT PRIMARY KEY, name TEXT, session TEXT, course TEXT)''')
    # Evaluation Records (Stores all history permanently)
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations 
                 (roll_no TEXT, session TEXT, course TEXT, type TEXT, attribute TEXT, 
                  score INTEGER, feedback TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # Metadata for dropdowns
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (category TEXT, value TEXT, UNIQUE(category, value))''')
    # Custom Rubrics
    c.execute('''CREATE TABLE IF NOT EXISTS rubrics (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT)''')
    
    # Self-Healing column check
    try:
        c.execute("ALTER TABLE evaluations ADD COLUMN type TEXT")
    except sqlite3.OperationalError: pass
        
    conn.commit()
    conn.close()

def get_meta(cat):
    conn = sqlite3.connect('atab_memory.db')
    df = pd.read_sql_query("SELECT value FROM metadata WHERE category=?", conn, params=(cat,))
    conn.close()
    return df['value'].tolist()

def add_meta(cat, val):
    conn = sqlite3.connect('atab_memory.db')
    try:
        conn.execute("INSERT INTO metadata (category, value) VALUES (?, ?)", (cat, val))
        conn.commit()
    except: pass
    conn.close()

# 3. KNOWLEDGE PROCESSING
def extract_text(uploaded_file):
    try:
        if uploaded_file.type == "application/pdf":
            return "".join([page.extract_text() for page in pypdf.PdfReader(uploaded_file).pages])
        elif "wordprocessingml" in uploaded_file.type:
            doc = Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs])
        else:
            return str(uploaded_file.read(), "utf-8")
    except Exception as e: return f"Error: {e}"

# 4. MAIN APP
def main():
    init_db()
    if 'kb_files' not in st.session_state: st.session_state['kb_files'] = {}

    st.sidebar.title("🎓 ATAB System")
    app_mode = st.sidebar.selectbox("Access Mode", ["Instructor View", "Student View"])
    
    # --- DYNAMIC SIDEBAR FILTERS ---
    s_list = get_meta('session') + ["Add New"]
    sel_session = st.sidebar.selectbox("Academic Session", s_list)
    if sel_session == "Add New":
        ns = st.sidebar.text_input("New Session Name")
        if st.sidebar.button("Register Session"):
            if ns: add_meta('session', ns); st.rerun()

    c_list = get_meta('course') + ["Add New"]
    sel_course = st.sidebar.selectbox("Course Code", c_list)
    if sel_course == "Add New":
        nc = st.sidebar.text_input("New Course Code")
        if st.sidebar.button("Register Course"):
            if nc: add_meta('course', nc); st.rerun()

    # --- INSTRUCTOR VIEW ---
    if app_mode == "Instructor View":
        st.title(f"👨‍🏫 Instructor: {sel_course} ({sel_session})")
        tabs = st.tabs(["Archives & Knowledge", "Rubric Upgrades", "Class Analytics", "Complete Evaluation History"])

        with tabs[0]:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Student Archive Upload")
                csv_file = st.file_uploader("Upload Student List (CSV)", type=["csv"], key="csv_uploader")
                if csv_file:
                    df_s = pd.read_csv(csv_file)
                    df_s.columns = df_s.columns.str.strip().str.lower().str.replace(' ', '_')
                    col_map = {'roll_number': 'roll_no', 'rollno': 'roll_no', 'id': 'roll_no', 'student_name': 'name', 'full_name': 'name'}
                    df_s = df_s.rename(columns=col_map)

                    if 'roll_no' in df_s.columns and 'name' in df_s.columns:
                        conn = sqlite3.connect('atab_memory.db')
                        # "INSERT OR REPLACE" keeps data persistent across app updates
                        for _, r in df_s.iterrows():
                            conn.execute("INSERT OR REPLACE INTO students (roll_no, name, session, course) VALUES (?,?,?,?)", 
                                         (str(r['roll_no']), r['name'], sel_session, sel_course))
                        conn.commit(); conn.close()
                        st.success(f"Archived {len(df_s)} students for {sel_course}.")
                    else: st.error("CSV error: Use 'Roll No' and 'Name' headers.")
            
            with col2:
                st.subheader("Knowledge Archive")
                kb = st.file_uploader("Upload Materials", accept_multiple_files=True)
                if kb:
                    for f in kb: st.session_state['kb_files'][f.name] = extract_text(f)
                    st.success(f"Knowledge Base active.")

        with tabs[1]:
            st.subheader("Upgrade Rubrics")
            new_r_name = st.text_input("Rubric Title")
            new_r_desc = st.text_area("Scoring Logic (1-5)")
            if st.button("Save New Rubric"):
                conn = sqlite3.connect('atab_memory.db')
                conn.execute("INSERT INTO rubrics (name, description) VALUES (?,?)", (new_r_name, new_r_desc))
                conn.commit(); conn.close()
                st.success("Custom Rubric saved.")

        with tabs[2]:
            st.subheader("Analytics (Active Selection)")
            conn = sqlite3.connect('atab_memory.db')
            query = "SELECT e.*, s.name FROM evaluations e JOIN students s ON e.roll_no = s.roll_no WHERE e.session=? AND e.course=?"
            df_ev = pd.read_sql_query(query, conn, params=(sel_session, sel_course))
            if not df_ev.empty:
                ranking = df_ev.groupby(['roll_no', 'name'])['score'].mean().sort_values(ascending=False)
                st.write("Top 5 Performance Ranking")
                st.table(ranking.head(5))
                fig, ax = plt.subplots(figsize=(10, 4))
                sns.heatmap(df_ev.pivot_table(index='name', columns='attribute', values='score'), annot=True, cmap="RdYlGn", ax=ax)
                st.pyplot(fig)
            else: st.info("Analytics will populate after evaluations begin.")
            conn.close()

        with tabs[3]:
            st.subheader("Complete Evaluation Ledger")
            conn = sqlite3.connect('atab_memory.db')
            # This query ensures EVERY student uploaded for this course appears, even with 0 evaluations
            ledger_query = """
            SELECT s.roll_no, s.name, e.attribute, e.score, e.feedback, e.timestamp 
            FROM students s 
            LEFT JOIN evaluations e ON s.roll_no = e.roll_no 
            WHERE s.session=? AND s.course=?
            """
            ledger_df = pd.read_sql_query(ledger_query, conn, params=(sel_session, sel_course))
            st.dataframe(ledger_df, use_container_width=True)
            
            # Export all data across ALL versions and classes
            if st.button("Export Entire Historical Archive"):
                full_archive = pd.read_sql_query("SELECT * FROM evaluations", conn)
                st.download_button("Download Full History (CSV)", full_archive.to_csv(index=False).encode('utf-8'), "Full_ATAB_Archive.csv")
            conn.close()

    # --- STUDENT VIEW ---
    else:
        st.title("🎓 Student Portal")
        s_roll = st.text_input("Login with Roll Number")
        if s_roll:
            conn = sqlite3.connect('atab_memory.db')
            s_data = conn.execute("SELECT name FROM students WHERE roll_no=?", (s_roll,)).fetchone()
            conn.close()
            if s_data:
                st.subheader(f"Welcome, {s_data[0]}")
                if st.button("Generate Exam"):
                    if st.session_state['kb_files']:
                        with st.spinner("Preparing exam..."):
                            full_ctx = "\n\n".join(st.session_state['kb_files'].values())
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            prompt = f"Using Context: {full_ctx[:15000]}\nGenerate 3 MCQs, 2 Short Questions, and 1 Essay Question."
                            resp = model.generate_content(prompt)
                            st.markdown(resp.text)
                    else: st.error("Knowledge base empty.")
            else: st.warning("Roll number not recognized in the Archive.")

if __name__ == "__main__":
    main()
