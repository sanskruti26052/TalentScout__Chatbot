"""
TalentScout – AI Hiring Assistant
==================================
• Dark theme UI with clear stage indicators
• Markdown formatting in chat bubbles
• Positive / Negative / Neutral sentiment indicators per answer
• Sentiment scoring overview at the end
• LLM generates questions → falls back to curated bank on failure
• Stage machine: name→email→phone→experience→position→location→tech_stack→questions→end
"""

import streamlit as st
import streamlit.components.v1 as components
import re
import json
import datetime
import sqlite3
import hashlib
import os

try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE  — SQLite, stores every completed interview persistently
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH    = "talentscout_candidates.db"
ADMIN_PASS = "admin123"   # change this in production

def db_connect():
    """Return a connection to the SQLite database, creating tables if needed."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            submitted_at  TEXT NOT NULL,
            name          TEXT,
            email         TEXT,
            phone         TEXT,
            experience    TEXT,
            position      TEXT,
            location      TEXT,
            tech_stack    TEXT,
            conf_score    INTEGER,
            conf_grade    TEXT,
            pos_answers   INTEGER,
            neu_answers   INTEGER,
            neg_answers   INTEGER,
            q_source      TEXT,
            answers_json  TEXT
        )
    """)
    conn.commit()
    return conn

