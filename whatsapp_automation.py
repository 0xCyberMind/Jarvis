import asyncio
import importlib
import random
import sys
from types import ModuleType
from typing import Optional

from actions import (
    whatsapp_get_unread,
    whatsapp_open,
    whatsapp_open_chat,
    whatsapp_send_file,
    whatsapp_send_message,
)

pyttsx3: Optional[ModuleType]
engine = None
try:
    pyttsx3 = importlib.import_module("pyttsx3")
    engine = pyttsx3.init()
    engine.setProperty("rate", 170)
    TTS_AVAILABLE = True
except Exception:
    pyttsx3 = None
    TTS_AVAILABLE = False

sr: Optional[ModuleType]
try:
    sr = importlib.import_module("speech_recognition")
    SR_AVAILABLE = True
except Exception:
    sr = None
    SR_AVAILABLE = False


class JarvisWhatsApp:
    def __init__(self):
        self.running = True
        self.whatsapp_open = False
        self.speak("Jarvis WhatsApp Automation is ready, sir.")

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def speak(self, text: str):
        print(f"JARVIS: {text}")
        if TTS_AVAILABLE and engine is not None:
            engine.say(text)
            engine.runAndWait()

    def listen(self) -> str:
        if not SR_AVAILABLE or sr is None:
            return ""

        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            print("Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = recognizer.listen(source, timeout=5)
                command = recognizer.recognize_google(audio)
                print(f"You said: {command}")
                return command.lower()
            except (sr.WaitTimeoutError, sr.UnknownValueError):
                return ""
            except sr.RequestError:
                self.speak("Speech service unavailable.")
                return ""

    def open_whatsapp(self):
        result = self._run(whatsapp_open())
        self.whatsapp_open = result.get("success", False)
        self.speak(result.get("confirmation", "WhatsApp opened, sir."))
        return result

    def open_chat(self, contact_name: str):
        result = self._run(whatsapp_open_chat(contact_name))
        self.speak(result.get("confirmation", f"Opened chat with {contact_name}, sir."))
        return result

    def send_message(self, contact_name: str, message: str):
        result = self._run(whatsapp_send_message(contact_name, message))
        self.speak(result.get("confirmation", f"Message sent to {contact_name}."))
        return result

    def send_file(self, contact_name: str, file_path: str):
        result = self._run(whatsapp_send_file(contact_name, file_path))
        self.speak(result.get("confirmation", f"Sent file to {contact_name}."))
        return result

    def read_chats(self):
        result = self._run(whatsapp_get_unread())
        self.speak(result.get("confirmation", "WhatsApp opened, sir."))
        return result

    def say_hi(self, contact_name: str):
        greetings = ["Hi!", "Hello there!", "Hey! What's up?"]
        self.send_message(contact_name, random.choice(greetings))


def parse_and_run(jarvis: JarvisWhatsApp, command: str):
    cmd = command.strip().lower()

    if any(k in cmd for k in ["open whatsapp chat with", "whatsapp chat with", "open chat with"]):
        for prefix in ["open whatsapp chat with", "whatsapp chat with", "open chat with"]:
            if cmd.startswith(prefix):
                jarvis.open_chat(command[len(prefix):].strip())
                break
    elif any(k in cmd for k in ["open whatsapp", "launch whatsapp", "start whatsapp"]):
        jarvis.open_whatsapp()
    elif cmd.startswith("send message") or "whatsapp message" in cmd:
        try:
            if "to" in command.lower() and ":" in command:
                part = command.split("to", 1)[1]
                contact, message = part.split(":", 1)
                jarvis.send_message(contact.strip(), message.strip())
            else:
                print("Format: send message to <name> : <your message>")
        except (IndexError, ValueError):
            print("Format: send message to <name> : <your message>")
    elif cmd.startswith("say hi") or cmd.startswith("send hi"):
        try:
            contact = command.split("to", 1)[1].strip()
            jarvis.say_hi(contact)
        except IndexError:
            print("Format: say hi to <name>")
    elif cmd.startswith("send file") or "whatsapp file" in cmd:
        try:
            part = command.split("to", 1)[1]
            contact, filepath = part.split(":", 1)
            jarvis.send_file(contact.strip(), filepath.strip())
        except (IndexError, ValueError):
            print("Format: send file to <name> : <file path>")
    elif any(k in cmd for k in ["read chats", "read chat", "check whatsapp", "whatsapp unread", "unread whatsapp", "whatsapp messages"]):
        jarvis.read_chats()
    elif cmd in ["voice", "listen", "voice mode"]:
        if SR_AVAILABLE:
            jarvis.speak("Voice mode active. Speak your command.")
            voice_cmd = jarvis.listen()
            if voice_cmd:
                parse_and_run(jarvis, voice_cmd)
        else:
            print("speech_recognition not installed. Run: pip install SpeechRecognition pyaudio")
    elif cmd in ["help", "commands", "?"]:
        print_help()
    elif cmd in ["exit", "quit", "bye", "stop"]:
        jarvis.speak("Goodbye, sir.")
        sys.exit(0)
    else:
        print(f"Unknown command: '{command}'")
        print("Type 'help' to see all commands.")


def print_help():
    print("""
JARVIS WHATSAPP COMMANDS
  open whatsapp
  open whatsapp chat with <name>
  send message to <name> : <message>
  say hi to <name>
  send file to <name> : <full file path>
  read chats
  voice
  help
  exit
""")


def main():
    print("""
JARVIS - WhatsApp Automation Assistant
Type 'help' for commands | Type 'exit' to quit
""")
    jarvis = JarvisWhatsApp()
    print_help()
    while True:
        try:
            command = input("\n> ").strip()
            if command:
                parse_and_run(jarvis, command)
        except KeyboardInterrupt:
            print("\nJarvis shutting down...")
            jarvis.speak("Goodbye, sir.")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
