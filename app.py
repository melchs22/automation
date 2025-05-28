import streamlit as st
import os
from huggingface_hub import InferenceClient

# Initialize Hugging Face Inference Client
try:
    hf_token = st.secrets["HF_TOKEN"] if "HF_TOKEN" in st.secrets else os.getenv("HF_TOKEN")
    if not hf_token:
        raise ValueError("Hugging Face API token not found. Set HF_TOKEN in Streamlit secrets or environment variables.")
    client = InferenceClient(token=hf_token)
except Exception as e:
    st.error(f"Error initializing Hugging Face client: {str(e)}")
    st.stop()

# Streamlit app configuration
st.set_page_config(page_title="Call Center AI Guide", page_icon="📞")
st.title("📞 Call Center AI Guide")
st.markdown("Ask your question, and our AI will provide a professional response to assist you.")

# Initialize session state for conversation history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Welcome to the Call Center AI Guide! How can I assist you today?"
        }
    ]

# Display conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
user_input = st.chat_input("Type your question here...")

if user_input:
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Display user message
    with st.chat_message("user"):
        st.markdown(user_input)

    # Prepare prompt for the AI
    prompt = (
        "You are a professional call center AI guide. Provide concise, polite, and accurate responses to user queries. "
        "Use a friendly and professional tone, as if assisting a customer over the phone. "
        "If the query is unclear, ask for clarification. "
        "Here is the user's query:\n\n"
        f"{user_input}\n\n"
        "Respond appropriately:"
    )

    try:
        # Call Hugging Face Inference API
        response = client.text_generation(
            prompt,
            model="mistralai/Mixtral-8x7B-Instruct-v0.1",
            max_new_tokens=200,
            temperature=0.7,
            do_sample=True
        )

        # Clean and format response
        response = response.strip()

        # Add AI response to history
        st.session_state.messages.append({"role": "assistant", "content": response})

        # Display AI response
        with st.chat_message("assistant"):
            st.markdown(response)

    except Exception as e:
        st.error(f"Error generating response: {str(e)}")
