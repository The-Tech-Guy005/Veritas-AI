"""
Evidence Verification Engine  (Person 3 - Evidence Collection & Claim Verification)

Pipeline (all offline / deterministic; Gemini is only an optional upgrade for extraction):
  1. extract_claims()               - pull atomic, check-worthy factual claims out of the generated answer
  2. _match_claim()                 - find the passage in each source that supports a claim
  3. (stance per source)            - supports / partially_supports / contradicts / does_not_address
  4. verify_evidence_and_claims()   - flag unsupported / partially supported claims
  5. find_conflicts()/detect_conflicts() - detect conflicts claim-vs-source and source-vs-source
  6. score_claim() (rubric.py)      - deterministic 0-100 score; ClaimRecord list is handed to Person 4

Public names kept from the original module:
  extract_claims, detect_conflicts, verify_evidence_and_claims
"""

import re
import math
import requests
from typing import List, Dict, Any, Tuple, Optional, Set
from app.config import settings
from app.schemas import (
    EvidenceItem, ClaimRecord, ClaimStatus, ClaimRelationship,
    EvidenceStrengthScore, EvidenceMatch, ConflictRecord,
)
from app.services.rubric import (
    score_claim, compute_aggregate_evidence_strength, assess_source_authority,
)

# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------
MATCH_MIN = 0.30          # below this a passage is treated as "does not address" the claim
SUPPORT_MIN = 0.65        # a single passage at/above this (numbers matching) fully supports the claim
FULL_COVERAGE_MIN = 0.70  # combined coverage across sources needed for VERIFIED
CONFLICT_MIN_OVERLAP = 0.45   # topical overlap needed before two texts can be "in conflict"
NEGATION_MIN_OVERLAP = 0.55
DEFAULT_MAX_CLAIMS = 8

# Evidence produced by our own agents is not independent proof of a claim.
NON_SUPPORTING_SOURCE_TYPES = {"analysis", "counter_analysis"}

# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------
STOPWORDS = set("""
a an the and or but if then than that this these those of in on at to for from by with without within into onto over under
about above below between among as is are was were be been being am do does did done has have had having it its they them their
there here which who whom whose what when where why how not no nor so such very can could may might must shall should will would
also however thus therefore while whereas although though because since per via just only more most less least much many some any
all each both either neither other another same own too one two three based according shows show showed shown report reports
reported found find finds said says say new use used using uses
""".split())

NEGATORS = {"not", "no", "never", "cannot", "without", "lack", "lacks", "lacking", "unable",
            "fails", "failed", "fail", "neither", "nor", "none", "nothing", "unlikely", "false"}

# word groups with opposite direction (raw lowercase words; compared after _stem)
_ANTONYM_GROUPS_RAW = [
    ({"increase", "increases", "increased", "increasing", "rise", "rises", "rose", "risen", "rising",
      "grow", "grows", "grew", "grown", "growing", "growth", "gain", "gains", "gained", "improve",
      "improves", "improved", "improving", "higher", "greater", "faster", "cheaper", "surge", "surged",
      "expand", "expanded", "expands", "more", "larger", "bigger"},
     {"decrease", "decreases", "decreased", "decreasing", "fall", "falls", "fell", "fallen", "falling",
      "decline", "declines", "declined", "declining", "drop", "drops", "dropped", "shrink", "shrinks",
      "shrank", "shrunk", "worsen", "worsens", "worsened", "degrade", "degrades", "degraded", "lower",
      "smaller", "slower", "costlier", "reduce", "reduces", "reduced", "reduction", "less", "fewer"}),
    ({"safe", "safer", "safest", "secure", "stable", "reliable", "effective", "viable", "feasible",
      "profitable", "cheap", "efficient", "approved", "legal", "supported"},
     {"unsafe", "dangerous", "riskier", "risky", "insecure", "unstable", "unreliable", "ineffective",
      "unviable", "infeasible", "unprofitable", "expensive", "inefficient", "rejected", "banned",
      "illegal", "unsupported"}),
]

_ABBREV = ["e.g.", "i.e.", "vs.", "etc.", "et al.", "fig.", "no.", "dr.", "mr.", "mrs.", "ms.", "prof.",
           "inc.", "ltd.", "u.s.", "u.k.", "approx.", "st."]
_DOT = "\u2024"  # placeholder for protected periods


