import type {
  ApiErrorBody,
  FinalReport,
  GenerateReportRequest,
  ParseResumeResponse,
  ParsedJobDescription,
  SkillGapRequest,
  SkillGapReport,
  StartSessionResponse,
} from "./types";

const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);
const WS_URL = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000").replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as Partial<ApiErrorBody> | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d) => d.msg).join("; ");
  }
  return fallback;
}

/**
 * Typed fetch wrapper. Pass a FormData body for multipart uploads; any other
 * body is sent as JSON. Throws ApiError on non-2xx responses.
 */
export async function request<T>(
  path: string,
  init: Omit<RequestInit, "body"> & { body?: unknown } = {},
): Promise<T> {
  const { body, headers, ...rest } = init;
  const isForm = body instanceof FormData;

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(body !== undefined && !isForm
        ? { "Content-Type": "application/json" }
        : {}),
      ...headers,
    },
    body:
      body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });

  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      // non-JSON error body
    }
    throw new ApiError(
      res.status,
      errorMessage(parsed, `${res.status} ${res.statusText}`),
    );
  }

  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** POST /parse/resume (multipart) */
export function parseResume(file: File): Promise<ParseResumeResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<ParseResumeResponse>("/parse/resume", {
    method: "POST",
    body: form,
  });
}

/** POST /parse/jd (JSON) */
export function parseJd(rawText: string): Promise<ParsedJobDescription> {
  return request<ParsedJobDescription>("/parse/jd", {
    method: "POST",
    body: { raw_text: rawText },
  });
}

/** POST /analyze/skill-gap (JSON) */
export function analyzeSkillGap(
  payload: SkillGapRequest,
): Promise<SkillGapReport> {
  return request<SkillGapReport>("/analyze/skill-gap", {
    method: "POST",
    body: payload,
  });
}

export interface StartSessionInput {
  resume: File;
  jobDescription: string;
  candidateId?: string;
  jobId?: string;
  candidateName?: string;
  candidateEmail?: string;
}

/** POST /session/start (multipart) */
export function startSession(
  input: StartSessionInput,
): Promise<StartSessionResponse> {
  const form = new FormData();
  form.append("resume", input.resume);
  form.append("job_description", input.jobDescription);
  if (input.candidateId) form.append("candidate_id", input.candidateId);
  if (input.jobId) form.append("job_id", input.jobId);
  if (input.candidateName) form.append("candidate_name", input.candidateName);
  if (input.candidateEmail) form.append("candidate_email", input.candidateEmail);

  return request<StartSessionResponse>("/session/start", {
    method: "POST",
    body: form,
  });
}

/** POST /report/generate (JSON) */
export function generateReport(
  payload: GenerateReportRequest,
): Promise<FinalReport> {
  return request<FinalReport>("/report/generate", {
    method: "POST",
    body: payload,
  });
}

/** POST /session/{session_id}/finalize */
export function finalizeSession(sessionId: string): Promise<FinalReport> {
  return request<FinalReport>(
    `/session/${encodeURIComponent(sessionId)}/finalize`,
    { method: "POST" },
  );
}

export interface BootstrapSessionResponse {
  session_id: string;
  websocket_path: string;
  total_questions: number;
}

/** POST /session/bootstrap — create in-memory session from pre-computed SkillGapReport */
export function bootstrapSession(payload: {
  skill_gap_report: SkillGapReport;
  resume_text: string;
  job_description_text: string;
}): Promise<BootstrapSessionResponse> {
  return request<BootstrapSessionResponse>("/session/bootstrap", {
    method: "POST",
    body: payload,
  });
}

/** Full URL for WS /ws/interview/{session_id} */
export function interviewSocketUrl(sessionId: string): string {
  return `${WS_URL}/ws/interview/${encodeURIComponent(sessionId)}`;
}
