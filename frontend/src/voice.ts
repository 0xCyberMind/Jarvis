/**
 * Voice input (Web Speech API) and audio output (AudioContext) for JARVIS.
 */

// ---------------------------------------------------------------------------
// Speech Recognition
// ---------------------------------------------------------------------------

export interface VoiceInput {
  start(): void;
  stop(): void;
  pause(): void;
  resume(): void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const webkitSpeechRecognition: any;

export function createVoiceInput(
  onTranscript: (text: string) => void,
  onError: (msg: string) => void
): VoiceInput {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const SR = (window as any).SpeechRecognition || (typeof webkitSpeechRecognition !== "undefined" ? webkitSpeechRecognition : null);
  if (!SR) {
    onError("Speech recognition not supported in this browser");
    return { start() {}, stop() {}, pause() {}, resume() {} };
  }

  const recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  let shouldListen = false;
  let paused = false;

  recognition.onresult = (event: any) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        const text = event.results[i][0].transcript.trim();
        if (text) onTranscript(text);
      }
    }
  };

  recognition.onend = () => {
    if (shouldListen && !paused) {
      try {
        recognition.start();
      } catch {
        // Already started
      }
    }
  };

  recognition.onerror = (event: any) => {
    if (event.error === "not-allowed") {
      onError("Microphone access denied. Please allow microphone access.");
      shouldListen = false;
    } else if (event.error === "no-speech") {
      // Normal, just restart
    } else if (event.error === "aborted") {
      // Expected during pause
    } else {
      console.warn("[voice] recognition error:", event.error);
    }
  };

  return {
    start() {
      shouldListen = true;
      paused = false;
      try {
        recognition.start();
      } catch {
        // Already started
      }
    },
    stop() {
      shouldListen = false;
      paused = false;
      recognition.stop();
    },
    pause() {
      paused = true;
      recognition.stop();
    },
    resume() {
      paused = false;
      if (shouldListen) {
        try {
          recognition.start();
        } catch {
          // Already started
        }
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Audio Player
// ---------------------------------------------------------------------------

export interface AudioPlayer {
  enqueue(base64: string): Promise<void>;
  speak(text: string): void;
  unlock(): Promise<void>;
  stop(): void;
  getAnalyser(): AnalyserNode;
  onFinished(cb: () => void): void;
}

export function createAudioPlayer(): AudioPlayer {
  const audioCtx = new AudioContext();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.8;
  analyser.connect(audioCtx.destination);

  const queue: AudioBuffer[] = [];
  let isPlaying = false;
  let currentSource: AudioBufferSourceNode | null = null;
  let finishedCallback: (() => void) | null = null;
  let speechFinishedTimer: number | null = null;
  let userActivatedAudio = false;
  const speechQueue: string[] = [];
  let isSpeaking = false;
  let currentUtterance: SpeechSynthesisUtterance | null = null;

  function shouldUseHindiVoice(text: string): boolean {
    if (/[\u0900-\u097F]/.test(text)) return true;
    return /\b(hindi|namaste|kaise|kya|haan|nahi|theek|bolo|batao|karo|kar raha|dekh raha|hoon|hai)\b/i.test(text);
  }

  function getEnglishVoice(): SpeechSynthesisVoice | null {
    const voices = window.speechSynthesis?.getVoices?.() ?? [];
    return (
      voices.find((voice) => /mark/i.test(voice.name)) ??
      voices.find((voice) => /en-(US|GB)/i.test(voice.lang) && /male|david|george|daniel/i.test(voice.name)) ??
      voices.find((voice) => /en-(US|GB)/i.test(voice.lang)) ??
      null
    );
  }

  function getHindiVoice(): SpeechSynthesisVoice | null {
    const voices = window.speechSynthesis?.getVoices?.() ?? [];
    return (
      voices.find((voice) => /^hi[-_]?IN$/i.test(voice.lang)) ??
      voices.find((voice) => /hindi|india|kalpana|hemant|swara|heera/i.test(`${voice.name} ${voice.lang}`)) ??
      voices.find((voice) => /en[-_]?IN/i.test(voice.lang)) ??
      null
    );
  }

  function getVoiceForText(text: string): SpeechSynthesisVoice | null {
    if (shouldUseHindiVoice(text)) {
      return getHindiVoice() ?? getEnglishVoice();
    }
    return getEnglishVoice();
  }

  if ("speechSynthesis" in window) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
  }

  function clearSpeechTimer() {
    if (speechFinishedTimer !== null) {
      window.clearTimeout(speechFinishedTimer);
      speechFinishedTimer = null;
    }
  }

  function finishSpeechFallback() {
    clearSpeechTimer();
    currentUtterance = null;
    isSpeaking = false;

    if (speechQueue.length > 0) {
      speakNext();
    } else {
      finishedCallback?.();
    }
  }

  function speakNext() {
    if (isSpeaking || speechQueue.length === 0 || !("speechSynthesis" in window)) {
      return;
    }

    if (!userActivatedAudio && audioCtx.state === "suspended") {
      return;
    }

    clearSpeechTimer();
    window.speechSynthesis.cancel();
    window.speechSynthesis.resume();

    const cleanText = speechQueue.shift()!;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    const useHindiVoice = shouldUseHindiVoice(cleanText);
    utterance.voice = getVoiceForText(cleanText);
    utterance.lang = utterance.voice?.lang ?? (useHindiVoice ? "hi-IN" : "en-US");
    utterance.rate = useHindiVoice ? 0.9 : 0.94;
    utterance.pitch = useHindiVoice ? 0.9 : 0.82;
    utterance.volume = 1;
    utterance.onend = finishSpeechFallback;
    utterance.onerror = finishSpeechFallback;

    currentUtterance = utterance;
    isSpeaking = true;

    // Chrome is less prone to dropping an utterance if it is spoken on the
    // next task after cancel/resume, especially when voices are still loading.
    window.setTimeout(() => {
      if (currentUtterance === utterance) {
        window.speechSynthesis.speak(utterance);
      }
    }, 0);

    speechFinishedTimer = window.setTimeout(finishSpeechFallback, Math.max(3000, cleanText.length * 90));
  }

  async function unlockAudio() {
    const hasUserActivation =
      Boolean((navigator as Navigator & { userActivation?: { hasBeenActive?: boolean } }).userActivation?.hasBeenActive) ||
      audioCtx.state === "running";

    if (audioCtx.state === "suspended") {
      try {
        await audioCtx.resume();
      } catch {
        // Chrome rejects resume() before a real click/touch/key gesture.
      }
    }

    userActivatedAudio = hasUserActivation || String(audioCtx.state) === "running";

    if ("speechSynthesis" in window) {
      window.speechSynthesis.resume();
    }

    speakNext();
  }

  function playNext() {
    if (queue.length === 0) {
      isPlaying = false;
      currentSource = null;
      finishedCallback?.();
      return;
    }

    isPlaying = true;
    const buffer = queue.shift()!;
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(analyser);
    currentSource = source;

    source.onended = () => {
      if (currentSource === source) {
        playNext();
      }
    };

    source.start();
  }

  const player: AudioPlayer = {
    async enqueue(base64: string) {
      // Resume audio context (browser autoplay policy)
      await unlockAudio();

      try {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }
        const audioBuffer = await audioCtx.decodeAudioData(bytes.buffer.slice(0));
        queue.push(audioBuffer);
        if (!isPlaying) playNext();
      } catch (err) {
        console.error("[audio] decode error:", err);
        // Skip bad audio, continue
        if (!isPlaying && queue.length > 0) playNext();
      }
    },

    speak(text: string) {
      const cleanText = text.trim();
      if (!cleanText || !("speechSynthesis" in window)) {
        finishedCallback?.();
        return;
      }

      // Chrome can silently drop speech before the page receives a user gesture.
      // Queue it and play as soon as click/touch/key unlocks audio.
      if (!userActivatedAudio && audioCtx.state === "suspended") {
        speechQueue.length = 0;
        speechQueue.push(cleanText);
        return;
      }

      speechQueue.push(cleanText);
      speakNext();
    },

    unlock: unlockAudio,

    stop() {
      queue.length = 0;
      clearSpeechTimer();
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      speechQueue.length = 0;
      currentUtterance = null;
      isSpeaking = false;
      if (currentSource) {
        try {
          currentSource.stop();
        } catch {
          // Already stopped
        }
        currentSource = null;
      }
      isPlaying = false;
    },

    getAnalyser() {
      return analyser;
    },

    onFinished(cb: () => void) {
      finishedCallback = cb;
    },
  };

  return player;
}