def _stem(word: str) -> str:
    w = word.lower()
    for suf in ("ings", "ing", "edly", "ied", "ies", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            if suf in ("ies", "ied"):
                return w[: -len(suf)] + "y"
            w = w[: -len(suf)]
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


_ANTONYM_GROUPS = [({_stem(x) for x in a}, {_stem(x) for x in b}) for a, b in _ANTONYM_GROUPS_RAW]
_NEGATOR_STEMS = {_stem(x) for x in NEGATORS} | NEGATORS


def _normalize(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\bcan['’]t\b", "cannot", t)
    t = re.sub(r"n['’]t\b", " not", t)
    return t


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z]+", _normalize(text))


def _content_terms(text: str) -> List[str]:
    """Stemmed, stop-word-free words of a text (numbers excluded)."""
    out = []
    for w in _words(text):
        if w in STOPWORDS or len(w) < 3:
            continue
        out.append(_stem(w))
    return out


def _protect_abbrev(text: str) -> str:
    low = text.lower()
    out = text
    for ab in _ABBREV:
        start = 0
        while True:
            i = low.find(ab, start)
            if i == -1:
                break
            out = out[:i] + out[i:i + len(ab)].replace(".", _DOT) + out[i + len(ab):]
            start = i + len(ab)
    return out


def _split_sentences(text: str) -> List[str]:
    """Sentence splitter that respects decimals (3.5), abbreviations (e.g.) and line breaks."""
    if not text:
        return []
    sentences: List[str] = []
    for block in re.split(r"\n+", text):
        block = block.strip()
        if not block:
            continue
        protected = _protect_abbrev(block)
        parts = re.split(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])", protected)
        for p in parts:
            p = p.replace(_DOT, ".").strip()
            if p:
                sentences.append(p)
    return sentences


# --- numbers / quantities ---------------------------------------------------
_UNIT_MAP = {
    "%": "%", "percent": "%", "pct": "%", "per cent": "%",
    "gwh": "gwh", "mwh": "mwh", "kwh": "kwh", "twh": "twh", "gw": "gw", "mw": "mw", "kw": "kw",
    "year": "year", "years": "year", "month": "month", "months": "month", "day": "day", "days": "day",
    "usd": "$", "dollars": "$", "dollar": "$", "eur": "eur", "euros": "eur", "inr": "inr", "rupees": "inr",
    "wh/kg": "wh/kg", "cycles": "cycles", "cycle": "cycles", "degrees": "deg", "c": "deg",
}
_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12}
_CURRENCY = {"$": "$", "€": "eur", "£": "gbp", "₹": "inr"}
_NUM_RE = re.compile(
    r"(?P<cur>[$€£₹])?\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s?"
    r"(?P<mult>thousand|million|billion|trillion|bn|k)?\s?"
    r"(?P<unit>%|per cent|percent|pct|gwh|mwh|kwh|twh|gw|mw|kw|years?|months?|days?|usd|dollars?|eur|euros|inr|rupees|"
    r"wh/kg|cycles?)?",
    re.I,
)


def _quantities(text: str) -> List[Tuple[float, str, str]]:
    """Return [(value, unit, surface_form)] for every number in the text.
    unit is '' for plain numbers and 'yr_abs' for calendar years (1900-2100)."""
    out = []
    for m in _NUM_RE.finditer(text or ""):
        raw = m.group("num").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        mult = (m.group("mult") or "").lower()
        if mult:
            val *= _MULT.get(mult, 1)
        unit = _UNIT_MAP.get((m.group("unit") or "").lower(), "")
        if not unit and m.group("cur"):
            unit = _CURRENCY.get(m.group("cur"), "")
        if not unit and not mult and re.fullmatch(r"(19|20)\d\d", raw):
            unit = "yr_abs"
        out.append((val, unit, m.group(0).strip()))
    return out


def _same_number(a: float, b: float) -> bool:
    return abs(a - b) <= 0.02 * max(abs(a), abs(b), 1e-9)


def _uncovered_numbers(claim_q, window_q) -> List[str]:
    missing = []
    for v, u, surf in claim_q:
        found = any(_same_number(v, v2) and (u == u2 or not u or not u2) for v2, u2, _ in window_q)
        if not found:
            missing.append(surf)
    return missing


def _jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# ===========================================================================
# BULLET 1 - Extract individual factual claims from the generated response
# ===========================================================================
_BOILERPLATE_PREFIXES = (
    "no evidence found", "evidence retrieved for your query", "llm synthesis was unavailable",
    "gemini ", "gemini_api_key", "here is", "here are", "below is", "below are", "the following",
    "in summary", "in conclusion", "to summarize", "note:", "disclaimer", "sources:", "references:",
    "web source:", "url:", "uploaded document:", "question:", "evidence:",
)
_OPINION_MARKERS = ("i think", "i believe", "in my opinion", "i feel", "we recommend", "i recommend",
                    "you should", "let me", "feel free", "hope this", "it seems like")
