import streamlit as st
import sqlite3
import pypdf
from docx import Document
import google.generativeai as genai
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import datetime

# --- UI CONFIG ---
st.set_page_config(page_title="ATAB Visual Pro", page_icon="🎓", layout="wide")

# 1. BRAIN CONFIG
api_key = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=api_key)

# 2. DATABASE INIT
def init_db():
    conn = sqlite3.connect('atab_memory.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (roll_no TEXT, name TEXT, session TEXT, course TEXT, 
                  PRIMARY KEY(roll_no, course, session))''')
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations 
                 (roll_no TEXT, session TEXT, course TEXT, attribute TEXT, 
                  score INTEGER, feedback TEXT, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (category TEXT, value TEXT, UNIQUE(category, value))''')
    c.execute('''CREATE TABLE IF NOT EXISTS rubrics (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT)''')
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

    st.sidebar.title("🎓 ATAB Visual Pro")
    app_mode = st.sidebar.selectbox("Access Mode", ["Student View", "Instructor View"])
    
    # Global Filters
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
        st.title(f"📊 Instructor Dashboard: {sel_course}")
        tabs = st.tabs(["Archives & Knowledge", "Manage Student Lists", "Rubrics", "Analytics & Ledger", "Visual Performance"])

        with tabs[0]:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Import Students")
                csv_file = st.file_uploader("Upload CSV", type=["csv"], key="csv")
                if csv_file:
                    df = pd.read_csv(csv_file)
                    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
                    df = df.rename(columns={'roll_number': 'roll_no', 'id': 'roll_no', 'student_name': 'name', 'full_name': 'name'})
                    if 'roll_no' in df.columns and 'name' in df.columns:
                        conn = sqlite3.connect('atab_memory.db')
                        for _, r in df.iterrows():
                            conn.execute("INSERT OR REPLACE INTO students VALUES (?,?,?,?)", (str(r['roll_no']), r['name'], sel_session, sel_course))
                        conn.commit(); conn.close()
                        st.success("Archive Updated.")
            with col2:
                st.subheader("Knowledge Ingestion")
                kb = st.file_uploader("Upload Files", accept_multiple_files=True)
                if kb:
                    for f in kb: st.session_state['kb_files'][f.name] = extract_text(f)
                    st.success("Brain Updated.")

        with tabs[1]:
            st.subheader("Current Archive Status")
            conn = sqlite3.connect('atab_memory.db')
            current_list = pd.read_sql_query("SELECT roll_no, name FROM students WHERE session=? AND course=?", conn, params=(sel_session, sel_course))
            st.dataframe(current_list, use_container_width=True)
            if st.button("Clean Current Selection"):
                conn.execute("DELETE FROM students WHERE course=? AND session=?", (sel_course, sel_session))
                conn.commit(); st.rerun()
            conn.close()

        with tabs[2]:
            st.subheader("Rubric Settings")
            r_n = st.text_input("Rubric Name")
            r_d = st.text_area("Criteria Description")
            if st.button("Save"):
                conn = sqlite3.connect('atab_memory.db')
                conn.execute("INSERT INTO rubrics (name, description) VALUES (?,?)", (r_n, r_d))
                conn.commit(); conn.close(); st.success("Saved.")

        with tabs[3]:
            st.subheader("Consolidated Ledger")
            conn = sqlite3.connect('atab_memory.db')
            query = """
            SELECT s.roll_no, s.name, e.attribute, e.score, e.feedback, e.timestamp 
            FROM students s 
            LEFT JOIN evaluations e ON s.roll_no = e.roll_no AND s.course = e.course AND s.session = e.session
            WHERE s.session=? AND s.course=?
            """
            master_df = pd.read_sql_query(query, conn, params=(sel_session, sel_course))
            st.dataframe(master_df, use_container_width=True)
            conn.close()

        with tabs[4]:
            st.subheader("Class Visual Performance Insights")
            if not master_df.dropna(subset=['score']).empty:
                col_v1, col_v2 = st.columns(2)
                
                with col_v1:
                    st.write("**Attribute Distribution (Average)**")
                    avg_scores = master_df.groupby('attribute')['score'].mean().reset_index()
                    fig_bar = px.bar(avg_scores, x='attribute', y='score', color='score', range_y=[0,5], color_continuous_scale="RdYlGn")
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                with col_v2:
                    st.write("**Student Capability Heatmap**")
                    fig_heat, ax = plt.subplots()
                    sns.heatmap(master_df.pivot_table(index='name', columns='attribute', values='score'), annot=True, cmap="RdYlGn", ax=ax)
                    st.pyplot(fig_heat)
            else:
                st.info("Visuals will appear once students begin evaluations.")

    # --- STUDENT VIEW ---
    else:
        st.title("🎓 Student Performance & Exam Portal")
        s_r = st.text_input("Login (Roll Number)")
        if s_r:
            conn = sqlite3.connect('atab_memory.db')
            user = conn.execute("SELECT name, session, course FROM students WHERE roll_no=?", (s_r,)).fetchone()
            if user:
                st.subheader(f"Welcome back, {user[0]}!")
                
                # --- INDIVIDUAL VISUAL FOR STUDENT ---
                my_data = pd.read_sql_query("SELECT attribute, AVG(score) as score FROM evaluations WHERE roll_no=? GROUP BY attribute", conn, params=(s_r,))
                if not my_data.empty and len(my_data) >= 3:
                    st.write("**My Learning Radar**")
                    fig_radar = px.line_polar(my_data, r='score', theta='attribute', line_close=True, range_r=[0,5])
                    fig_radar.update_traces(fill='toself')
                    st.plotly_chart(fig_radar, use_container_width=True)
                elif not my_data.empty:
                    st.info("Complete more evaluations to unlock your Learning Radar chart.")
                
                if st.button("Generate Exam"):
                    if st.session_state['kb_files']:
                        ctx = "\n\n".join(st.session_state['kb_files'].values())
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        p = f"Context: {ctx[:12000]}\nGenerate 3 MCQs, 2 Short Questions, 1 Essay."
                        st.session_state['exam'] = model.generate_content(p).text
                    else: st.error("No course materials found.")
                
                if 'exam' in st.session_state:
                    st.markdown(st.session_state['exam'])
                    ans = st.text_area("Your Answers:")
                    if st.button("Submit for Grading"):
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        g_p = f"Grading student submission. Provide 3 scores (1-5): Technical Accuracy, English Proficiency, Analytical Depth. Context: {ctx[:8000]}\nAns: {ans}\nFormat: ATTR: [Name] | SCORE: [1-5] | FEED: [Text]"
                        res = model.generate_content(g_p).text
                        st.markdown(res)
                        
                        # Database Update
                        conn_in = sqlite3.connect('atab_memory.db')
                        for line in res.split('\n'):
                            if "ATTR:" in line:
                                parts = line.split('|')
                                attr = parts[0].replace("ATTR:", "").strip()
                                score = int(parts[1].replace("SCORE:", "").strip())
                                feed = parts[2].replace("FEED:", "").strip()
                                conn_in.execute("INSERT INTO evaluations (roll_no, session, course, attribute, score, feedback, timestamp) VALUES (?,?,?,?,?,?,?)",
                                             (s_r, user[1], user[2], attr, score, feed, datetime.now()))
                        conn_in.commit(); conn_in.close()
                        st.success("Results archived in your history.")
            else:
                st.warning("Roll number not found.")
            conn.close()

if __name__ == "__main__":
    main()
