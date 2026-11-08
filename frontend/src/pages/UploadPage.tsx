import { useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  analyzeSkillGap,
  parseJd,
  parseResume,
} from "../api/client";
import { saveSessionData } from "../api/sessionStore";
import { Header } from "../components/Header";
import {
  FileText,
  Briefcase,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Cpu,
  BrainCircuit,
  Workflow
} from "lucide-react";

const ACCEPTED_FILE = /\.(pdf|docx)$/i;

type LoadingStep =
  | "idle"
  | "parsing_resume"
  | "parsing_jd"
  | "analyzing_gaps";

const STEP_LABELS: Record<LoadingStep, { title: string; desc: string; stepNum: number }> = {
  idle: { title: "", desc: "", stepNum: 0 },
  parsing_resume: {
    title: "Intake Agent: Parsing Resume",
    desc: "Extracting work history, technical proficiencies, and candidate competencies...",
    stepNum: 1,
  },
  parsing_jd: {
    title: "Analysis Agent: Structuring Job Description",
    desc: "Identifying key role deliverables, required proficiencies, and must-have credentials...",
    stepNum: 2,
  },
  analyzing_gaps: {
    title: "Evaluator Agent: Computing Skill Gaps",
    desc: "Synthesizing cross-entropy match matrix and tailoring targeted interview questions...",
    stepNum: 3,
  },
};

function toMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof TypeError) {
    return "Couldn't reach the server. Check that the backend is running, that VITE_API_URL is correct, and that CORS allows this origin.";
  }
  return "Something went wrong. Please try again.";
}