_RECOMMENDATION_STARTS = ("consider ", "ensure ", "make sure", "recommend", "please ", "try ", "use ",
                          "configure ", "upload ", "install ", "add ", "set ", "check ", "see ", "refer ")
_FACT_VERBS = {"is", "are", "was", "were", "has", "have", "had", "reach", "reached", "achieve", "achieved",
               "require", "requires", "required", "cost", "costs", "show", "shows", "showed", "found",
               "increase", "increased", "decrease", "decreased", "grew", "grow", "rose", "fell", "provides",
               "provide", "offers", "offer", "use", "uses", "enables", "enable", "report", "reports",
               "reported", "exceed", "exceeds", "exceeded", "support", "supports", "lower", "higher",
               "operate", "operates", "store", "stores", "contain", "contains", "remain", "remains"}


def _clean_line(line: str) -> str:
    """Strip markdown / bullets / citations / URLs from one line of an answer."""
    s = line.strip()
    s = re.sub(r"^\s*(?:[-*•>]+|\d+[.)])\s+", "", s)          # bullets / numbering
    s = re.sub(r"^#+\s*", "", s)                                # headings
    s = re.sub(r"\[([^\]]+)\]\((?:https?://)[^)]*\)", r"\1", s)  # [text](url) -> text
    s = re.sub(r"\(?https?://\S+\)?", "", s)                    # bare URLs
    s = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", "", s)                # [1] [2,3]
    s = re.sub(r"[*_`]{1,3}", "", s)                            # emphasis / code
    s = re.sub(r"^(?:content|chunk)\s*:\s*", "", s, flags=re.I)  # evidence-dump labels (keep the text)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)                     # "text ." -> "text."
    s = s.strip(" -\t")
    m = re.match(r"^(however|moreover|additionally|furthermore|overall|thus|therefore|also|in addition|"
                 r"notably|importantly|meanwhile)\s*,\s*", s, flags=re.I)
    if m and len(s) > m.end():
        s = s[m.end():]
        s = s[0].upper() + s[1:]
    return s


def _is_check_worthy(sentence: str) -> float:
    """Heuristic check-worthiness score. 0 = not a factual claim."""
    s = sentence.strip()
    low = s.lower()
    words = s.split()
    if len(words) < 5 or len(s) < 25:
        return 0.0
    if s.endswith("?"):
        return 0.0
    if low.startswith(_BOILERPLATE_PREFIXES) or any(m in low for m in _OPINION_MARKERS):
        return 0.0
    if low.startswith(_RECOMMENDATION_STARTS):
        return 0.0
    if s.endswith(":") or re.fullmatch(r"[-=_*\s]+", s):
        return 0.0
    score = 0.0
    if re.search(r"\d", s):
        score += 2.0
    # named entities: capitalised word not at sentence start, or acronym
    tail = words[1:]
    if any((w[:1].isupper() and w.isalpha() and len(w) > 2) or (w.isupper() and len(w) >= 2 and w.isalpha()) for w in tail):
        score += 1.5
    if any(w.lower().strip(".,;:()") in _FACT_VERBS for w in words):
        score += 1.0
    if re.search(r"\b(than|more|less|higher|lower|largest|smallest|majority|minority|most|least)\b", low):
        score += 0.5
    if len(words) >= 7:
        score += 0.5
    return score


def _split_compound(sentence: str) -> List[str]:
    """Split a sentence into independent clauses on ';' so each claim is atomic."""
    parts = [p.strip(" ,") for p in re.split(r";\s+", sentence) if p.strip()]
    return parts or [sentence]


def extract_claims_with_spans(raw_text: str, max_claims: int = DEFAULT_MAX_CLAIMS) -> List[Tuple[str, str]]:
    """
    Offline claim extractor. Returns [(claim, answer_sentence_it_came_from)] in answer order.
    Drops questions, headings, boilerplate, opinions, recommendations and evidence-dump labels,
    keeps the most check-worthy sentences (numbers, entities, factual verbs) and removes near-duplicates.
    """
    if not raw_text or not raw_text.strip():
        return []
    if raw_text.strip().lower().startswith(("no evidence found", "llm synthesis was unavailable")):
        return []   # system placeholder text, not an answer

    scored: List[Tuple[float, int, str, str]] = []
    idx = 0
    for sentence in _split_sentences(raw_text):
        cleaned = _clean_line(sentence)
        if not cleaned:
            continue
        for clause in _split_compound(cleaned):
            sc = _is_check_worthy(clause)
            if sc >= 1.5 or (sc >= 1.0 and re.search(r"\d", clause)):
                if len(clause) > 320:
                    clause = clause[:320].rsplit(" ", 1)[0]
                scored.append((sc, idx, clause, cleaned))
                idx += 1

    # de-duplicate near-identical claims (keep the first)
    unique: List[Tuple[float, int, str, str]] = []
    seen_sets: List[Set[str]] = []
    for item in scored:
        terms = set(_content_terms(item[2]))
        if any(_jaccard(terms, prev) >= 0.8 for prev in seen_sets):
            continue
        seen_sets.append(terms)
        unique.append(item)

    # keep the most check-worthy, restore answer order
    if len(unique) > max_claims:
        unique = sorted(sorted(unique, key=lambda x: (-x[0], x[1]))[:max_claims], key=lambda x: x[1])
    return [(claim, span) for _, _, claim, span in unique]


