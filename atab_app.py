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
    if 'kb_files' not in st.session_state:
        st.session_state['kb_files'] = {}

    st.sidebar.title("🎓 ATAB Control")
    app_mode = st.sidebar.selectbox("Access Mode", ["Instructor View", "Student View"])
    
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

    if app_mode == "Instructor View":
        st.title(f"👨‍🏫 Instructor: {sel_course} ({sel_session})")
        
        # ADDED "Edit / Delete" TAB
        tabs = st.tabs(["Archives & Knowledge", "Edit & Clean Archive", "Rubric Upgrades", "Class Analytics", "Evaluation History"])

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
                        st.success(f"Archived {len(df_s)} students.")
                
                # NEW: LIST OF CLASSES ALREADY UPLOADED
                st.markdown("---")
                st.write("**📂 Existing Class Lists in Archive:**")
                conn = sqlite3.connect('atab_memory.db')
                existing_classes = pd.read_sql_query("SELECT DISTINCT session, course FROM students", conn)
                if not existing_classes.empty:
                    for idx, row in existing_classes.iterrows():
                        st.info(f"Class: {row['course']} | Session: {row['session']}")
                else: st.write("No lists uploaded yet.")
                conn.close()
            
            with col2:
                st.subheader("Knowledge Archive")
                kb = st.file_uploader("Add to Knowledge Base", accept_multiple_files=True, key="kb_up")
                if kb:
                    for f in kb: st.session_state['kb_files'][f.name] = extract_text(f)
                    st.success("Knowledge Base Updated.")
                
                with st.expander("View Active Knowledge Assets"):
                    for fname in st.session_state['kb_files'].keys():
                        st.write(f"✅ {fname}")

        # NEW TAB 2: EDIT & CLEAN ARCHIVE
        with tabs[1]:
            st.subheader("Manage & Clean Student Records")
            conn = sqlite3.connect('atab_memory.db')
            current_archive = pd.read_sql_query("SELECT * FROM students WHERE session=? AND course=?", conn, params=(sel_session, sel_course))
            
            if not current_archive.empty:
                st.write(f"Currently viewing {len(current_archive)} students in {sel_course}.")
                # Multi-select for deletion
                to_delete = st.multiselect("Select Students to Remove (Roll No - Name)", 
                                           options=[f"{r} - {n}" for r, n in zip(current_archive['roll_no'], current_archive['name'])])
                
                if st.button("🗑️ Delete Selected from Archive"):
                    c = conn.cursor()
                    for item in to_delete:
                        r_to_del = item.split(" - ")[0]
                        c.execute("DELETE FROM students WHERE roll_no=? AND course=? AND session=?", (r_to_del, sel_course, sel_session))
                    conn.commit()
                    st.warning("Archive cleaned. Reloading...")
                    st.rerun()
                
                if st.button("🔥 Wipe Entire Class List"):
                    conn.execute("DELETE FROM students WHERE course=? AND session=?", (sel_course, sel_session))
                    conn.commit()
                    st.rerun()
            else: st.info("This course archive is currently clean (empty).")
            conn.close()

        # TAB 3: RUBRIC UPGRADES
        with tabs[2]:
            st.subheader("Add or Modify Rubrics")
            r_name = st.text_input("Rubric Title")
            r_desc = st.text_area("Detail the 5-point scale criteria")
            if st.button("Save Rubric"):
                conn = sqlite3.connect('atab_memory.db')
                conn.execute("INSERT INTO rubrics (name, description) VALUES (?,?)", (r_name, r_desc))
                conn.commit(); conn.close()
                st.success("Rubric added.")

        # TAB 4: CLASS ANALYTICS
        with tabs[3]:
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
                st.table(ranking.head(5))
                fig, ax = plt.subplots(figsize=(10, 4))
                sns.heatmap(df_ev.pivot_table(index='name', columns='attribute', values='score'), annot=True, cmap="RdYlGn", ax=ax)
                st.pyplot(fig)
            else: st.info("No assessment data available.")
            conn.close()

        # TAB 5: EVALUATION HISTORY
        with tabs[4]:
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
                            grade_p = f"Evaluate Technical Accuracy, English Proficiency, and Analytical Depth. Context: {ctx[:8000]}\nAns: {ans}\nFormat: ATTR: [Name] | SCORE: [1-5] | FEED: [Text]"
                            res = model.generate_content(grade_p).text
                            st.markdown(res)
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
                            st.success("Results recorded.")
            else: st.warning("Roll number unrecognized.")

if __name__ == "__main__":
    main()
