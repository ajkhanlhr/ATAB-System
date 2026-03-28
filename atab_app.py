import streamlit as st
import sqlite3
import pypdf
from docx import Document
import google.generativeai as genai
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# --- 1. STYLISH ICON & MOBILE APP BEHAVIOR ---
st.set_page_config(page_title="ATAB System", page_icon="🎓", layout="wide")

# This hides the 'made with streamlit' footer and adds professional styling
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """
st.markdown(hide_style, unsafe_allow_html=True)

# 2. BRAIN CONFIGURATION
genai.configure(api_key="YOUR_ACTUAL_API_KEY_HERE")

# 3. DATABASE INITIALIZATION
def init_db():
    conn = sqlite3.connect('atab_memory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (roll_no TEXT PRIMARY KEY, name TEXT, session TEXT, course TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations (roll_no TEXT, session TEXT, course TEXT, attribute TEXT, score INTEGER, feedback TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (category TEXT, value TEXT, UNIQUE(category, value))''')
    conn.commit()
    conn.close()

def get_metadata(category):
    conn = sqlite3.connect('atab_memory.db')
    df = pd.read_sql_query("SELECT value FROM metadata WHERE category=?", conn, params=(category,))
    conn.close()
    return df['value'].tolist()

def add_metadata(category, value):
    conn = sqlite3.connect('atab_memory.db')
    try:
        conn.execute("INSERT INTO metadata (category, value) VALUES (?, ?)", (category, value))
        conn.commit()
    except: pass
    conn.close()

# 4. MAIN APP
def main():
    init_db()
    if 'kb_files' not in st.session_state: st.session_state['kb_files'] = {}

    st.sidebar.title("ATAB Control")
    app_mode = st.sidebar.selectbox("Select Mode", ["Student View", "Instructor View"])
    
    # Dynamic Dropdowns
    sessions = get_metadata('session') + ["Add New"]
    sel_session = st.sidebar.selectbox("Session", sessions)
    if sel_session == "Add New":
        ns = st.sidebar.text_input("New Session Name")
        if st.sidebar.button("Add Session"):
            add_metadata('session', ns)
            st.rerun()

    courses = get_metadata('course') + ["Add New"]
    sel_course = st.sidebar.selectbox("Course", courses)
    if sel_course == "Add New":
        nc = st.sidebar.text_input("New Course Code")
        if st.sidebar.button("Add Course"):
            add_metadata('course', nc)
            st.rerun()

    if app_mode == "Instructor View":
        st.title(f"👨‍🏫 Instructor: {sel_course}")
        t1, t2, t3 = st.tabs(["Archives", "Analytics", "History"])
        
        with t1:
            st.subheader("Knowledge & Student Archive")
            up = st.file_uploader("Upload Knowledge", accept_multiple_files=True)
            if up:
                for f in up: st.session_state['kb_files'][f.name] = "Content Processed" # Simplified for UI
            
            st.markdown("---")
            st.write("Batch Student Upload (CSV)")
            csv_up = st.file_uploader("Upload CSV (roll_no, name)")
            if csv_up:
                df_s = pd.read_csv(csv_up)
                conn = sqlite3.connect('atab_memory.db')
                for _, r in df_s.iterrows():
                    conn.execute("INSERT OR REPLACE INTO students VALUES (?,?,?,?)", (str(r['roll_no']), r['name'], sel_session, sel_course))
                conn.commit(); conn.close()
                st.success("Students Archived.")

        with t2:
            st.subheader("Performance Heatmap")
            conn = sqlite3.connect('atab_memory.db')
            df_ev = pd.read_sql_query("SELECT * FROM evaluations WHERE course=?", conn, params=(sel_course,))
            if not df_ev.empty:
                # Top 5 / Bottom 5 logic here...
                st.dataframe(df_ev)
            conn.close()

    else:
        st.title("🎓 Student Portal")
        roll = st.text_input("Enter Roll Number")
        if st.button("Generate Exam"):
            st.write("Generating your 3-part exam (MCQs, Short, Essay)...")
            # AI Exam Gen Logic...

if __name__ == "__main__":
    main()