def db_save_candidate(candidate: dict, sentiment_summary: dict,
                      q_answers: list, used_fallback: bool):
    """
    Persist a completed interview to the database.
    Called once when the interview finishes.
    """
    conn = db_connect()
    conn.execute("""
        INSERT INTO candidates
            (submitted_at, name, email, phone, experience, position,
             location, tech_stack, conf_score, conf_grade,
             pos_answers, neu_answers, neg_answers, q_source, answers_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        candidate.get("name",""),
        candidate.get("email",""),
        candidate.get("phone",""),
        candidate.get("experience",""),
        candidate.get("position",""),
        candidate.get("location",""),
        candidate.get("tech_stack",""),
        sentiment_summary.get("score", 0),
        sentiment_summary.get("grade",""),
        sentiment_summary.get("pos", 0),
        sentiment_summary.get("neu", 0),
        sentiment_summary.get("neg", 0),
        "Question Bank" if used_fallback else "LLM Generated",
        json.dumps(q_answers, default=str),
    ))
    conn.commit()
    conn.close()

def db_fetch_all():
    """Return all candidate rows as a list of dicts."""
    conn = db_connect()
    rows = conn.execute(
        "SELECT * FROM candidates ORDER BY submitted_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_fetch_one(candidate_id: int):
    """Return one candidate row by ID."""
    conn = db_connect()
    row = conn.execute(
        "SELECT * FROM candidates WHERE id=?", (candidate_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def db_delete(candidate_id: int):
    """Delete a candidate record."""
    conn = db_connect()
    conn.execute("DELETE FROM candidates WHERE id=?", (candidate_id,))
    conn.commit()
    conn.close()

def check_admin_password(pw: str) -> bool:
    return pw == ADMIN_PASS

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
MODEL_PATH = r"C:\Users\91883\aiml\orca_mini_3b.IQ3_M.gguf"

STAGES = ["name","email","phone","experience","position","location","tech_stack","questions","end"]

STAGE_LABELS = {
    "name":"Full Name","email":"Email","phone":"Phone","experience":"Experience",
    "position":"Position","location":"Location","tech_stack":"Tech Stack",
    "questions":"Assessment","end":"Complete",
}

STAGE_ICONS = {
    "name":"👤","email":"📧","phone":"📱","experience":"🗓️",
    "position":"💼","location":"📍","tech_stack":"🛠️",
    "questions":"🧠","end":"✅",
}

EXIT_WORDS = {"exit","quit","bye","goodbye","stop","cancel"}

# ─────────────────────────────────────────────────────────────────────────────
# LLM PROMPT
# ─────────────────────────────────────────────────────────────────────────────
QUESTION_PROMPT = """### System:
You are a senior technical interviewer. Output ONLY a numbered list. No preamble. No extra text.

### Task:
Generate exactly 5 technical interview questions for a candidate whose tech stack is: {tech_stack}

Rules:
- Questions must be specific to the technologies listed
- Mix: 2 conceptual, 2 practical/coding, 1 system-design
- Output format strictly: 1. question\n2. question\n3. question\n4. question\n5. question

### Questions:
1."""

# ─────────────────────────────────────────────────────────────────────────────
# QUESTION BANK  (fallback when LLM fails or is unavailable)
# ─────────────────────────────────────────────────────────────────────────────
BANK = {
    "python":[
        "What is the difference between a list and a tuple in Python, and when would you use each?",
        "Explain how Python's GIL affects multithreading. When would you use multiprocessing instead?",
        "What are decorators in Python? Write a simple example that logs function call time.",
        "How does Python handle memory management and garbage collection?",
        "Explain the difference between `deepcopy` and `copy` with a practical example.",
    ],
    "django":[
        "Walk me through the Django request-response lifecycle from URL to HTTP response.",
        "What is the N+1 query problem? How do `select_related` and `prefetch_related` solve it?",
        "Explain Django signals. Give a real use-case for the `post_save` signal.",
        "How do Django database migrations work? What happens with conflicting migrations?",
        "How would you implement role-based access control in a Django application?",
    ],
    "flask":[
        "What is the difference between Flask's application context and request context?",
        "How do you structure a large Flask application using Blueprints?",
        "How would you implement JWT authentication in a Flask REST API?",
        "Explain how Flask-SQLAlchemy session management works and its common pitfalls.",
        "What are 4 things you must do to make a Flask app production-ready?",
    ],
    "fastapi":[
        "What makes FastAPI faster than Flask for I/O-bound workloads?",
        "Explain dependency injection in FastAPI with a practical example.",
        "How does FastAPI use Pydantic models for request and response validation?",
        "What is the difference between `async def` and `def` route handlers in FastAPI?",
        "How would you implement background tasks in FastAPI?",
    ],
    "javascript":[
        "Explain the JavaScript event loop, call stack, and microtask queue.",
        "What are closures in JavaScript? Give a real-world example.",
        "Explain `Promise.all`, `Promise.allSettled`, and `Promise.race` with use-cases.",
        "How does prototypal inheritance work in JavaScript?",
        "What is the difference between debouncing and throttling? Implement one from scratch.",
    ],
    "react":[
        "What is the Virtual DOM and how does React's reconciliation algorithm work?",
        "What is the difference between `useEffect` and `useLayoutEffect`?",
        "How do you prevent unnecessary re-renders using `useMemo`, `useCallback`, and `React.memo`?",
        "What is the Context API and when would you use it over Redux?",
        "How would you build a custom hook `useFetch` with loading, error, and abort support?",
    ],
    "node":[
        "How does Node.js handle concurrency with a single thread?",
        "What is the difference between `process.nextTick`, `setImmediate`, and `setTimeout`?",
        "How would you detect and fix a memory leak in a production Node.js app?",
        "Explain Node.js streams and when you would use Transform streams.",
        "How do you handle uncaught exceptions and unhandled promise rejections in Node.js?",
    ],
    "sql":[
        "What is the difference between INNER JOIN, LEFT JOIN, and FULL OUTER JOIN?",
        "Explain database normalization — what are 1NF, 2NF, and 3NF?",
        "What are indexes? When do they help, and when can they hurt performance?",
        "Explain ACID properties. How does a database guarantee atomicity on a crash?",
        "You have a query returning 1M rows in 30s. Walk me through your optimization process.",
    ],
    "postgresql":[
        "How does PostgreSQL's MVCC (Multi-Version Concurrency Control) work?",
        "What are CTEs and recursive CTEs? Give a use-case for each.",
        "Explain partial indexes, expression indexes, and covering indexes in PostgreSQL.",
        "How would you use `EXPLAIN ANALYZE` to diagnose a slow query?",
        "What are PostgreSQL table partitioning strategies and when would you use each?",
    ],
    "mongodb":[
        "When would you embed a document vs use a reference in MongoDB?",
        "Explain the MongoDB aggregation pipeline with an example.",
        "How does MongoDB handle transactions and what are their limitations?",
        "What are compound indexes in MongoDB and how does the ESR rule apply?",
        "How would you design a MongoDB schema for a social media feed at scale?",
    ],
    "docker":[
        "What is the difference between a Docker image, layer, and container?",
        "Explain multi-stage Docker builds and how they reduce image size.",
        "What is the difference between Docker volumes, bind mounts, and tmpfs mounts?",
        "How would you debug a container that exits immediately with code 1?",
        "Design a Docker Compose setup for a Python backend, PostgreSQL, and Redis.",
    ],
    "kubernetes":[
        "Explain the difference between a Pod, Deployment, and StatefulSet.",
        "How does Kubernetes service discovery work? Explain ClusterIP vs LoadBalancer.",
        "What is the difference between a ConfigMap and a Secret?",
        "How do liveness probes, readiness probes, and startup probes differ?",
        "Explain Kubernetes Horizontal Pod Autoscaling.",
    ],
    "aws":[
        "What is the difference between EC2, ECS Fargate, and Lambda?",
        "Explain the difference between SQS and SNS. Give a use-case for each.",
        "What is IAM? Explain the principle of least privilege.",
        "How does S3 ensure durability and availability?",
        "Design a fault-tolerant, auto-scaling web app architecture on AWS.",
    ],
    "git":[
        "What is the difference between `git merge`, `git rebase`, and `git cherry-pick`?",
        "How would you recover commits after an accidental `git reset --hard HEAD~5`?",
        "What is a Git hook? Give a practical pre-commit hook example.",
        "Explain the Git object model — blobs, trees, commits, and tags.",
        "Compare Gitflow, trunk-based development, and GitHub Flow.",
    ],
    "default":[
        "Describe the most complex system you've built. What were the key design decisions?",
        "How do you approach debugging a critical production issue?",
        "Explain horizontal vs vertical scaling. When would you prefer each?",
        "What does clean code mean to you? How do you balance quality with speed?",
        "Describe a time you had to learn a new technology quickly. What was your approach?",
    ],
}

def llm_generate_questions(llm, tech_stack: str) -> list:
    """
    Primary: LLM generates questions via engineered prompt.
    Fallback: curated bank used if LLM fails or output unparseable.
    """
    prompt = QUESTION_PROMPT.format(tech_stack=tech_stack)
    try:
        out = llm(prompt, max_tokens=600,
                  stop=["### ","\n\n\n","User:","Human:","System:"],
                  echo=False, temperature=0.4, top_p=0.9, repeat_penalty=1.15)
        raw = "1." + out["choices"][0]["text"]
        questions = []
        for line in raw.split("\n"):
            m = re.match(r"^\d+[.)\s]+(.+)", line.strip())
            if m:
                q = m.group(1).strip()
                if len(q) > 20 and "?" in q:
                    questions.append(q)
        if len(questions) >= 3:
            return questions[:5]
    except Exception:
        pass
    # ── LLM fallback ──────────────────────────────────────────────────────────
    return get_questions(tech_stack)

def get_questions(tech_stack: str) -> list:
    """Curated question bank — 14 stacks with priority matching."""
    tech = tech_stack.lower()
    priority = ["postgresql","mongodb","kubernetes","fastapi","django","flask",
                "react","node","javascript","python","docker","aws","sql","git"]
    selected = []
    for key in priority:
        if key in tech and len(selected) < 5:
            for q in BANK[key]:
                if q not in selected:
                    selected.append(q)
                    break
    for q in BANK["default"]:
        if len(selected) >= 5: break
        if q not in selected: selected.append(q)
    return selected[:5]

# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT  — keyword heuristic scoring
# ─────────────────────────────────────────────────────────────────────────────
POS_WORDS = {"great","love","enjoy","excited","excellent","good","happy","confident",
             "strong","expert","built","solved","improved","yes","absolutely","sure",
             "experience","worked","implemented","designed","led","created","proficient"}
NEG_WORDS = {"not sure","don't know","never","difficult","struggle","fail","no",
             "confused","unfamiliar","haven't","weak","poor","unsure","unclear"}

def analyse_sentiment(text: str) -> dict:
    """
    Returns sentiment label, emoji, score (-1..+1), and a short descriptor.
    Used to show per-answer confidence indicators during Q&A.
    """
    t = text.lower()
    p = sum(1 for w in POS_WORDS if w in t)
    n = sum(1 for w in NEG_WORDS if w in t)
    total = p + n
    if total == 0:
        score, label = 0.0, "Neutral"
    else:
        score = round((p - n) / total, 2)
        label = "Positive" if score > 0.2 else ("Negative" if score < -0.2 else "Neutral")

    descriptors = {
        "Positive": "Confident & knowledgeable",
        "Neutral":  "Measured response",
        "Negative": "Some uncertainty expressed",
    }
    emojis = {"Positive": "😊", "Neutral": "😐", "Negative": "😟"}
    colors = {"Positive": "#22c55e", "Neutral": "#a78bfa", "Negative": "#f87171"}

    return {
        "label":      label,
        "emoji":      emojis[label],
        "score":      score,
        "descriptor": descriptors[label],
        "color":      colors[label],
    }

def sentiment_score_summary(sentiments: list) -> dict:
    """Aggregate sentiment into a confidence overview score (0–100)."""
    if not sentiments:
        return {"score": 0, "grade": "N/A", "color": "#6b7280"}
    pos = sentiments.count("Positive")
    neg = sentiments.count("Negative")
    neu = sentiments.count("Neutral")
    total = len(sentiments)
    # Weighted: Positive=1.0, Neutral=0.5, Negative=0.0
    raw = (pos * 1.0 + neu * 0.5) / total
    score = int(raw * 100)
    if score >= 70:   grade, color = "High Confidence",   "#22c55e"
    elif score >= 45: grade, color = "Moderate Confidence","#f59e0b"
    else:             grade, color = "Low Confidence",     "#f87171"
    return {"score": score, "grade": grade, "color": color,
            "pos": pos, "neu": neu, "neg": neg, "total": total}

# ─────────────────────────────────────────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="⏳ Loading AI model…")
def load_model():
    if not LLAMA_AVAILABLE:
        return None, "llama-cpp-python not installed"
    try:
        llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=4,
                    n_gpu_layers=0, verbose=False, n_batch=512)
        return llm, None
    except Exception as e:
        return None, str(e)

# ─────────────────────────────────────────────────────────────────────────────
# MARKDOWN → HTML  (used inside iframe — bypasses Streamlit sanitizer)
# ─────────────────────────────────────────────────────────────────────────────
def md(text: str) -> str:
    """Convert markdown subset to HTML for chat bubble rendering."""
    text = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    # Bold before italic
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`",
        r"<code>\1</code>", text)
    text = re.sub(r"(?m)^---$", "<hr>", text)
    lines, out, in_ul = text.split("\n"), [], False
    for line in lines:
        s = line.strip()
        if re.match(r"^[-•] ", s):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{s[2:]}</li>")
        else:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(line)
    if in_ul: out.append("</ul>")
    return "\n".join(out).replace("\n", "<br>")

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
def init():
    defs = {
        "stage":"name", "history":[], "candidate":{},
        "questions":[], "q_idx":0, "q_answers":[],
        "sentiments":[], "greeted":False,
        "started":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ic":0, "_li":"", "used_fallback": False,
    }
    for k,v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

def advance():
    s = st.session_state
    i = STAGES.index(s.stage)
    if i + 1 < len(STAGES): s.stage = STAGES[i+1]

def is_exit(t): return bool(set(t.lower().split()) & EXIT_WORDS)

# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION HANDLER
# ─────────────────────────────────────────────────────────────────────────────
def handle(llm, user_input: str) -> str:
    s = st.session_state
    c = s.candidate
    u = user_input.strip()

    if is_exit(u):
        s.stage = "end"
        name = c.get("name","")
        return (f"Thank you{', **'+name+'**' if name else ''}! 👋\n\n"
                "Your profile has been saved. We'll be in touch if there's a great match.\n\n"
                "Goodbye and best of luck! 🍀")

    stage = s.stage

    if stage == "name":
        name = u.title()
        if len(name) < 2 or any(ch.isdigit() for ch in name):
            return "Please enter your full name (first and last name)."
        c["name"] = name; advance()
        return f"Nice to meet you, **{name}**! 😊\n\nWhat is your **email address**?"

    elif stage == "email":
        if "@" not in u or "." not in u.split("@")[-1]:
            return "That doesn't look valid. Please enter a correct email.\n_Example: name@company.com_"
        c["email"] = u.lower(); advance()
        return "Got it! ✅\n\nWhat is your **phone number**?\n_(Include country code — e.g. +91 98765 43210)_"

    elif stage == "phone":
        if len(re.sub(r"[^\d]","",u)) < 7:
            return "Please enter a valid phone number with at least 7 digits."
        c["phone"] = u; advance()
        return "How many **years of professional experience** do you have in tech?\n_(e.g. 1, 3, 5+, 10+)_"

    elif stage == "experience":
        c["experience"] = u; advance()
        return ("What **position(s)** are you applying for?\n"
                "_(e.g. Backend Developer, Data Scientist, DevOps Engineer)_")

    elif stage == "position":
        if len(u) < 2:
            return "Please enter the role(s) you are interested in."
        c["position"] = u; advance()
        return "What is your **current location**?\n_(City, Country — e.g. Mumbai, India)_"

    elif stage == "location":
        c["location"] = u; advance()
        return ("Almost done with the basics! 🎉\n\n"
                "Please list your complete **tech stack** — every language, framework, "
                "database, and tool you're comfortable using.\n\n"
                "💡 _Be thorough — this determines your technical questions._\n\n"
                "_Example: Python, Django, PostgreSQL, Redis, Docker, AWS_")

    elif stage == "tech_stack":
        if len(u) < 2:
            return "Please list at least one technology you work with."
        c["tech_stack"] = u; advance()
        with st.spinner("🧠 Generating technical questions based on your stack…"):
            if llm:
                qs = llm_generate_questions(llm, u)
                # Detect if we fell back to bank
                bank_qs = get_questions(u)
                s.used_fallback = (qs == bank_qs)
            else:
                qs = get_questions(u)
                s.used_fallback = True
        s.questions = qs
        s.q_idx = 0
        s.q_answers = []
        src = " _(using question bank — LLM unavailable)_" if s.used_fallback else " _(generated by AI)_"
        return (f"Based on your stack (**{u}**), I have **{len(qs)} technical questions** for you.{src}\n\n"
                "Take your time — answer as clearly as you can.\n\n"
                f"---\n\n**Question 1 of {len(qs)}:**\n\n{qs[0]}")

    elif stage == "questions":
        # ── Triple safety guard ───────────────────────────────────────────
        # 1. questions list must exist and be non-empty
        if not s.questions:
            advance()
            return "No questions found. Moving on — thank you!"
        # 2. index must be within bounds (prevents IndexError on double-submit)
        if s.q_idx >= len(s.questions):
            return "All your answers have been recorded. Thank you! 🙌"
        # 3. stage must still be questions (not already advanced)
        if s.stage != "questions":
            return "The interview is complete. Thank you! 🙌"
        idx = s.q_idx
        sent = analyse_sentiment(u)
        s.q_answers.append({
            "question": s.questions[idx],
            "answer":   u,
            "sentiment": sent,
        })
        s.sentiments.append(sent["label"])
        s.q_idx += 1

        if s.q_idx < len(s.questions):
            nxt   = s.questions[s.q_idx]
            total = len(s.questions)
            # Show sentiment indicator for the answer just given
            sent_line = f"\n\n_{sent['emoji']} {sent['descriptor']}_"
            return (f"Thank you for your answer.{sent_line}\n\n"
                    f"**Question {s.q_idx+1} of {total}:**\n\n{nxt}")
        else:
            c["answers"]  = s.q_answers
            c["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            advance()
            summary = sentiment_score_summary(s.sentiments)
            # ── Persist to database ───────────────────────────────────────
            try:
                db_save_candidate(
                    candidate       = c,
                    sentiment_summary = summary,
                    q_answers       = s.q_answers,
                    used_fallback   = s.get("used_fallback", False),
                )
            except Exception as _db_err:
                pass   # never crash the interview on a DB write failure
            return (f"🎊 **That's a wrap, {c.get('name','there')}!**\n\n"
                    f"You've completed the TalentScout screening.\n\n"
                    f"**Confidence Score: {summary['score']}/100** — {summary['grade']}\n\n"
                    f"- 😊 Positive answers: **{summary['pos']}**\n"
                    f"- 😐 Neutral answers: **{summary['neu']}**\n"
                    f"- 😟 Uncertain answers: **{summary['neg']}**\n\n"
                    "Our team will review your profile and reach out within "
                    "**2–3 business days**.\n\nBest of luck! 🍀")

    elif stage == "end":
        return "The interview is complete. Thank you again! 🙌"

    return "I didn't catch that — could you please try again?"

# ─────────────────────────────────────────────────────────────────────────────
# DARK THEME CSS
# ─────────────────────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg:         #0e1117;
    --bg2:        #161b27;
    --surface:    #1c2233;
    --surface2:   #222840;
    --border:     #2d3450;
    --border2:    #3a4060;
    --accent:     #6366f1;
    --accent-lt:  #818cf8;
    --accent-dk:  #4f46e5;
    --teal:       #14b8a6;
    --green:      #22c55e;
    --green-dim:  rgba(34,197,94,.12);
    --amber:      #f59e0b;
    --amber-dim:  rgba(245,158,11,.12);
    --red:        #f87171;
    --red-dim:    rgba(248,113,113,.12);
    --purple-dim: rgba(99,102,241,.12);
    --text:       #e2e8f8;
    --text2:      #94a3c8;
    --muted:      #5a6480;
    --user-bubble:#4f46e5;
    --bot-bubble: #1c2233;
}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stHeader"]  { background: transparent !important; }
[data-testid="stSidebar"] {
    background: var(--bg2) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.2rem; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }

/* ── TOP BAR ─────────────────────────────────────────────────────────── */
.topbar {
    display: flex; align-items: center; gap: .9rem;
    padding: .9rem 1.2rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    margin-bottom: 1rem;
    box-shadow: 0 2px 12px rgba(0,0,0,.3);
}
.tb-logo {
    width: 42px; height: 42px; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent), var(--accent-dk));
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.3rem;
    box-shadow: 0 0 14px rgba(99,102,241,.4);
}
.tb-name {
    font-size: 1.1rem; font-weight: 800;
    color: var(--text); letter-spacing: -.025em; line-height: 1.1;
}
.tb-name span { color: var(--accent-lt); }
.tb-sub  { font-size: .68rem; color: var(--text2); margin-top: .15rem; }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: .6rem; }
.tb-pill {
    font-size: .6rem; font-weight: 700;
    letter-spacing: .1em; text-transform: uppercase;
    padding: .25rem .7rem; border-radius: 20px;
}
.tb-pill.llm  { background: var(--green-dim);  color: var(--green); border: 1px solid rgba(34,197,94,.25); }
.tb-pill.bank { background: var(--amber-dim); color: var(--amber); border: 1px solid rgba(245,158,11,.25); }
.tb-badge {
    background: var(--purple-dim);
    color: var(--accent-lt);
    border: 1px solid rgba(99,102,241,.25);
    font-size: .6rem; font-weight: 700;
    letter-spacing: .1em; text-transform: uppercase;
    padding: .25rem .7rem; border-radius: 20px;
}

/* ── STAGE PROGRESS ──────────────────────────────────────────────────── */
.stages-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: .9rem 1.1rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 12px rgba(0,0,0,.25);
}
.stages-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: .7rem;
}
.stages-title { font-size: .7rem; font-weight: 600; color: var(--text2); }
.stages-pct   { font-size: .7rem; font-weight: 700; color: var(--accent-lt); }
.bar-bg {
    height: 5px; background: var(--bg); border-radius: 99px;
    overflow: hidden; margin-bottom: .75rem;
}
.bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--teal));
    border-radius: 99px;
    transition: width .5s cubic-bezier(.4,0,.2,1);
    box-shadow: 0 0 8px rgba(99,102,241,.5);
}
.stages-row {
    display: flex; gap: .3rem;
}
.stage-chip {
    flex: 1; text-align: center;
    padding: .3rem .1rem;
    border-radius: 7px;
    font-size: .58rem; font-weight: 500;
    border: 1px solid transparent;
    transition: all .25s;
    cursor: default;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.stage-chip.pending {
    background: var(--bg); color: var(--muted); border-color: var(--border);
}
.stage-chip.done {
    background: rgba(20,184,166,.1); color: var(--teal);
    border-color: rgba(20,184,166,.3); font-weight: 600;
}
.stage-chip.active {
    background: var(--accent); color: #fff;
    border-color: var(--accent);
    font-weight: 700;
    box-shadow: 0 0 10px rgba(99,102,241,.45);
}

/* ── SIDEBAR ─────────────────────────────────────────────────────────── */
.s-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: .8rem .95rem;
    margin-bottom: .75rem;
}
.s-title {
    font-size: .62rem; font-weight: 700;
    color: var(--muted); letter-spacing: .1em;
    text-transform: uppercase; margin-bottom: .6rem;
    display: flex; align-items: center; gap: .35rem;
}
.s-row {
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: .4rem; margin-bottom: .28rem; font-size: .72rem;
}
.s-row .k { color: var(--text2); flex-shrink: 0; }
.s-row .v { color: var(--text); font-weight: 600; text-align: right; word-break: break-all; max-width: 58%; }

/* Sentiment pills */
.pill {
    display: inline-flex; align-items: center; gap: .22rem;
    font-size: .61rem; font-weight: 600;
    padding: .18rem .55rem; border-radius: 20px; margin: .1rem;
}
.pill.Positive { background: var(--green-dim); color: var(--green); border: 1px solid rgba(34,197,94,.3); }
.pill.Neutral  { background: var(--purple-dim); color: var(--accent-lt); border: 1px solid rgba(99,102,241,.3); }
.pill.Negative { background: var(--red-dim); color: var(--red); border: 1px solid rgba(248,113,113,.3); }

/* Confidence score ring placeholder */
.conf-score {
    text-align: center; padding: .5rem 0;
}
.conf-num {
    font-size: 2rem; font-weight: 800; line-height: 1;
}
.conf-label {
    font-size: .68rem; font-weight: 600; margin-top: .2rem;
}

/* Q&A progress bar in sidebar */
.mini-bar-bg { height: 6px; background: var(--bg); border-radius: 99px; overflow: hidden; margin-top: .45rem; }
.mini-bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--teal)); border-radius: 99px; transition: width .5s; }

/* Status banners in sidebar */
.sb-ok   { background: var(--green-dim); border: 1px solid rgba(34,197,94,.25); border-radius: 9px; padding: .55rem .8rem; font-size: .7rem; font-weight: 600; color: var(--green);  margin-bottom: .75rem; }
.sb-warn { background: var(--amber-dim); border: 1px solid rgba(245,158,11,.25); border-radius: 9px; padding: .55rem .8rem; font-size: .7rem; font-weight: 600; color: var(--amber); margin-bottom: .75rem; }

/* ── INPUT AREA ──────────────────────────────────────────────────────── */
.input-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: .8rem 1rem;
    margin-top: .75rem;
    box-shadow: 0 2px 12px rgba(0,0,0,.25);
}
.input-hint {
    font-size: .66rem; color: var(--muted); margin-bottom: .45rem;
}
[data-testid="stTextInput"] > div > div > input {
    background: var(--bg2) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: .84rem !important;
    padding: .62rem .95rem !important;
    transition: border-color .2s, box-shadow .2s !important;
}
[data-testid="stTextInput"] > div > div > input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,.18) !important;
    background: var(--surface) !important;
}
[data-testid="stTextInput"] > div > div > input::placeholder {
    color: var(--muted) !important;
}

/* ── SEND BUTTON ─────────────────────────────────────────────────────── */
[data-testid="stButton"] > button {
    background: linear-gradient(135deg, var(--accent), var(--accent-dk)) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    font-size: .82rem !important;
    padding: .6rem 1.3rem !important;
    box-shadow: 0 2px 10px rgba(99,102,241,.4) !important;
    transition: transform .15s, box-shadow .15s !important;
}
[data-testid="stButton"] > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 16px rgba(99,102,241,.55) !important;
}

/* ── END SCREEN ──────────────────────────────────────────────────────── */
.end-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 2.5rem 2rem;
    text-align: center;
    margin-top: 1rem;
    box-shadow: 0 4px 24px rgba(0,0,0,.4);
}
.end-icon { font-size: 3.2rem; margin-bottom: .8rem; }
.end-wrap h2 {
    font-size: 1.55rem; font-weight: 800;
    color: var(--text); margin-bottom: .5rem; letter-spacing: -.02em;
}
.end-wrap p { color: var(--text2); font-size: .82rem; line-height: 1.7; }

.divider { border: none; border-top: 1px solid var(--border); margin: .7rem 0; }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# CHAT IFRAME CSS  — dark bubble styles, markdown, sentiment chips
# ─────────────────────────────────────────────────────────────────────────────
CHAT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: transparent; font-family: 'Inter', sans-serif; padding: 4px 2px 12px; }

/* Message row */
.msg { display: flex; gap: 9px; margin-bottom: 16px; align-items: flex-end; }
.msg.user { flex-direction: row-reverse; }

/* Avatars */
.av {
    width: 32px; height: 32px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; flex-shrink: 0;
}
.av.bot  { background: linear-gradient(135deg,#6366f1,#4f46e5); box-shadow: 0 2px 8px rgba(99,102,241,.4); }
.av.user { background: linear-gradient(135deg,#14b8a6,#0d9488); box-shadow: 0 2px 8px rgba(20,184,166,.4); }

/* Bubbles */
.bub {
    max-width: 76%; padding: 10px 14px; border-radius: 16px;
    font-size: 13.5px; line-height: 1.65; word-break: break-word;
}
.bub.bot {
    background: #1c2233; border: 1px solid #2d3450;
    border-bottom-left-radius: 4px; color: #e2e8f8;
    box-shadow: 0 2px 8px rgba(0,0,0,.3);
}
.bub.user {
    background: linear-gradient(135deg, #4f46e5, #4338ca);
    border-bottom-right-radius: 4px; color: #fff;
    box-shadow: 0 2px 10px rgba(79,70,229,.4);
}

/* Markdown */
b  { font-weight: 700; }
.bub.bot  b { color: #818cf8; }
.bub.user b { color: #fff; }
i  { font-style: italic; }
.bub.bot  i { color: #94a3c8; }
.bub.user i { color: rgba(255,255,255,.8); }
code {
    font-family: 'JetBrains Mono', monospace;
    font-size: .82em; padding: 1px 5px;
    border-radius: 4px;
}
.bub.bot  code { background: #0e1117; color: #a5b4fc; border: 1px solid #2d3450; }
.bub.user code { background: rgba(255,255,255,.15); color: #fff; }
hr { border: none; border-top: 1px solid #2d3450; margin: .5rem 0; }
ul { margin: .3rem 0 .3rem 1.2rem; padding: 0; }
li { margin: .18rem 0; }

/* Sentiment chip below bot message */
.sent-chip {
    display: inline-flex; align-items: center; gap: .3rem;
    font-size: 10.5px; font-weight: 600;
    padding: .18rem .6rem; border-radius: 20px;
    margin-top: 5px; margin-left: 41px;
}
.sent-chip.Positive { background: rgba(34,197,94,.12);  color: #22c55e; border: 1px solid rgba(34,197,94,.3); }
.sent-chip.Neutral  { background: rgba(99,102,241,.12); color: #818cf8; border: 1px solid rgba(99,102,241,.3); }
.sent-chip.Negative { background: rgba(248,113,113,.12);color: #f87171; border: 1px solid rgba(248,113,113,.3); }
"""

# ─────────────────────────────────────────────────────────────────────────────
# UI RENDERERS
# ─────────────────────────────────────────────────────────────────────────────
def render_topbar(llm_ok: bool):
    pill_cls = "llm" if llm_ok else "bank"
    pill_txt = "🟢 LLM Active" if llm_ok else "🟡 Question Bank"
    st.markdown(f"""
    <div class="topbar">
        <div class="tb-logo">🎯</div>
        <div>
            <div class="tb-name">Talent<span>Scout</span></div>
            <div class="tb-sub">AI Hiring Assistant &nbsp;·&nbsp; Tech Recruitment</div>
        </div>
        <div class="tb-right">
            <span class="tb-pill {pill_cls}">{pill_txt}</span>
            <span class="tb-badge">Screening Portal</span>
        </div>
    </div>""", unsafe_allow_html=True)


def render_progress():
    s   = st.session_state
    idx = STAGES.index(s.stage) if s.stage in STAGES else 0
    pct = int(idx / (len(STAGES) - 1) * 100)
    cur_label = f"{STAGE_ICONS.get(s.stage,'')} {STAGE_LABELS.get(s.stage,'')}"

    chips = ""
    for i, st_name in enumerate(STAGES):
        cls  = "done" if i < idx else ("active" if i == idx else "pending")
        icon = STAGE_ICONS.get(st_name,"")
        lbl  = STAGE_LABELS.get(st_name,"")
        chips += f'<div class="stage-chip {cls}" title="{lbl}">{icon}</div>'

    st.markdown(f"""
    <div class="stages-wrap">
        <div class="stages-header">
            <span class="stages-title">Current: {cur_label}</span>
            <span class="stages-pct">{pct}% complete</span>
        </div>
        <div class="bar-bg"><div class="bar-fill" style="width:{pct}%"></div></div>
        <div class="stages-row">{chips}</div>
    </div>""", unsafe_allow_html=True)


def render_chat():
    """
    Renders chat history inside a components.html iframe.
    Bypasses Streamlit's HTML sanitizer so markdown, bold, code all render.
    Sentiment chips shown below each bot Q&A response.
    """
    if not st.session_state.history:
        return

    s = st.session_state
    # Build a lookup of sentiment per bot message index
    sent_lookup = {}
    q_counter = 0
    for turn in s.history:
        if turn.get("role") == "bot" and s.q_answers:
            # If this message corresponds to a question transition, tag it
            pass

    bubbles = ""
    q_answer_idx = 0
    for turn in s.history:
        role = turn.get("role","")
        text = turn.get("text","")
        if not text: continue
        html_text = md(text)

        if role == "bot":
            bubbles += (f'<div class="msg bot">'
                        f'<div class="av bot">🤖</div>'
                        f'<div class="bub bot">{html_text}</div>'
                        f'</div>')
        elif role == "user":
            # Show sentiment chip after user answer during Q&A
            chip = ""
            if (s.stage in ("questions","end") and
                    q_answer_idx < len(s.q_answers)):
                sent = s.q_answers[q_answer_idx].get("sentiment",{})
                lbl  = sent.get("label","Neutral")
                emj  = sent.get("emoji","😐")
                desc = sent.get("descriptor","")
                chip = (f'<div class="sent-chip {lbl}">'
                        f'{emj} {desc}</div>')
                q_answer_idx += 1

            bubbles += (f'<div class="msg user">'
                        f'<div class="av user">👤</div>'
                        f'<div>'
                        f'<div class="bub user">{html_text}</div>'
                        f'{chip}'
                        f'</div>'
                        f'</div>')

    scroll = "<script>window.scrollTo(0,document.body.scrollHeight);</script>"
    full   = f"<style>{CHAT_CSS}</style>{bubbles}{scroll}"
    height = max(260, len(s.history) * 100)
    components.html(full, height=height, scrolling=True)


def render_sidebar(llm_ok: bool):
    s = st.session_state
    c = s.candidate

    with st.sidebar:
        # LLM status
        if llm_ok:
            st.markdown('<div class="sb-ok">🟢 &nbsp;LLM loaded — orca_mini_3b</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="sb-warn">🟡 &nbsp;LLM offline — question bank active</div>', unsafe_allow_html=True)

        # ── Candidate profile ──────────────────────────────────────────────
        if c:
            fields = [
                ("👤","Name",       c.get("name")),
                ("📧","Email",      c.get("email")),
                ("📱","Phone",      c.get("phone")),
                ("🗓️","Experience", c.get("experience")),
                ("💼","Position",   c.get("position")),
                ("📍","Location",   c.get("location")),
                ("🛠️","Tech Stack", c.get("tech_stack")),
            ]
            rows = "".join(
                f'<div class="s-row"><span class="k">{icon} {k}</span>'
                f'<span class="v">{v}</span></div>'
                for icon,k,v in fields if v)
            if rows:
                st.markdown(
                    f'<div class="s-card">'
                    f'<div class="s-title">📋 Candidate Profile</div>'
                    f'{rows}</div>',
                    unsafe_allow_html=True)

        # ── Sentiment analysis ─────────────────────────────────────────────
        if s.sentiments:
            summary = sentiment_score_summary(s.sentiments)
            emoji_map = {"Positive":"😊","Neutral":"😐","Negative":"😟"}
            pills = "".join(
                f'<span class="pill {l}">{emoji_map[l]} {l}</span>'
                for l in s.sentiments)

            # Confidence score
            score_color = summary["color"]
            st.markdown(
                f'<div class="s-card">'
                f'<div class="s-title">📊 Sentiment Analysis</div>'
                f'<div class="conf-score">'
                f'<div class="conf-num" style="color:{score_color}">{summary["score"]}</div>'
                f'<div style="font-size:.6rem;color:#5a6480;margin-top:.1rem">/ 100</div>'
                f'<div class="conf-label" style="color:{score_color}">{summary["grade"]}</div>'
                f'</div>'
                f'<div style="margin:.6rem 0">{pills}</div>'
                f'<div class="s-row"><span class="k">😊 Positive</span><span class="v" style="color:#22c55e">{summary["pos"]}</span></div>'
                f'<div class="s-row"><span class="k">😐 Neutral</span><span class="v" style="color:#818cf8">{summary["neu"]}</span></div>'
                f'<div class="s-row"><span class="k">😟 Uncertain</span><span class="v" style="color:#f87171">{summary["neg"]}</span></div>'
                f'</div>',
                unsafe_allow_html=True)

        # ── Q&A progress ───────────────────────────────────────────────────
        if s.questions and s.stage in ("questions","end"):
            done  = min(s.q_idx, len(s.questions))
            total = len(s.questions)
            pct   = int(done / total * 100)
            st.markdown(
                f'<div class="s-card">'
                f'<div class="s-title">🧠 Assessment Progress</div>'
                f'<div class="s-row"><span class="k">Questions answered</span>'
                f'<span class="v">{done} / {total}</span></div>'
                f'<div class="mini-bar-bg">'
                f'<div class="mini-bar-fill" style="width:{pct}%"></div></div>'
                f'</div>',
                unsafe_allow_html=True)

        # ── Session info ───────────────────────────────────────────────────
        st.markdown(
            f'<div class="s-card">'
            f'<div class="s-title">🕒 Session</div>'
            f'<div class="s-row"><span class="k">Started</span><span class="v">{s.started}</span></div>'
            f'<div class="s-row"><span class="k">Stage</span>'
            f'<span class="v">{STAGE_ICONS.get(s.stage,"")} {STAGE_LABELS.get(s.stage,s.stage)}</span></div>'
            f'{"<div class=s-row><span class=k>Source</span><span class=v style=color:#f59e0b>Question Bank</span></div>" if s.get("used_fallback") else ""}'
            f'</div>',
            unsafe_allow_html=True)

        # ── Download report ────────────────────────────────────────────────
        if s.stage == "end" and c:
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            summary_data = sentiment_score_summary(s.sentiments) if s.sentiments else {}
            report = {
                "candidate": {k:v for k,v in c.items() if k != "answers"},
                "interview":  {
                    "date":    s.started,
                    "answers": c.get("answers",[]),
                    "sentiment_summary": summary_data,
                },
            }
            st.download_button(
                "⬇️  Download Report (JSON)",
                data=json.dumps(report, indent=2),
                file_name=f"talentscout_{c.get('name','candidate').replace(' ','_').lower()}.json",
                mime="application/json",
                use_container_width=True)


def render_end():
    c = st.session_state.candidate
    st.markdown(
        f'<div class="end-wrap">'
        f'<div class="end-icon">🎉</div>'
        f'<h2>Screening Complete!</h2>'
        f'<p>Thank you, <b>{c.get("name","Candidate")}</b>!<br><br>'
        f'Your responses have been recorded and your profile is ready for review.<br>'
        f'Our team will be in touch within <b>2–3 business days</b>.</p>'
        f'</div>',
        unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄  Start New Interview"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="TalentScout – Hiring Assistant",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    init()
    s = st.session_state

    llm, err = load_model()

    render_sidebar(llm_ok=(llm is not None))
    render_topbar(llm_ok=(llm is not None))

    # One-time greeting
    if not s.greeted:
        s.history.append({"role":"bot","text":(
            "👋 Welcome to **TalentScout**! I'm **TalentBot**, your AI hiring assistant.\n\n"
            "I'll guide you through a quick screening — about **5 minutes**. "
            "I'll collect your basic info then ask technical questions matched to your skill set.\n\n"
            "📌 Type **exit** at any point to end the session.\n\n---\n\n"
            "Let's begin! 🚀\n\nWhat is your **full name**?")})
        s.greeted = True

    render_progress()
    render_chat()

    if s.stage == "end":
        render_end()
        return

    # Input area
    st.markdown('<div class="input-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="input-hint">💬 Type your answer and press Enter or click Send →</div>',
                unsafe_allow_html=True)
    col_in, col_btn = st.columns([5,1])
    with col_in:
        user_input = st.text_input(
            "ans", key=f"inp_{s.ic}",
            placeholder="Your answer here…",
            label_visibility="collapsed")
    with col_btn:
        send = st.button("Send →", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Only fire when there is new input not yet processed
    has_new = user_input.strip() and user_input.strip() != s._li
    triggered = (send and has_new) or (has_new and not send)

    if triggered:
        txt = user_input.strip()
        s._li = txt          # lock: mark as processed before any rerun
        s.ic += 1            # rotate key: clears input widget on rerun
        s.history.append({"role":"user","text":txt})
        with st.spinner(""):
            reply = handle(llm, txt)
        s.history.append({"role":"bot","text":reply})
        st.rerun()


if __name__ == "__main__":
    main()