import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { bootstrapSession } from "../api/client";
import { loadSessionData, saveSessionData, type SessionData } from "../api/sessionStore";
import SkillGroup from "../components/SkillGroup";
import { groupSkills } from "../utils/skillGroups";
import { Header } from "../components/Header";
import { ArrowRight, ArrowLeft, Target, Loader2 } from "lucide-react";

export default function SkillGapPage() {
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const data = useMemo(() => loadSessionData(sessionId), [sessionId]);
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  if (!data) {
    return (
      <div className="min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col">
        <Header />
        <main className="flex-1 mx-auto max-w-xl px-6 py-20 text-center">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-8">
            <h1 className="text-xl font-bold text-white">Session Not Found</h1>
            <p className="mt-2 text-sm text-slate-400">
              We couldn't find the skill-gap report for this session in this browser tab.
            </p>
            <Link
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
              to="/"
            >
              <ArrowLeft className="h-4 w-4" /> Back to Upload
            </Link>
          </div>
        </main>
      </div>
    );
  }

  const report = data.skill_gap_report;
  const groups = groupSkills(report);
  const matchPct = Math.round(report.overall_match_score * 100);

  async function handleStartInterview() {
    if (!data) return;
    setIsStarting(true);
    setStartError(null);
    try {
      const { session_id } = await bootstrapSession({
        skill_gap_report: data.skill_gap_report,
        resume_text: data.resume_text ?? "",
        job_description_text: data.job_description_text ?? "",
      });

      const sessionPayload: SessionData = {
        skill_gap_report: data.skill_gap_report,
        resume_text: data.resume_text,
        job_description_text: data.job_description_text,
      };
      saveSessionData(sessionPayload);
      try {
        sessionStorage.setItem(`hiremind:session:${session_id}`, JSON.stringify(sessionPayload));
      } catch { /* ignore */ }
      navigate(`/session/${session_id}/interview`);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to start interview. Please try again.");
      setIsStarting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col pb-28">
      <Header subtitle="Stage 2: Skill Match & Gap Analysis" />

      <main className="flex-1 mx-auto w-full max-w-5xl px-6 py-10 space-y-8">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white transition"
          >
            <ArrowLeft className="h-4 w-4" /> Change Resume / Job Description
          </Link>
          <span className="text-xs text-slate-400 font-mono">
            Report ID: {report.report_id.slice(0, 8)}...
          </span>
        </div>

        {/* Top Alignment Hero Card */}
        <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-[#101726] to-[#0c101c] p-6 sm:p-8 backdrop-blur-xl shadow-2xl shadow-black/50">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div className="space-y-2 max-w-xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-0.5 text-xs font-semibold text-indigo-300">
                <Target className="h-3.5 w-3.5 text-indigo-400" />
                Cognitive Role-Fit Alignment
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
                Skill Match Analysis
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
                Our agent has cross-referenced your background with the target position requirements. Gaps are automatically prioritized to shape your personalized 5-question technical interview.
              </p>
            </div>

            {/* Score Ring Card */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-indigo-500/30 bg-indigo-950/20 px-8 py-6 text-center shadow-inner">
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
                Overall Role Match
              </span>
              <div className="mt-2 text-4xl sm:text-5xl font-black tracking-tight text-white">
                {matchPct}%
              </div>
              <div className="mt-3 h-2 w-32 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 transition-all duration-700"
                  style={{ width: `${matchPct}%` }}
                />
              </div>
              <span className="mt-2 text-[11px] text-slate-400">
                {groups.matched.length} Matched · {groups.partial.length} Partial · {groups.missing.length} Gaps
              </span>
            </div>
          </div>
        </div>

        {/* Skill Category Groups */}
        <div className="space-y-6">
          <SkillGroup
            title="Matched Strengths"
            description="Verified skills where your claimed proficiency meets or exceeds role specifications."
            tone="matched"
            skills={groups.matched}
          />
          <SkillGroup
            title="Partial Proficiencies"
            description="Skills found on your profile that appear at a lower tier than requested. Interview will probe depth."
            tone="partial"
            skills={groups.partial}
          />
          <SkillGroup
            title="Identified Skill Gaps"
            description="Target requirements with no direct evidence on your resume. Priority interview questions target these."
            tone="missing"
            skills={groups.missing}
          />
        </div>
      </main>

      {/* Floating Bottom Launch Bar */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-800/80 bg-[#0b0f17]/90 p-4 backdrop-blur-xl">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-slate-300">
              Ready to begin?
            </p>
            <p className="text-[11px] text-slate-400">
              The AI interviewer will ask 5 targeted questions probing your {groups.partial.length + groups.missing.length} skill gaps.
            </p>
            {startError && (
              <p className="mt-1 text-xs text-red-400 font-semibold">{startError}</p>
            )}
          </div>
          <button
            type="button"
            onClick={handleStartInterview}
            disabled={isStarting}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 hover:shadow-indigo-600/50 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 transition"
          >
            {isStarting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Preparing Interview Agent…</span>
              </>
            ) : (
              <>
                <span>Start AI Interview</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

