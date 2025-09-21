from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List

# Minimal DSPy/GEPA setup
import dspy
from dspy.teleprompt.gepa import GEPA
from flask import Flask, jsonify, request

app = Flask(__name__)

# Ensure library logs (dspy, tqdm-routed) are emitted at INFO
# so our handler can capture
logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("dspy").setLevel(logging.INFO)
logging.getLogger("dspy.teleprompt").setLevel(logging.INFO)
logging.getLogger("dspy.teleprompt.gepa").setLevel(logging.INFO)

# Configure DSPy once at import time
# to avoid per-request reconfiguration errors
API_KEY = os.getenv("AI_GATEWAY_API_KEY") or os.getenv("AI_GATEWAY_API_KEY")
MAIN_MODEL = os.getenv("GEPA_MODEL", "openai/gpt-4.1-mini")
REFLECTION_MODEL = os.getenv("GEPA_REFLECTION_MODEL", "openai/gpt-4.1")

dspy.configure(lm=dspy.LM(
    model=MAIN_MODEL,
    api_key=API_KEY,
    base_url="https://ai-gateway.vercel.sh/v1"))


dspy.configure_cache(
    enable_disk_cache=False,
    enable_memory_cache=False,
)

# Build reflection LM once
REFLECTION_LM = (
    dspy.LM(
        model=REFLECTION_MODEL,
        api_key=API_KEY,
        base_url="https://ai-gateway.vercel.sh/v1",
    )
)


def build_signature() -> dspy.Signature:
    class NextTurn(dspy.Signature):
        """Given the conversation so far, produce the next assistant message.

        Optimize for clear, helpful continuation that improves the chat
        trajectory. Learn from ideal examples; mirror their structure, tone,
        and tool usage.
        """
        conversationContext = dspy.InputField(
            desc="Conversation so far (user and assistant turns)",
            prefix="Conversation so far:"
        )
        expectedTurnResponse = dspy.OutputField(
            desc=(
                "Next assistant message that advances the dialogue "
                "(with any tool usage)"
            ),
            prefix="Next assistant message:"
        )

    return NextTurn


def build_program() -> dspy.Module:
    # Simple Predict module over the signature
    return dspy.Predict(build_signature())


class ScoreFeedback(dict):
    # Dict-like with attribute access for compatibility with GEPA's logs
    def __getattr__(self, name: str) -> Any:  # fb.score
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


def build_metric():
    # GEPA metric must accept (gold, pred, trace, pred_name, pred_trace)
    # Return a float score in [0,1] or a dict {score, feedback}
    def metric(
        gold: dspy.Example,
        pred: dspy.Prediction,
        trace: Any | None = None,
        pred_name: str | None = None,
        pred_trace: Any | None = None,
    ) -> Any:
        gold_text = getattr(gold, "expectedTurnResponse", "") or ""
        pred_text = getattr(pred, "expectedTurnResponse", "") or ""
        # crude token overlap
        g = set(gold_text.lower().split()) if gold_text else set()
        p = set(pred_text.lower().split()) if pred_text else set()
        overlap = len(g & p) if g else 0
        score = (overlap / len(g)) if g else 0.0
        # For general evaluation calls, always return a float
        # (even on missing text)
        if pred_name is None and pred_trace is None:
            return float(score)
        # For reflection calls, return rich feedback
        feedback = (
            f"Overlap tokens: {overlap}/{len(g) if g else 0} "
            f"for {pred_name or 'program'}."
        )
        return ScoreFeedback(
            score=float(score),
            feedback=feedback,
        )

    return metric


def _extract_instruction_text(compiled: Any) -> str | None:
    """Best-effort extraction of the optimized instruction/prompt.

    Tries common locations on the compiled module and, if present,
    on the best candidate from detailed_results.
    """
    def _first_text(*candidates: Any) -> str | None:
        for c in candidates:
            if isinstance(c, str) and c.strip():
                return c.strip()
        return None

    # Direct locations
    instr = _first_text(
        getattr(compiled, "instruction", None),
        getattr(compiled, "instructions", None),
    )
    if instr:
        return instr

    # Common child holders
    for child_name in ("predict", "predictor"):
        child = getattr(compiled, child_name, None)
        if child is None:
            continue
        instr = _first_text(
            getattr(child, "instruction", None),
            getattr(child, "instructions", None),
        )
        if instr:
            return instr
        sig = getattr(child, "signature", None)
        instr = _first_text(
            getattr(sig, "instructions", None),
            getattr(sig, "docstring", None),
        )
        if instr:
            return instr

    # Signature on the compiled
    sig = getattr(compiled, "signature", None)
    instr = _first_text(
        getattr(sig, "instructions", None),
        getattr(sig, "docstring", None),
    )
    if instr:
        return instr

    # Fallback to detailed results best candidate
    results = getattr(compiled, "detailed_results", None)
    best = getattr(results, "best_candidate", None)
    if best is not None:
        instr = _first_text(
            getattr(best, "instruction", None),
            getattr(best, "instructions", None),
        )
        if instr:
            return instr
        sig = getattr(best, "signature", None)
        instr = _first_text(
            getattr(sig, "instructions", None),
            getattr(sig, "docstring", None),
        )
        if instr:
            return instr

    return None


