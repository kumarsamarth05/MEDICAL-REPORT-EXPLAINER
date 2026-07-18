"""
nlp/summarizer.py

Converts structured parameter results into plain-English explanations,
and produces an overall summary of the report.

A template-based approach is used by default (fast, deterministic, no
GPU/model download required). If `transformers` is installed, you can
swap `explain_parameter()` to call a text-generation pipeline for more
natural phrasing — see `generate_with_llm()` below for the optional path.
"""

from utils.normal_ranges import PARAMETERS


def explain_parameter(param: dict) -> str:
    """Build a one-paragraph plain-English explanation for a single parameter."""
    name = param["name"]
    status = param["status"]
    value = param["value"]
    unit = param["unit"]
    info = PARAMETERS[name]
    description = info["description"]

    if status == "Normal":
        return (
            f"Your {name} level is {value} {unit}, which is within the normal "
            f"range ({info['low']}-{info['high']} {unit}). {name} {description}."
        )

    # Abnormal (Low / High / Deficient / etc.)
    direction = "below" if status.lower() in ("low", "deficient") else "above"
    return (
        f"Your {name} level is {value} {unit}, which is {direction} the normal "
        f"range ({info['low']}-{info['high']} {unit}). {name.capitalize()} {description}. "
        f"This result is flagged as '{status}'. Consult a healthcare professional "
        f"for proper evaluation."
    )


def summarize_report(parsed_params: list) -> dict:
    """Produce per-parameter explanations plus an overall summary sentence."""
    explanations = []
    abnormal_count = 0

    for p in parsed_params:
        explanations.append({
            "name": p["name"],
            "status": p["status"],
            "explanation": explain_parameter(p),
        })
        if p["status"] != "Normal":
            abnormal_count += 1

    total = len(parsed_params)
    if total == 0:
        overview = "No recognizable medical parameters were found in this report."
    elif abnormal_count == 0:
        overview = f"All {total} detected parameters are within normal ranges. Great job!"
    else:
        overview = (
            f"{abnormal_count} out of {total} detected parameters are outside the "
            f"normal range and may need attention."
        )

    return {"overview": overview, "explanations": explanations}


def generate_with_llm(prompt: str) -> str:
    """OPTIONAL: swap-in point for a real generative model instead of templates.

    Example usage (requires `pip install transformers torch`):

        from transformers import pipeline
        _generator = pipeline("text-generation", model="gpt2")
        return _generator(prompt, max_new_tokens=80)[0]["generated_text"]

    Left unimplemented by default to keep the project lightweight and runnable
    without downloading multi-GB models.
    """
    raise NotImplementedError(
        "Plug in a Hugging Face pipeline here if you want LLM-generated explanations."
    )
