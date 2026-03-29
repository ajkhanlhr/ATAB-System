import streamlit as st
import sqlite3
import pypdf
from docx import Document
import google.generativeai as genai
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime

# --- UI CONFIG ---
st.set_page_config(page_title="ATAB System Pro", page_icon="🎓", layout="wide")

# 1. BRAIN CONFIG
api_key = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=api_key)

# 2. DATABASE INIT
def init_db():
    conn = sqlite3.connect('atab_memory.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (roll_no TEXT, name TEXT, session TEXT, course TEXT, PRIMARY KEY(roll_no, course, session))''')
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations 
                 (roll_no TEXT, session TEXT, course TEXT, type TEXT, attribute TEXT, 
                  score INTEGER, feedback TEXT, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (category TEXT, value TEXT, UNIQUE(category, value))''')
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
    
    # --- SIDEBAR FILTERS ---
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
        tabs = st.tabs(["Archives & Knowledge", "Class Analytics", "Complete Evaluation Ledger"])

        with tabs[0]:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Student Archive Upload")
                csv_file = st.file_uploader("Upload CSV (Roll No, Name)", type=["csv"])
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
                kb = st.file_uploader("Upload Materials", accept_multiple_files=True)
                if kb:
                    for f in kb: st.session_state['kb_files'][f.name] = extract_text(f)
                    st.success("Knowledge Base updated.")

        with tabs[1]:
            st.subheader("Performance Analytics")
            conn = sqlite3.connect('atab_memory.db')
            # Fixed Join to prevent cross-course data leakage
            query = """
            SELECT e.*, s.name FROM evaluations e 
            JOIN students s ON e.roll_no = s.roll_no AND e.course = s.course AND e.session = s.session
            WHERE e.session=? AND e.course=?
            """
            df_ev = pd.read_sql_query(query, conn, params=(sel_session, sel_course))
            if not df_ev.empty:
                ranking = df_ev.groupby(['roll_no', 'name'])['score'].mean().sort_values(ascending=False)
                st.table(ranking.head(5))
                fig, ax = plt.subplots(figsize=(10, 4))
                sns.heatmap(df_ev.pivot_table(index='name', columns='attribute', values='score'), annot=True, cmap="RdYlGn", ax=ax)
                st.pyplot(fig)
            else: st.info("No assessment data available for this class.")
            conn.close()

        with tabs[2]:
            st.subheader("Complete Evaluation Ledger")
            conn = sqlite3.connect('atab_memory.db')
            # FIXED LEDGER QUERY: Isolates students strictly by Course and Session
            ledger_query = """
            SELECT s.roll_no, s.name, e.attribute, e.score, e.feedback, e.timestamp 
            FROM students s 
            LEFT JOIN evaluations e ON s.roll_no = e.roll_no AND s.course = e.course AND s.session = e.session
            WHERE s.session=? AND s.course=?
            ORDER BY s.roll_no ASC
            """
            ledger_df = pd.read_sql_query(ledger_query, conn, params=(sel_session, sel_course))
            st.dataframe(ledger_df, use_container_width=True)
            conn.close()

    # --- STUDENT VIEW ---
    else:
        st.title("🎓 Student Portal")
        s_roll = st.text_input("Enter Roll Number to Login")
        if s_roll:
            conn = sqlite3.connect('atab_memory.db')
            s_data = conn.execute("SELECT name, session, course FROM students WHERE roll_no=?", (s_roll,)).fetchone()
            conn.close()
            
            if s_data:
                st.subheader(f"Welcome, {s_data[0]} ({s_data[2]})")
                
                # Step 1: Generate Exam
                if st.button("Start New Exam"):
                    if st.session_state['kb_files']:
                        full_ctx = "\n\n".join(st.session_state['kb_files'].values())
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        prompt = f"Using Context: {full_ctx[:15000]}\nGenerate 3 MCQs, 2 Short Questions, and 1 Essay."
                        resp = model.generate_content(prompt)
                        st.session_state['current_exam'] = resp.text
                    else: st.error("No course materials uploaded.")
                
                if 'current_exam' in st.session_state:
                    st.markdown(st.session_state['current_exam'])
                    
                    # Step 2: Submit & Automated Grade
                    st.markdown("---")
                    st.subheader("Submit Your Answers")
                    student_submission = st.text_area("Paste your answers here...", height=200)
                    
                    if st.button("Submit & Grade My Exam"):
                        with st.spinner("ATAB is evaluating your Accuracy, Proficiency, and Depth..."):
                            full_ctx = "\n\n".join(st.session_state['kb_files'].values())
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            
                            grade_prompt = f"""
                            Course Material: {full_ctx[:10000]}
                            Student Submission: {student_submission}
                            
                            Evaluate this submission based on 3 distinct attributes:
                            1. Technical Accuracy (Knowledge of course facts)
                            2. English Proficiency (Grammar and clarity)
                            3. Analytical Depth (Critical thinking)
                            
                            Format your response STRICTLY as follows:
                            ATTR: Technical Accuracy | SCORE: [1-5] | FEED: [text]
                            ATTR: English Proficiency | SCORE: [1-5] | FEED: [text]
                            ATTR: Analytical Depth | SCORE: [1-5] | FEED: [text]
                            """
                            
                            grading_result = model.generate_content(grade_prompt).text
                            st.markdown("### Your Results")
                            st.write(grading_result)
                            
                            # Step 3: Parse and Append to Ledger automatically
                            conn = sqlite3.connect('atab_memory.db')
                            for line in grading_result.split('\n'):
                                if "ATTR:" in line:
                                    parts = line.split('|')
                                    attr = parts[0].replace("ATTR:", "").strip()
                                    score = int(parts[1].replace("SCORE:", "").strip())
                                    feed = parts[2].replace("FEED:", "").strip()
                                    
                                    conn.execute("INSERT INTO evaluations (roll_no, session, course, attribute, score, feedback, timestamp) VALUES (?,?,?,?,?,?,?)",
                                                 (s_roll, s_data[1], s_data[2], attr, score, feed, datetime.now()))
                            conn.commit(); conn.close()
                            st.success("Record updated in the Academic Ledger.")
            else:
                st.warning("Roll number not recognized.")

if __name__ == "__main__":
    main()
