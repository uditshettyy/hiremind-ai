class AppError(Exception):
    """Base class for business-logic exceptions across all modules."""


class EvaluationError(AppError):
    """
    Raised by evaluate_answer() when it cannot produce a valid AnswerEvaluation —
    either the LLM output was unparseable/invalid, the answer was too short to
    evaluate meaningfully, or the call exceeded its timeout budget.

    Per ARCHITECTURE.md §5.1: the Interview Agent catches this and may ask the
    candidate to elaborate, retry, or skip evaluation for that turn.
    """

    def __init__(self, message: str, *, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason  # one of: "answer_too_short", "unparseable_output", "timeout"


class ReportGenerationError(AppError):
    """Raised by generate_final_report() when a report cannot be synthesized
    (e.g. no evaluated turns in the session)."""

