🎯 TalentScout — AI Hiring Assistant

> An intelligent chatbot that screens tech candidates through a structured interview, generates tailored technical questions using a **local LLM**, tracks sentiment per answer, and provides a confidence score overview — all running **100% offline** with no API keys required.
📌 Project Overview

TalentScout is a **Streamlit-based AI hiring assistant** built for TalentScout, a fictional tech recruitment agency. It automates the initial candidate screening process by:

- Greeting candidates and guiding them through a structured 9-stage interview
- Collecting essential profile information (name, email, phone, experience, position, location, tech stack)
- Generating **5 tailored technical questions** using a local LLM based on the candidate's declared tech stack
- Falling back to a **curated question bank** (14 tech stacks) if the LLM fails or is unavailable
- Scoring every answer as **Positive / Neutral / Negative** using sentiment analysis
- Displaying a **confidence score (0–100)** at the end of the interview
- Showing a live **candidate profile card** and **sentiment tracker** in the sidebar

---

## 🚀 Installation Instructions

### Prerequisites

Requirements -

Python :- 3.9 – 3.13 
Visual Studio Build Tools :- Required to compile llama-cpp-python. Select "Desktop development with C++" during install 
Model file :- orca_mini_3b.IQ3_M.gguf saved at C:\Users\91883\aiml\orca_mini_3b.IQ3_M.gguf 

Step 1 — Install Visual Studio Build Tools

1. Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Run the installer and select "Desktop development with C++"
3. Click Install (~4–6 GB download)
4. Restart your PC after installation

Step 2 — Install Python dependencies

Open a new terminal after the restart and run:

    pip install llama-cpp-python streamlit

Step 3 — Project folder structure

    C:\Users\91883\aiml\
    ├── app.py
    ├── requirements.txt
    ├── README.md
    └── orca_mini_3b.IQ3_M.gguf

Step 4 — Run the app

    cd C:\Users\91883\aiml
    streamlit run app.py

Opens at http://localhost:8501

First launch: ~30 seconds for model to load into RAM.
After that: model is cached — responses in 5–20 seconds on CPU.

 🧭 Usage Guide

For Candidates

Step 1 — App greets you and explains the process
Step 2 — Answer each question — press Enter or click Send →
Step 3 — Provide your tech stack (e.g. Python, Django, PostgreSQL)
Step 4 — Answer 5 technical questions tailored to your stack
Step 5 — Receive a confidence score summary at the end

- Type exit, quit, bye, stop, or cancel at any time to end the session
- The sidebar updates live with your profile and sentiment scores as you answer

Interview Flow

Name → Email → Phone → Experience → Position → Location → Tech Stack → Technical Assessment (5 questions) → Complete

---

🏗️ Technical Details :-

#Libraries Used - 

| Library | Version | Purpose |
|---|---|---|
| streamlit | >= 1.32 | Web UI — pages, widgets, session state, sidebar |
| llama-cpp-python | >= 0.3.0 | Loads and runs local GGUF model on CPU |
| streamlit.components.v1 | built-in | iframe renderer for chat bubbles (bypasses HTML sanitizer) |
| re | stdlib | Input validation and markdown-to-HTML conversion |
| json | stdlib | Serialising session data |
| datetime | stdlib | Session start time and interview timestamps |

#AI Model

| Model name - orca_mini_3b.IQ3_M.gguf 
| Architecture - LLaMA 
| Parameters - 3 billion 
| Quantization - IQ3_M (reduces RAM, runs on CPU) 
| Context window - 2048 tokens 
| Inference - CPU only — no GPU required 
| Loaded via - llama-cpp-python with @st.cache_resource 

