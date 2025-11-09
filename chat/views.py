import os
import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import google.generativeai as genai
from .models import chats
from .anyliser import analyze_chats

# Helper function to safely get API key
def get_gemini_api_key():
    try:
        return settings.GEMINI_API_KEY
    except AttributeError:
        return os.environ.get('GEMINI_API_KEY')

# Configure Gemini API
api_key = get_gemini_api_key()
if api_key:
    genai.configure(api_key=api_key)
else:
    print("WARNING: GEMINI_API_KEY not found in settings or environment.")

def get_system_prompt(year, level):
    year_map = {'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th'}
    year_str = year_map.get(year, '1st')
    level_str = level if level in ['easy', 'medium', 'hard', 'pro'] else 'medium'
    return f'''You are an expert interview preparation coach. Your role is to guide candidates professionally and supportively while building their confidence throughout the interaction. Avoid any introductions.

Interaction Framework:
Start the session by asking the candidate for their target role and company, and then confirm if the focus should be on a technical deep-dive, a behavioral session, or a full mock interview. Ask relevant, role-specific questions one at a time, tailored to the candidate's experience of {year_str} year and a {level_str} difficulty level. After each response, provide simple and direct feedback covering two key areas: what they did well and what could be improved, along with one concise, actionable tip. Conclude each feedback round by checking for understanding with a simple question like, "Does that make sense?" before proceeding. Throughout the interaction, maintain a confident and professional yet conversational tone, ensuring all responses are direct and to the point,remember answer without any formatting like asterisks or bullet points.'''

def get_chat_history(request):
    '''Retrieve chat history from session or database'''
    if 'chat_history' not in request.session:
        request.session['chat_history'] = []
        if request.user.is_authenticated:
            # Load last 50 messages from DB to avoid overloading session
            user_chats = chats.objects.filter(user=request.user).order_by('-timestamp')[:50]
            history = []
            for chat in reversed(user_chats): # Reverse back to chronological order
                history.append({'user': chat.user_input, 'bot': chat.bot_reply})
            request.session['chat_history'] = history
    return request.session['chat_history']

@login_required
def chat_view(request):
    '''Main chat view - handles both GET and POST requests'''
    if request.method == 'GET':
        chat_history = get_chat_history(request)
        return render(request, 'chat/index.html', {'chat_history': chat_history})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
            
            if not user_message:
                return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
            if not get_gemini_api_key():
                 return JsonResponse({'error': 'Server misconfiguration: API Key missing.'}, status=500)

            chat_history = get_chat_history(request)
            year = request.session.get('year', 'first')
            level = request.session.get('level', 'medium')
            system_prompt = get_system_prompt(year, level)
            
            # Build context for Gemini
            conversation_context = system_prompt + "\n\nConversation History:\n"
            # Limit context to last 10 turns to save tokens and keep relevant
            recent_history = chat_history[-10:] 
            for msg in recent_history:
                conversation_context += f"User: {msg['user']}\nAssistant: {msg['bot']}\n"
            conversation_context += f"User: {user_message}\nAssistant:"
            
            try:
                model = genai.GenerativeModel('gemini-1.5-flash') # Updated model name
                response = model.generate_content(conversation_context)
                bot_response = response.text
            except Exception as e:
                print(f"Gemini API Error: {e}")
                return JsonResponse({'error': 'AI service temporarily unavailable. Please try again.'}, status=503)
            
            # Update session history
            chat_history.append({'user': user_message, 'bot': bot_response})
            request.session['chat_history'] = chat_history
            request.session.modified = True
            
            # Save to DB asynchronously if possible, but for now synchronously
            try:
                chats.objects.create(user=request.user, user_input=user_message, bot_reply=bot_response)
            except Exception as e:
                print(f"DB Save Error: {e}") # Non-critical error, don't fail request

            return JsonResponse({'status': 'success', 'bot_response': bot_response})
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except Exception as e:
            print(f"Unexpected Error: {e}")
            return JsonResponse({'error': 'An unexpected error occurred'}, status=500)

@csrf_exempt
@login_required
def run_code(request):
    """Executes code using Piston API"""
    if request.method != 'POST':
         return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)

    try:
        data = json.loads(request.body)
        code = data.get('code', '')
        language = data.get('language', 'python')

        # Piston API configuration
        language_map = {
            'python': {'language': 'python', 'version': '3.10.0'},
            'javascript': {'language': 'javascript', 'version': '18.15.0'},
            'c': {'language': 'c', 'version': '10.2.0'},
            'cpp': {'language': 'c++', 'version': '10.2.0'},
            'java': {'language': 'java', 'version': '15.0.2'},
        }
        
        config = language_map.get(language.lower())
        if not config:
            return JsonResponse({'error': f'Language {language} not supported yet.'}, status=400)
        
        payload = {
            "language": config['language'],
            "version": config['version'],
            "files": [{"content": code}],
            "stdin": "",
            "run_timeout": 5000,
            "compile_timeout": 10000,
        }
        
        # Call Piston API
        response = requests.post("https://emkc.org/api/v2/piston/execute", json=payload, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            run_status = result.get('run', {})
            output = run_status.get('output', '')
            
            # Check for signals (like segfaults) or errors
            if run_status.get('signal'):
                 output += f"\nProcess terminated by signal: {run_status.get('signal')}"

            return JsonResponse({'output': output if output else "Program executed successfully with no output."})
        else:
            return JsonResponse({'error': 'External compiler service failed.', 'details': response.text}, status=502)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except requests.Timeout:
         return JsonResponse({'error': 'Compiler request timed out.'}, status=504)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ... (Keep other views like anylise_chat_history, swot_analysis_view, logout_view as they were) ...
def swot_analysis_view(request):
    chat_history = chats.objects.filter(user=request.user)
    analysis = analyze_chats(request.user)
    return render(request, 'chat/swot_analysis.html', {'chat_history': chat_history, 'analysis': analysis})

def logout_view(request):
    request.session.flush()
    return redirect('login')