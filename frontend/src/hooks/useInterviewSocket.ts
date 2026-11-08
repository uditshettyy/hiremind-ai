import { useCallback, useEffect, useRef, useState } from "react";
import { interviewSocketUrl } from "../api/client";
import type {
  AnswerEvaluation,
  Question,
  RoutingHint,
  ServerMessage,
} from "../api/types";

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "reconnecting"
  | "error";

export interface ChatMessage {
  id: string;
  sender: "interviewer" | "candidate" | "system";
  text: string;
  timestamp: Date;
  turnNumber?: number;
  question?: Question;
  evaluation?: AnswerEvaluation | null;
  routingHint?: RoutingHint;
}

export interface UseInterviewSocketOptions {
  onQuestion?: (question: Question, turnNumber: number) => void;
  onEvaluation?: (evaluation: AnswerEvaluation | null, turnNumber: number) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
  initialTotalQuestions?: number;
}

export interface UseInterviewSocketReturn {
  // State
  messages: ChatMessage[];
  connectionStatus: ConnectionStatus;
  isInterviewComplete: boolean;
  currentQuestion: Question | null;
  turnNumber: number;
  totalQuestions: number;
  isWaitingForQuestion: boolean;
  error: string | null;

  // Actions
  sendAnswer: (text: string) => void;
  reconnect: () => void;
  disconnect: () => void;

  // Voice layer extension hooks (ready for audio without rewriting hook)
  sendAudioAnswer: (audioBlob: Blob) => Promise<void>;
  isRecording: boolean;
  setIsRecording: (recording: boolean) => void;
  isPlayingAudio: boolean;
  setIsPlayingAudio: (playing: boolean) => void;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY_MS = 1500;

export function useInterviewSocket(
  sessionId?: string,
  options: UseInterviewSocketOptions = {},
): UseInterviewSocketReturn {
  const { initialTotalQuestions = 5 } = options;

  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("connecting");
  const [isInterviewComplete, setIsInterviewComplete] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [turnNumber, setTurnNumber] = useState(0);
  const [totalQuestions, setTotalQuestions] = useState(initialTotalQuestions);
  const [isWaitingForQuestion, setIsWaitingForQuestion] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Voice state placeholders for seamless voice layer extension
  const [isRecording, setIsRecording] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const manuallyClosedRef = useRef(false);

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!sessionId) {
      setConnectionStatus("error");
      setError("No session ID provided.");
      return;
    }

    clearReconnectTimeout();
    manuallyClosedRef.current = false;
    setConnectionStatus(
      reconnectAttemptsRef.current > 0 ? "reconnecting" : "connecting",
    );
    setError(null);