#Architecture

    app.py
    │
    ├── CONFIG
    │   ├── MODEL_PATH, STAGES, STAGE_LABELS, STAGE_ICONS, EXIT_WORDS
    │   └── QUESTION_PROMPT  (LLM prompt template)
    │
    ├── QUESTION GENERATION
    │   ├── llm_generate_questions()   LLM-powered (primary)
    │   └── get_questions()            Curated bank keyword match (fallback)
    │
    ├── QUESTION BANK (BANK dict)
    │   └── 14 stacks × 5 questions + 5 default questions
    │
    ├── SENTIMENT ENGINE
    │   ├── analyse_sentiment()        Per-answer Positive/Neutral/Negative
    │   └── sentiment_score_summary()  Overall confidence score 0–100
    │
    ├── MODEL
    │   └── load_model()               Loads GGUF via llama-cpp-python (cached)
    │
    ├── MARKDOWN CONVERTER
    │   └── md()                       Converts **bold**, _italic_, code, lists → HTML
    │
    ├── SESSION STATE
    │   ├── init()                     Initialises all session variables
    │   ├── advance()                  Moves to next interview stage
    │   └── is_exit()                  Detects exit keywords
    │
    ├── CONVERSATION HANDLER
    │   └── handle()                   9-stage state machine — routes every user input
    │
    ├── CSS (CSS + CHAT_CSS)
    │   ├── Dark theme variables
    │   ├── Top bar, progress bar, stage chips
    │   ├── Sidebar cards, sentiment pills
    │   ├── Input area and send button
    │   └── Chat bubble styles (inside iframe)
    │
    ├── UI RENDERERS
    │   ├── render_topbar()            App header with LLM status
    │   ├── render_progress()          Animated stage progress bar with icon chips
    │   ├── render_chat()              iframe chat via components.html
    │   ├── render_sidebar()           Live profile + sentiment dashboard
    │   └── render_end()               Completion screen with restart button
    │
    └── main()                         Entry point — wires everything together

#Key Design Decisions

 Decision | Reason |

 Stage machine for data collection - Deterministic — no LLM needed for simple fields. Prevents hallucination and ensures all 7 fields are always collected |
 LLM only for question generation - Maximises LLM value while keeping the rest of the app fast and reliable |
 Chat rendered via components.html - Streamlit's HTML sanitizer strips bold and italic tags. An iframe bypasses this so markdown renders correctly |
 Dynamic input widget key - Streamlit has no native clear input API. Incrementing the key forces a fresh empty widget after each submit |
 Pre-emptive _li lock - Set before handle() is called to prevent double-fire when Streamlit reruns the script |

---

## 🧠 Prompt Design

### Prompt — Technical Question Generation

    ### System:
    You are a senior technical interviewer. Output ONLY a numbered list.
    No preamble. No extra text.

    ### Task:
    Generate exactly 5 technical interview questions for a candidate
    whose tech stack is: {tech_stack}

    Rules:
    - Questions must be specific to the technologies listed
    - Mix: 2 conceptual, 2 practical/coding, 1 system-design
    - Output format strictly:
      1. question
      2. question
      3. question
      4. question
      5. question

    ### Questions:
    1.

### Engineering Decisions in This Prompt

| Decision | Why |
|---|---|
| "Output ONLY a numbered list" | Stops the model adding conversational text before the list |
| "No preamble. No extra text." | Reinforces the format constraint — 3B models need repetition |
| "Mix: 2 conceptual, 2 practical, 1 system-design" | Ensures varied difficulty levels in every interview |
| Priming with 1. | Forces the model to start the list immediately with no intro sentence |
| temperature=0.4 | Lower than default (0.7) — reduces randomness and hallucination risk |
| repeat_penalty=1.15 | Prevents the model repeating the same question twice |
| Stop tokens | Cuts off output if the model starts generating a new section |
| Validation: len(q) > 20 and "?" in q | Rejects filler lines — only real questions with a ? are accepted |
| Minimum 3 questions required | If fewer than 3 valid questions parsed, falls back to question bank |

### Information Gathering — No LLM Needed

