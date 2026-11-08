/**
 * TypeScript mirror of app/core/schemas.py.
 *
 * Conventions:
 *  - datetime  -> ISO 8601 string
 *  - Optional[X] = None -> X | null (FastAPI serialises None as null)
 *  - str Enums -> string-literal unions
 *  - dict -> Record<string, unknown>
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type ProficiencyLevel =
  | "expert"
  | "proficient"
  | "competent"
  | "novice"
  | "absent";

export type QuestionType =
  | "technical"
  | "behavioral"
  | "situational"
  | "follow_up"
  | "clarifying";

export type Difficulty = "easy" | "medium" | "hard";

export type TurnStatus =
  | "pending"
  | "answered"
  | "evaluated"
  | "follow_up"
  | "skipped";

export type ScoreDimension =
  | "accuracy"
  | "depth"
  | "clarity"
  | "relevance"
  | "confidence";

export type SessionStatus =
  | "created"
  | "in_progress"
  | "paused"
  | "completed"
  | "abandoned";

/** Backend types this as `str`; these are the documented values. */
export type RoutingHint =
  | "next_question"
  | "follow_up"
  | "drill_deeper"
  | "skip_to_harder";

// ---------------------------------------------------------------------------
// Module 1: intake & parsing
// ---------------------------------------------------------------------------

export interface ResumeSkill {
  skill_name: string;
  category: string;
  proficiency: ProficiencyLevel;
  evidence: string | null;
}

export interface ResumeProfile {
  name: string | null;
  summary: string | null;
  skills: ResumeSkill[];
  experience: string[];
  projects: string[];
  education: string[];
}

export interface ParseResumeResponse {
  resume_text: string;
  profile: ResumeProfile;
}

export interface JDRequirement {
  skill_name: string;
  category: string;
  required_level: ProficiencyLevel;
  priority: number;
  evidence: string;
}

export interface ParsedJobDescription {
  title: string | null;
  company: string | null;
  requirements: JDRequirement[];
  responsibilities: string[];
  raw_text: string;
}

export interface ParseJdRequest {
  raw_text: string;
}

export interface SkillGapRequest {
  candidate_id: string;
  job_id: string;
  resume_text: string;
  parsed_jd: ParsedJobDescription;
  candidate_name?: string | null;
  candidate_email?: string | null;
}

// ---------------------------------------------------------------------------
// Module 1 -> 2: skill gap
// ---------------------------------------------------------------------------

export interface SkillGap {
  skill_name: string;
  category: string;
  jd_required_level: ProficiencyLevel;
  resume_claimed_level: ProficiencyLevel;
  gap_level: ProficiencyLevel;
  /** 1 = minor, 5 = critical */
  gap_severity: number;
  jd_evidence: string;
  resume_evidence: string | null;
  suggested_focus: string;
}

export interface SkillGapReport {
  report_id: string;
  candidate_id: string;
  job_id: string;
  generated_at: string;
  /** 0.0 - 1.0 */
  overall_match_score: number;
  /** Ordered by gap_severity desc, max 10 */
  top_gaps: SkillGap[];
  strengths: SkillGap[];
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Questions
// ---------------------------------------------------------------------------

export interface Question {
  question_id: string;
  question_text: string;
  question_type: QuestionType;
  target_skill: string;
  target_skill_gap_id: string | null;
  difficulty: Difficulty;
  expected_bullet_points: string[];
  /** Recommended answer time limit; backend default is 180 */
  max_duration_seconds: number;
  source_chunks: string[];
}

export interface QuestionSet {
  set_id: string;
  session_id: string;
  questions: Question[];
  created_at: string;
}

// ---------------------------------------------------------------------------
// Module 3: evaluation
// ---------------------------------------------------------------------------

export interface DimensionScore {
  dimension: ScoreDimension;
  /** 0.0 - 10.0 */
  score: number;
  rationale: string;
}

export interface AnswerEvaluation {
  evaluation_id: string;
  session_id: string;
  turn_number: number;
  candidate_id: string;
  evaluated_at: string;

  dimension_scores: DimensionScore[];
  /** 0.0 - 10.0 */
  overall_score: number;
  /** 0.0 - 10.0 */
  weighted_score: number;

