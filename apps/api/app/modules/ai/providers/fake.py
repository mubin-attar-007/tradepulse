"""A deterministic in-process provider.

This exists so the AI layer is testable and demonstrable WITHOUT a network call, an
API key, or a model download. Without it, CI can only test the AI layer by mocking
at the call site, which tests the mock; and the "free local path" would require a
multi-gigabyte download before a developer could see the product work at all.

It is not a model and never pretends to be one. It compiles the deterministic
intent extraction (:mod:`app.modules.ai.compiler`) into the same intermediate
representation a real model is asked to produce, so:

* the schema, validation, repair and semantic-check machinery is exercised end to
  end on real data rather than on a canned string;
* CI can assert an exact tool trajectory, because the output is a pure function of
  the input;
* a demo works offline, clearly labelled as the deterministic compiler rather than
  as AI output.

Every response carries ``meta['deterministic'] = True`` so a trace, an evaluation,
or a UI can never present its output as model-generated.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from app.modules.ai.providers.base import (
    Capability,
    ErrorKind,
    LLMResponse,
    ModelProfile,
    ProviderError,
)

FAKE_PROFILE = ModelProfile(
    name="deterministic",
    provider="fake",
    model="deterministic-compiler",
    capabilities=frozenset({Capability.TEXT, Capability.STRUCTURED_OUTPUT}),
    context_tokens=1_000_000,
    local=True,
    description=(
        "A rule-based compiler, not a language model. Produces the same output for "
        "the same input, every time. Used for tests, CI and the offline demo."
    ),
)


class FakeProvider:
    """Deterministic responder.

    ``responder`` maps (system, prompt) -> text. The default delegates to the
    deterministic NL compiler, which is what makes this useful rather than merely
    inert. ``scripted`` overrides it with a fixed sequence, for exercising repair
    loops and error paths.
    """

    name = "fake"
    local = True

    def __init__(
        self,
        *,
        responder: Callable[[str, str], str] | None = None,
        scripted: list[str] | None = None,
        fail_with: ErrorKind | None = None,
    ) -> None:
        self._responder = responder
        self._scripted = list(scripted) if scripted is not None else None
        self._fail_with = fail_with
        self.calls: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str = FAKE_PROFILE.model,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout_seconds: float = 120.0,
    ) -> LLMResponse:
        started = time.perf_counter()
        self.calls.append({"system": system, "prompt": prompt, "json_mode": json_mode})
        if self._fail_with is not None:
            raise ProviderError(self._fail_with, f"simulated {self._fail_with}", provider="fake")

        if self._scripted is not None:
            index = min(len(self.calls) - 1, len(self._scripted) - 1)
            text = self._scripted[index]
        elif self._responder is not None:
            text = self._responder(system, prompt)
        else:
            text = self._default_response(prompt)

        return LLMResponse(
            text=text,
            # Word count is a stand-in for tokenization: the budget path needs a
            # plausible non-zero number, and pretending to a real token count here
            # would put a fabricated figure into the trace.
            tokens_in=len(system.split()) + len(prompt.split()),
            tokens_out=len(text.split()),
            model=model,
            provider="fake",
            latency_ms=(time.perf_counter() - started) * 1000,
            meta={"deterministic": True},
        )

    @staticmethod
    def _default_response(prompt: str) -> str:
        """Compile the request deterministically into the strategy IR.

        Imported lazily to keep this module importable from anywhere in the AI
        package without a cycle (the compiler builds prompts that reference it).
        """
        from app.modules.ai.compiler import extract_intent

        # The user's request is delimited in the prompt; recover it, falling back to
        # the whole prompt so the provider still produces something useful when
        # called with an unusual template.
        request = prompt
        marker = "<user_request>"
        if marker in prompt and "</user_request>" in prompt:
            request = prompt.split(marker, 1)[1].split("</user_request>", 1)[0]
        intent = extract_intent(request)
        return json.dumps(intent.model_dump(mode="json"), separators=(",", ":"))

    async def healthy(self) -> bool:
        return True
