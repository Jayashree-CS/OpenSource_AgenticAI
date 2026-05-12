from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv

load_dotenv()

def get_llm(model_type="groq_fast"):
    """
    Hybrid LLM Routing:
    - groq_fast: Llama 3.1 8B (Speed)
    - groq_versatile: Llama 3.3 70B (Reasoning)
    - gemini_flash: Gemini 2.0 Flash (Lightweight/Classification)
    """
    if model_type == "gemini_flash":
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0
        )
    elif model_type == "groq_versatile":
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0
        )
    else: # Default groq_fast
        return ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0
        )
 
# Default instances
llm = get_llm("groq_fast")
llm_versatile = get_llm("groq_versatile")
llm_flash = get_llm("gemini_flash")