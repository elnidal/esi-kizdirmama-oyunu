import os
import time
import random
import json
import requests
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# OpenAI API configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')  # Get API key from environment variable
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Game configuration
MAX_SCENARIOS = 20  # Increased to 20 questions
WRONG_CHOICES_THRESHOLD = {
    "divorce": 8,     # 8+ wrong choices leads to divorce
    "couch": 6,       # 6-7 wrong choices leads to couch
    "mother_in_law": 4, # 4-5 wrong choices leads to mother-in-law
    "cold_war": 2,    # 2-3 wrong choices leads to cold war
    "happy": 0        # 0-1 wrong choices leads to happy ending
}

# Base scenarios to start with (we'll generate more dynamically)
base_scenarios = [
    {
        'title': 'Senaryo 1: Saç Kesimi Faciası',
        'description': 'Eşin yeni bir saç kesimi yaptırdı ve soruyor, "Aşkım, nasıl olmuş?" Saç kesimi hiç hoşuna gitmedi ama ne diyeceksin?',
        'choice_a': 'Çok güzel olmuş hayatım, sana her şey yakışıyor!',
        'choice_b': 'Eskisi daha iyiydi sanki…',
        'correct_choice': 'A',
        'next_scenario_a': 2,  # If A is chosen, go to scenario 2
        'next_scenario_b': 3,  # If B is chosen, go to scenario 3
        'image': 'scenario1.jpg'
    }
]

# Endings remain the same
endings = {
    'happy': {
        'title': 'MUTLU SON!',
        'description': 'Tebrikler! Evliliğin hala sapasağlam devam ediyor. Eşini mutlu etmeyi başardın ve huzurlu bir ilişkiniz var. Karı kızdırmama konusunda gerçek bir ustasın!',
        'image': 'ending_happy.jpg',
        'type': 'result-happy'
    },
    'cold_war': {
        'title': 'SOĞUK SAVAŞ!',
        'description': 'Eşin seninle konuşmuyor ve evde buz gibi bir hava var. Birkaç gün boyunca tek kelime etmeden yan yana yaşayacaksınız. Belki bir çiçek ya da hediye ile durumu kurtarabilirsin.',
        'image': 'ending_cold_war.jpg',
        'type': 'result-cold-war'
    },
    'mother_in_law': {
        'title': 'KAYINVALİDE MÜDAHALESİ!',
        'description': 'Eşin annesini arayıp senin hakkında şikayet etti. Şimdi kayınvaliden her gün evde ve sana "Kızımı nasıl üzersin?" bakışları atıyor. Evindeki huzur kaçtı!',
        'image': 'ending_mother_in_law.jpg',
        'type': 'result-mother-in-law'
    },
    'couch': {
        'title': 'KANEPE ENDİNG!',
        'description': 'Tebrikler! Artık yatak odasına giremiyorsun. Önümüzdeki birkaç haftada kanepede uyuyacaksın ve bel ağrısı çekeceksin. En azından kumanda sende!',
        'image': 'ending_couch.jpg',
        'type': 'result-couch'
    },
    'divorce': {
        'title': 'ANINDA BOŞANMA!',
        'description': 'Eşin avukatını aradı bile! Evliliğin bitme noktasına geldi. Belki hala bir şansın vardır... ya da bekarlığın tadını çıkarmaya hazırlan!',
        'image': 'ending_divorce.jpg',
        'type': 'result-divorce'
    }
}

# Scenario topics for generation
scenario_topics = [
    "Eşinin yeni kıyafeti hakkında yorum yapma",
    "Kayınvalide ile ilgili bir durum",
    "Eşinin arkadaşlarıyla plan yapma",
    "Unutulan önemli bir tarih (doğum günü, yıldönümü)",
    "Eşinin yaptığı yemek hakkında yorum yapma",
    "Eşinin harcamaları hakkında konuşma",
    "Akşam planları yapma",
    "Tatil planlaması",
    "Eşinin eski sevgilisiyle karşılaşma",
    "Eşinin iş arkadaşları hakkında konuşma",
    "Eşinin ailesiyle geçirilecek zaman",
    "Ev işleri paylaşımı",
    "Çocuk yetiştirme konusunda anlaşmazlık",
    "Sosyal medya kullanımı",
    "İş-yaşam dengesi",
    "Araba kullanma tarzı",
    "Alışveriş alışkanlıkları",
    "Televizyon/film seçimi",
    "Evcil hayvan edinme kararı",
    "Taşınma veya ev değiştirme kararı",
    "Maddi konularda anlaşmazlık",
    "Sağlık ve beslenme alışkanlıkları",
    "Arkadaş seçimi ve sosyal çevre",
    "Teknoloji kullanımı ve ekran süresi",
    "Gelecek planları hakkında konuşma"
]

