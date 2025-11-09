import google.generativeai as genai
from .models import chats
from django.conf import settings
import logging

# Configure the library to use the API key from your settings
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Failed to configure Gemini API: {e}")

def analyze_chats(user):
    try:
        # Step 1: Get all chats for the user
        user_chats = chats.objects.filter(user=user)

        # Handle case where there is no chat history
        if not user_chats.exists():
             return ["No chat history to analyze.", "Start a conversation first!", 0, 0, 0]

        # Step 2: Combine all chats into a single string for the model
        chat_history = "\n\n".join([
            f"User: {c.user_input}\nAI: {c.bot_reply}"
            for c in user_chats
        ])

        # A more direct prompt for the model
        prompt = f"""
        Analyze the following interview practice conversation. Based on the user's responses, provide a SWOT analysis.

        Return the analysis ONLY as a Python list with 5 elements:
        1. A string describing the user's strengths.
        2. A string describing the user's weaknesses.
        3. An integer score for strengths (0-100).
        4. An integer score for weaknesses (0-100, where higher means more weakness).
        5. A final combined score for the user's performance (0-100).

        Do not include any explanation, introductory text, or markdown formatting like ```python. The output must be a valid Python list.

        Conversation:
        {chat_history}
        """

        # Step 3: Use the official Gemini library to get the analysis
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)

        # Step 4: Clean the response text
        clean_text = response.text.strip()

        # Step 5: Convert the string list to a Python list
        # The eval() function is used here as the prompt strictly asks for a list.
        result = eval(clean_text)
        
        # Basic validation to ensure the result is in the correct format
        if isinstance(result, list) and len(result) == 5:
            print(f"Analysis successful: {result}")
            return result
        else:
            raise ValueError("Model did not return the expected list format.")

    except Exception as e:
        logging.error(f"Error during analysis for user {user.username}: {e}")
        return ["Error analyzing chat.", "Could not generate analysis due to an internal error.", 0, 0, 0]