@app.get("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.post("/optimize")
def optimize() -> Any:
    payload = request.get_json(force=True) or {}
    examples_input: List[Dict[str, Any]] = payload.get(
        "examples", []
    )
    max_metric_calls: int = int(
        payload.get("maxMetricCalls", 5)
    )
    auto_mode = payload.get("auto")  # off|light|medium|heavy
    candidate_selection = payload.get("candidateSelectionStrategy")
    reflection_minibatch_size = payload.get("reflectionMinibatchSize")
    use_merge = payload.get("useMerge")
    num_threads = payload.get("numThreads")

    # Optional runtime overrides for models and cache
    main_model = payload.get("mainModel")
    reflection_model = payload.get("reflectionModel")
    enable_disk_cache = payload.get("enableDiskCache")
    enable_memory_cache = payload.get("enableMemoryCache")

    # Streaming trace configuration
    run_id = payload.get("runId")
    trace_dir = payload.get("traceDir")
    trace_path: Path | None = None
    if isinstance(trace_dir, str) and trace_dir.strip():
        try:
            trace_path = Path(trace_dir).joinpath("trace.jsonl")
            trace_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            trace_path = None

    # Resolve per-request LMs without reconfiguring global settings
    local_lm = None
    if isinstance(main_model, str) and main_model.strip():
        local_lm = dspy.LM(
            model=main_model.strip(),
            api_key=API_KEY,
            base_url="https://ai-gateway.vercel.sh/v1",
        )
    local_reflection_lm = REFLECTION_LM
    if isinstance(reflection_model, str) and reflection_model.strip():
        local_reflection_lm = dspy.LM(
            model=reflection_model.strip(),
            api_key=API_KEY,
            base_url="https://ai-gateway.vercel.sh/v1",
        )
    if (enable_disk_cache is not None) or (enable_memory_cache is not None):
        dspy.configure_cache(
            enable_disk_cache=(
                bool(enable_disk_cache)
                if enable_disk_cache is not None
                else False
            ),
            enable_memory_cache=(
                bool(enable_memory_cache)
                if enable_memory_cache is not None
                else False
            ),
        )

    # LMs are already configured at import-time; avoid reconfiguration here

    trainset: List[dspy.Example] = []
    for ex in examples_input:
        trainset.append(
            dspy.Example(
                conversationContext=ex.get("conversationContext", ""),
                expectedTurnResponse=ex.get("expectedTurnResponse", ""),
            ).with_inputs("conversationContext")
        )

    program = build_program()
    metric = build_metric()

    # Run GEPA
    start = time.time()
    gepa = GEPA(
        metric=metric,
        reflection_lm=local_reflection_lm,
        track_stats=True,
        max_metric_calls=max_metric_calls,
        add_format_failure_as_feedback=True,
        # Map Basic settings if provided
        auto=(
            auto_mode
            if auto_mode in (
                None,
                "light",
                "medium",
                "heavy",
            )
            else None
        ),
        candidate_selection_strategy=(
            candidate_selection
            if candidate_selection in (None, "pareto", "current_best")
            else "pareto"
        ),
        reflection_minibatch_size=(
            int(reflection_minibatch_size)
            if isinstance(reflection_minibatch_size, (int, float, str))
            and str(reflection_minibatch_size) != ""
            else 3
        ),
        use_merge=bool(use_merge) if use_merge is not None else True,
        num_threads=(
            int(num_threads)
            if isinstance(num_threads, (int, float, str))
            and str(num_threads) != ""
            else None
        ),
    )
    # Attach a transient log handler to capture GEPA iteration progress
    handler: logging.Handler | None = None
    attached_loggers: list[logging.Logger] = []
    if trace_path is not None:
        class _TraceHandler(logging.Handler):
            def __init__(self, file_path: Path):
                super().__init__(level=logging.INFO)
                self.file_path = file_path
                self.iteration: int | None = None
                self.best_so_far: float | None = None
                self._re_iter = re.compile(
                    r"Iteration\s+(\d+):.*?score:\s*([0-9eE+\-.]+)"
                )
                self._re_avg = re.compile(
                    r"Average Metric:\s*([0-9eE+\-.]+)"
                )
                self._re_skip = re.compile(
                    r"New subsample score is not better, skipping"
                )
                # Start of prompt block (reflection proposal)
                self._re_prompt_start = re.compile(
                    r"Proposed new text for self:\s*"
                )
                self._collecting_prompt = False
                self._prompt_lines: list[str] = []

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = record.getMessage()
                    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    obj: dict[str, Any] | None = None

                    # Helper to flush any collected prompt block
                    def _flush_prompt_if_any() -> None:
                        if self._collecting_prompt and self._prompt_lines:
                            prompt_text = "\n".join(self._prompt_lines).strip()
                            try:
                                with self.file_path.open(
                                    "a", encoding="utf-8"
                                ) as f:
                                    f.write(
                                        json.dumps(
                                            {
                                                "type": "prompt",
                                                "timestamp": now,
                                                "iteration": self.iteration,
                                                "prompt": prompt_text,
                                            }
                                        )
                                        + "\n"
                                    )
                            except Exception:
                                pass
                        self._collecting_prompt = False
                        self._prompt_lines = []

                    m_iter = self._re_iter.search(msg)
                    if m_iter:
                        self.iteration = int(m_iter.group(1))
                        selected = float(m_iter.group(2))
                        cond = (
                            self.best_so_far is None
                            or selected > self.best_so_far
                        )
                        if cond:
                            self.best_so_far = selected
                        _flush_prompt_if_any()
                        obj = {
                            "type": "iteration",
                            "timestamp": now,
                            "iteration": self.iteration,
                            "selectedProgramScore": selected,
                            "bestSoFar": self.best_so_far,
                        }
                    else:
                        m_avg = self._re_avg.search(msg)
                        if m_avg:
                            avg = float(m_avg.group(1))
                            _flush_prompt_if_any()
                            obj = {
                                "type": "metric",
                                "timestamp": now,
                                "iteration": self.iteration,
                                "averageMetric": avg,
                                "bestSoFar": self.best_so_far,
                            }
                        elif self._re_skip.search(msg):
                            _flush_prompt_if_any()
                            obj = {
                                "type": "note",
                                "timestamp": now,
                                "iteration": self.iteration,
                                "note": (
                                    "New subsample score is not better, "
                                    "skipping"
                                ),
                                "bestSoFar": self.best_so_far,
                            }
                        else:
                            # Prompt capture handling
                            m_prompt = self._re_prompt_start.search(msg)
                            if m_prompt:
                                after = msg[m_prompt.end():].strip()
                                self._collecting_prompt = True
                                self._prompt_lines = []
                                if after:
                                    self._prompt_lines.append(after)
                            elif self._collecting_prompt:
                                self._prompt_lines.append(msg)
                    if obj is not None:
                        with self.file_path.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(obj) + "\n")
                except Exception:
                    # Never raise from logging
                    pass

        handler = _TraceHandler(trace_path)
        # Attach to relevant loggers explicitly because some libraries
        # disable propagation
        logger_names = [
            "",  # root
            "dspy",
            "dspy.teleprompt",
            "dspy.teleprompt.gepa",
            "dspy.teleprompt.gepa.gepa",
            "dspy.evaluate",
            "dspy.evaluate.evaluate",
        ]
        for name in logger_names:
            try:
                lg = logging.getLogger(name)
                lg.setLevel(logging.INFO)
                # Ensure records bubble up unless the library overrides it
                try:
                    lg.propagate = True  # type: ignore[attr-defined]
                except Exception:
                    pass
                lg.addHandler(handler)
                attached_loggers.append(lg)
            except Exception:
                # Best-effort attach; never fail
                pass

    try:
        if local_lm is not None:
            with dspy.settings.context(lm=local_lm):
                compiled = gepa.compile(
                    program,
                    trainset=trainset,
                    valset=trainset,
                )
        else:
            compiled = gepa.compile(
                program,
                trainset=trainset,
                valset=trainset,
            )
    finally:
        if handler is not None:
            # Remove from all attached loggers
            for lg in attached_loggers:
                try:
                    lg.removeHandler(handler)
                except Exception:
                    pass

    # Extract results
    best_prog = getattr(compiled, "detailed_results", None)
    best_score = None
    if best_prog is not None:
        scores = getattr(best_prog, "val_aggregate_scores", None)
        idx = getattr(best_prog, "best_idx", None)
        if isinstance(scores, list) and isinstance(idx, int):
            try:
                best_score = float(scores[idx])
            except Exception:
                best_score = None

    instruction = _extract_instruction_text(compiled)
    demos: List[Any] = []
    optimized_program: Dict[str, Any] = {
        "bestScore": best_score if best_score is not None else 0,
        "instruction": instruction,
        "demos": demos,
        "examples": examples_input,
        "optimizerType": "GEPA",
        "optimizationTime": int((time.time() - start) * 1000),
        "totalRounds": None,
        "converged": None,
        "stats": getattr(best_prog, "val_aggregate_scores", None),
    }

    result: Dict[str, Any] = {
        "bestScore": optimized_program["bestScore"],
        "optimizedProgram": optimized_program,
        "stats": optimized_program.get("stats"),
    }

    # Best-effort write a final event for clients tailing the trace
    if trace_path is not None:
        try:
            final_event = {
                "type": "final",
                "runId": run_id,
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
                "bestSoFar": optimized_program["bestScore"],
            }
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(final_event) + "\n")
        except Exception:
            pass
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
