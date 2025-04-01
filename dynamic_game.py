import os
import time
import random
import json
import requests
import sqlite3
try:
    import psycopg2
    from psycopg2.extras import DictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    # psycopg2 is not installed, so we'll use SQLite only
    POSTGRES_AVAILABLE = False
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import timedelta, datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'sqlite:///game_data.db')

# OpenAI API configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')  # Get API key from environment variable
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Database setup
def get_db_connection():
    """Get database connection based on configuration"""
    if app.config['DATABASE_URL'].startswith('postgres') and POSTGRES_AVAILABLE:
        # PostgreSQL connection
        conn = psycopg2.connect(app.config['DATABASE_URL'])
        conn.cursor_factory = DictCursor
        return conn
    else:
        # SQLite connection as fallback
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'game_data.db'))
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if app.config['DATABASE_URL'].startswith('postgres') and POSTGRES_AVAILABLE:
        # PostgreSQL
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            score INTEGER NOT NULL,
            success_rate INTEGER NOT NULL,
            wrong_choices INTEGER NOT NULL,
            time_taken INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
    else:
        # SQLite
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            score INTEGER NOT NULL,
            success_rate INTEGER NOT NULL,
            wrong_choices INTEGER NOT NULL,
            time_taken INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
    
    conn.commit()
    conn.close()

# Initialize database when the app starts
init_db()

# Game configuration
MAX_SCENARIOS = 10  # Changed from 20 to 10 questions
WRONG_CHOICES_THRESHOLD = {
    "divorce": 5,     # 5+ wrong choices leads to divorce (adjusted from 8)
    "couch": 4,       # 4 wrong choices leads to couch (adjusted from 6-7)
    "mother_in_law": 3, # 3 wrong choices leads to mother-in-law (adjusted from 4-5)
    "cold_war": 2,    # 2 wrong choices leads to cold war
    "happy": 0        # 0-1 wrong choices leads to happy ending
}

