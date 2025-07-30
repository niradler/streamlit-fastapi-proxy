import random
import time

import streamlit as st

st.title("🚀 Test Streamlit App")

st.write("This is a test app to demonstrate the WebSocket-enabled proxy!")

# Add some interactive elements that require WebSocket
if st.button("Generate Random Number"):
    st.success(f"Random number: {random.randint(1, 100)}")

# Add a slider that updates in real-time
value = st.slider("Select a value", 0, 100, 50)
st.write(f"Current value: {value}")

# Add a text input
name = st.text_input("Enter your name:")
if name:
    st.write(f"Hello, {name}! 👋")

# Add a chart that could benefit from WebSocket updates
chart_data = []
for i in range(10):
    chart_data.append({"x": i, "y": random.randint(1, 10)})

st.line_chart(chart_data)

# Add a status indicator
st.markdown("---")
st.write("🟢 **Status:** App is running and WebSocket connection is active!")
st.write(f"⏰ **Current time:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
