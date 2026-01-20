import json
import requests
import os
from gtts import gTTS
from playsound import playsound
import time


def get_meaning(word):
    word = word.lower().strip()
    
    #  local JSON database
    try:
        with open('words.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    # Check if word  in your local database
    if word in data:
        return data[word], "Local-Database"

    # If not found, call the API (The Fallback)
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            meaning = response.json()[0]['meanings'][0]['definitions'][0]['definition']
            
            # Save the new word to JSON
            data[word] = meaning
            with open('words.json', 'w') as f:
                json.dump(data, f, indent=4)
            
            return meaning, "API (Learned Word)"
            
    except Exception:
        pass

    return "Meaning not found.", "Error"

#  Pronunciation Generator
def generate_pronunciation(word):
    
    audio_dir = "static/audio"
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)
        
    audio_path = os.path.join(audio_dir, f"{word}.mp3")
    
    if not os.path.exists(audio_path):
        tts = gTTS(text=word, lang='en')
        tts.save(audio_path)
    
    try:
        playsound(audio_path)
    except Exception as e:
        print(f"Audio Playback Error: {e}")
        
    return audio_path

#  Function 
def process_word_logic(word):
    definition, source = get_meaning(word)
    audio_file = generate_pronunciation(word)
    
    return {
        "word": word,
        "definition": definition,
        "audio_path": audio_file,
        "source": source
    }

# testing
if __name__ == "__main__":
    test_word = "nebula" 
    result = process_word_logic(test_word)
    print(f"Result: {result}")