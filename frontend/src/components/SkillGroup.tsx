import type { SkillGap } from "../api/types";
import { CheckCircle2, AlertTriangle, XCircle, ChevronDown } from "lucide-react";

export type SkillTone = "matched" | "partial" | "missing";

const TONES: Record<
  SkillTone,
  { section: string; badge: string; iconColor: string; titleColor: string }
> = {
  matched: {
    section: "border-emerald-500/30 bg-emerald-950/20",
    badge: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30",
    iconColor: "text-emerald-400",
    titleColor: "text-emerald-300",
  },
  partial: {
    section: "border-amber-500/30 bg-amber-950/20",
    badge: "bg-amber-500/20 text-amber-300 border border-amber-500/30",
    iconColor: "text-amber-400",
    titleColor: "text-amber-300",
  },
  missing: {
    section: "border-rose-500/30 bg-rose-950/20",
    badge: "bg-rose-500/20 text-rose-300 border border-rose-500/30",
    iconColor: "text-rose-400",
    titleColor: "text-rose-300",
  },
};

interface SkillGroupProps {
  title: string;
  description: string;
  tone: SkillTone;
  skills: SkillGap[];
}

function SkillRow({ skill, tone }: { skill: SkillGap; tone: SkillTone }) {
  const isGap = tone !== "matched";

  return (
    <li className="rounded-xl border border-slate-800/90 bg-[#0d121f]/90 p-4 shadow-sm transition hover:border-slate-700">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="font-semibold text-white text-sm tracking-tight">{skill.skill_name}</span>
          <span className="rounded-md border border-slate-700/60 bg-slate-800/60 px-2 py-0.5 text-[10px] font-medium text-slate-300 uppercase tracking-wider">
            {skill.category}
          </span>
        </div>
        {isGap && (
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-300">
            Severity {skill.gap_severity}/5
          </span>
        )}
      </div>

      <div className="mt-2.5 flex items-center gap-2 text-xs text-slate-400">
        <span className="text-slate-300 font-medium">JD Target:</span>
        <span className="capitalize text-indigo-300">{skill.jd_required_level}</span>
        <span className="text-slate-600">•</span>
        <span className="text-slate-300 font-medium">Resume Evidence:</span>
        <span className="capitalize text-slate-300">{skill.resume_claimed_level}</span>
      </div>

      {isGap && skill.suggested_focus && (
        <p className="mt-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-xs text-slate-300 leading-relaxed">
          <span className="font-semibold text-indigo-400">Interview Focus: </span>
          {skill.suggested_focus}
        </p>
      )}

      <details className="mt-2.5 text-xs text-slate-400 group">
        <summary className="cursor-pointer text-[11px] font-medium text-indigo-400 hover:text-indigo-300 transition flex items-center gap-1 select-none">
          <span>Inspect Grounding Evidence</span>
          <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-2 space-y-1.5 rounded-lg border border-slate-800/80 bg-slate-900/40 p-3 text-[11px]">
          <p>
            <span className="font-semibold text-slate-300">Job Description:</span>{" "}
            <span className="text-slate-400">{skill.jd_evidence}</span>
          </p>
          <p>
            <span className="font-semibold text-slate-300">Resume:</span>{" "}
            <span className="text-slate-400">{skill.resume_evidence ?? "No direct keyword match found."}</span>
          </p>
        </div>
      </details>
    </li>
  );
}

export default function SkillGroup({
  title,
  description,
  tone,
  skills,
}: SkillGroupProps) {
  const Icon = tone === "matched" ? CheckCircle2 : tone === "partial" ? AlertTriangle : XCircle;

  return (
    <section className={`rounded-2xl border p-5 backdrop-blur-md shadow-lg ${TONES[tone].section}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Icon className={`h-5 w-5 ${TONES[tone].iconColor}`} />
          <h2 className={`text-base font-bold tracking-tight ${TONES[tone].titleColor}`}>{title}</h2>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${TONES[tone].badge}`}>
          {skills.length}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-400">{description}</p>

      {skills.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500 italic">No competencies identified in this category.</p>
      ) : (
        <ul className="mt-4 space-y-2.5">
          {skills.map((skill) => (
            <SkillRow key={skill.skill_name} skill={skill} tone={tone} />
          ))}
        </ul>
      )}
    </section>
  );
}