def _best_span(claim: str, raw_text: str) -> Optional[str]:
    """Find the answer sentence that best matches an (LLM-extracted) claim."""
    c_terms = set(_content_terms(claim))
    best, best_s = None, 0.0
    for sent in _split_sentences(raw_text):
        s = _jaccard(c_terms, set(_content_terms(sent)))
        if s > best_s:
            best, best_s = _clean_line(sent), s
    return best


def _gemini_extract(raw_text: str, max_claims: int) -> List[str]:
    prompt = (
        f"Extract up to {max_claims} concise, verifiable, factual claims from the following text.\n"
        "Each claim must be an independent factual statement of 1-2 sentences.\n"
        "Return them as a numbered list with no filler.\n\n"
        f"TEXT:\n{raw_text[:3000]}"
    )
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}"
           f":generateContent?key={settings.gemini_api_key}")
    resp = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}},
        timeout=settings.subagent_timeout_seconds,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    lines = [re.sub(r"^\d+[\.\)]\s*", "", ln).strip() for ln in text.split("\n") if ln.strip()]
    return [ln for ln in lines if len(ln) > 15][:max_claims]


def extract_claims(raw_text: str, max_claims: int = 5) -> List[str]:
    """
    Extracts key factual statements from synthesized findings or subtask results.
    Uses Gemini when configured, otherwise (or on any failure) the deterministic offline extractor.
    """
    if not raw_text or len(raw_text.strip()) == 0:
        return []

    if settings.gemini_api_key:
        try:
            claims = _gemini_extract(raw_text, max_claims)
            if claims:
                return claims
        except Exception:
            pass

    return [claim for claim, _ in extract_claims_with_spans(raw_text, max_claims)]


# ===========================================================================
# BULLETS 2 & 3 - Find supporting evidence for each claim and match claims to sources
# ===========================================================================
class _EvidenceIndex:
    """Sentence-level index over the evidence passages (offline retrieval, IDF-weighted term overlap)."""

    def __init__(self, evidence: List[EvidenceItem]):
        self.items: List[EvidenceItem] = []
        self.windows: List[List[Tuple[str, Set[str], list]]] = []   # per item: (text, term_set, quantities)
        df: Dict[str, int] = {}
        n_docs = 0
        for ev in evidence:
            if ev.source_type in NON_SUPPORTING_SOURCE_TYPES or not (ev.passage or "").strip():
                continue
            sents = _split_sentences(ev.passage)
            texts = list(sents) + [f"{a} {b}" for a, b in zip(sents, sents[1:])]   # 1- and 2-sentence windows
            wins = []
            for t in texts:
                terms = set(_content_terms(t))
                wins.append((t, terms, _quantities(t)))
            for t in sents:
                n_docs += 1
                for term in set(_content_terms(t)):
                    df[term] = df.get(term, 0) + 1
            self.items.append(ev)
            self.windows.append(wins)
        self._df, self._n = df, max(n_docs, 1)

    def idf(self, term: str) -> float:
        return math.log(1.0 + (self._n + 1.0) / (self._df.get(term, 0) + 1.0))


def _weighted_coverage(claim_terms: Set[str], window_terms: Set[str], idx: _EvidenceIndex) -> float:
    total = sum(idx.idf(t) for t in claim_terms)
    if total <= 0:
        return 0.0
    return sum(idx.idf(t) for t in claim_terms if t in window_terms) / total


