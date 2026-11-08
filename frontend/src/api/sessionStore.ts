import type { InterviewSession, SkillGapReport, StartSessionResponse } from "./types";

export interface SessionData {
  session?: InterviewSession;
  skill_gap_report: SkillGapReport;
  websocket_path?: string;
  /** Raw resume text — needed by /session/bootstrap */
  resume_text?: string;
  /** Raw job description text — needed by /session/bootstrap */
  job_description_text?: string;
}

const key = (id: string) => `hiremind:session:${id}`;

export function saveSessionData(data: StartSessionResponse | SessionData): void {
  try {
    const reportId = data.skill_gap_report.report_id;
    sessionStorage.setItem(key(reportId), JSON.stringify(data));

    if ("session" in data && data.session?.session_id) {
      sessionStorage.setItem(key(data.session.session_id), JSON.stringify(data));
    }

    // Also index by session_id string if present as a plain field
    const anyData = data as any;
    if (anyData.session_id && typeof anyData.session_id === "string") {
      sessionStorage.setItem(key(anyData.session_id), JSON.stringify(data));
    }
  } catch {
    // Storage unavailable or full
  }
}

export function loadSessionData(id: string): SessionData | null {
  try {
    const raw = sessionStorage.getItem(key(id));
    if (!raw) return null;
    return JSON.parse(raw) as SessionData;
  } catch {
    return null;
  }
}