def generate_scenario(scenario_id, previous_choice=None, previous_scenario=None):
    """Generate a new scenario using OpenAI API based on previous choices"""
    if not OPENAI_API_KEY:
        # Fallback to predefined scenarios if no API key
        return generate_fallback_scenario(scenario_id)
    
    # Select a random topic
    topic = random.choice(scenario_topics)
    
    # Create context based on previous scenario and choice if available
    context = ""
    if previous_scenario and previous_choice:
        context = f"Previous scenario: {previous_scenario['description']} Player chose: {previous_scenario['choice_' + previous_choice.lower()]}"
    
    # Prepare the prompt for OpenAI
    prompt = f"""
    Create a humorous marriage scenario for a Turkish couple game called "Eşi Kızdırmama Oyunu" (Don't Make Your Wife Angry).
    
    Topic: {topic}
    Scenario ID: {scenario_id}
    {context}
    
    The scenario should be funny, slightly exaggerated, and based on common relationship dynamics in Turkish culture.
    It should include:
    1. A title starting with "Senaryo {scenario_id}: "
    2. A description of the situation (1-2 sentences)
    3. Two choices (A and B) where one is clearly better for maintaining marital harmony
    4. Indicate which choice is correct (A or B)
    5. Two different next scenario IDs depending on which choice is made
    
    Format the response as a JSON object with the following structure:
    {{
        "title": "Senaryo X: [Title]",
        "description": "[Description]",
        "choice_a": "[Choice A text]",
        "choice_b": "[Choice B text]",
        "correct_choice": "[A or B]",
        "next_scenario_a": [scenario ID if A is chosen],
        "next_scenario_b": [scenario ID if B is chosen]
    }}
    
    Make sure the next_scenario_a and next_scenario_b are numbers between 1 and {MAX_SCENARIOS}, and they should be different from the current scenario ID ({scenario_id}).
    """
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        response = requests.post(OPENAI_API_URL, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            scenario_text = result['choices'][0]['message']['content']
            
            # Extract the JSON part from the response
            try:
                scenario_json = json.loads(scenario_text)
                scenario_json['image'] = f'scenario{scenario_id}.jpg'
                return scenario_json
            except json.JSONDecodeError:
                print(f"Error parsing JSON from API response: {scenario_text}")
                return generate_fallback_scenario(scenario_id)
        else:
            print(f"API error: {response.status_code}, {response.text}")
            return generate_fallback_scenario(scenario_id)
            
    except Exception as e:
        print(f"Error generating scenario: {e}")
        return generate_fallback_scenario(scenario_id)

def generate_fallback_scenario(scenario_id):
    """Generate a fallback scenario when API is not available"""
    topic = random.choice(scenario_topics)
    
    # Create a basic scenario structure
    scenario = {
        'title': f'Senaryo {scenario_id}: {topic}',
        'description': f'Eşinle {topic.lower()} konusunda bir durum yaşıyorsunuz. Ne yapacaksın?',
        'choice_a': 'Eşinin istediği şekilde davranırsın.',
        'choice_b': 'Kendi bildiğin gibi davranırsın.',
        'correct_choice': 'A',
        'next_scenario_a': min(scenario_id + 1, MAX_SCENARIOS),
        'next_scenario_b': min(scenario_id + 2, MAX_SCENARIOS),
        'image': f'scenario{scenario_id}.jpg'
    }
    
    return scenario

def get_scenario(scenario_id, previous_choice=None, previous_scenario=None):
    """Get a scenario by ID, generating it if needed"""
    if scenario_id == 1:
        return base_scenarios[0]
    
    # Check if we've already generated this scenario in the session
    if 'scenarios' in session and str(scenario_id) in session['scenarios']:
        return session['scenarios'][str(scenario_id)]
    
    # Generate a new scenario
    new_scenario = generate_scenario(scenario_id, previous_choice, previous_scenario)
    
    # Store it in the session
    if 'scenarios' not in session:
        session['scenarios'] = {}
    
    session['scenarios'][str(scenario_id)] = new_scenario
    return new_scenario

def determine_ending(wrong_choices):
    """Determine which ending to show based on wrong choices"""
    if wrong_choices >= WRONG_CHOICES_THRESHOLD["divorce"]:
        return endings["divorce"]
    elif wrong_choices >= WRONG_CHOICES_THRESHOLD["couch"]:
        return endings["couch"]
    elif wrong_choices >= WRONG_CHOICES_THRESHOLD["mother_in_law"]:
        return endings["mother_in_law"]
    elif wrong_choices >= WRONG_CHOICES_THRESHOLD["cold_war"]:
        return endings["cold_war"]
    else:
        return endings["happy"]

@app.route('/')
def index():
    return render_template('dynamic/index.html')

@app.route('/start_game')
def start_game():
    # Initialize game state
    session.clear()
    session.permanent = True
    session['current_scenario'] = '1'
    session['wrong_choices'] = 0
    session['choices_made'] = []
    session['scenarios'] = {}
    session['scenarios']['1'] = base_scenarios[0]  # Add the first scenario
    
    return redirect(url_for('show_scenario', scenario_id=1))

@app.route('/scenario/<int:scenario_id>')
def show_scenario(scenario_id):
    # Initialize session if needed
    if 'current_scenario' not in session:
        return redirect(url_for('start_game'))
        
    # Check if we've reached the maximum number of scenarios
    if int(scenario_id) > MAX_SCENARIOS:
        return redirect(url_for('game_result'))
    
    # Initialize scenarios in session if it doesn't exist
    if 'scenarios' not in session:
        session['scenarios'] = {}
        session['scenarios']['1'] = base_scenarios[0]  # Add the first scenario
    
    # Get the previous scenario and choice if available
    previous_scenario = None
    previous_choice = None
    
    if len(session.get('choices_made', [])) > 0:
        previous_choice = session['choices_made'][-1]
        previous_scenario_id = session['current_scenario']
        previous_scenario = session['scenarios'].get(previous_scenario_id)
    
    # Get or generate the current scenario
    scenario = get_scenario(scenario_id, previous_choice, previous_scenario)
    
    # Update current scenario
    session['current_scenario'] = str(scenario_id)
    
    # Force session to save
    session.modified = True
    
    return render_template('dynamic/game.html', 
                          scenario=scenario,
                          scenario_id=scenario_id,
                          total_scenarios=MAX_SCENARIOS,
                          progress=int((int(scenario_id)-1) / MAX_SCENARIOS * 100))

@app.route('/make_choice', methods=['POST'])
def make_choice():
    # Make sure session is permanent
    session.permanent = True
    
    choice = request.form.get('choice')
    scenario_id = int(request.form.get('scenario_id'))
    
    # Initialize session variables if they don't exist
    if 'choices_made' not in session:
        session['choices_made'] = []
    
    if 'wrong_choices' not in session:
        session['wrong_choices'] = 0
    
    if 'current_scenario' not in session:
        session['current_scenario'] = str(scenario_id)
    
    # Initialize scenarios in session if it doesn't exist
    if 'scenarios' not in session:
        session['scenarios'] = {}
        # Add the first scenario to ensure we have at least one
        session['scenarios']['1'] = base_scenarios[0]
    
    # Get the current scenario - convert scenario_id to string for dictionary key
    scenario_id_str = str(scenario_id)
    scenario = session['scenarios'].get(scenario_id_str)
    
    if not scenario:
        # Try to generate the scenario
        previous_choice = session['choices_made'][-1] if session['choices_made'] else None
        previous_scenario_id = session['current_scenario']
        previous_scenario_id_str = str(previous_scenario_id)
        previous_scenario = session['scenarios'].get(previous_scenario_id_str)
        
        scenario = get_scenario(scenario_id, previous_choice, previous_scenario)
        session['scenarios'][scenario_id_str] = scenario
    
    # Record choice
    session['choices_made'] = session.get('choices_made', []) + [choice]
    
    # Check if choice is correct
    if choice != scenario.get('correct_choice'):
        session['wrong_choices'] = session.get('wrong_choices', 0) + 1
    
    # Check if this is the final scenario
    if scenario_id >= MAX_SCENARIOS:
        # Force session to save
        session.modified = True
        return redirect(url_for('game_result'))
        
    # Determine next scenario based on choice
    if choice == 'A':
        next_scenario = scenario.get('next_scenario_a', scenario_id + 1)
    else:
        next_scenario = scenario.get('next_scenario_b', scenario_id + 1)
    
    # Update current scenario
    session['current_scenario'] = str(next_scenario)
    
    # Force session to save
    session.modified = True
    
    # Check if we've reached the maximum number of scenarios
    if int(next_scenario) > MAX_SCENARIOS:
        return redirect(url_for('game_result'))
    
    return redirect(url_for('show_scenario', scenario_id=int(next_scenario)))

@app.route('/result')
def game_result():
    wrong_choices = session.get('wrong_choices', 0)
    
    # Determine ending based on wrong choices
    ending = determine_ending(wrong_choices)
    
    return render_template('dynamic/result.html', 
                          ending=ending, 
                          wrong_choices=wrong_choices,
                          total_scenarios=MAX_SCENARIOS,
                          success_rate=int(((MAX_SCENARIOS - wrong_choices) / MAX_SCENARIOS) * 100))

@app.route('/api/set_api_key', methods=['POST'])
def set_api_key():
    """Set the OpenAI API key"""
    global OPENAI_API_KEY
    data = request.get_json()
    api_key = data.get('api_key')
    
    if api_key:
        OPENAI_API_KEY = api_key
        return jsonify({"status": "success", "message": "API key set successfully"})
    else:
        return jsonify({"status": "error", "message": "No API key provided"}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5012))
    app.run(debug=True, host='0.0.0.0', port=port)