export default function UploadPage() {
  const navigate = useNavigate();
  const [resume, setResume] = useState<File | null>(null);
  const [jobDescription, setJobDescription] = useState("");
  const [step, setStep] = useState<LoadingStep>("idle");
  const [error, setError] = useState<string | null>(null);

  const loading = step !== "idle";
  const canSubmit =
    resume !== null && jobDescription.trim().length > 0 && !loading;

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;

    if (file && !ACCEPTED_FILE.test(file.name)) {
      e.target.value = "";
      setResume(null);
      setError("Only PDF and DOCX resumes are supported.");
      return;
    }

    setError(null);
    setResume(file);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!resume || !canSubmit) return;

    setError(null);

    try {
      // 1. Parse resume
      setStep("parsing_resume");
      const { resume_text, profile } = await parseResume(resume);

      // 2. Parse job description
      setStep("parsing_jd");
      const parsed_jd = await parseJd(jobDescription.trim());

      // 3. Analyze skill gap
      setStep("analyzing_gaps");
      const candidateId = crypto.randomUUID();
      const jobId = crypto.randomUUID();

      const report = await analyzeSkillGap({
        candidate_id: candidateId,
        job_id: jobId,
        resume_text,
        parsed_jd,
        candidate_name: profile.name ?? undefined,
      });

      saveSessionData({
        skill_gap_report: report,
        resume_text,
        job_description_text: jobDescription.trim(),
      });

      navigate(`/session/${report.report_id}/skill-gap`);
    } catch (err) {
      setError(toMessage(err));
      setStep("idle");
    }
  }

  return (
    <div className="min-h-screen bg-[#0b0f17] text-slate-100 flex flex-col">
      <Header />

      <main className="flex-1 mx-auto w-full max-w-5xl px-6 py-10">
        {/* Hero Section */}
        <div className="mb-10 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3.5 py-1 text-xs font-semibold text-indigo-300 mb-4 backdrop-blur-md">
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            Next-Gen Multi-Agent Evaluation System
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-white">
            Transform Your Job Prep With <br />
            <span className="bg-gradient-to-r from-indigo-400 via-purple-300 to-pink-400 bg-clip-text text-transparent">
              Autonomous AI Interview Agents
            </span>
          </h1>
          <p className="mt-3.5 max-w-2xl mx-auto text-sm sm:text-base text-slate-400 leading-relaxed">
            Upload your resume and paste your target job description. Our multi-agent system extracts competencies, pinpoints exact skill gaps, and runs an adaptive audio-enabled technical interview.
          </p>
        </div>

        {/* Feature Badges */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
          <div className="flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Resume & JD Gap Matrix</p>
              <p className="text-[11px] text-slate-400">Deep NLP skill alignment</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Cpu className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Dynamic Adaptive Questioning</p>
              <p className="text-[11px] text-slate-400">5 tailored technical questions</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-pink-500/10 border border-pink-500/20 text-pink-400">
              <Workflow className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Exemplar Diagnosis</p>
              <p className="text-[11px] text-slate-400">Actionable study roadmaps</p>
            </div>
          </div>
        </div>

        {/* Form Container */}
        <form onSubmit={handleSubmit} className="relative rounded-2xl border border-slate-800/90 bg-[#101726]/70 p-6 sm:p-8 backdrop-blur-xl shadow-2xl shadow-black/40 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Resume Upload Area */}
            <div className="space-y-2">
              <label htmlFor="resume" className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <FileText className="h-4 w-4 text-indigo-400" />
                Upload Resume
                <span className="text-[10px] text-slate-400 font-normal">(PDF or DOCX)</span>
              </label>

              <div className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-all duration-200 ${
                resume
                  ? "border-emerald-500/50 bg-emerald-950/10"
                  : "border-slate-700/80 hover:border-indigo-500/50 bg-slate-900/40 hover:bg-slate-900/60"
              }`}>
                <input
                  id="resume"
                  type="file"
                  accept=".pdf,.docx"
                  disabled={loading}
                  onChange={handleFileChange}
                  className="absolute inset-0 h-full w-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
                />
                
                {resume ? (
                  <div className="flex flex-col items-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 mb-2">
                      <CheckCircle2 className="h-6 w-6" />
                    </div>
                    <p className="text-sm font-semibold text-emerald-300 max-w-[200px] truncate">{resume.name}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{(resume.size / 1024).toFixed(1)} KB · Click to replace</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-500/10 text-indigo-400 mb-2">
                      <FileText className="h-6 w-6" />
                    </div>
                    <p className="text-sm font-medium text-slate-200">Choose file or drag & drop</p>
                    <p className="text-xs text-slate-400 mt-1">PDF or DOCX up to 10MB</p>
                  </div>
                )}
              </div>
            </div>

            {/* Job Description Area */}
            <div className="space-y-2">
              <label htmlFor="jd" className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Briefcase className="h-4 w-4 text-indigo-400" />
                Target Job Description
              </label>
              <textarea
                id="jd"
                rows={7}
                value={jobDescription}
                disabled={loading}
                onChange={(e) => setJobDescription(e.target.value)}
                placeholder="Paste the role title, responsibilities, technical stacks, and qualifications here..."
                className="w-full resize-none rounded-xl border border-slate-700/80 bg-slate-900/50 p-3.5 text-xs sm:text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50 transition"
              />
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div
              role="alert"
              className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-950/30 p-3.5 text-sm text-red-300"
            >
              <AlertCircle className="h-5 w-5 shrink-0 text-red-400" />
              <span>{error}</span>
            </div>
          )}

          {/* Action Button & Multi-Agent Progress Bar */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={!canSubmit}
              className="w-full relative flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 px-6 py-3.5 text-base font-semibold text-white shadow-lg shadow-indigo-600/30 hover:shadow-indigo-600/40 hover:from-indigo-500 hover:to-purple-500 disabled:cursor-not-allowed disabled:opacity-40 transition-all duration-300"
            >
              {loading ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Multi-Agent Pipeline Running...</span>
                </>
              ) : (
                <>
                  <span>Analyze Alignment & Build Interview</span>
                  <ArrowRight className="h-5 w-5" />
                </>
              )}
            </button>

            {loading && (
              <div className="mt-4 rounded-xl border border-indigo-500/30 bg-indigo-950/30 p-4 backdrop-blur-md">
                <div className="flex items-center justify-between text-xs text-indigo-300 mb-2">
                  <span className="font-semibold">{STEP_LABELS[step].title}</span>
                  <span className="rounded-full bg-indigo-500/20 px-2.5 py-0.5 text-[11px] font-mono">
                    Step {STEP_LABELS[step].stepNum} of 3
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
                    style={{ width: `${(STEP_LABELS[step].stepNum / 3) * 100}%` }}
                  />
                </div>
                <p className="mt-2.5 text-xs text-slate-400 leading-relaxed">
                  {STEP_LABELS[step].desc}
                </p>
              </div>
            )}
          </div>
        </form>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-400">
        HireMind AI · Multi-Agent Cognitive Interview & Performance Benchmark Suite
      </footer>
    </div>
  );
}