Each information stage uses pure Python validation:

    # Email validation
    if "@" not in u or "." not in u.split("@")[-1]:
        return "Please enter a valid email."

    # Phone validation
    if len(re.sub(r"[^\d]", "", u)) < 7:
        return "Please enter a valid phone number."

This approach is faster, more reliable, and eliminates hallucination risk entirely.

### Fallback Question Bank

14 supported stacks:
python, django, flask, fastapi, javascript, react, node, sql, postgresql, mongodb, docker, kubernetes, aws, git

Selection algorithm:
1. Convert tech stack string to lowercase
2. Match against priority-ordered keyword list (most specific first)
3. Pick one question per matched technology (no duplicates)
4. Fill remaining slots from default general engineering questions
5. Return exactly 5 questions

# Sentiment Analysis

    POS_WORDS = {great, confident, built, solved, expert, implemented, ...}
    NEG_WORDS = {not sure, confused, never, struggle, haven't, unclear, ...}

    score = (positive_hits - negative_hits) / total_hits
    score > 0.2  →  Positive  "Confident & knowledgeable"
    score < -0.2 →  Negative  "Some uncertainty expressed"
    otherwise    →  Neutral   "Measured response"

Overall confidence score formula:

    score = (positive × 1.0 + neutral × 0.5 + negative × 0.0) / total × 100
    >= 70  →  High Confidence
    >= 45  →  Moderate Confidence
    <  45  →  Low Confidence

---

## 🐛 Challenges & Solutions

| # | Challenge | Root Cause |

|---|---|---|---|
| 1 | ChatGPT / Claude / Gemini APIs unavailable | All major LLM APIs require paid subscriptions — not feasible for a student project 
Solution - Used orca_mini_3b.IQ3_M.gguf — a free, open-source model that runs entirely on local CPU with zero API cost 
| 2 | llama-cpp-python fails to install on Python 3.13 | No pre-built wheel — requires C++ compiler 
Solution - Install Visual Studio Build Tools with "Desktop development with C++".
| 3 | integer divide by zero error loading the model | ctransformers does not support IQ3_M quantization format 
Solution - Switched to llama-cpp-python which handles IQ3_M correctly.
| 4 | LLM hallucinating fake candidate answers in transitions | 3B model too small to comment reliably on specific answers 
solution - Removed LLM from transitions entirely — hardcoded "Thank you for your answer" .
| 5 | LLM generating conversational filler instead of questions | Model ignores format at higher temperature 
Solution - Added strict format constraints, temperature=0.4, output validation requiring ? 
| 6 | Bold text rendering blank in chat bubbles | Streamlit HTML sanitizer strips bold and italic tags from unsafe_allow_html content 
Solution - Switched chat to st.components.v1.html() — renders in sandboxed iframe, no sanitizer .
| 7 | Chat message order wrong | Both messages stored in one dict — no guaranteed render order 
solution- Store user message first, then bot reply as separate role/text entries .
| 8 | Input not clearing after send | Streamlit has no native clear API 
Solution -  Dynamic widget key inp_{counter} — incrementing forces a fresh empty input widget 
| 9 | IndexError: list index out of range on question stage | Streamlit reruns script on every interaction — q_idx incremented twice before lock 
Solution - Triple guard: bounds check on q_idx, stage check, _li lock set before handle() call 
| 10 | Enter key not working | st.text_input only triggers on value change 
Solution - Added has_new check: user_input.strip() != s._li fires on Enter without needing the button 

---

## 📦 requirements.txt

    streamlit>=1.32.0
    llama-cpp-python>=0.3.0

---

## 🔐 Data Privacy

- All candidate data exists only in Streamlit session state (in-memory, per browser session)
- Nothing is written to disk or sent externally
- The LLM runs entirely on the local CPU — zero cloud calls
- Data is cleared automatically when the browser tab is closed
- No third-party data processors involved — GDPR-friendly by design Sonnet 4.6