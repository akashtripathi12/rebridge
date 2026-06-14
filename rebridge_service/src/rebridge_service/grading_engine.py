"""The Grading_Engine: the model cascade with timeout and strict-JSON retry.

The :class:`GradingEngine` wraps the ``Model_Cascade`` (Requirement 8). It is
constructed with an *ordered* list of :class:`~rebridge_data.interfaces.GradingProvider`
implementations (Bedrock Nova Lite first, Claude vision second, per design.md)
and drives them as follows:

* Invoke the providers **in order**, beginning with the first (Nova Lite)
  (Requirements 8.1, Property 13).
* Enforce a **per-call timeout** on each provider invocation. A timeout is
  treated exactly like any other provider error: fall through to the next
  provider in the cascade (Requirement 8.2).
* Parse each returned response with the strict schema parser
  (:func:`~rebridge_service.grade_schema.parse_grade_assessment`). A response
  that does not conform to the grade-assessment schema is retried against the
  **same** provider up to ``max_json_retries`` additional times (default 2,
  i.e. 3 attempts total) before falling through to the next provider
  (Requirements 5.1-5.6).
* Return the **first** schema-conforming :class:`~rebridge_service.models.GradeAssessment`
  produced by any provider (Property 13, Property 15: provider identity does
  not change downstream behavior).
* If every provider in the cascade fails, times out, or never yields conforming
  JSON, raise :class:`TotalCascadeFailure`. The Grading_Pipeline (task 9.1)
  catches this and routes the Item to ``PENDING_REVIEW`` (Requirement 8.3).

The timeout mechanism is **injectable** so the engine is testable without real
wall-clock sleeps: a ``timeout_runner`` callable receives the zero-argument
provider call and the timeout budget and is responsible for raising
:class:`TimeoutError` when the budget is exceeded. The default runner uses a
single worker thread; tests typically inject providers that raise
``TimeoutError`` directly (with ``timeout=None``) to exercise fallthrough
deterministically.

This module imports only the standard library, the service-layer domain models,
the strict schema parser, and the abstract data-layer types. It never imports
boto3.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Callable, Sequence

from rebridge_data.interfaces import GradingProvider
from rebridge_data.models import CatalogContext, RawModelResponse

from rebridge_service.grade_schema import GradeSchemaError, parse_grade_assessment
from rebridge_service.models import GradeAssessment

__all__ = [
    "ProviderCall",
    "TimeoutRunner",
    "GradingEngineError",
    "TotalCascadeFailure",
    "GradingEngine",
    "thread_timeout_runner",
]

# A zero-argument call that invokes a single provider and returns its raw
# response (or raises). The timeout runner wraps one of these.
ProviderCall = Callable[[], RawModelResponse]

# A timeout runner executes a :data:`ProviderCall` under a timeout budget. It
# MUST raise :class:`TimeoutError` if the budget (in seconds) is exceeded; a
# ``None`` budget means "run inline with no timeout". Injecting a runner keeps
# the engine free of real wall-clock dependence in tests.
TimeoutRunner = Callable[[ProviderCall, "float | None"], RawModelResponse]


class GradingEngineError(Exception):
    """Base class for Grading_Engine failures."""


@dataclass
class _Attempt:
    """Diagnostic record of a single failed cascade attempt."""

    provider: str
    reason: str  # "timeout" | "error" | "non_conforming_json"
    detail: str


@dataclass
class TotalCascadeFailure(GradingEngineError):
    """Raised when every provider in the cascade fails (Requirement 8.3).

    Carries the per-attempt diagnostics so the pipeline can log why grading
    fell through to human review.
    """

    attempts: list[_Attempt] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        if not self.attempts:
            return "grading cascade failed: no providers configured"
        summary = "; ".join(
            f"{a.provider}:{a.reason}({a.detail})" for a in self.attempts
        )
        return f"grading cascade exhausted across all providers: {summary}"


def thread_timeout_runner(call: ProviderCall, timeout: float | None) -> RawModelResponse:
    """Default timeout runner backed by a single worker thread.

    Runs ``call`` and raises :class:`TimeoutError` if it does not complete
    within ``timeout`` seconds. A ``None`` timeout runs the call inline with no
    timeout. Note that a timed-out worker thread cannot be force-killed; the
    underlying provider is expected to honor its own client-side deadline, with
    this wrapper providing the cascade-level safety bound.
    """

    if timeout is None:
        return call()
    
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError as exc:  # pragma: no cover - timing dependent
        raise TimeoutError(
            f"provider call exceeded {timeout}s timeout"
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


class GradingEngine:
    """Drives the ordered provider cascade with timeout and JSON-retry policy.

    Args:
        providers: Ordered cascade of grading providers (Nova Lite first).
        timeout: Per-call timeout budget in seconds, or ``None`` for no bound.
        max_json_retries: Additional attempts against the *same* provider when
            its response is non-conforming JSON (default 2 => 3 attempts total).
        timeout_runner: Injectable runner that enforces the per-call timeout;
            defaults to :func:`thread_timeout_runner`.
    """

    def __init__(
        self,
        providers: Sequence[GradingProvider],
        timeout: float | None = None,
        max_json_retries: int = 2,
        timeout_runner: TimeoutRunner | None = None,
    ) -> None:
        if max_json_retries < 0:
            raise ValueError("max_json_retries must be non-negative")
        self._providers: list[GradingProvider] = list(providers)
        self._timeout = timeout
        self._max_json_retries = max_json_retries
        self._run: TimeoutRunner = timeout_runner or thread_timeout_runner

    @property
    def providers(self) -> list[GradingProvider]:
        """The cascade in invocation order (Nova Lite -> Claude vision)."""
        return list(self._providers)

    def grade(
        self, images: list[bytes], catalog: CatalogContext
    ) -> GradeAssessment:
        """Grade a photo set through the cascade.

        Returns the first schema-conforming :class:`GradeAssessment`. Raises
        :class:`TotalCascadeFailure` if no provider yields conforming output
        after timeouts, errors, and the allowed JSON retries are exhausted.
        """

        attempts: list[_Attempt] = []

        for provider in self._providers:
            print(f"[GradingEngine] Trying provider: {provider.name}")
            # Up to (1 + max_json_retries) attempts against this provider, but
            # a timeout or non-schema error short-circuits straight to the next
            # provider (only non-conforming JSON earns a retry).
            for _attempt_index in range(self._max_json_retries + 1):
                try:
                    response = self._run(
                        lambda p=provider: p.grade(images, catalog), self._timeout
                    )
                except TimeoutError as exc:
                    print(f"[GradingEngine] {provider.name} TIMEOUT: {exc}")
                    attempts.append(
                        _Attempt(provider.name, "timeout", str(exc) or "timed out")
                    )
                    break  # fall through to the next provider
                except Exception as exc:  # noqa: BLE001 - any provider error falls through
                    print(f"[GradingEngine] {provider.name} ERROR: {type(exc).__name__}: {exc}")
                    attempts.append(
                        _Attempt(provider.name, "error", f"{type(exc).__name__}: {exc}")
                    )
                    break  # fall through to the next provider

                try:
                    return parse_grade_assessment(response.content)
                except GradeSchemaError as exc:
                    # Non-conforming JSON: retry the same provider until the
                    # retry budget is spent, then fall through.
                    print(f"[GradingEngine] {provider.name} NON-CONFORMING JSON: {exc}")
                    attempts.append(
                        _Attempt(provider.name, "non_conforming_json", str(exc))
                    )
                    continue

        raise TotalCascadeFailure(attempts=attempts)
