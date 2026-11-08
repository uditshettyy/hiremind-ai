import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { loadSessionData } from "../api/sessionStore";
import { MicButton } from "../components/MicButton";
import { useInterviewSocket } from "../hooks/useInterviewSocket";
import { useSpeech } from "../hooks/useSpeech";
import {
  Volume2,
  VolumeX,
  RotateCcw,
  Send,
  Sparkles,
  Bot,
  User,
  ArrowLeft
} from "lucide-react";

export default function InterviewPage() {
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const sessionData = loadSessionData(sessionId);
  const totalQuestionsConfig =
    sessionData?.session?.question_set?.questions?.length ?? 5;

  const [inputAnswer, setInputAnswer] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const {
    speak,
    stop: stopSpeech,
    replay: replayQuestion,
    isSpeaking,
    isMuted,
    toggleMute,
  } = useSpeech();

  const {
    messages,
    connectionStatus,
    isInterviewComplete,
    turnNumber,
    totalQuestions,
    isWaitingForQuestion,
    error,
    sendAnswer,
    sendAudioAnswer,
    reconnect,
  } = useInterviewSocket(sessionId, {
    initialTotalQuestions: totalQuestionsConfig,
    onQuestion: (question) => {
      speak(question.question_text);
    },
    onComplete: () => {
      stopSpeech();
      setTimeout(() => {
        navigate(`/session/${sessionId}/report`);
      }, 1500);
    },
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isWaitingForQuestion]);

  useEffect(() => {
    if (!isWaitingForQuestion && connectionStatus === "connected") {
      textareaRef.current?.focus();
    }
  }, [isWaitingForQuestion, connectionStatus]);

  function handleSend(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!inputAnswer.trim() || isWaitingForQuestion) return;
    stopSpeech();
    sendAnswer(inputAnswer);
    setInputAnswer("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const progressPercent = Math.min(
    100,
    Math.round(((turnNumber > 0 ? turnNumber : 1) / (totalQuestions || 5)) * 100),
  );

  return (
    <div className="flex h-screen flex-col bg-[#0b0f17] text-slate-100">
      {/* ---------------- Header with Status & Voice Controls ---------------- */}
      <header className="border-b border-slate-800 bg-[#0d121f]/90 px-6 py-3.5 backdrop-blur-xl shadow-lg shadow-black/20 z-10">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to={`/session/${sessionId}/skill-gap`}
              className="flex items-center gap-1 text-xs font-semibold text-slate-400 hover:text-white transition"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Skill Gap
            </Link>
            <span className="text-slate-700">|</span>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 border border-indigo-500/30 text-indigo-400">
                <Bot className="h-4 w-4" />
              </div>
              <h1 className="text-sm font-bold text-white tracking-tight">
                AI Technical Interview Session
              </h1>
            </div>
          </div>

          {/* Voice Controls & Connection Status */}
          <div className="flex items-center gap-2.5">
            {/* Replay Question Button */}
            <button
              type="button"
              onClick={replayQuestion}
              disabled={turnNumber === 0}
              title="Replay audio"
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 hover:border-indigo-400 hover:bg-slate-800 hover:text-indigo-300 disabled:opacity-40 transition"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Replay</span>
            </button>

            {/* Mute Toggle */}
            <button
              type="button"
              onClick={toggleMute}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                isMuted
                  ? "border-slate-700 bg-slate-800/50 text-slate-400 hover:bg-slate-800"
                  : isSpeaking
                  ? "border-indigo-500/50 bg-indigo-950/60 text-indigo-300 ring-1 ring-indigo-500/30 animate-pulse"
                  : "border-slate-700 bg-slate-800/80 text-slate-200 hover:text-indigo-300"
              }`}
            >
              {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
              <span>{isMuted ? "Muted" : isSpeaking ? "Speaking..." : "Voice On"}</span>
            </button>

            <span className="text-slate-700">|</span>

            {/* Status indicator */}
            <div className="flex items-center gap-1.5">
              <span
                className={`h-2 w-2 rounded-full ${
                  connectionStatus === "connected"
                    ? "bg-emerald-400 shadow-sm shadow-emerald-400/50"
                    : connectionStatus === "reconnecting" || connectionStatus === "connecting"
                    ? "animate-pulse bg-amber-400"
                    : "bg-rose-500"
                }`}
              />
              <span className="text-[11px] font-medium capitalize text-slate-400">
                {connectionStatus}
              </span>
              {connectionStatus === "disconnected" && (
                <button
                  type="button"
                  onClick={reconnect}
                  className="ml-1 rounded bg-indigo-600/30 border border-indigo-500/40 px-2 py-0.5 text-[11px] font-medium text-indigo-300 hover:bg-indigo-600/50"
                >
                  Reconnect
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Top Progress bar */}
        <div className="mx-auto mt-2.5 max-w-5xl">
          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span>
              {turnNumber > 0
                ? `Question ${turnNumber} of ${totalQuestions || 5}`
                : "Initializing Question Set..."}
            </span>
            <span>{progressPercent}% Complete</span>
          </div>
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </header>

      {/* ---------------- Error Notification Banner ---------------- */}
      {error && (
        <div
          role="alert"
          className="border-b border-rose-500/30 bg-rose-950/40 px-6 py-2 text-center text-xs font-medium text-rose-300 backdrop-blur-md"
        >
          {error}
        </div>
      )}

      {/* ---------------- Chat Stream Viewport ---------------- */}
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((msg) => {
            if (msg.sender === "system") {
              return (
                <div key={msg.id} className="text-center my-3">
                  <span className="inline-block rounded-full border border-slate-800 bg-slate-900/60 px-3.5 py-1 text-[11px] text-slate-400">
                    {msg.text}
                  </span>
                </div>
              );
            }

            const isInterviewer = msg.sender === "interviewer";

            return (
              <div
                key={msg.id}
                className={`flex gap-3.5 ${
                  isInterviewer ? "justify-start" : "justify-end"
                }`}
              >
                {/* Interviewer Avatar */}
                {isInterviewer && (
                  <div className="flex h-9 w-9 shrink-0 select-none items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-600 text-xs font-bold text-white shadow-lg shadow-indigo-600/30">
                    <Bot className="h-5 w-5" />
                  </div>
                )}

                {/* Message Bubble */}
                <div
                  className={`max-w-[85%] rounded-2xl p-5 shadow-xl sm:max-w-[80%] ${
                    isInterviewer
                      ? "rounded-tl-xs border border-slate-800 bg-[#101726]/90 text-slate-100 backdrop-blur-md"
                      : "rounded-tr-xs border border-indigo-500/30 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-indigo-500/10"
                  }`}
                >
                  {/* Header Row */}
                  <div className="mb-2 flex items-center justify-between gap-3 border-b border-white/5 pb-1.5">
                    <span
                      className={`text-xs font-bold ${
                        isInterviewer ? "text-indigo-400" : "text-indigo-200"
                      }`}
                    >
                      {isInterviewer ? "AI Technical Interviewer" : "Candidate Response"}
                    </span>
                    {msg.turnNumber && (
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                          isInterviewer ? "bg-slate-800 text-slate-400" : "bg-indigo-800/60 text-indigo-200"
                        }`}
                      >
                        Turn {msg.turnNumber} of 5
                      </span>
                    )}
                  </div>

                  {/* Question Target Skill Tag */}
                  {isInterviewer && msg.question?.target_skill && (
                    <div className="mb-3">
                      <span className="inline-flex items-center gap-1 rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs font-medium text-indigo-300">
                        <Sparkles className="h-3 w-3" /> Probing Skill: {msg.question.target_skill}
                      </span>
                    </div>
                  )}

                  {/* Message Content */}
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200 font-normal">
                    {msg.text}
                  </div>

                  {/* Audio Replay for Interviewer */}
                  {isInterviewer && msg.question && (
                    <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-end">
                      <button
                        type="button"
                        onClick={() => speak(msg.question!.question_text)}
                        title="Replay this question"
                        className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium text-indigo-400 hover:bg-indigo-500/10 hover:text-indigo-300 transition"
                      >
                        <Volume2 className="h-3.5 w-3.5" />
                        <span>Replay Audio</span>
                      </button>
                    </div>
                  )}

                  {/* Candidate Evaluation Summary Card */}
                  {!isInterviewer && msg.evaluation && (
                    <div className="mt-3.5 rounded-xl border border-white/10 bg-black/20 p-3.5 space-y-2">
                      <div className="flex items-center justify-between text-xs font-semibold text-indigo-200">
                        <span>Turn Score: {msg.evaluation.overall_score}/10</span>
                        {msg.routingHint && (
                          <span className="capitalize text-indigo-300 text-[11px] font-normal">
                            Next: {msg.routingHint.replace(/_/g, " ")}
                          </span>
                        )}
                      </div>
                      {msg.evaluation.summary_feedback && (
                        <p className="text-xs text-indigo-100/90 italic leading-relaxed">
                          "{msg.evaluation.summary_feedback}"
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* Candidate Avatar */}
                {!isInterviewer && (
                  <div className="flex h-9 w-9 shrink-0 select-none items-center justify-center rounded-xl bg-slate-800 border border-slate-700 text-xs font-bold text-slate-300 shadow-md">
                    <User className="h-5 w-5" />
                  </div>
                )}
              </div>
            );
          })}

          {/* Evaluating State Indicator */}
          {isWaitingForQuestion && connectionStatus === "connected" && (
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 select-none items-center justify-center rounded-xl bg-indigo-600 text-xs font-bold text-white shadow-lg shadow-indigo-600/30">
                <Bot className="h-5 w-5" />
              </div>
              <div className="rounded-2xl rounded-tl-xs border border-slate-800 bg-[#101726]/90 px-5 py-3.5 shadow-xl">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:-0.3s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:-0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-500" />
                  <span className="ml-2 text-xs font-medium text-slate-400">
                    {turnNumber === 0
                      ? "Generating targeted question bank..."
                      : "Evaluator Agent scoring response and analyzing competencies..."}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* ---------------- Completion Banner ---------------- */}
      {isInterviewComplete && (
        <div className="border-t border-emerald-500/30 bg-emerald-950/40 p-4 text-center backdrop-blur-xl">
          <p className="font-bold text-emerald-300">
            Interview Complete!
          </p>
          <p className="text-xs text-slate-300 mt-0.5">
            Generating your multi-dimensional competency benchmark & personalized study plan...
          </p>
          <button
            type="button"
            onClick={() => navigate(`/session/${sessionId}/report`)}
            className="mt-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-6 py-2.5 text-xs font-semibold text-white shadow-lg shadow-emerald-600/30 hover:from-emerald-500 hover:to-teal-500 transition"
          >
            View Full Report →
          </button>
        </div>
      )}

      {/* ---------------- Bottom Input Control Bar ---------------- */}
      {!isInterviewComplete && (
        <footer className="border-t border-slate-800 bg-[#0d121f]/90 p-4 backdrop-blur-xl shadow-2xl">
          <div className="mx-auto max-w-3xl">
            {voiceError && (
              <div
                role="alert"
                className="mb-3 flex items-center justify-between rounded-xl border border-amber-500/30 bg-amber-950/40 px-4 py-2 text-xs font-medium text-amber-300"
              >
                <span>⚠️ {voiceError}</span>
                <button
                  type="button"
                  onClick={() => setVoiceError(null)}
                  className="rounded px-1.5 py-0.5 text-amber-400 hover:bg-amber-900/40"
                >
                  ✕
                </button>
              </div>
            )}

            <form onSubmit={handleSend} className="flex items-end gap-2.5">
              {/* Mic Button */}
              <MicButton
                disabled={isWaitingForQuestion || connectionStatus !== "connected"}
                onRecordingStart={stopSpeech}
                onRecordingComplete={async (audioBlob) => {
                  setVoiceError(null);
                  await sendAudioAnswer(audioBlob);
                }}
                onError={(msg) => setVoiceError(msg)}
              />

              {/* Text Input area */}
              <div className="relative flex-1">
                <textarea
                  ref={textareaRef}
                  rows={2}
                  value={inputAnswer}
                  onChange={(e) => setInputAnswer(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isWaitingForQuestion || connectionStatus !== "connected"}
                  placeholder={
                    connectionStatus !== "connected"
                      ? "Connecting to interview session..."
                      : isWaitingForQuestion
                      ? "Interviewer is speaking or evaluating your answer..."
                      : "Speak via mic or type your technical answer here... (Enter to send, Shift+Enter for newline)"
                  }
                  className="block w-full resize-none rounded-xl border border-slate-700/80 bg-slate-900/60 p-3.5 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-900/30 disabled:text-slate-600 transition"
                />
              </div>

              {/* Send Button */}
              <button
                type="submit"
                disabled={
                  !inputAnswer.trim() ||
                  isWaitingForQuestion ||
                  connectionStatus !== "connected"
                }
                className="flex h-11 items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-5 font-semibold text-white shadow-lg shadow-indigo-600/30 hover:from-indigo-500 hover:to-purple-500 disabled:cursor-not-allowed disabled:opacity-40 transition"
              >
                <span>Send</span>
                <Send className="h-4 w-4" />
              </button>
            </form>

            <p className="mt-2 text-center text-[11px] text-slate-400">
              Speak naturally using the microphone or type. Real-time Groq Whisper transcription & adaptive evaluation enabled.
            </p>
          </div>
        </footer>
      )}
    </div>
  );
}