# Achievements system
ACHIEVEMENTS = {
    "perfect_game": {
        "title": "Mutlu Evlilik",
        "description": "Tüm senaryolarda doğru seçimler yaparak oyunu tamamla",
        "icon": "trophy",
        "condition": lambda session: session.get('wrong_choices', 0) == 0
    },
    "quick_thinker": {
        "title": "Hızlı Düşünür",
        "description": "Oyunu 5 dakikadan kısa sürede tamamla",
        "icon": "stopwatch",
        "condition": lambda session: (time.time() - session.get('start_time', 0)) < 300
    },
    "persistent": {
        "title": "İnatçı",
        "description": "En az bir kez oyunu yeniden oyna",
        "icon": "redo",
        "condition": lambda session: session.get('games_played', 0) > 1
    },
    "survivor": {
        "title": "Hayatta Kalan",
        "description": "En az 6 yanlış seçim yaparak oyunu tamamla",
        "icon": "life-ring",
        "condition": lambda session: session.get('wrong_choices', 0) >= 6
    }
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
        'image': 'scenario1.jpg',
        'difficulty': 'Kolay'
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
    
    # Calculate difficulty based on scenario id
    if scenario_id <= 7:
        difficulty = "Kolay"
    elif scenario_id <= 14:
        difficulty = "Orta"
    else:
        difficulty = "Zor"
    
    # Randomize humor level for more variety
    humor_levels = [
        "witty and clever with wordplay",
        "over-the-top exaggerated and comedic",
        "dry humor with a touch of sarcasm",
        "absurdist with unexpected twists",
        "relatable everyday marriage situations with a funny twist"
    ]
    
    humor_level = random.choice(humor_levels)
    
    # Prepare the prompt for OpenAI
    prompt = f"""
    Create a humorous marriage scenario for a Turkish couple game called "Eşi Kızdırmama Oyunu" (Don't Make Your Wife Angry).
    
    Topic: {topic}
    Scenario ID: {scenario_id}
    Difficulty: {difficulty}
    Humor style: {humor_level}
    {context}
    
    The scenario should be funny, slightly exaggerated, and based on common relationship dynamics in Turkish culture.
    It should include:
    1. A title starting with "Senaryo {scenario_id}: " (make it catchy and humorous)
    2. A description of the situation (1-2 sentences, make it very funny and relatable)
    3. Two choices (A and B) where one is clearly better for maintaining marital harmony
    4. Indicate which choice is correct (A or B)
    5. Two different next scenario IDs depending on which choice is made
    6. A brief image description that represents this scenario visually (include emojis and make it fun, like "😱 Husband looking confused at wife's new haircut 💇‍♀️")
    
    Format the response as a JSON object with the following structure:
    {{
        "title": "Senaryo X: [Title]",
        "description": "[Description]",
        "choice_a": "[Choice A text]",
        "choice_b": "[Choice B text]",
        "correct_choice": "[A or B]",
        "next_scenario_a": [scenario ID if A is chosen],
        "next_scenario_b": [scenario ID if B is chosen],
        "difficulty": "{difficulty}",
        "image_description": "[Brief description for image with emojis]"
    }}
    
    Make sure the next_scenario_a and next_scenario_b are numbers between 1 and {MAX_SCENARIOS}, and they should be different from the current scenario ID ({scenario_id}). Also ensure next scenarios never point to scenario 1.
    """
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        
        data = {
            "model": "gpt-4",  # Upgraded from gpt-3.5-turbo to gpt-4 for better quality
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,  # Increased slightly for more creative responses
            "max_tokens": 600
        }
        
        response = requests.post(OPENAI_API_URL, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            scenario_text = result['choices'][0]['message']['content']
            
            # Extract the JSON part from the response
            try:
                scenario_json = json.loads(scenario_text)
                # Use dynamic image URL with the image description
                image_description = scenario_json.get('image_description', 'Turkish couple scenario 😊')
                encoded_desc = requests.utils.quote(image_description)
                # Use both Unsplash for real photos and emojis in the description
                scenario_json['image_url'] = f"https://source.unsplash.com/600x400/?{encoded_desc}"
                scenario_json['image'] = f'scenario{scenario_id}.jpg' # Keep for compatibility
                
                # Ensure next scenarios are within bounds and never point to scenario 1
                scenario_json['next_scenario_a'] = max(2, min(scenario_json.get('next_scenario_a', scenario_id + 1), MAX_SCENARIOS))
                scenario_json['next_scenario_b'] = max(2, min(scenario_json.get('next_scenario_b', scenario_id + 2), MAX_SCENARIOS))
                
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
    
    # Calculate difficulty based on scenario id
    if scenario_id <= 7:
        difficulty = "Kolay"
    elif scenario_id <= 14:
        difficulty = "Orta"
    else:
        difficulty = "Zor"
    
    # Create a basic scenario structure with emojis for more fun
    image_descriptions = [
        "😱 couple arguing kitchen 🍳",
        "🛍️ husband surprised wife shopping 👗",
        "😡 wife angry husband watching tv 📺",
        "🍽️ couple discussing dinner table 🍷",
        "💐 husband apologizing flowers 🌹",
        "👗 wife showing new clothes 👠",
        "🏖️ couple vacation planning ✈️",
        "😕 husband confused wife crying 😭",
        "🎂 couple celebrating anniversary 💝",
        "👵 family dinner mother in law 🍴",
        "🧹 husband forgot chores 🧼",
        "💇‍♀️ wife new haircut reaction 😮",
        "📱 husband texting too much 💬",
        "🛌 couple bedtime argument 😴",
        "🚗 backseat driving situation 🛣️",
        "👨‍👩‍👧 parenting disagreement 👶",
        "💰 unexpected purchase surprise 💳",
        "🎮 gaming vs spending time together ⏰",
        "👫 social plans with friends 🎉",
        "🍔 cooking disaster in kitchen 🔥"
    ]
    
    image_description = random.choice(image_descriptions)
    encoded_desc = requests.utils.quote(image_description)
    
    # Randomize choices for more variety
    is_a_correct = random.choice([True, False])
    correct_choice = "A" if is_a_correct else "B"
    
    # More fun alternatives for choices
    good_choices = [
        "Eşinin istediği şekilde davranırsın.",
        "Diplomatik davranıp eşini desteklersin.",
        "Anlayışlı bir şekilde eşinin yanında olursun.",
        "Sabırla ve sevgiyle yaklaşırsın.",
        "Bir çiçek alıp gönlünü alırsın.",
        "Eşini haklı bulup özür dilersin.",
        "Eşinin istediğini yaparsın.",
        "Onu dinler ve isteklerini anlamaya çalışırsın."
    ]
    
    bad_choices = [
        "Kendi bildiğin gibi davranırsın.",
        "Eşini görmezden gelip istediğini yaparsın.",
        "İnatla kendi fikrinde ısrar edersin.",
        "Homurdanarak kabul edersin.",
        "Gözlerini devirerek cevap verirsin.",
        "Espri yaparak durumu geçiştirmeye çalışırsın.",
        "Ona mantık çerçevesinde açıklamaya çalışırsın.",
        "Konuyu değiştirmeye çalışırsın."
    ]
    
    choice_a = random.choice(good_choices) if is_a_correct else random.choice(bad_choices)
    choice_b = random.choice(bad_choices) if is_a_correct else random.choice(good_choices)
    
    # Create interesting scenario titles with emojis
    title_emojis = ["😊", "😱", "🤔", "😬", "🙄", "😍", "🤦‍♂️", "💪", "🤷‍♀️", "🏆", "🔥", "💯", "🎭", "🎮", "🚨"]
    random_emoji = random.choice(title_emojis)
    
    # Funny title prefixes
    title_prefixes = [
        "Büyük Kriz:",
        "Tehlikeli Sularda:",
        "Evlilik İmtihanı:",
        "Kaçış Yok:",
        "Diplomatik Kriz:",
        "Sürpriz Saldırı:",
        "Sabır Testi:",
        "Savaş Alanı:",
        "Beklenmedik Durum:",
        "Evliliğin Sınavı:"
    ]
    
    # Make more interesting descriptions
    descriptions = [
        f"Eşinle {topic.lower()} konusunda bir anlaşmazlık yaşıyorsunuz. Ne yapacaksın?",
        f"Eşin {topic.lower()} hakkında senin fikrini soruyor. Nasıl cevap vereceksin?",
        f"{topic.capitalize()} konusunda eşinle aranızda bir gerginlik oluştu. Nasıl davranacaksın?",
        f"Eşinin {topic.lower()} konusunda bir isteği var ama sen farklı düşünüyorsun. Ne diyeceksin?",
        f"{topic.capitalize()} durumunda eşinle karşı karşıyasın. Tepkin ne olacak?"
    ]
    
    # Add humor phrases to descriptions
    humor_phrases = [
        " Aman dikkat, bir yanlış adım ve kanepe seni bekliyor!",
        " Yanlış cevap verirsen kayınvalide devreye girebilir!",
        " Hatırla, her 'tamam aşkım' bir gün fazladan huzur demek.",
        " Evliliğin altın kuralı: Eşin her zaman haklıdır, özellikle haksız olduğunda!",
        " Bu senaryo gerçek evliliklerde test edilmiştir ve boşanmalar yaşanmıştır!",
        " İyi düşün, bu sorunun cevabı evliliğinin kaderini belirleyebilir!",
        " Dikkat et, her yanlış cevap bir gece kanepede uyumak demek.",
        " Eşinin gözlerindeki o bakışı görüyor musun? Tehlike çanları çalıyor!",
        " Şu an bir mayın tarlasında yürüyorsun, adımını dikkatli at!",
        " Bu soruyu eşlerin %87'si yanlış cevaplamış ve hala pişmanlar!"
    ]
    
    random_description = random.choice(descriptions)
    random_humor = random.choice(humor_phrases)
    enhanced_description = random_description + random_humor
    
    scenario = {
        'title': f'Senaryo {scenario_id}: {random_emoji} {random.choice(title_prefixes)} {topic}',
        'description': enhanced_description,
        'choice_a': choice_a,
        'choice_b': choice_b,
        'correct_choice': correct_choice,
        'next_scenario_a': min(max(scenario_id + 1, 2), MAX_SCENARIOS),
        'next_scenario_b': min(max(scenario_id + 2, 2), MAX_SCENARIOS),
        'image': f'scenario{scenario_id}.jpg',
        'image_url': f"https://source.unsplash.com/600x400/?{encoded_desc}",
        'difficulty': difficulty,
        'image_description': image_description
    }
    
    return scenario

def get_scenario(scenario_id, previous_choice=None, previous_scenario=None):
    """Get a scenario by ID, generating it if needed"""
    # Ensure first scenario is also randomized instead of always using the base scenario
    if scenario_id == 1 and random.random() > 0.3:  # 70% chance to get a random first scenario
        new_scenario = generate_scenario(scenario_id, previous_choice, previous_scenario)
        if 'scenarios' not in session:
            session['scenarios'] = {}
        session['scenarios']['1'] = new_scenario
        return new_scenario
    elif scenario_id == 1:
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

def calculate_score(wrong_choices, time_taken):
    """Calculate player's score based on performance"""
    base_score = 1000
    wrong_choice_penalty = 50 * wrong_choices
    time_penalty = min(300, time_taken) / 2  # Cap time penalty
    
    final_score = max(0, base_score - wrong_choice_penalty - time_penalty)
    return int(final_score)

def check_achievements(session_data):
    """Check which achievements the player has earned"""
    earned_achievements = []
    
    for achievement_id, achievement in ACHIEVEMENTS.items():
        if achievement["condition"](session_data):
            earned_achievements.append({
                "id": achievement_id,
                **achievement
            })
    
    return earned_achievements

def format_game_history(session_data):
    """Format the game history for display"""
    history = []
    scenarios = session_data.get('scenarios', {})
    choices_made = session_data.get('choices_made', [])
    visited_scenarios = session_data.get('visited_scenarios', [])
    
    # Skip the first element which is just the scenario ID
    for i, scenario_id in enumerate(visited_scenarios):
        if scenario_id not in scenarios:
            continue
            
        scenario = scenarios[scenario_id]
        choice = choices_made[i-1] if i > 0 and i-1 < len(choices_made) else None
        
        history_item = {
            'scenario_id': scenario_id,
            'title': scenario.get('title', f'Senaryo {scenario_id}'),
            'description': scenario.get('description', ''),
            'choice': choice,
            'choice_text': scenario.get(f'choice_{choice.lower()}', '') if choice else '',
            'was_correct': choice == scenario.get('correct_choice') if choice else None,
            'difficulty': scenario.get('difficulty', 'Normal')
        }
        
        history.append(history_item)
    
    return history

# Tutorial mode scenarios
tutorial_scenarios = [
    {
        'title': 'Eğitim 1: Sınav Sonuçları',
        'description': 'Eşin üniversite yıllarından bir sınav kağıdı buldu. Aldığı not çok düşük ve biraz utanmış görünüyor. Ne diyeceksin?',
        'choice_a': 'Hayatım, o günler geçmişte kaldı. Sen şimdi çok başarılısın!',
        'choice_b': 'Vay be, bu notu nasıl aldın ya? Demek öyle kopya çekiyordun!',
        'correct_choice': 'A',
        'next_scenario_a': 2,
        'next_scenario_b': 2,
        'image': 'tutorial1.jpg',
        'image_url': 'https://source.unsplash.com/600x400/?exam+paper',
        'difficulty': 'Eğitim',
        'tip': 'Eşinin geçmişteki başarısızlıklarını yüzüne vurma, destek ol ve şimdiki başarılarına odaklan.'
    },
    {
        'title': 'Eğitim 2: Kayınvalide Ziyareti',
        'description': 'Hafta sonu için kayınvaliden ziyarete gelmek istiyor. Eşin fikrini soruyor. Bu hafta sonu maç var ve arkadaşlarınla izlemeyi planlıyordun.',
        'choice_a': 'Tabii ki gelebilir, ben de özledim kayınvalidemi. Arkadaşlarımla başka zaman buluşurum.',
        'choice_b': 'Bu hafta sonu arkadaşlarımla maç izleyecektim, başka zamana erteleyemez mi?',
        'correct_choice': 'A',
        'next_scenario_a': 3,
        'next_scenario_b': 3,
        'image': 'tutorial2.jpg',
        'image_url': 'https://source.unsplash.com/600x400/?mother+in+law',
        'difficulty': 'Eğitim',
        'tip': 'Eşinin ailesine değer vermek ve kendi planlarını bazen ikinci plana atmak evlilikte önemlidir.'
    },
    {
        'title': 'Eğitim 3: Saç Rengi Değişimi',
        'description': 'Eşin saçını yeni bir renge boyattı ve "Nasıl olmuş?" diye soruyor. Renk gerçekten hoşuna gitmedi.',
        'choice_a': 'Farklı olmuş ama sana çok yakışmış. Her şey yakışıyor sana zaten!',
        'choice_b': 'Açıkçası önceki renk daha güzeldi. Bu biraz tuhaf durmuş.',
        'correct_choice': 'A',
        'next_scenario_a': 4,
        'next_scenario_b': 4,
        'image': 'tutorial3.jpg',
        'image_url': 'https://source.unsplash.com/600x400/?hair+color+change',
        'difficulty': 'Eğitim',
        'tip': 'Eşinin görünüşü hakkında her zaman olumlu konuş, özellikle yeni bir değişiklik yaptığında.'
    },
    {
        'title': 'Eğitim 4: Oyun Tamamlandı',
        'description': 'Tebrikler! Eğitim modunu tamamladın. Artık oyunun nasıl oynandığını ve doğru seçimlerin önemini biliyorsun. Gerçek oyunda 20 farklı senaryo seni bekliyor ve her seçim bir sonraki senaryoyu belirleyecek. Hatalı seçimlerin sayısına göre farklı sonlara ulaşacaksın.',
        'choice_a': 'Gerçek oyuna başla!',
        'choice_b': 'Ana menüye dön',
        'correct_choice': 'A',
        'next_scenario_a': 1,
        'next_scenario_b': 1,
        'image': 'tutorial4.jpg',
        'image_url': 'https://source.unsplash.com/600x400/?completion+trophy',
        'difficulty': 'Eğitim',
        'tip': 'Her seçimin önemli ve sonuçlarının olduğunu unutma. İyi şanslar!'
    }
]

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
    session['anger_level'] = 0  # Initialize anger level
    session['choices_made'] = []
    session['scenarios'] = {}
    session['scenarios']['1'] = base_scenarios[0]  # Add the first scenario
    session['start_time'] = time.time()  # Track when the game started
    session['games_played'] = session.get('games_played', 0) + 1
    session['visited_scenarios'] = ['1']  # Track which scenarios the player has visited
    
    # Pre-generate scenarios if using OpenAI
    if OPENAI_API_KEY:
        generate_all_scenarios()
        
    # Use the route that handles dynamic scenarios
    return redirect(url_for('play_game'))

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

@app.route('/submit_choice', methods=['POST'])
def submit_choice():
    data = request.get_json() if request.is_json else request.form
    choice_id = data.get('choice_id') or data.get('choice')
    scenario_id = data.get('scenario_id', session.get('current_scenario_id'))
    
    if not choice_id or not scenario_id:
        if request.is_json:
            return jsonify({'status': 'error', 'message': 'Missing choice or scenario ID'})
        else:
            flash('Bir seçim yapmalısınız!', 'error')
            return redirect(url_for('play_game'))
    
    # Convert to string for comparison if needed
    choice_id = str(choice_id)
    
    # Get the current scenario
    scenario = session.get('scenarios', [])[int(scenario_id) - 1]
    
    # Get the correct choice
    correct_choice = scenario.get('correct_choice', 'A')
    
    # Check if the choice is correct
    is_correct = choice_id == correct_choice
    
    # Update wrong choices and anger level
    if not is_correct:
        session['wrong_choices'] = session.get('wrong_choices', 0) + 1
        # Increase anger level, capping at the divorce threshold
        max_anger = WRONG_CHOICES_THRESHOLD["divorce"]
        session['anger_level'] = min(session.get('anger_level', 0) + 1, max_anger)
    
    # Update session data
    choices = session.get('choices', [])
    choices.append({
        'scenario_id': scenario_id,
        'choice': choice_id,
        'is_correct': is_correct,
        'title': scenario.get('title', ''),
        'description': scenario.get('description', ''),
        'choice_text': scenario.get(f'choice_{choice_id.lower()}', ''),
        'difficulty': scenario.get('difficulty', 'Orta')
    })
    session['choices'] = choices
    
    # Determine the next URL
    total_scenarios = session.get('total_scenarios', 10)
    next_scenario_id = int(scenario_id) + 1
    
    if next_scenario_id > total_scenarios:
        next_url = url_for('show_result')
    else:
        session['current_scenario_id'] = next_scenario_id
        next_url = url_for('play_game')
    
    # Return JSON response if the request was JSON
    if request.is_json:
        return jsonify({
            'status': 'success',
            'correct': is_correct,
            'next_url': next_url,
            'scenario_id': scenario_id,
            'choice': choice_id,
            'anger_level': session.get('anger_level', 0) # Include anger level in response
        })
    else:
        return redirect(next_url)

@app.route('/history')
def game_history():
    """Display the player's game history"""
    if 'visited_scenarios' not in session or len(session.get('visited_scenarios', [])) <= 1:
        # No history yet
        return redirect(url_for('index'))
    
    history = format_game_history(session)
    wrong_choices = session.get('wrong_choices', 0)
    total_scenarios = len(history)
    success_rate = int(((total_scenarios - wrong_choices) / total_scenarios) * 100) if total_scenarios > 0 else 0
    
    return render_template('dynamic/history.html', 
                           history=history,
                           wrong_choices=wrong_choices,
                           total_scenarios=total_scenarios,
                           success_rate=success_rate)

@app.route('/result')
def game_result():
    wrong_choices = session.get('wrong_choices', 0)
    
    # Calculate time taken
    start_time = session.get('start_time', time.time())
    time_taken = time.time() - start_time
    
    # Calculate score
    score = calculate_score(wrong_choices, time_taken)
    
    # Check for achievements
    achievements = check_achievements(session)
    
    # Format game history
    history = format_game_history(session)
    
    # Determine ending based on wrong choices
    ending = determine_ending(wrong_choices)
    
    return render_template('dynamic/result.html', 
                          ending=ending, 
                          wrong_choices=wrong_choices,
                          total_scenarios=MAX_SCENARIOS,
                          success_rate=int(((MAX_SCENARIOS - wrong_choices) / MAX_SCENARIOS) * 100),
                          time_taken=int(time_taken),
                          score=score,
                          achievements=achievements,
                          history=history)

@app.route('/leaderboard')
def leaderboard():
    """Show the leaderboard page with data from the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leaderboard ORDER BY score DESC LIMIT 20')
    
    if app.config['DATABASE_URL'].startswith('postgres') and POSTGRES_AVAILABLE:
        leaderboard_data = cursor.fetchall()
    else:
        leaderboard_data = conn.execute('SELECT * FROM leaderboard ORDER BY score DESC LIMIT 20').fetchall()
    
    conn.close()
    
    # Convert to list of dictionaries for template
    leaderboard = []
    for row in leaderboard_data:
        if app.config['DATABASE_URL'].startswith('postgres') and POSTGRES_AVAILABLE:
            # For PostgreSQL, row is already a dict-like object via DictCursor
            leaderboard.append({
                'name': row['name'],
                'score': row['score'],
                'success_rate': row['success_rate'],
                'wrong_choices': row['wrong_choices'],
                'time_taken': row['time_taken'],
                'timestamp': str(row['timestamp'])
            })
        else:
            # For SQLite
            leaderboard.append({
                'name': row['name'],
                'score': row['score'],
                'success_rate': row['success_rate'],
                'wrong_choices': row['wrong_choices'],
                'time_taken': row['time_taken'],
                'timestamp': row['timestamp']
            })
    
    return render_template('dynamic/leaderboard.html', leaderboard=leaderboard)

@app.route('/api/save_score', methods=['POST'])
def save_score():
    """Save the player's score to the database"""
    data = request.get_json()
    player_name = data.get('name')
    score = data.get('score')
    
    if player_name and score:
        # Get other game stats from session
        wrong_choices = session.get('wrong_choices', 0)
        total_scenarios = len(session.get('visited_scenarios', []))
        success_rate = int(((total_scenarios - wrong_choices) / total_scenarios) * 100) if total_scenarios > 0 else 0
        start_time = session.get('start_time', time.time())
        time_taken = int(time.time() - start_time)
        
        # Save to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if app.config['DATABASE_URL'].startswith('postgres') and POSTGRES_AVAILABLE:
            # PostgreSQL
            cursor.execute(
                'INSERT INTO leaderboard (name, score, success_rate, wrong_choices, time_taken) VALUES (%s, %s, %s, %s, %s)',
                (player_name, score, success_rate, wrong_choices, time_taken)
            )
        else:
            # SQLite
            cursor.execute(
                'INSERT INTO leaderboard (name, score, success_rate, wrong_choices, time_taken) VALUES (?, ?, ?, ?, ?)',
                (player_name, score, success_rate, wrong_choices, time_taken)
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "Score saved successfully"})
    else:
        return jsonify({"status": "error", "message": "Missing required data"}), 400

@app.route('/tutorial')
def tutorial():
    """Start the tutorial mode"""
    # Initialize game state for tutorial
    session.clear()
    session.permanent = True
    session['tutorial_mode'] = True
    session['current_scenario'] = '1'
    session['wrong_choices'] = 0
    session['choices_made'] = []
    session['scenarios'] = {}
    
    # Add tutorial scenarios
    for i, scenario in enumerate(tutorial_scenarios, 1):
        session['scenarios'][str(i)] = scenario
    
    session['start_time'] = time.time()
    session['visited_scenarios'] = ['1']
    
    return redirect(url_for('show_tutorial', scenario_id=1))

@app.route('/tutorial/<int:scenario_id>')
def show_tutorial(scenario_id):
    """Show a tutorial scenario"""
    if 'tutorial_mode' not in session or not session['tutorial_mode']:
        return redirect(url_for('start_game'))
    
    # Check if we're at the end of the tutorial
    if scenario_id > len(tutorial_scenarios):
        return redirect(url_for('index'))
    
    # Get the tutorial scenario
    scenario = tutorial_scenarios[scenario_id - 1]
    
    # Update current scenario
    session['current_scenario'] = str(scenario_id)
    
    # Record that we've visited this scenario
    visited = session.get('visited_scenarios', [])
    if str(scenario_id) not in visited:
        visited.append(str(scenario_id))
    session['visited_scenarios'] = visited
    
    # Force session to save
    session.modified = True
    
    return render_template('dynamic/tutorial.html', 
                           scenario=scenario,
                           scenario_id=scenario_id,
                           total_scenarios=len(tutorial_scenarios),
                           progress=int((int(scenario_id)-1) / len(tutorial_scenarios) * 100))

@app.route('/make_tutorial_choice', methods=['POST'])
def make_tutorial_choice():
    """Handle a tutorial choice"""
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
    
    # Get the tutorial scenario
    scenario = tutorial_scenarios[scenario_id - 1]
    
    # Record choice
    session['choices_made'] = session.get('choices_made', []) + [choice]
    
    # Check if choice is correct
    if choice != scenario.get('correct_choice'):
        session['wrong_choices'] = session.get('wrong_choices', 0) + 1
    
    # Determine next scenario
    next_scenario = scenario_id + 1
    
    # Check if we've reached the last tutorial scenario
    if next_scenario > len(tutorial_scenarios):
        # If it's the last scenario's choice A, start the real game
        if scenario_id == len(tutorial_scenarios) and choice == 'A':
            session['tutorial_mode'] = False
            return redirect(url_for('start_game'))
        # Otherwise, go back to the index
        return redirect(url_for('index'))
    
    # Update current scenario
    session['current_scenario'] = str(next_scenario)
    
    # Force session to save
    session.modified = True
    
    return redirect(url_for('show_tutorial', scenario_id=next_scenario))

@app.route('/game')
def play_game():
    # Make sure session is permanent
    session.permanent = True
    
    # Initialize session variables if needed
    if 'current_scenario_id' not in session:
        session['current_scenario_id'] = 1
    
    if 'scenarios' not in session or not session['scenarios']:
        generate_scenarios()
    
    # Get the current scenario
    current_scenario_id = session.get('current_scenario_id', 1)
    scenarios = session.get('scenarios', [])
    
    if current_scenario_id > len(scenarios):
        return redirect(url_for('show_result'))
    
    scenario = scenarios[current_scenario_id - 1]
    total_scenarios = len(scenarios)
    progress = int((current_scenario_id - 1) / total_scenarios * 100)
    
    # Get current anger level and max anger
    current_anger = session.get('anger_level', 0)
    max_anger = WRONG_CHOICES_THRESHOLD["divorce"] 
    
    # Pass additional CSS for the shake animation
    shake_css = """
    @keyframes shake {
        0% { transform: translateX(0); }
        10% { transform: translateX(-10px); }
        20% { transform: translateX(10px); }
        30% { transform: translateX(-10px); }
        40% { transform: translateX(10px); }
        50% { transform: translateX(-5px); }
        60% { transform: translateX(5px); }
        70% { transform: translateX(-5px); }
        80% { transform: translateX(5px); }
        90% { transform: translateX(-3px); }
        100% { transform: translateX(0); }
    }
    
    body.shake {
        animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
    }
    """
    
    return render_template('dynamic/game.html', 
                          scenario=scenario, 
                          scenario_id=current_scenario_id, 
                          total_scenarios=total_scenarios, 
                          progress=progress,
                          shake_css=shake_css,
                          current_anger=current_anger, # Pass current anger
                          max_anger=max_anger)        # Pass max anger

def generate_all_scenarios():
    """Pre-generate all scenarios and store them in the session"""
    scenarios = [base_scenarios[0]] # Start with the base scenario
    for i in range(2, MAX_SCENARIOS + 1):
        # Try to provide context from a random previous scenario for better continuity
        previous_scenario = random.choice(scenarios)
        # Simulate a random choice for context generation
        previous_choice = random.choice(['A', 'B'])
        
        new_scenario = generate_scenario(i, previous_choice, previous_scenario)
        scenarios.append(new_scenario)
        
    session['scenarios'] = scenarios
    session['total_scenarios'] = len(scenarios)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5012))
    app.run(debug=True, host='0.0.0.0', port=port)