def _best_window(claim: str, claim_terms: Set[str], claim_q, item_windows, idx: _EvidenceIndex):
    """Best matching window of ONE source for a claim -> (score, term_cov, text, window_terms, missing_numbers)."""
    best = None
    for text, terms, quants in item_windows:
        cov = _weighted_coverage(claim_terms, terms, idx)
        missing = _uncovered_numbers(claim_q, quants) if claim_q else []
        if claim_q:
            num_cov = 1.0 - len(missing) / len(claim_q)
            score = 0.7 * cov + 0.3 * num_cov
        else:
            score = cov
        cand = (score, cov, text, terms, missing)
        if best is None or cand[0] > best[0] + 1e-9 or (abs(cand[0] - best[0]) <= 1e-9 and len(text) < len(best[2])):
            best = cand
    return best


def _matched_terms(claim_terms: Set[str], window_terms: Set[str]) -> List[str]:
    return sorted(claim_terms & window_terms)


# ===========================================================================
# BULLET 5 (primitives) - conflict signals between two pieces of text
#   used for claim-vs-source AND source-vs-source comparison
# ===========================================================================
def _context_terms(text: str, surface: str, window: int = 6) -> Set[str]:
    """Content terms in the few words around a number (tells us WHAT is being measured)."""
    i = text.find(surface)
    if i < 0:
        return set()
    before = re.findall(r"[A-Za-z]+", text[:i])[-window:]
    after = re.findall(r"[A-Za-z]+", text[i + len(surface):])[:window]
    return {_stem(w.lower()) for w in before + after if w.lower() not in STOPWORDS and len(w) >= 3}


def _numeric_conflict(a: str, b: str) -> Optional[str]:
    """Same measure (same unit + shared context words) reported with different values."""
    qa, qb = _quantities(a), _quantities(b)
    for va, ua, sa in qa:
        if not ua or ua == "yr_abs":
            continue
        same_unit = [(vb, sb) for vb, ub, sb in qb if ub == ua]
        if not same_unit or any(_same_number(va, vb) for vb, _ in same_unit):
            continue
        ctx_a = _context_terms(a, sa)
        for vb, sb in same_unit:
            if ctx_a & _context_terms(b, sb):
                return f"numbers disagree for the same measure: '{sa}' vs '{sb}'"
    return None


def _negation_conflict(a: str, b: str) -> Optional[str]:
    neg_a = sum(1 for w in _words(a) if w in _NEGATOR_STEMS) % 2
    neg_b = sum(1 for w in _words(b) if w in _NEGATOR_STEMS) % 2
    if neg_a != neg_b:
        return "one text affirms the statement while the other negates it"
    return None


def _direction_conflict(a: str, b: str) -> Optional[str]:
    sa = {_stem(w) for w in _words(a)}
    sb = {_stem(w) for w in _words(b)}
    for grp_a, grp_b in _ANTONYM_GROUPS:
        a_pos, a_neg = sa & grp_a, sa & grp_b
        b_pos, b_neg = sb & grp_a, sb & grp_b
        if (a_pos and not a_neg and b_neg and not b_pos) or (a_neg and not a_pos and b_pos and not b_neg):
            x = sorted(a_pos or a_neg)[0]
            y = sorted(b_pos or b_neg)[0]
            return f"opposite direction/polarity ('{x}' vs '{y}')"
    return None


def _compare_passages(a: str, b: str, overlap: float) -> Optional[Tuple[str, str]]:
    """
    Do two texts about the same topic disagree?  `overlap` = topical term overlap (0-1).
    Returns (conflict_type, description) or None.
    """
    if overlap < CONFLICT_MIN_OVERLAP:
        return None
    d = _numeric_conflict(a, b)
    if d:
        return "numeric_mismatch", d
    d = _direction_conflict(a, b)
    if d:
        return "direction", d
    if overlap >= NEGATION_MIN_OVERLAP:
        d = _negation_conflict(a, b)
        if d:
            return "negation", d
    return None


def _source_weight(ev: EvidenceItem) -> float:
    """Authority weight reused from the rubric (30/28/20/12 -> 3.0/2.8/2.0/1.2)."""
    return assess_source_authority([ev])[0] / 10.0


def _origin(ev: EvidenceItem) -> str:
    u = ev.url_or_id or ev.source_title
    return u.split("/")[2] if "://" in u and len(u.split("/")) > 2 else u


def _excerpt(text: str, n: int = 200) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# ===========================================================================
# BULLETS 2 & 3 (continued) - match one claim against every source
# ===========================================================================
def _surface_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for w in _words(text):
        if w not in STOPWORDS and len(w) >= 3:
            out.setdefault(_stem(w), w)
    return out


