import streamlit as st
import httpx

API_URL = "http://localhost:8000/api"

st.set_page_config(page_title="dubizzle Cars AI Assistant", page_icon="🚗", layout="wide")
st.title("🚗 dubizzle Cars AI Assistant")

st.sidebar.header("User Identification")
uid = st.sidebar.text_input("User ID", value="usr_101")

if "messages" not in st.session_state or st.session_state.get("last_uid") != uid:
    st.session_state["messages"] = []
    st.session_state["last_uid"] = uid
    try:
        r = httpx.get(f"{API_URL}/user/{uid}", timeout=10.0)
        if r.status_code == 200:
            u = r.json()
            if u.get("name"):
                st.sidebar.success(f"Welcome back, {u['name']}!")
            if u.get("prefs"):
                st.sidebar.markdown("**Known preferences:**")
                st.sidebar.json(u["prefs"])
            # Optionally replay prior conversation into the chat window
            for turn in (u.get("history") or [])[-6:]:
                st.session_state["messages"].append({"role": "user", "content": turn["user"]})
                st.session_state["messages"].append({"role": "assistant", "content": turn["assistant"]})
    except Exception:
        st.sidebar.warning("Backend API disconnected")

for m in st.session_state["messages"]:
    with st.chat_message(m["role"]):
        st.write(m["content"])

inp = st.chat_input("Ask about cars, booking viewings, or your preferences...")
if inp:
    st.session_state["messages"].append({"role": "user", "content": inp})
    with st.chat_message("user"):
        st.write(inp)

    with st.chat_message("assistant"):
        with st.spinner("Searching inventory..."):
            try:
                res = httpx.post(f"{API_URL}/chat", json={"uid": uid, "message": inp}, timeout=30.0)
                if res.status_code == 200:
                    data = res.json()
                    ans = data["response"]
                    st.write(ans)
                    st.session_state["messages"].append({"role": "assistant", "content": ans})
                else:
                    st.error(f"Error communicating with backend ({res.status_code}).")
            except Exception as e:
                st.error(f"Failed to connect: {e}")
