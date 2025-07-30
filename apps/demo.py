import streamlit as st

st.title("Authenticated State Example")

# Initialize counter
if "count" not in st.session_state:
    st.session_state.count = 0

if st.button("Increment"):
    st.session_state.count += 1

st.write("Count:", st.session_state.count)

# Load user from JWT on first run
if "user" not in st.session_state:
    try:
        user = st.query_params("user")
        st.session_state.user = user
    except:
        st.session_state.user = {"error": "invalid user"}


st.write("User:", st.session_state.user)
