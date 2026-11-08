import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, finalizeSession, generateReport } from "../api/client";
import { loadSessionData } from "../api/sessionStore";
import type { AnswerEvaluation, FinalReport, ScoreDimension } from "../api/types";
import { Header } from "../components/Header";
import {
  CheckCircle2,
  AlertTriangle,
  Lightbulb,
  RotateCcw,
  BookOpen,
  TrendingUp,
  Brain
} from "lucide-react";

export default function ReportPage() {
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<FinalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Interactive checklist state for the study plan
  const [completedStudyItems, setCompletedStudyItems] = useState<Set<number>>(
    new Set(),
  );

  // Expanded turns toggle state
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(
    new Set([1]), // first turn expanded by default
  );

  useEffect(() => {
    let isMounted = true;

    async function fetchReport() {
      if (!sessionId) {
        setError("Missing session ID.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const data = await finalizeSession(sessionId);
        if (isMounted) {
          setReport(data);
          setLoading(false);
        }
      } catch (err) {
        const sessionData = loadSessionData(sessionId);
        if (sessionData?.session && sessionData.skill_gap_report) {
          try {
            const fallbackData = await generateReport({
              session_id: sessionId,
              candidate_id: sessionData.session.candidate_id,
              job_id: sessionData.session.job_id,
              turns: sessionData.session.turns,
              skill_gap_report: sessionData.skill_gap_report,
              total_session_duration_seconds: 900,
            });
            if (isMounted) {
              setReport(fallbackData);
              setLoading(false);
            }
            return;
          } catch {
            // Keep original error below
          }
        }

        if (isMounted) {
          const message =
            err instanceof ApiError
              ? err.message
              : "Unable to generate interview report. Check that the backend is running.";
          setError(message);
          setLoading(false);
        }
      }
    }

    fetchReport();

    return () => {
      isMounted = false;
    };
  }, [sessionId]);

  function toggleTurn(turnNum: number) {
    setExpandedTurns((prev) => {
      const next = new Set(prev);
      if (next.has(turnNum)) {
        next.delete(turnNum);
      } else {
        next.add(turnNum);
      }
      return next;
    });
  }

  function toggleStudyItem(index: number) {
    setCompletedStudyItems((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col">
        <Header subtitle="Synthesizing Final Benchmark..." />
        <main className="flex-1 flex items-center justify-center p-6">
          <div className="rounded-3xl border border-slate-800 bg-[#101726]/80 p-10 text-center shadow-2xl backdrop-blur-xl max-w-md w-full">
            <div className="relative mx-auto h-16 w-16 mb-4">
              <div className="absolute inset-0 rounded-full bg-indigo-500/20 animate-ping" />
              <div className="relative flex h-full w-full items-center justify-center rounded-full bg-gradient-to-tr from-indigo-600 to-purple-600 text-white shadow-lg">
                <Brain className="h-8 w-8 animate-pulse" />
              </div>
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Synthesizing Performance Report...
            </h2>
            <p className="mt-2 text-xs text-slate-400 leading-relaxed">
              Our evaluation agent is computing rubric-weighted dimension averages, skill delta progressions, and your personalized actionable study roadmap.
            </p>
          </div>
        </main>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col">
        <Header />
        <main className="mx-auto max-w-xl p-8 my-auto">
          <div
            role="alert"
            className="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-8 text-center backdrop-blur-md"
          >
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/20 text-rose-400 mb-3">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-bold text-white">
              Report Generation Error
            </h2>
            <p className="mt-2 text-xs text-slate-400">
              {error || "Could not retrieve the evaluation report for this interview session."}
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 transition"
              >
                Try Again
              </button>
              <Link
                to="/"
                className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
              >
                Back to Start
              </Link>
            </div>
          </div>
        </main>
      </div>
    );
  }

  const readinessColor =
    report.readiness_level === "ready"
      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
      : report.readiness_level === "needs_work"
      ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
      : "bg-rose-500/20 text-rose-300 border-rose-500/40";

  return (
    <div className="min-h-screen bg-[#0b0f17] text-slate-100 pb-28">
      <Header subtitle="Executive Diagnostic Report & Skill Benchmark" />

      <main className="mx-auto mt-8 max-w-5xl space-y-8 px-6">
        {/* Top Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Diagnostic Performance Benchmark
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Session <span className="font-mono text-indigo-300">{sessionId.slice(0, 8)}...</span> · Completed on{" "}
              {new Date(report.generated_at).toLocaleDateString()}
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="inline-flex items-center gap-2 self-start rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-600/30 hover:from-indigo-500 hover:to-purple-500 transition"
          >
            <RotateCcw className="h-4 w-4" /> Practice Another Role
          </button>
        </div>

        {/* ---------------- 1. Executive Summary & Overall Score Card ---------------- */}
        <section className="rounded-2xl border border-slate-800 bg-gradient-to-br from-[#101726] to-[#0d121f] p-6 sm:p-8 backdrop-blur-xl shadow-2xl">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="space-y-3 md:max-w-xl">
              <div className="flex items-center gap-3">
                <span
                  className={`rounded-full border px-3 py-0.5 text-xs font-bold capitalize ${readinessColor}`}
                >
                  {report.readiness_level.replace(/_/g, " ")}
                </span>
                {report.percentile_estimate !== null && (
                  <span className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-0.5 text-xs font-semibold text-indigo-300">
                    Top {100 - report.percentile_estimate}% Percentile
                  </span>
                )}
              </div>
              <h2 className="text-xl font-bold text-white">Executive Synthesis</h2>
              <p className="text-xs sm:text-sm leading-relaxed text-slate-300">
                {report.executive_summary}
              </p>
            </div>

            {/* Score Ring / Card */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-indigo-500/30 bg-indigo-950/20 px-8 py-6 text-center shadow-inner">
              <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-400">
                Overall Benchmark
              </span>
              <div className="mt-1 text-5xl font-black text-white tracking-tight">
                {report.overall_score.toFixed(1)}
                <span className="text-xl font-normal text-slate-500">/10</span>
              </div>
              <span className="mt-2 text-[11px] text-slate-400">
                Evaluated across {report.total_turns} targeted turns
              </span>
            </div>
          </div>

          {/* Dimension Averages Grid */}
          <div className="mt-8 border-t border-slate-800/80 pt-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Evaluator Dimension Breakdown
            </h3>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
              {(
                Object.entries(report.dimension_averages) as [
                  ScoreDimension,
                  number,
                ][]
              ).map(([dim, score]) => (
                <div
                  key={dim}
                  className="rounded-xl border border-slate-800/90 bg-[#0d121f]/90 p-3.5 text-center shadow-sm"
                >
                  <p className="text-xs font-medium capitalize text-slate-400">
                    {dim}
                  </p>
                  <p className="mt-1 text-xl font-bold text-white">
                    {score.toFixed(1)}
                  </p>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-purple-500"
                      style={{ width: `${(score / 10) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---------------- 2. Strengths & Weak Areas ---------------- */}
        <section className="grid gap-6 md:grid-cols-2">
          {/* Top Strengths */}
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/10 p-6 backdrop-blur-md shadow-lg">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <h2 className="text-base font-bold text-emerald-300">
                Validated Strengths
              </h2>
            </div>
            <ul className="mt-4 space-y-2.5">
              {report.top_strengths.map((str, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 text-xs text-slate-300 leading-relaxed"
                >
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                  <span>{str}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Priority Gaps / Weak Areas */}
          <div className="rounded-2xl border border-amber-500/30 bg-amber-950/10 p-6 backdrop-blur-md shadow-lg">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/20 text-amber-400">
                <AlertTriangle className="h-4 w-4" />
              </div>
              <h2 className="text-base font-bold text-amber-300">
                Priority Growth Opportunities
              </h2>
            </div>
            <ul className="mt-4 space-y-2.5">
              {report.priority_gaps.map((gap, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 text-xs text-slate-300 leading-relaxed"
                >
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                  <span>{gap}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------- 3. Skill Progression ---------------- */}
        {report.skill_progressions.length > 0 && (
          <section className="rounded-2xl border border-slate-800 bg-[#101726]/70 p-6 backdrop-blur-xl shadow-xl">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-indigo-400" />
              <h2 className="text-base font-bold text-white">
                Skill Demonstration Trajectory
              </h2>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Direct comparison between resume claims and demonstrated live technical reasoning.
            </p>

            <div className="mt-6 space-y-3">
              {report.skill_progressions.map((prog) => {
                const isImproved = prog.progression_delta > 0;
                return (
                  <div
                    key={prog.skill_name}
                    className="flex flex-col gap-2 rounded-xl border border-slate-800/90 bg-[#0d121f]/90 p-4 sm:flex-row sm:items-center sm:justify-between shadow-sm"
                  >
                    <div>
                      <span className="font-semibold text-white capitalize text-sm">
                        {prog.skill_name.replace(/_/g, " ")}
                      </span>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Probed in questions: {prog.evidence_turns.join(", ")}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 text-xs">
                      <span className="rounded-lg border border-slate-700 bg-slate-800/60 px-2.5 py-1 font-medium text-slate-300 capitalize">
                        Initial: {prog.initial_gap}
                      </span>
                      <span className="text-slate-500">→</span>
                      <span
                        className={`rounded-lg border px-2.5 py-1 font-semibold capitalize ${
                          isImproved
                            ? "border-emerald-500/40 bg-emerald-500/20 text-emerald-300"
                            : "border-indigo-500/40 bg-indigo-500/20 text-indigo-300"
                        }`}
                      >
                        Inferred: {prog.final_inferred_level}
                      </span>
                      {prog.progression_delta !== 0 && (
                        <span
                          className={`text-xs font-bold ${
                            isImproved ? "text-emerald-400" : "text-amber-400"
                          }`}
                        >
                          {prog.progression_delta > 0 ? `+${prog.progression_delta}` : prog.progression_delta}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* ---------------- 4. Expandable Per-Question Breakdown ---------------- */}
        <section className="rounded-2xl border border-slate-800 bg-[#101726]/70 p-6 backdrop-blur-xl shadow-xl">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white">
                Turn-by-Turn Diagnostic Analysis
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Detailed examiner scoring rubrics, qualitative feedback, and exemplar answer models for all 5 questions.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {report.per_turn_evaluations.map((evalItem: AnswerEvaluation) => {
              const isExpanded = expandedTurns.has(evalItem.turn_number);

              return (
                <div
                  key={evalItem.turn_number}
                  className="rounded-xl border border-slate-800/90 bg-[#0d121f]/90 overflow-hidden shadow-sm"
                >
                  <button
                    type="button"
                    onClick={() => toggleTurn(evalItem.turn_number)}
                    className="flex w-full items-center justify-between bg-slate-900/40 px-5 py-4 text-left hover:bg-slate-900/70 transition"
                  >
                    <div className="flex items-center gap-3">
                      <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600/30 border border-indigo-500/40 text-xs font-bold text-indigo-300">
                        {evalItem.turn_number}
                      </span>
                      <span className="font-semibold text-white text-sm">
                        Question {evalItem.turn_number}
                      </span>
                      <span className="text-slate-600">·</span>
                      <span className="text-xs text-slate-300">
                        Score: <strong className="text-white font-bold">{evalItem.overall_score.toFixed(1)}/10</strong>
                      </span>
                      {evalItem.skill_level_inferred && (
                        <span className="hidden rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-300 capitalize sm:inline-block">
                          {evalItem.skill_level_inferred}
                        </span>
                      )}
                    </div>
                    <span className="text-xs font-semibold text-indigo-400">
                      {isExpanded ? "Collapse ▲" : "Inspect ▼"}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="space-y-4 p-5 text-xs border-t border-slate-800/80">
                      {/* Feedback */}
                      <div>
                        <h4 className="font-bold text-slate-400 uppercase tracking-wider text-[10px]">
                          Examiner Qualitative Critique
                        </h4>
                        <p className="mt-1 text-slate-300 leading-relaxed text-xs">
                          {evalItem.summary_feedback}
                        </p>
                      </div>

                      {/* Dimension Scores */}
                      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5 pt-1">
                        {evalItem.dimension_scores.map((ds) => (
                          <div
                            key={ds.dimension}
                            className="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-center"
                          >
                            <span className="text-[10px] text-slate-400 capitalize block">
                              {ds.dimension}
                            </span>
                            <span className="text-sm font-bold text-white">
                              {ds.score.toFixed(1)}
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Strengths & Improvements */}
                      <div className="grid gap-3 sm:grid-cols-2 pt-1">
                        {evalItem.strengths.length > 0 && (
                          <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/20 p-3 text-emerald-300">
                            <span className="font-bold block mb-1">What went well:</span>
                            <ul className="list-disc pl-4 space-y-1 text-slate-300">
                              {evalItem.strengths.map((s, i) => (
                                <li key={i}>{s}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {evalItem.improvements.length > 0 && (
                          <div className="rounded-lg border border-amber-500/20 bg-amber-950/20 p-3 text-amber-300">
                            <span className="font-bold block mb-1">Target suggestions:</span>
                            <ul className="list-disc pl-4 space-y-1 text-slate-300">
                              {evalItem.improvements.map((imp, i) => (
                                <li key={i}>{imp}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      {/* Exemplar Model Answer */}
                      {evalItem.model_answer_snippet && (
                        <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4">
                          <div className="flex items-center gap-1.5 text-indigo-300 font-bold text-[11px] mb-1">
                            <Lightbulb className="h-3.5 w-3.5" />
                            <span>Gold-Standard Exemplar Response:</span>
                          </div>
                          <p className="text-xs text-indigo-200/90 leading-relaxed italic">
                            "{evalItem.model_answer_snippet}"
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* ---------------- 5. Study Plan Checklist ---------------- */}
        <section className="rounded-2xl border border-slate-800 bg-[#101726]/70 p-6 backdrop-blur-xl shadow-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-indigo-400" />
              <div>
                <h2 className="text-base font-bold text-white">
                  Actionable Preparation Roadmap
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Follow this checklist to fill identified gaps before live company interviews.
                </p>
              </div>
            </div>
            <span className="text-xs font-semibold text-indigo-300 font-mono">
              {completedStudyItems.size} of {report.study_plan.length} completed
            </span>
          </div>

          <ul className="mt-6 space-y-2.5">
            {report.study_plan.map((item, idx) => {
              const isChecked = completedStudyItems.has(idx);

              return (
                <li
                  key={idx}
                  onClick={() => toggleStudyItem(idx)}
                  className={`flex cursor-pointer select-none items-start gap-3 rounded-xl border p-3.5 transition-all ${
                    isChecked
                      ? "border-emerald-500/30 bg-emerald-950/20 text-slate-400"
                      : "border-slate-800 bg-[#0d121f]/90 hover:border-slate-700 text-slate-200"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}}
                    className="mt-0.5 h-4 w-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-0 cursor-pointer"
                  />
                  <span
                    className={`text-xs leading-relaxed ${
                      isChecked ? "line-through text-slate-500" : ""
                    }`}
                  >
                    {item}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Bottom Practice Again Action */}
        <div className="flex justify-center pt-4">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 px-8 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 hover:from-indigo-500 hover:to-purple-500 transition"
          >
            Practice Another Interview →
          </button>
        </div>
      </main>
    </div>
  );
}