def _match_claim(claim: str, idx: _EvidenceIndex) -> Dict[str, Any]:
    """
    Compare a claim with the best passage of every source.
    Returns {"matches": [...], "combined_cov": float, "missing_numbers": [...], "uncovered_terms": [...]}
    where each match is a dict(item, window, em=EvidenceMatch).
    """
    claim_terms = set(_content_terms(claim))
    claim_q = _quantities(claim)
    surface = _surface_map(claim)
    matches: List[Dict[str, Any]] = []

    for item, wins in zip(idx.items, idx.windows):
        best = _best_window(claim, claim_terms, claim_q, wins, idx)
        if not best:
            continue
        score, cov, text, wterms, missing = best
        if score < MATCH_MIN:
            continue                      # does_not_address -> not a match
        conflict = _compare_passages(claim, text, cov)
        if conflict:
            stance = ClaimRelationship.CONTRADICTS
        elif score >= SUPPORT_MIN and not missing:
            stance = ClaimRelationship.SUPPORTS
        else:
            stance = ClaimRelationship.PARTIALLY_SUPPORTS
        em = EvidenceMatch(
            source_title=item.source_title,
            url_or_id=item.url_or_id,
            source_type=item.source_type,
            supporting_passage=_excerpt(text, 300),
            match_score=round(min(1.0, max(0.0, score)), 3),
            stance=stance,
            matched_terms=[surface.get(t, t) for t in _matched_terms(claim_terms, wterms)],
            missing_numbers=missing,
        )
        matches.append({"item": item, "window": text, "terms": wterms, "em": em,
                        "conflict": conflict})

    matches.sort(key=lambda m: -m["em"].match_score)

    supportive = [m for m in matches if m["em"].stance != ClaimRelationship.CONTRADICTS]
    union_terms: Set[str] = set().union(*[m["terms"] for m in supportive]) if supportive else set()
    combined_cov = _weighted_coverage(claim_terms, union_terms, idx) if supportive else 0.0
    sup_quants = [q for m in supportive for q in _quantities(m["window"])]
    missing_numbers = _uncovered_numbers(claim_q, sup_quants) if supportive else [s for _, _, s in claim_q]
    uncovered = sorted((t for t in claim_terms if t not in union_terms), key=lambda t: -idx.idf(t))
    return {
        "matches": matches,
        "combined_cov": combined_cov,
        "missing_numbers": missing_numbers,
        "uncovered_terms": [surface.get(t, t) for t in uncovered[:4]],
    }


# ===========================================================================
# BULLET 5 - Detect conflicting information between sources
# ===========================================================================
_OBJECTION_TERMS = ["however", "dispute", "contradict", "fails to", "unproven", "overstated",
                    "inaccurate", "deviate", "limitation"]


def _supporters_outweigh(supporters: List[Dict[str, Any]], opponents: List[Dict[str, Any]]) -> bool:
    """A conflict counts as 'resolved' when >=2 independent origins back the claim with >=2x the authority weight."""
    if not supporters:
        return False
    origins = {_origin(m["item"]) for m in supporters}
    w_sup = sum(_source_weight(m["item"]) for m in supporters)
    w_opp = sum(_source_weight(m["item"]) for m in opponents)
    return len(origins) >= 2 and w_sup >= 2.0 * w_opp


def _conflicts_for(claim: str, matches: List[Dict[str, Any]], objections: List[str]) -> List[ConflictRecord]:
    conflicts: List[ConflictRecord] = []
    supporters = [m for m in matches if m["em"].stance != ClaimRelationship.CONTRADICTS]
    opponents = [m for m in matches if m["em"].stance == ClaimRelationship.CONTRADICTS]

    # (a) claim vs source: a source says something incompatible with the claim
    claim_resolved = _supporters_outweigh(supporters, opponents)
    for m in opponents:
        kind, desc = m["conflict"]
        best_sup = supporters[0] if supporters else None
        conflicts.append(ConflictRecord(
            conflict_type=kind,
            description=f"Claim vs source: {desc}.",
            source_a=m["item"].source_title,
            source_b=best_sup["item"].source_title if best_sup else None,
            excerpt_a=_excerpt(m["window"]),
            excerpt_b=_excerpt(best_sup["window"]) if best_sup else "",
            resolved=claim_resolved,
            resolution_note=("Outweighed by >=2 independent, higher-authority supporting sources."
                             if claim_resolved else "No clear majority/authority advantage; left unresolved."),
        ))

    # (b) source vs source: two sources that both address the claim disagree with each other
    top = supporters[:4]
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i], top[j]
            ta, tb = a["terms"], b["terms"]
            overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
            found = _compare_passages(a["window"], b["window"], overlap)
            if not found:
                continue
            kind, desc = found
            wa, wb = _source_weight(a["item"]), _source_weight(b["item"])
            resolved = max(wa, wb) >= 2.0 * min(wa, wb)
            winner = a if wa >= wb else b
            conflicts.append(ConflictRecord(
                conflict_type="source_vs_source",
                description=f"Sources disagree ({kind}): {desc}.",
                source_a=a["item"].source_title,
                source_b=b["item"].source_title,
                excerpt_a=_excerpt(a["window"]),
                excerpt_b=_excerpt(b["window"]),
                resolved=resolved,
                resolution_note=(f"Higher-authority source preferred: {winner['item'].source_title}."
                                 if resolved else "Sources have comparable authority; disagreement unresolved."),
            ))

    # (c) counter-analysis objections (original behaviour retained)
    claim_terms = set(_content_terms(claim))
    high_auth = sum(1 for m in supporters if m["item"].authority_level == "high")
    for obj in objections or []:
        low = obj.lower()
        if any(t in low for t in _OBJECTION_TERMS) and len(claim_terms & set(_content_terms(obj))) >= 2:
            conflicts.append(ConflictRecord(
                conflict_type="counter_analysis",
                description="Counter-analysis agent raised an objection touching this claim.",
                source_a="Counter-Analysis Agent",
                excerpt_a=_excerpt(obj),
                resolved=high_auth >= 2,
                resolution_note=("Addressed by >=2 high-authority sources." if high_auth >= 2 else None),
            ))
            break
    return conflicts


