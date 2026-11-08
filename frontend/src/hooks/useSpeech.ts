import { useCallback, useEffect, useRef, useState } from "react";

export interface UseSpeechOptions {
  initialMuted?: boolean;
  rate?: number;
  pitch?: number;
  lang?: string;
}

export interface UseSpeechReturn {
  speak: (text: string) => void;
  stop: () => void;
  replay: () => void;
  isSpeaking: boolean;
  isMuted: boolean;
  toggleMute: () => void;
  setIsMuted: (muted: boolean) => void;
  isSupported: boolean;
  lastSpokenText: string | null;
}

/**
 * Chooses a natural sounding English voice with resilient fallbacks across
 * Chrome, Edge, Safari, and Firefox.
 */
function selectSensibleVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices.length) return null;

  // 1. Preferred modern natural voices (Google, Microsoft Natural, Apple Samantha/Alex)
  const preferred = voices.find((v) => {
    const name = v.name.toLowerCase();
    const isEn = v.lang.startsWith("en");
    return (
      isEn &&
      (name.includes("natural") ||
        name.includes("google") ||
        name.includes("samantha") ||
        name.includes("jenny") ||
        name.includes("guy") ||
        name.includes("aria"))
    );
  });
  if (preferred) return preferred;

  // 2. English US standard
  const enUS = voices.find((v) => v.lang === "en-US" || v.lang === "en_US");
  if (enUS) return enUS;

  // 3. Any English voice
  const anyEn = voices.find((v) => v.lang.toLowerCase().startsWith("en"));
  if (anyEn) return anyEn;

  // 4. Fallback to default voice or first voice in browser
  return voices.find((v) => v.default) || voices[0] || null;
}

export function useSpeech(options: UseSpeechOptions = {}): UseSpeechReturn {
  const {
    initialMuted = false,
    rate = 1.0,
    pitch = 1.0,
    lang = "en-US",
  } = options;

  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMutedState] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("hiremind_speech_muted");
      if (saved !== null) return saved === "true";
    }
    return initialMuted;
  });
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [lastSpokenText, setLastSpokenText] = useState<string | null>(null);

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const isMutedRef = useRef(isMuted);
  isMutedRef.current = isMuted;

  const isSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  // Load and cache browser speech voices
  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const available = window.speechSynthesis.getVoices();
      if (available.length) {
        setVoices(available);
      }
    };

    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
    };
  }, [isSupported]);

  // Persist mute state to localStorage
  const setIsMuted = useCallback((muted: boolean) => {
    setIsMutedState(muted);
    if (typeof window !== "undefined") {
      localStorage.setItem("hiremind_speech_muted", String(muted));
    }
    // If muting while currently speaking, cancel immediately
    if (muted && typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted(!isMutedRef.current);
  }, [setIsMuted]);

  // Stop any ongoing speech synthesis immediately
  const stop = useCallback(() => {
    if (isSupported) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    utteranceRef.current = null;
  }, [isSupported]);

  // Speak text using browser speechSynthesis
  const speak = useCallback(
    (text: string) => {
      if (!isSupported || !text?.trim()) return;

      const cleanText = text.trim();
      setLastSpokenText(cleanText);

      // Respect mute toggle
      if (isMutedRef.current) return;

      // Cancel any currently active utterance before starting new one
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = rate;
      utterance.pitch = pitch;
      utterance.lang = lang;

      const selectedVoice = selectSensibleVoice(voices);
      if (selectedVoice) {
        utterance.voice = selectedVoice;
      }

      utterance.onstart = () => {
        setIsSpeaking(true);
      };

      utterance.onend = () => {
        setIsSpeaking(false);
        utteranceRef.current = null;
      };

      utterance.onerror = (e) => {
        // "interrupted" or "canceled" are standard events when stop() is called
        if (e.error !== "interrupted" && e.error !== "canceled") {
          console.warn("SpeechSynthesis error:", e.error);
        }
        setIsSpeaking(false);
        utteranceRef.current = null;
      };

      // Keep strong reference to prevent GC cutting speech off in Chromium
      utteranceRef.current = utterance;

      // Resume if browser synthesis was paused
      if (window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
      }

      window.speechSynthesis.speak(utterance);
    },
    [isSupported, voices, rate, pitch, lang],
  );

  // Replay the last spoken text
  const replay = useCallback(() => {
    if (lastSpokenText) {
      // If user clicks replay while muted, unmute so they can hear it
      if (isMutedRef.current) {
        setIsMuted(false);
      }
      speak(lastSpokenText);
    }
  }, [lastSpokenText, speak, setIsMuted]);

  // Cleanup speech on unmount
  useEffect(() => {
    return () => {
      if (isSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [isSupported]);

  return {
    speak,
    stop,
    replay,
    isSpeaking,
    isMuted,
    toggleMute,
    setIsMuted,
    isSupported,
    lastSpokenText,
  };
}

export default useSpeech;

