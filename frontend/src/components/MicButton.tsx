import { useCallback, useEffect, useRef, useState } from "react";

export interface MicButtonProps {
  onRecordingComplete: (audioBlob: Blob) => void | Promise<void>;
  onRecordingStart?: () => void;
  disabled?: boolean;
  onError?: (errorMessage: string) => void;
  className?: string;
}

export function MicButton({
  onRecordingComplete,
  onRecordingStart,
  disabled = false,
  onError,
  className = "",
}: MicButtonProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const startTimeRef = useRef<number>(0);

  const clearTimer = useCallback(() => {
    if (timerIntervalRef.current !== null) {
      window.clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  const cleanupStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      clearTimer();
      cleanupStream();
    };
  }, [clearTimer, cleanupStream]);

  const startRecording = async () => {
    // 1. Check browser support
    if (
      typeof window === "undefined" ||
      !navigator?.mediaDevices?.getUserMedia ||
      typeof window.MediaRecorder === "undefined"
    ) {
      onError?.(
        "Voice recording is not supported in this browser. Please use the text input.",
      );
      return;
    }

    try {
      // 2. Request microphone stream
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // 3. Determine best supported mimeType
      let mimeType = "audio/webm";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm";
      } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      } else if (MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")) {
        mimeType = "audio/ogg;codecs=opus";
      }

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        clearTimer();
        cleanupStream();
        setIsRecording(false);

        const durationSec = (Date.now() - startTimeRef.current) / 1000;
        const audioBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || mimeType,
        });

        // 4. Validate non-empty recording
        if (audioBlob.size === 0 || durationSec < 0.6) {
          onError?.(
            "Recording was too short or empty. Please speak clearly and try again.",
          );
          return;
        }

        try {
          setIsProcessing(true);
          await onRecordingComplete(audioBlob);
        } catch (err) {
          onError?.(
            err instanceof Error
              ? err.message
              : "Failed to process audio recording.",
          );
        } finally {
          setIsProcessing(false);
        }
      };

      // 5. Start recording and elapsed timer
      onRecordingStart?.();
      startTimeRef.current = Date.now();
      audioChunksRef.current = [];
      recorder.start(250); // Slice data every 250ms
      setIsRecording(true);
      setElapsedSeconds(0);

      timerIntervalRef.current = window.setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err: unknown) {
      clearTimer();
      cleanupStream();
      setIsRecording(false);

      if (err instanceof DOMException) {
        if (
          err.name === "NotAllowedError" ||
          err.name === "PermissionDeniedError"
        ) {
          onError?.(
            "Microphone permission was denied. Please allow microphone access in your browser or type your answer.",
          );
          return;
        }
        if (
          err.name === "NotFoundError" ||
          err.name === "DevicesNotFoundError"
        ) {
          onError?.(
            "No microphone detected on your device. Please connect a microphone or use the text input.",
          );
          return;
        }
      }

      onError?.(
        err instanceof Error
          ? `Microphone error: ${err.message}`
          : "Could not access microphone. Please type your answer.",
      );
    }
  };

  const stopRecording = () => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }
  };

  const handleClick = () => {
    if (disabled || isProcessing) return;
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  return (
    <div className={`relative inline-flex items-center gap-2 ${className}`}>
      {/* Live recording indicator and elapsed time */}
      {isRecording && (
        <div className="flex items-center gap-1.5 rounded-full bg-red-100 px-2.5 py-1 text-xs font-semibold text-red-700 animate-pulse">
          <span className="h-2 w-2 rounded-full bg-red-600" />
          <span>REC {formatTime(elapsedSeconds)}</span>
        </div>
      )}

      {/* Processing indicator */}
      {isProcessing && (
        <div className="flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
          <span className="h-2 w-2 animate-ping rounded-full bg-blue-600" />
          <span>Transcribing...</span>
        </div>
      )}

      {/* Mic Action Button */}
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || isProcessing}
        title={
          isRecording
            ? "Click to stop recording"
            : disabled
            ? "Voice input disabled"
            : "Click to record voice answer"
        }
        aria-label={
          isRecording
            ? "Stop recording answer"
            : "Start recording voice answer"
        }
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition-all shadow-sm ${
          isRecording
            ? "border-red-500 bg-red-600 text-white hover:bg-red-700 ring-2 ring-red-300"
            : isProcessing
            ? "border-blue-300 bg-blue-50 text-blue-600 cursor-wait"
            : disabled
            ? "border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed"
            : "border-gray-300 bg-white text-gray-700 hover:border-blue-500 hover:bg-blue-50 hover:text-blue-600"
        }`}
      >
        {isRecording ? (
          // Stop recording icon (Square)
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4 fill-current"
            viewBox="0 0 24 24"
          >
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
        ) : isProcessing ? (
          // Processing spinner icon
          <svg
            className="h-5 w-5 animate-spin text-blue-600"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </svg>
        ) : (
          // Microphone icon
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 003-3V5a3 3 0 00-6 0v6a3 3 0 003 3z"
            />
          </svg>
        )}
      </button>
    </div>
  );
}
export default MicButton;