  summary_feedback: string;
  strengths: string[];
  improvements: string[];
  model_answer_snippet: string | null;

  routing_hint: RoutingHint;
  suggested_follow_up: string | null;
  skill_level_inferred: ProficiencyLevel | null;

  evaluator_version: string;
  latency_ms: number;
}

// ---------------------------------------------------------------------------
// Module 2: interview session
// ---------------------------------------------------------------------------

export interface InterviewTurn {
  turn_number: number;
  question: Question;
  answer_text: string | null;
  answer_audio_url: string | null;
  answer_started_at: string | null;
  answer_submitted_at: string | null;
  status: TurnStatus;
  evaluation: AnswerEvaluation | null;
  /** Nested follow-ups (tree, usually depth <= 2) */
  follow_up_turns: InterviewTurn[];
}

export interface InterviewSession {
  session_id: string;
  candidate_id: string;
  job_id: string;
  skill_gap_report_id: string;
  status: SessionStatus;
  current_turn_number: number;
  turns: InterviewTurn[];
  question_set: QuestionSet;
  session_started_at: string;
  session_ended_at: string | null;
  /** Backend default: { max_turns: 12, allow_follow_ups: true } */
  config: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Final report
// ---------------------------------------------------------------------------

export interface SkillProgression {
  skill_name: string;
  initial_gap: ProficiencyLevel;
  final_inferred_level: ProficiencyLevel;
  progression_delta: number;
  evidence_turns: number[];
}

export interface FinalReport {
  report_id: string;
  session_id: string;
  candidate_id: string;
  job_id: string;
  generated_at: string;

  /** 0.0 - 10.0 */
  overall_score: number;
  /** 0.0 - 100.0 */
  percentile_estimate: number | null;
  /** e.g. 'ready', 'needs_work', 'not_ready' */
  readiness_level: string;

  dimension_averages: Record<ScoreDimension, number>;
  skill_progressions: SkillProgression[];
  per_turn_evaluations: AnswerEvaluation[];

  executive_summary: string;
  top_strengths: string[];
  priority_gaps: string[];
  study_plan: string[];

  total_session_duration_seconds: number;
  total_turns: number;
  report_version: string;
}

export interface GenerateReportRequest {
  session_id: string;
  candidate_id: string;
  job_id: string;
  turns: InterviewTurn[];
  skill_gap_report: SkillGapReport;
  total_session_duration_seconds: number;
}

// ---------------------------------------------------------------------------
// REST: POST /session/start
// ---------------------------------------------------------------------------

export interface StartSessionResponse {
  session: InterviewSession;
  skill_gap_report: SkillGapReport;
  /** e.g. "/ws/interview/{session_id}" */
  websocket_path: string;
}

/** FastAPI HTTPException body */
export interface ApiErrorBody {
  detail: string | Array<{ loc?: Array<string | number>; msg: string }>;
}

// ---------------------------------------------------------------------------
// WebSocket: /ws/interview/{session_id}
// (shapes taken from app/agents/interview/websocket.py)
// ---------------------------------------------------------------------------

/** Client -> server */
export interface AnswerMessage {
  type: "answer";
  answer_text: string;
}

export interface AudioAnswerMessage {
  type: "audio" | "audio_answer";
  audio_base64: string;
  format?: string;
  mime_type?: string;
}

export type ClientMessage = AnswerMessage | AudioAnswerMessage;

/** Server -> client */
export interface ConnectedMessage {
  type: "connected";
  session_id: string;
  status: SessionStatus;
}

export interface QuestionMessage {
  type: "question";
  turn_number: number;
  question: Question;
}

export interface TranscriptMessage {
  type: "transcript";
  turn_number: number;
  text: string;
}

export interface EvaluationMessage {
  type: "evaluation";
  turn_number: number;
  evaluation: AnswerEvaluation | null;
}

export interface CompletedMessage {
  type: "completed";
  session_id: string;
  status: SessionStatus;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage =
  | ConnectedMessage
  | QuestionMessage
  | TranscriptMessage
  | EvaluationMessage
  | CompletedMessage
  | ErrorMessage;
