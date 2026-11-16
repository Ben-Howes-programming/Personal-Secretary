"""
assistant.py
============
Purpose : Talk to Claude with your own data as context, by typing or by voice.
Location: views/assistant.py
Tokens  : Only the sources you tick are sent. Only the last few turns are re-sent.
          Chats are saved locally so you can pick one up later.
"""

import hashlib

import streamlit as st

import config
from ai import claude, context, voice
from database import database as db
from ui import state
from ui import theme as ui

ui.header("Assistant", "Ask about your mail, week, money, training or course.")

backend = claude.backend_status()
if backend["active"] is None:
    ui.note("bad", "Claude is not connected. Install Claude Code and sign in with your Pro account, or add an API key. Settings has the steps.")
    st.stop()

# ------------------------------------------------------------------
# Sidebar: saved chats and options
# ------------------------------------------------------------------
with st.sidebar:
    ui.section("Chats")
    if ui.button("New chat", type="primary"):
        st.session_state.pop("conversation_id", None)
        st.rerun()
    for chat in db.list_conversations(10):
        if ui.button(chat["title"] or "Untitled", key=f"chat_{chat['id']}"):
            st.session_state["conversation_id"] = chat["id"]
            st.rerun()

conversation_id = st.session_state.get("conversation_id")
history = db.get_messages(conversation_id) if conversation_id else []

# ------------------------------------------------------------------
# Controls
# ------------------------------------------------------------------
options, model_col, voice_col = st.columns([3, 1, 1])
with options:
    sources = st.pills("Share with Claude", context.SOURCES, selection_mode="multi",
                       default=context.DEFAULT_SOURCES, key="chat_sources",
                       help="Fewer sources means fewer tokens per message.")
with model_col:
    tier = st.selectbox("Model", ["chat", "fast", "deep"], key="chat_tier",
                        format_func={"chat": "Balanced", "fast": "Quick and cheap", "deep": "Deepest"}.get)
with voice_col:
    speak = st.toggle("Read replies aloud", value=bool(state.pref("speak_replies")), disabled=not voice.can_speak())
    if speak != bool(state.pref("speak_replies")):
        state.set_pref("speak_replies", speak)
    if voice.can_speak() and st.button("Stop speaking"):
        voice.stop_speaking()

# ------------------------------------------------------------------
# Conversation so far
# ------------------------------------------------------------------
for message in history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = None
if not history:
    ui.muted("Try one of these, or ask anything.")
    starters = ["What needs my attention today?", "Plan my week around lectures, gym and deadlines.",
                "Where is my free time for study this week?", "Explain what moved my funds this week."]
    for column, starter in zip(st.columns(len(starters)), starters):
        if column.button(starter, key=f"starter_{starter[:12]}"):
            prompt = starter

# Voice in: record, transcribe locally, then treat it as a typed message
if voice.stt_engine():
    recording = st.audio_input("Speak instead of typing", key="voice_in")
    if recording is not None:
        audio = recording.getvalue()
        fingerprint = hashlib.sha1(audio).hexdigest()
        if st.session_state.get("last_audio") != fingerprint:   # do not resend the same clip on every rerun
            st.session_state["last_audio"] = fingerprint
            with st.spinner("Transcribing on your Mac"):
                heard, problem = voice.transcribe(audio)
            if problem:
                st.warning(problem)
            elif heard:
                prompt = heard
else:
    ui.muted("Voice: press the microphone key in the box below to dictate (macOS dictation). "
             "For hands-free voice, see the voice section of the setup guide.")

typed = st.chat_input("Message your secretary")
prompt = typed or prompt

# ------------------------------------------------------------------
# Answer
# ------------------------------------------------------------------
if prompt:
    if conversation_id is None:
        conversation_id = db.create_conversation(claude.title_for(prompt))
        st.session_state["conversation_id"] = conversation_id
    db.add_message(conversation_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    events = state.week_events() if "Calendar" in (sources or []) else []
    facts = context.build_context(sources or [], events)
    recent = (history + [{"role": "user", "content": prompt}])[-config.CHAT_HISTORY_TURNS:]
    while recent and recent[0]["role"] != "user":     # the API needs the first turn to be yours
        recent = recent[1:]
    with st.chat_message("assistant"):
        with st.spinner("Thinking"):
            answer = st.write_stream(claude.stream(recent, context=facts, tier=tier))
    answer = answer if isinstance(answer, str) else "".join(str(part) for part in answer)
    db.add_message(conversation_id, "assistant", answer)
    if speak:
        voice.speak(answer)

if conversation_id and history:
    if st.button("Delete this chat"):
        db.delete_conversation(conversation_id)
        st.session_state.pop("conversation_id", None)
        st.rerun()