def find_conflicts(claim: str, evidence: List[EvidenceItem], objections: List[str]) -> List[ConflictRecord]:
    """Detailed conflict report for one claim (claim-vs-source, source-vs-source, counter-analysis)."""
    idx = _EvidenceIndex(evidence)
    return _conflicts_for(claim, _match_claim(claim, idx)["matches"], objections)


def detect_conflicts(claim: str, evidence: List[EvidenceItem], objections: List[str]) -> Tuple[bool, bool]:
    """
    Checks whether the claim conflicts with the evidence, between the sources themselves,
    or with the counter-analysis objections.
    Returns (has_conflicts, conflict_resolved).
    """
    conflicts = find_conflicts(claim, evidence, objections)
    if not conflicts:
        return False, False
    return True, all(c.resolved for c in conflicts)


# ===========================================================================
# BULLET 4 + 6 - Flag unsupported / partially supported claims and hand results to Person 4
# ===========================================================================
def _dedupe_items(items: List[EvidenceItem]) -> List[EvidenceItem]:
    seen, out = set(), []
    for it in items:
        key = (it.url_or_id, it.source_title)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _verify_single_claim(
    claim: str,
    span: Optional[str],
    idx: _EvidenceIndex,
    objections: List[str],
    derived_from_evidence: bool = False,
) -> ClaimRecord:
    m = _match_claim(claim, idx)
    matches = m["matches"]
    supportive = [x for x in matches if x["em"].stance != ClaimRelationship.CONTRADICTS]
    conflicts = _conflicts_for(claim, matches, objections)
    has_conflicts = bool(conflicts)
    conflict_resolved = all(c.resolved for c in conflicts) if has_conflicts else True

    record = score_claim(
        statement=claim,
        sources=_dedupe_items([x["item"] for x in supportive]),
        has_conflicts=has_conflicts,
        conflict_resolved=conflict_resolved,
    )

    notes: List[str] = []
    limits: List[str] = list(record.limitations)
    unsupported: List[str] = []
    has_strong = any(x["em"].stance == ClaimRelationship.SUPPORTS for x in supportive)
    fully_supported = (has_strong and m["combined_cov"] >= FULL_COVERAGE_MIN and not m["missing_numbers"])

    if not matches:
        # nothing in any source addresses the claim -> unsupported
        record.status = ClaimStatus.UNVERIFIED
        record.relationship = ClaimRelationship.DOES_NOT_ADDRESS
        unsupported.append("entire claim - no retrieved source addresses it")
        notes.append("No source passage matched this claim.")
        limits.append("Unsupported: no retrieved source addresses this claim.")
    elif not supportive:
        notes.append("Only conflicting evidence was found for this claim.")
    else:
        if not fully_supported:
            if m["missing_numbers"]:
                unsupported.append("number(s) not found in sources: " + ", ".join(m["missing_numbers"]))
            if m["combined_cov"] < FULL_COVERAGE_MIN and m["uncovered_terms"]:
                unsupported.append("not covered by sources: " + ", ".join(m["uncovered_terms"]))
            if record.status == ClaimStatus.VERIFIED:
                record.status = ClaimStatus.PARTIALLY_SUPPORTED
                record.relationship = ClaimRelationship.PARTIALLY_SUPPORTS
                record.rubric_score = min(record.rubric_score, 74)
                notes.append("Downgraded from verified: sources cover only part of the claim.")
            limits.append("Partially supported: " + "; ".join(unsupported) if unsupported
                          else "Partially supported: sources only loosely match the claim wording.")
        else:
            notes.append(f"Fully covered by {len(supportive)} source(s) "
                         f"(coverage {m['combined_cov']:.0%}).")

    if derived_from_evidence:
        notes.append("Claim was derived from the retrieved evidence itself (no generated answer was supplied), "
                     "so support is circular and cannot exceed 'partially supported'.")
        limits.append("Claim derived from evidence text, not from an independent answer.")
        if record.status == ClaimStatus.VERIFIED:
            record.status = ClaimStatus.PARTIALLY_SUPPORTED
            record.relationship = ClaimRelationship.PARTIALLY_SUPPORTS
            record.rubric_score = min(record.rubric_score, 74)

    if record.status == ClaimStatus.DISPUTED and record.rubric_score > 59:
        record.rubric_score = 59
        notes.append("Score capped at 59: unresolved conflicting evidence.")

    for c in conflicts:
        tag = "resolved" if c.resolved else "UNRESOLVED"
        limits.append(f"Conflict ({c.conflict_type}, {tag}): {c.description}")

    record.source_answer_span = span
    record.evidence_matches = [x["em"] for x in matches]
    record.conflicts = conflicts
    record.unsupported_parts = unsupported
    record.verification_notes = notes
    seen_l = set()
    record.limitations = [l for l in limits if not (l in seen_l or seen_l.add(l))]
    return record


