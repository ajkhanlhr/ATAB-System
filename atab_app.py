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
st.set_page_config(page_title="ATAB System Pro", page_icon="🎓", layout="wide")

# 1. BRAIN CONFIG
api_key = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=api_key)

# 2. DATABASE INIT (With Persistent Schema)
def init_db():
    conn = sqlite3.connect('atab_memory.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (roll_no TEXT, name TEXT, session TEXT, course TEXT, PRIMARY KEY(roll_no, course, session))''')
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations 
                 (roll_no TEXT, session TEXT, course TEXT, type TEXT, attribute TEXT, 
                  score INTEGER, feedback TEXT, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (category TEXT, value TEXT, UNIQUE(category, value))''')
    c.execute('''CREATE TABLE IF NOT EXISTS rubrics 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT)''')
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
    
    # CRITICAL: Keep Knowledge Archive persistent in Session State
    if 'kb_files' not in st.session_state:
        st.session_state['kb_files'] = {}

    st.sidebar.title("🎓 ATAB System Control")
    app_mode = st.sidebar.selectbox("Access Mode", ["Instructor View", "Student View"])
    
    # SideBar Navigation Filters
    s_list = get_meta('session') + ["Add New"]
    sel_session = st.sidebar.selectbox("Academic Session", s_list)
    if sel_session == "Add New":
        ns = st.sidebar.text_input("New Session (e.g. SP2026)")
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
        
        # DEFINING ALL 4 SECTIONS
        tabs = st.tabs(["Archives & Knowledge", "Rubric Upgrades", "Class Analytics", "Complete Evaluation History"])

        # TAB 1: ARCHIVES
        with tabs[0]:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Student Info Archive")
                csv_file = st.file_uploader("Upload Student List (CSV)", type=["csv"], key="csv_up")
                if csv_file:
                    df_s = pd.read_csv(csv_file)
                    df_s.columns = df_s.columns.str.strip().str.lower().str.replace(' ', '_')
                    df_s = df_s.rename(columns={'roll_number': 'roll_no', 'id': 'roll_no', 'student_name': 'name', 'full_name': 'name'})
                    if 'roll_no' in df_s.columns and 'name' in df_s.columns:
                        conn = sqlite3.connect('atab_memory.db')
                        for _, r in df_s.iterrows():
                            conn.execute("INSERT OR REPLACE INTO students VALUES (?,?,?,?)", 
                                         (str(r['roll_no']), r['name'], sel_session, sel_course))
                        conn.commit(); conn.close()
                        st.success(f"Archived {len(df_s)} students for {sel_course}.")
            
            with col2:
                st.subheader("Knowledge Archive")
                kb = st.file_uploader("Add to Knowledge Base", accept_multiple_files=True, key="kb_up")
                if kb:
                    for f in kb:
                        st.session_state['kb_files'][f.name] = extract_text(f)
                    st.success(f"Knowledge Base now contains {len(st.session_state['kb_files'])} documents.")
                
                with st.expander("View Active Knowledge Assets"):
                    for fname in st.session_state['kb_files'].keys():
                        st.write(f"✅ {fname}")

        # TAB 2: RUBRIC UPGRADES
        with tabs[1]:
            st.subheader("Add or Modify Rubrics")
            r_name = st.text_input("Rubric Title")
            r_desc = st.text_area("Detail the 5-point scale criteria")
            if st.button("Save Rubric to ATAB"):
                conn = sqlite3.connect('atab_memory.db')
                conn.execute("INSERT INTO rubrics (name, description) VALUES (?,?)", (r_name, r_desc))
                conn.commit(); conn.close()
                st.success("New Rubric integrated.")

        # TAB 3: CLASS ANALYTICS
        with tabs[2]:
            st.subheader("Performance Visuals")
            conn = sqlite3.connect('atab_memory.db')
            query = """
            SELECT e.*, s.name FROM evaluations e 
            JOIN students s ON e.roll_no = s.roll_no AND e.course = s.course AND e.session = s.session
            WHERE e.session=? AND e.course=?
            """
            df_ev = pd.read_sql_query(query, conn, params=(sel_session, sel_course))
            if not df_ev.empty:
                ranking = df_ev.groupby(['roll_no', 'name'])['score'].mean().sort_values(ascending=False)
                st.write("**Top 5 Performers**")
                st.table(ranking.head(5))
                
                fig, ax = plt.subplots(figsize=(10, 4))
                sns.heatmap(df_ev.pivot_table(index='name', columns='attribute', values='score'), annot=True, cmap="RdYlGn", ax=ax)
                st.pyplot(fig)
            else: st.info("No assessment data to visualize yet.")
            conn.close()

        # TAB 4: EVALUATION HISTORY
        with tabs[3]:
            st.subheader("Complete Evaluation Ledger")
            conn = sqlite3.connect('atab_memory.db')
            ledger_query = """
            SELECT s.roll_no, s.name, e.attribute, e.score, e.feedback, e.timestamp 
            FROM students s 
            LEFT JOIN evaluations e ON s.roll_no = e.roll_no AND s.course = e.course AND s.session = e.session
            WHERE s.session=? AND s.course=?
            """
            ledger_df = pd.read_sql_query(ledger_query, conn, params=(sel_session, sel_course))
            st.dataframe(ledger_df, use_container_width=True)
            if not ledger_df.empty:
                csv = ledger_df.to_csv(index=False).encode('utf-8')
                st.download_button("Export Class Record (CSV)", csv, "Class_Ledger.csv")
            conn.close()

    # --- STUDENT VIEW ---
    else:
        st.title("🎓 Student Portal")
        s_roll = st.text_input("Login (Roll Number)")
        if s_roll:
            conn = sqlite3.connect('atab_memory.db')
            s_data = conn.execute("SELECT name, session, course FROM students WHERE roll_no=?", (s_roll,)).fetchone()
            conn.close()
            
            if s_data:
                st.subheader(f"Welcome, {s_data[0]}!")
                if st.button("Generate Exam"):
                    if st.session_state['kb_files']:
                        ctx = "\n\n".join(st.session_state['kb_files'].values())
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        p = f"Context: {ctx[:12000]}\nGenerate 3 MCQs, 2 Short Questions, 1 Essay."
                        st.session_state['exam_text'] = model.generate_content(p).text
                    else: st.error("No course materials found.")
                
                if 'exam_text' in st.session_state:
                    st.markdown(st.session_state['exam_text'])
                    ans = st.text_area("Submit your answers below:", height=200)
                    if st.button("Submit & Score"):
                        with st.spinner("Analyzing..."):
                            ctx = "\n\n".join(st.session_state['kb_files'].values())
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            grade_p = f"""
                            Context: {ctx[:8000]}
                            Student Ans: {ans}
                            Provide 3 scores (1-5) for: Technical Accuracy, English Proficiency, Analytical Depth.
                            Format: ATTR: [Name] | SCORE: [1-5] | FEED: [Text]
                            """
                            res = model.generate_content(grade_p).text
                            st.markdown(res)
                            # Automatic saving logic...
                            conn = sqlite3.connect('atab_memory.db')
                            for line in res.split('\n'):
                                if "ATTR:" in line:
                                    parts = line.split('|')
                                    at = parts[0].replace("ATTR:", "").strip()
                                    sc = int(parts[1].replace("SCORE:", "").strip())
                                    fd = parts[2].replace("FEED:", "").strip()
                                    conn.execute("INSERT INTO evaluations (roll_no, session, course, attribute, score, feedback, timestamp) VALUES (?,?,?,?,?,?,?)",
                                                 (s_roll, s_data[1], s_data[2], at, sc, fd, datetime.now()))
                            conn.commit(); conn.close()
                            st.success("Results recorded in History.")
            else: st.warning("Roll number unrecognized.")

if __name__ == "__main__":
    main()
