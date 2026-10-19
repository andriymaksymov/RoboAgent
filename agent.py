import os
import subprocess
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")    

# 1. Gemini Client initialisieren (Liest GEMINI_API_KEY aus der Umgebung)
client = genai.Client()

# 2. Lokale Werkzeuge (Tools)
# Docstrings und Type-Hints dienen Gemini automatisch als Werkzeugbeschreibung!

def execute_python(code: str) -> str:
    """Führt Python-Code in einem Subprocess aus und gibt stdout/stderr zurück."""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]:\n{result.stderr}"
        return output if output else "[Code erfolgreich ohne Ausgabe ausgeführt]"
    except Exception as e:
        return f"[Fehler bei der Ausführung]: {str(e)}"

def read_file(path: str) -> str:
    """Liest den Inhalt einer lokalen Datei von der Festplatte."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[Fehler beim Lesen]: {str(e)}"

def write_file(path: str, content: str) -> str:
    """Erstellt eine neue Datei oder überschreibt eine bestehende Datei vollständig."""
    try:
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[Erfolg]: Datei '{path}' wurde erfolgreich geschrieben."
    except Exception as e:
        return f"[Fehler beim Schreiben]: {str(e)}"

def replace_in_file(path: str, target_text: str, replacement_text: str) -> str:
    """Ersetzt einen spezifischen Textblock in einer Datei durch neuen Text."""
    try:
        if not os.path.exists(path):
            return f"[Fehler]: Datei '{path}' existiert nicht."
        
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if target_text not in content:
            return f"[Fehler]: Der zu ersetzende Textabschnitt wurde in '{path}' nicht gefunden."
        
        new_content = content.replace(target_text, replacement_text, 1)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"[Erfolg]: Textabschnitt in '{path}' wurde erfolgreich ersetzt."
    except Exception as e:
        return f"[Fehler beim Ersetzen]: {str(e)}"


# 3. Agenten-Konfiguration und Ausführung
def run_agent(user_prompt: str):
    # Liste der Werkzeug-Funktionen
    tools = [
        execute_python, 
        read_file, 
        write_file, 
        replace_in_file
    ]

    # Chat-Session mit System-Instruktion und Tools starten
    chat = client.chats.create(
        model=GEMINI_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Du bist ein automatisierter Python Coding Agent. "
                "Nutze die zur Verfügung stehenden Werkzeuge, um Dateien zu lesen, zu erstellen oder zu bearbeiten. "
                "Führe Code aus, um deine Änderungen zu testen und behebe Fehler selbstständig."
            ),
            temperature=0.1,
            tools=tools
        )
    )

    print(f"--- Starte Aufgabe: {user_prompt} ---\n")
    
    # send_message führt automatisch alle benötigten Tool-Calls aus
    # und liefert das Endergebnis zurück.
    response = chat.send_message(user_prompt)

    print("\n[Agent Finale Antwort]:")
    print(response.text)


if __name__ == "__main__":
    prompt = (
        "Erstelle ein Python-Skript namens 'calculator.py' mit einer Funktion 'add(a, b)'. "
        "Führe einen kurzen Test mit execute_python aus. "
        "Füge danach mit replace_in_file eine Funktion 'multiply(a, b)' hinzu und teste erneut."
    )
    run_agent(prompt)

