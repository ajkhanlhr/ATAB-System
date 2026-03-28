import streamlit as st
import sqlite3
import pypdf
from docx import Document
import google.generativeai as genai
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# --- UI CONFIG ---
st.set_page_config(page_title="ATAB System", page_icon="🎓", layout="wide")

# 1. BRAIN CONFIG
api_key = st.secrets.get("GEMINI_API_KEY", "")
genai.configure(api_key=api_key)

# 2. DATABASE INIT
def init_db():
    conn = sqlite3.connect('atab_memory.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (roll_no TEXT PRIMARY KEY, name TEXT, session TEXT, course TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations (roll_no TEXT, session TEXT, course TEXT, attribute TEXT, score INTEGER, feedback TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
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

# 3. MAIN APP
def main():
    init_db()
    if 'kb_files' not in st.session_state: st.session_state['kb_files'] = {}

    st.sidebar.title("🎓 ATAB System")
    app_mode = st.sidebar.selectbox("Access Mode", ["Instructor View", "Student View"])
    
    # Session/Course Logic
    s_list = get_meta('session') + ["Add New"]
    sel_session = st.sidebar.selectbox("Academic Session", s_list)
    if sel_session == "Add New":
        ns = st.sidebar.text_input("New Session Name")
        if st.sidebar.button("Register Session"):
            add_meta('session', ns); st.rerun()

    c_list = get_meta('course') + ["Add New"]
    sel_course = st.sidebar.selectbox("Course Code", c_list)
    if sel_course == "Add New":
        nc = st.sidebar.text_input("New Course Code")
        if st.sidebar.button("Register Course"):
            add_meta('course', nc); st.rerun()

    if app_mode == "Instructor View":
        st.title(f"👨‍🏫 Instructor: {sel_course}")
        t1, t2 = st.tabs(["Archives", "Analytics"])
        
        with t1:
            st.subheader("Student Archive Upload")
            csv_file = st.file_uploader("Upload CSV (Required columns: Roll No and Name)", type=["csv"])
            
            if csv_file:
                df_s = pd.read_csv(csv_file)
                # --- FLEXIBLE HEADER CLEANER ---
                # This fixes the KeyError by making everything lowercase and removing spaces
                df_s.columns = df_s.columns.str.strip().str.lower().str.replace(' ', '_')
                
                # Mapping common variations
                col_map = {
                    'roll_number': 'roll_no', 'rollno': 'roll_no', 'id': 'roll_no',
                    'student_name': 'name', 'full_name': 'name'
                }
                df_s = df_s.rename(columns=col_map)

                if 'roll_no' in df_s.columns and 'name' in df_s.columns:
                    conn = sqlite3.connect('atab_memory.db')
                    for _, r in df_s.iterrows():
                        conn.execute("INSERT OR REPLACE INTO students VALUES (?,?,?,?)", 
                                     (str(r['roll_no']), r['name'], sel_session, sel_course))
                    conn.commit(); conn.close()
                    st.success(f"Archived {len(df_s)} students successfully!")
                else:
                    st.error(f"Missing columns! Found: {list(df_s.columns)}. Please ensure your CSV has 'Roll No' and 'Name'.")

    else:
        st.title("🎓 Student Portal")
        st.write("Login with your Roll Number to begin.")

if __name__ == "__main__":
    main()
