type SpeechRecognitionCtor = new () => SpeechRecognition;

export class VoiceController {
  private recognition: SpeechRecognition | null = null;

  constructor() {
    const Ctor = (window.SpeechRecognition || window.webkitSpeechRecognition) as SpeechRecognitionCtor | undefined;
    if (Ctor) {
      this.recognition = new Ctor();
      this.recognition.lang = "en-US";
      this.recognition.continuous = false;
      this.recognition.interimResults = false;
    }
  }

  listen(onText: (text: string) => void, onStatus: (status: string) => void): void {
    if (!this.recognition) {
      onStatus("Speech recognition unavailable in this browser");
      return;
    }

    this.recognition.onstart = () => onStatus("Listening...");
    this.recognition.onend = () => onStatus("Connected");
    this.recognition.onerror = () => onStatus("Voice error");
    this.recognition.onresult = (event) => {
      const result = event.results[0][0].transcript;
      onText(result);
    };
    this.recognition.start();
  }

  speak(text: string): void {
    if (!("speechSynthesis" in window)) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }
}
