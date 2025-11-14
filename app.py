import os
import re
import time
import tempfile
import speech_recognition as sr
from flask import Flask, render_template, request, jsonify, send_file
from gtts import gTTS
from groq import Groq
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# -----------------------------------
# MARKDOWN CLEANER FOR SPEECH (TTS)
# -----------------------------------
def clean_for_tts(text):
    """Remove Markdown formatting so speech sounds natural."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # italics
    text = re.sub(r'[`#>-]', '', text)            # symbols
    text = re.sub(r'\|', ' ', text)               # table bars
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# -----------------------------------
# LLM
# -----------------------------------
def ask_llm(message):
    response = client.chat.completions.create(
        model="groq/compound-mini",
        messages=[{"role": "user", "content": message}]
    )
    return response.choices[0].message.content


# -----------------------------------
# TEXT TO SPEECH — Always overwrite
# -----------------------------------
def generate_tts(text):
    audio_dir = "audio"
    os.makedirs(audio_dir, exist_ok=True)

    audio_path = os.path.join(audio_dir, "response.mp3")
    temp_path = audio_path + ".tmp"

    # Delete old output safely
    if os.path.exists(audio_path):
        for _ in range(5):
            try:
                os.remove(audio_path)
                break
            except PermissionError:
                time.sleep(0.1)

    # Save new TTS to temporary file
    tts = gTTS(text=text, lang="en")
    tts.save(temp_path)

    # Atomic replace
    os.replace(temp_path, audio_path)

    return audio_path


# -----------------------------------
# SPEECH TO TEXT
# -----------------------------------
def speech_to_text(path):
    rec = sr.Recognizer()
    with sr.AudioFile(path) as src:
        audio = rec.record(src)
    return rec.recognize_google(audio)


# -----------------------------------
# ROUTES
# -----------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------------
# PROCESS TEXT MESSAGE
# -----------------------------------
@app.route("/process_text", methods=["POST"])
def process_text():
    user_text = request.json.get("user_text")

    bot_reply = ask_llm(user_text)

    # Clean version for TTS
    clean_text = clean_for_tts(bot_reply)
    audio_path = generate_tts(clean_text)

    ts = int(time.time())

    return jsonify({
        "user_text": user_text,
        "bot_reply": bot_reply,
        "audio_url": f"/get_audio/{audio_path}?t={ts}"
    })


# -----------------------------------
# PROCESS VOICE INPUT
# -----------------------------------
@app.route("/process_audio", methods=["POST"])
def process_audio():
    audio_file = request.files["audio"]

    # Save input temp file
    with tempfile.NamedTemporaryFile(delete=False) as temp_in:
        input_path = temp_in.name
        audio_file.save(input_path)

    # Save WAV temp
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
        wav_path = temp_wav.name

    try:
        # Convert to WAV
        try:
            AudioSegment.from_file(input_path).export(wav_path, format="wav")
        except:
            wav_path = input_path

        user_text = speech_to_text(wav_path)
        bot_reply = ask_llm(user_text)

        clean_text = clean_for_tts(bot_reply)
        audio_path = generate_tts(clean_text)

        ts = int(time.time())

        return jsonify({
            "user_text": user_text,
            "bot_reply": bot_reply,
            "audio_url": f"/get_audio/{audio_path}?t={ts}"
        })

    finally:
        # Cleanup
        for p in [input_path, wav_path]:
            try:
                os.remove(p)
            except:
                pass


@app.route("/get_audio/<path:path>")
def get_audio(path):
    return send_file(path, mimetype="audio/mpeg")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