def verify_evidence_and_claims(
    claims_text_or_list: Any,
    evidence: List[EvidenceItem],
    objections: List[str],
    max_claims: int = DEFAULT_MAX_CLAIMS,
) -> Tuple[List[ClaimRecord], EvidenceStrengthScore]:
    """
    Main verification pipeline:
    1. Extracts claims from the generated answer (text) or accepts a ready list of claims
    2. Finds the supporting passage for each claim in every source and assigns a stance
    3. Flags unsupported / partially supported claims, detects conflicts
    4. Scores each claim with the deterministic rubric and aggregates the evidence strength
    Returns (claim-level ClaimRecords for Person 4, aggregate EvidenceStrengthScore).
    """
    objections = objections or []
    pairs: List[Tuple[str, Optional[str]]]
    if isinstance(claims_text_or_list, str):
        if settings.gemini_api_key and claims_text_or_list.strip():
            texts = extract_claims(claims_text_or_list, max_claims)
            pairs = [(c, _best_span(c, claims_text_or_list)) for c in texts]
        else:
            pairs = list(extract_claims_with_spans(claims_text_or_list, max_claims))
    else:
        pairs = [(str(c).strip(), None) for c in (claims_text_or_list or []) if str(c).strip()]

    derived = False
    if not pairs and evidence:
        # Fallback: no answer text given -> derive claims from the evidence passages themselves (flagged as circular)
        derived = True
        for ev in evidence:
            if ev.source_type in NON_SUPPORTING_SOURCE_TYPES:
                continue
            for c, sp in extract_claims_with_spans(ev.passage, 2):
                pairs.append((c, None))
            if len(pairs) >= max_claims:
                break
        pairs = pairs[:max_claims]

    idx = _EvidenceIndex(evidence)
    records: List[ClaimRecord] = [
        _verify_single_claim(claim, span, idx, objections, derived_from_evidence=derived)
        for claim, span in pairs
    ]
    return records, compute_aggregate_evidence_strength(records)


def build_verification_summary(claims: List[ClaimRecord]) -> Dict[str, Any]:
    """Compact claim-level summary for trace logs / Person 4 (synthesis, PDF, chat delivery)."""
    return {
        "total_claims": len(claims),
        "verified": [c.claim_id for c in claims if c.status == ClaimStatus.VERIFIED],
        "partially_supported": [c.claim_id for c in claims if c.status == ClaimStatus.PARTIALLY_SUPPORTED],
        "disputed": [c.claim_id for c in claims if c.status == ClaimStatus.DISPUTED],
        "unverified": [c.claim_id for c in claims if c.status == ClaimStatus.UNVERIFIED],
        "conflict_count": sum(len(c.conflicts) for c in claims),
        "unresolved_conflicts": sum(1 for c in claims for x in c.conflicts if not x.resolved),
        "unsupported_claims": [c.statement for c in claims if c.unsupported_parts],
    }
