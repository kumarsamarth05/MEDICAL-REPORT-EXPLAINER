"""
nlp/chatbot.py

A lightweight retrieval-based chatbot that answers questions about a user's
report using:
  1. The user's own parsed parameter data (for questions like
     "why is my glucose high?")
  2. A general medical FAQ knowledge base (for questions like
     "what does HDL mean?")

Matching is done with simple keyword/substring scoring by default so the
project runs with zero extra downloads. If `sentence-transformers` is
installed, semantic similarity matching is used instead for better recall
on paraphrased questions (see `_semantic_match`).
"""

import re
from config import settings
from utils.normal_ranges import PARAMETERS, RISK_RULES

_FAQ = {
    "what is hemoglobin": "Hemoglobin is the protein in red blood cells that carries oxygen from your lungs to the rest of your body.",
    "what is glucose": "Glucose is the sugar in your blood that your body uses as its main source of energy.",
    "what is hdl": "HDL is often called 'good' cholesterol — it helps remove excess cholesterol from your bloodstream.",
    "what is ldl": "LDL is often called 'bad' cholesterol — high levels can build up in artery walls over time.",
    "what is vitamin d": "Vitamin D supports bone health, calcium absorption, and immune function.",
    "what is tsh": "TSH (thyroid-stimulating hormone) signals your thyroid gland and helps regulate metabolism.",
    "what foods improve hemoglobin": "Iron-rich foods like leafy greens, legumes, and lean meats, paired with vitamin C for better absorption, may help.",
    "what foods lower cholesterol": "Foods high in soluble fiber (oats, beans), healthy fats (olive oil, nuts), and regular exercise can help manage cholesterol.",
}

_SEMANTIC_MODEL = None  # lazy-loaded if available


def _try_load_semantic_model():
    global _SEMANTIC_MODEL
    if not settings.enable_semantic_chatbot:
        return False
    if _SEMANTIC_MODEL is not None:
        return _SEMANTIC_MODEL
    try:
        from sentence_transformers import SentenceTransformer

        _SEMANTIC_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _SEMANTIC_MODEL = False  # mark as unavailable
    return _SEMANTIC_MODEL


def _semantic_match(question: str, choices: list) -> str | None:
    model = _try_load_semantic_model()
    if not model:
        return None
    from sentence_transformers import util

    q_emb = model.encode(question, convert_to_tensor=True)
    c_emb = model.encode(choices, convert_to_tensor=True)
    scores = util.cos_sim(q_emb, c_emb)[0]
    best_idx = int(scores.argmax())
    if float(scores[best_idx]) < 0.45:
        return None
    return choices[best_idx]


def _keyword_match(question: str, choices: list) -> str | None:
    q_words = set(re.findall(r"[a-z0-9]+", question.lower()))
    best, best_score = None, 0
    for choice in choices:
        c_words = set(re.findall(r"[a-z0-9]+", choice.lower()))
        overlap = len(q_words & c_words)
        if overlap > best_score:
            best, best_score = choice, overlap
    return best if best_score > 0 else None


def _find_parameter_in_question(question: str):
    q_lower = question.lower()
    for name in PARAMETERS:
        if name.lower() in q_lower:
            return name
        for alias in PARAMETERS[name]["aliases"]:
            if re.search(alias, q_lower):
                return name
    return None


def answer_question(question: str, report_params: list | None = None) -> str:
    """Answer a user's question, using their report data when relevant.

    `report_params` = the parsed parameter list for their most recent report
    (as produced by nlp.medical_parser.parse_parameters), or None.
    """
    question_clean = question.strip()
    param_name = _find_parameter_in_question(question_clean)

    # Case 1: user is asking "why is my X high/low" and we have their data
    if param_name and report_params:
        match = next((p for p in report_params if p["name"] == param_name), None)
        if match and match["status"] != "Normal":
            rule = RISK_RULES.get((param_name, match["status"]))
            if rule:
                tips = "; ".join(rule["suggestions"])
                return (
                    f"Your {param_name} was {match['value']} {match['unit']} "
                    f"({match['status']}). {rule['risk']} Some general suggestions: {tips}. "
                    f"This is educational information, not a diagnosis — please consult a doctor."
                )
        if match:
            return (
                f"Your {param_name} was {match['value']} {match['unit']}, which is "
                f"within the normal range ({PARAMETERS[param_name]['low']}-"
                f"{PARAMETERS[param_name]['high']} {match['unit']})."
            )

    # Case 2: general "what is X" style question -> FAQ / description lookup
    choices = list(_FAQ.keys())
    matched_key = _semantic_match(question_clean, choices) or _keyword_match(question_clean, choices)
    if matched_key:
        return _FAQ[matched_key]

    # Case 3: fall back to parameter description if we recognized the term
    if param_name:
        return f"{param_name} {PARAMETERS[param_name]['description']}."

    return (
        "I'm not sure about that one. Try asking about a specific parameter, "
        "e.g. 'What does HDL mean?' or 'Why is my glucose high?'. "
        "For medical concerns, please consult a healthcare professional."
    )
