import os
import uuid
import requests
import streamlit as st

# -----------------------
# Config
# -----------------------
API_BASE = os.getenv("AGENT_API_BASE", "http://localhost:8000")  # FastAPI base URL
CHAT_ENDPOINT = f"{API_BASE}/chat"
RESET_ENDPOINT = f"{API_BASE}/reset"
HEALTH_ENDPOINT = f"{API_BASE}/health"

st.set_page_config(page_title="Agents Chat", page_icon="🤖", layout="centered")

# -----------------------
# Session state
# -----------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    # Store chat UI history locally for display (server maintains its own history)
    # Only store 'user' and 'assistant' roles to keep chat UI stable.
    st.session_state.messages = []  # list[{"role": "user"|"assistant", "content": str}]

# Optionally keep the last metadata for this session (not rendered as chat)
if "last_metadata" not in st.session_state:
    st.session_state.last_metadata = None

# -----------------------
# Sidebar controls
# -----------------------
with st.sidebar:
    st.title("⚙️ Settings")
    st.caption(f"Session ID: `{st.session_state.session_id}`")

    if st.button("🔁 Reset conversation (server + UI)"):
        try:
            requests.post(
                RESET_ENDPOINT,
                json={"session_id": st.session_state.session_id},
                timeout=15
            )
        except Exception as e:
            st.warning(f"Reset call failed: {e}")
        st.session_state.messages = []
        st.session_state.last_metadata = None
        st.success("Conversation reset.")

    st.divider()
    if st.button("🔄 New session ID"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.last_metadata = None
        st.success("Session updated. UI history cleared.")

    st.divider()
    try:
        resp = requests.get(HEALTH_ENDPOINT, timeout=5)
        ok = (resp.status_code == 200 and resp.json().get("status") == "ok")
        st.caption(f"API health: {'🟢 OK' if ok else '🔴 Unavailable'}")
    except Exception:
        st.caption("API health: 🔴 Unavailable")

# -----------------------
# Header
# -----------------------
st.title("🤖 Agents Chat")
st.write("Ask me anything. The assistant uses RAG and tools under the hood.")

# -----------------------
# Render chat history
# -----------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -----------------------
# Chat input
# -----------------------
user_input = st.chat_input("Type your message...")

if user_input:
    # Append user to UI/history
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Call backend
    try:
        payload = {
            "session_id": st.session_state.session_id,
            "user_input": user_input
        }

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                r = requests.post(CHAT_ENDPOINT, json=payload, timeout=36000)

                # Defaults
                text = "No answer returned."
                metadata_display = None

                if r.status_code != 200:
                    # API error path
                    st.error(f"API error {r.status_code}: {r.text}")
                    text = "Sorry, something went wrong while contacting the server."

                else:
                    # Success path
                    # Be defensive: server might return non-JSON
                    data = None
                    try:
                        data = r.json()
                    except ValueError:
                        st.error("Server returned invalid JSON.")
                        data = None

                    if data is not None:
                        # Expected: data.get("answer") may be dict or string
                        assistant_answer = data.get("answer")

                        if isinstance(assistant_answer, dict):
                            # Expected shape: {'final_answer': {'text': ...}, 'metadata': {...}}
                            final_answer = assistant_answer.get("final_answer", {}) or {}
                            text = final_answer.get("text", text)

                            raw_meta = assistant_answer.get("metadata", {}) or {}

                            # Build a safe, trimmed metadata object
                            metadata_display = {
                                'total_duration': raw_meta.get("total_duration"),
                                'load_duration': raw_meta.get("load_duration"),
                                'prompt_eval_duration': raw_meta.get("prompt_eval_duration"),
                                'eval_duration': raw_meta.get("eval_duration"),
                                'prompt_eval_count': raw_meta.get("prompt_eval_count"),
                                'eval_count': raw_meta.get("eval_count")
                            }

                        elif isinstance(assistant_answer, str):
                            # Plain string answer
                            text = assistant_answer

                        else:
                            # Fallback stays as default text
                            pass

                # Render the assistant answer
                st.markdown(text)
                st.markdown("---")

                # Render metadata (if present)
                if metadata_display is not None:
                    st.caption("Execution metadata")
                    st.json(metadata_display)

                # Optionally persist last metadata for later use
                st.session_state.last_metadata = metadata_display

        # Append assistant text to UI history (just the text)
        st.session_state.messages.append({"role": "assistant", "content": text})

    except requests.RequestException as e:
        with st.chat_message("assistant"):
            st.error(f"Request failed: {e}")
        st.session_state.messages.append({"role": "assistant", "content": "Request failed. Please try again."})