    try {
      const url = interviewSocketUrl(sessionId);
      const ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0;
        setConnectionStatus("connected");
        setError(null);
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as ServerMessage;

          switch (data.type) {
            case "connected": {
              // Avoid duplicate system connection messages if reconnecting
              setMessages((prev) => {
                if (prev.some((m) => m.sender === "system" && m.text.includes("Connected to AI Interview Agent"))) {
                  return prev;
                }
                return [
                  ...prev,
                  {
                    id: `sys-${Date.now()}`,
                    sender: "system",
                    text: "Connected to AI Interview Agent. Preparing your first question...",
                    timestamp: new Date(),
                  },
                ];
              });
              break;
            }

            case "question": {
              const q = data.question;
              const qTurn = data.turn_number;
              setCurrentQuestion(q);
              setTurnNumber(qTurn);
              setIsWaitingForQuestion(false);

              if (qTurn > totalQuestions) {
                setTotalQuestions(qTurn);
              }

              setMessages((prev) => {
                // Avoid duplicating the exact question if already rendered for this turn
                if (prev.some((m) => m.sender === "interviewer" && m.turnNumber === qTurn)) {
                  return prev;
                }
                return [
                  ...prev,
                  {
                    id: `q-${q.question_id}-${Date.now()}`,
                    sender: "interviewer",
                    text: q.question_text,
                    timestamp: new Date(),
                    turnNumber: qTurn,
                    question: q,
                  },
                ];
              });

              optionsRef.current.onQuestion?.(q, qTurn);
              break;
            }

            case "transcript": {
              const transcriptText = data.text;
              const tTurn = data.turn_number;
              setMessages((prev) => [
                ...prev,
                {
                  id: `tr-${Date.now()}`,
                  sender: "candidate",
                  text: transcriptText,
                  timestamp: new Date(),
                  turnNumber: tTurn,
                },
              ]);
              break;
            }

            case "evaluation": {
              const evalTurn = data.turn_number;
              const evaluation = data.evaluation;

              setMessages((prev) => {
                // Attach evaluation to the corresponding candidate answer turn
                return prev.map((msg) => {
                  if (msg.sender === "candidate" && msg.turnNumber === evalTurn) {
                    return {
                      ...msg,
                      evaluation,
                      routingHint: evaluation?.routing_hint,
                    };
                  }
                  return msg;
                });
              });

              setIsWaitingForQuestion(true);
              optionsRef.current.onEvaluation?.(evaluation, evalTurn);
              break;
            }

            case "completed": {
              setIsInterviewComplete(true);
              setIsWaitingForQuestion(false);
              setMessages((prev) => [
                ...prev,
                {
                  id: `complete-${Date.now()}`,
                  sender: "system",
                  text: "Interview completed! Preparing your comprehensive evaluation report...",
                  timestamp: new Date(),
                },
              ]);
              optionsRef.current.onComplete?.();
              break;
            }

            case "error": {
              setError(data.message);
              setIsWaitingForQuestion(false);
              optionsRef.current.onError?.(data.message);
              setMessages((prev) => [
                ...prev,
                {
                  id: `err-${Date.now()}`,
                  sender: "system",
                  text: `Error: ${data.message}`,
                  timestamp: new Date(),
                },
              ]);
              break;
            }
          }
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onerror = () => {
        setConnectionStatus("error");
        setError("WebSocket connection error.");
      };

      ws.onclose = (event: CloseEvent) => {
        socketRef.current = null;

        // Fatal server-side codes — do not reconnect, show error instead.
        // 1008 = session not found / policy violation
        // 1011 = unexpected server error
        const isFatal = event.code === 1008 || event.code === 1011;

        if (manuallyClosedRef.current || isInterviewComplete || event.code === 1000 || isFatal) {
          setConnectionStatus("disconnected");
          if (isFatal) {
            setError(
              event.code === 1008
                ? "Session not found. Please start a new interview."
                : "Server error. Please try again."
            );
          }
          return;
        }

        // Handle unexpected disconnects with reconnection attempts
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1;
          const delay =
            BASE_RECONNECT_DELAY_MS *
            Math.pow(1.5, reconnectAttemptsRef.current - 1);
          setConnectionStatus("reconnecting");
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect();
          }, delay);
        } else {
          setConnectionStatus("disconnected");
          setError("Connection lost. Please click Reconnect to continue.");
        }
      };
    } catch (err) {
      setConnectionStatus("error");
      setError(err instanceof Error ? err.message : "Failed to open WebSocket.");
    }
  }, [
    sessionId,
    clearReconnectTimeout,
    isInterviewComplete,
    totalQuestions,
  ]);

  const disconnect = useCallback(() => {
    manuallyClosedRef.current = true;
    clearReconnectTimeout();
    if (socketRef.current) {
      socketRef.current.close(1000, "User disconnected");
      socketRef.current = null;
    }
    setConnectionStatus("disconnected");
  }, [clearReconnectTimeout]);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    connect();
  }, [connect]);

  const sendAnswer = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isWaitingForQuestion || !socketRef.current) return;
      if (socketRef.current.readyState !== WebSocket.OPEN) {
        setError("Cannot send answer: connection is not open.");
        return;
      }

      // Add local candidate message to chat
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          sender: "candidate",
          text: trimmed,
          timestamp: new Date(),
          turnNumber,
        },
      ]);

      // Lock input until next question or evaluation returns
      setIsWaitingForQuestion(true);

      // Send answer packet per backend protocol
      socketRef.current.send(
        JSON.stringify({
          type: "answer",
          answer_text: trimmed,
        }),
      );
    },
    [isWaitingForQuestion, turnNumber],
  );

  // Send candidate audio blob converted to base64 over WebSocket
  const sendAudioAnswer = useCallback(
    async (audioBlob: Blob): Promise<void> => {
      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
        const msg = "Cannot send audio: connection is not open.";
        setError(msg);
        throw new Error(msg);
      }
      if (isWaitingForQuestion) {
        const msg = "Cannot send audio: waiting for interviewer.";
        setError(msg);
        throw new Error(msg);
      }

      setError(null);
      setIsWaitingForQuestion(true);

      const reader = new FileReader();
      return new Promise<void>((resolve, reject) => {
        reader.onloadend = () => {
          const result = reader.result as string;
          const base64 = result?.includes(",") ? result.split(",")[1] : result;
          if (base64 && socketRef.current) {
            socketRef.current.send(
              JSON.stringify({
                type: "audio_answer",
                audio_base64: base64,
                format: audioBlob.type || "audio/webm",
              }),
            );
            resolve();
          } else {
            setIsWaitingForQuestion(false);
            const err = new Error("Failed to encode audio data.");
            setError(err.message);
            reject(err);
          }
        };
        reader.onerror = () => {
          setIsWaitingForQuestion(false);
          const err = new Error("Failed to read audio blob.");
          setError(err.message);
          reject(err);
        };
        reader.readAsDataURL(audioBlob);
      });
    },
    [isWaitingForQuestion],
  );

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    messages,
    connectionStatus,
    isInterviewComplete,
    currentQuestion,
    turnNumber,
    totalQuestions,
    isWaitingForQuestion,
    error,
    sendAnswer,
    reconnect,
    disconnect,
    sendAudioAnswer,
    isRecording,
    setIsRecording,
    isPlayingAudio,
    setIsPlayingAudio,
  };
}
