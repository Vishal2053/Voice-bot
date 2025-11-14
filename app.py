import os
import speech_recognition as sr
from flask import Flask, render_template, request, jsonify, send_file
from gtts import gTTS
from groq import Groq
from dotenv import load_dotenv
import tempfile
import shutil
from pydub import AudioSegment

load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --------------------------
#  SPEECH TO TEXT
# --------------------------
def speech_to_text(audio_file_path):
    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_file_path) as source:
        audio = recognizer.record(source)
    return recognizer.recognize_google(audio)

# --------------------------
#  LLM (Groq)
# --------------------------
def ask_llm(question):
    response = client.chat.completions.create(
        model="groq/compound-mini",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

# --------------------------
#  TEXT TO SPEECH (gTTS) - Use temp file, no persistent save
# --------------------------
def generate_tts(text):
    tts = gTTS(text=text, lang="en")
    # Use temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tts.save(temp_file.name)
    temp_file.close()
    return temp_file.name

# --------------------------
#  ROUTES
# --------------------------
@app.route("/")
def index():
    return render_template("index.html")

# --------------------------
#  VOICE INPUT ROUTE
# --------------------------
@app.route("/process_audio", methods=["POST"])
def process_audio():
    audio_file = request.files["audio"]
    # Save input temporarily (keep original extension if provided)
    input_tf = tempfile.NamedTemporaryFile(delete=True)
    input_path = input_tf.name
    input_tf.close()
    audio_file.save(input_path)

    # Convert uploaded audio to PCM WAV (speech_recognition compatible)
    wav_tf = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    wav_path = wav_tf.name
    wav_tf.close()

    try:
        try:
            AudioSegment.from_file(input_path).export(wav_path, format="wav")
        except Exception:
            # if conversion fails, try using the original file as WAV
            wav_path = input_path

        # 1. Speech → Text (use converted WAV)
        user_text = speech_to_text(wav_path)

        # 2. LLM Response
        bot_reply = ask_llm(user_text)

        # 3. Generate TTS (temp file)
        audio_path = generate_tts(bot_reply)

        return jsonify({
            "user_text": user_text,
            "bot_reply": bot_reply,
            "audio_url": f"/get_audio/{audio_path}"
        })
    finally:
        # Clean up temporary files
        for p in (input_path, wav_path):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass

# --------------------------
#  TEXT INPUT ROUTE
# --------------------------
@app.route("/process_text", methods=["POST"])
def process_text():
    user_text = request.json.get("user_text")

    # 1. Ask LLM
    bot_reply = ask_llm(user_text)

    # 2. TTS Output (temp file)
    audio_path = generate_tts(bot_reply)

    return jsonify({
        "user_text": user_text,
        "bot_reply": bot_reply,
        "audio_url": f"/get_audio/{audio_path}"
    })

@app.route("/get_audio/<path:audio_path>")
def get_audio(audio_path):
    response = send_file(audio_path, mimetype="audio/mpeg")
    # Clean up after serving (defer to after response)
    @response.call_on_close
    def cleanup():
        if os.path.exists(audio_path):
            os.unlink(audio_path)
    return response

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)