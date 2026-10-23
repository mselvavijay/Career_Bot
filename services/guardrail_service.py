import re
import json
import time
import os
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("guardrails")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.json")

def load_guardrails_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load guardrails config from {CONFIG_PATH}: {e}")
        return {}

CONFIG = load_guardrails_config()

# In-memory violation tracker for rate limiting: user_or_session_id -> list of timestamps
_violation_history: Dict[str, List[float]] = {}
COOLDOWN_WINDOW_SECONDS = 600  # 10 minutes
VIOLATION_THRESHOLD = 3
COOLDOWN_PERIOD_SECONDS = 60

# Leetspeak translation mapping
LEET_MAP = {
    '0': 'o',
    '1': 'i',
    '3': 'e',
    '4': 'a',
    '@': 'a',
    '$': 's',
    '5': 's',
    '7': 't',
    # Removed '!' mapping to avoid greeting corruption
    '+': 't',
}

def normalize_text(text: str) -> str:
    """
    STEP 1: NORMALIZE
    - Trim, lowercase, collapse repeated spaces.
    - Map common obfuscation (leetspeak, e.g. 0->o, 1->i, 3->e, @->a, $->s).
    - Collapse repeated letters (e.g. 'heyyyy' -> 'hey', 'soooo' -> 'so', but leave max 2 repeats).
    - Strip punctuation and emoji for clean matching, handling characters separated by dots or spaces.
    """
    if not text:
        return ""

    lowered = text.strip().lower()

    # Leetspeak substitution
    leet_subbed = []
    for char in lowered:
        leet_subbed.append(LEET_MAP.get(char, char))
    converted = "".join(leet_subbed)

    # Collapse character separators like p.o.r.n or p o r n
    # If single characters separated by dots, underscores or hyphens:
    converted = re.sub(r'(?<=\b\w)[._\-](?=\w\b)', '', converted)

    # Collapse excessive repeated characters (more than 2 of same char -> 2 chars, e.g. heyyyy -> heyy)
    converted = re.sub(r'([a-z])\1{3,}', r'\1\1', converted)

    # Strip punctuation and emoji, retain alphanumeric and basic whitespace
    cleaned = re.sub(r'[^\w\s]', ' ', converted)

    # Collapse repeated whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned

def is_rate_limited(identifier: str) -> Tuple[bool, Optional[str]]:
    """
    Check if the user is in cooldown due to 3 violations in the last 10 minutes.
    """
    if not identifier:
        return False, None

    now = time.time()
    history = _violation_history.get(identifier, [])
    # Filter within last 10 minutes
    recent = [t for t in history if now - t < COOLDOWN_WINDOW_SECONDS]
    _violation_history[identifier] = recent

    if len(recent) >= VIOLATION_THRESHOLD:
        latest = recent[-1]
        if now - latest < COOLDOWN_PERIOD_SECONDS:
            return True, CONFIG.get("messages", {}).get("rate_limit_cooldown", "Please wait before sending another message.")

    return False, None

def record_violation(identifier: str, category: str):
    """
    Log category + timestamp + user id (NEVER sensitive message content).
    """
    now = time.time()
    logger.warning(f"GUARDRAIL_VIOLATION | category={category} | timestamp={int(now)} | identifier={identifier}")
    if identifier:
        if identifier not in _violation_history:
            _violation_history[identifier] = []
        _violation_history[identifier].append(now)

def is_self_harm(normalized: str) -> bool:
    """
    Check if input expresses self-harm or distress.
    """
    self_harm_terms = [
        "suicide", "kill myself", "end my life", "self harm", "cut myself", "hang myself"
    ]
    for term in self_harm_terms:
        # Match as whole phrase or with boundary
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, normalized):
            return True
    return False

def is_unsafe(normalized: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    STEP 2: SAFETY FILTER (blocks the message; no model call)
    Matches whole words or phrases only to avoid false positives on normal words (e.g. assess, analysis, class).
    Returns (is_blocked, refusal_message, category).
    """
    safety_cfg = CONFIG.get("safety", {})
    msgs = CONFIG.get("messages", {})

    # 1. Check self-harm first for empathetic response
    if is_self_harm(normalized):
        return True, msgs.get("self_harm_refusal"), "self_harm"

    # Also check also without spaces for condensed obfuscations like 'p o r n' -> 'porn'
    no_space_norm = normalized.replace(" ", "")

    # 2. Check explicit terms
    for term in safety_cfg.get("explicit_terms", []):
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, normalized):
            return True, msgs.get("safety_refusal"), "explicit_content"
        # Check condensed if term is 4+ letters
        if len(term) >= 4 and term in no_space_norm:
            # Verify it's not a harmless substring like class or assess
            safe_terms = ["class", "assess", "asset", "analysis", "analyst", "essex", "pass", "passion"]
            if not any(st in no_space_norm for st in safe_terms):
                return True, msgs.get("safety_refusal"), "explicit_content"

    # 3. Check hate and harassment
    for term in safety_cfg.get("hate_and_harassment", []):
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, normalized):
            return True, msgs.get("safety_refusal"), "hate_speech"

    # 4. Check harm, illegal, fraud
    for term in safety_cfg.get("harm_illegal_fraud", []):
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, normalized):
            return True, msgs.get("safety_refusal"), "harm_illegal_fraud"

    for pat in safety_cfg.get("harm_regex_patterns", []):
        if re.search(pat, normalized):
            return True, msgs.get("safety_refusal"), "harm_illegal_fraud"

    # 5. Check prompt injection
    for term in safety_cfg.get("prompt_injection", []):
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, normalized):
            return True, msgs.get("safety_refusal"), "prompt_injection"

    for pat in safety_cfg.get("prompt_injection_patterns", []):
        if re.search(pat, normalized):
            return True, msgs.get("safety_refusal"), "prompt_injection"

    return False, None, None

def detect_small_talk(original_text: str, normalized: str) -> Tuple[bool, Optional[str]]:
    """
    STEP 3: GREETING AND SMALL TALK (no job search, no LLM call)
    - Greeting-only messages return greeting reply.
    - Thanks ("thanks", "thank you") -> thanks reply.
    - Goodbye ("bye", "see you") -> goodbye reply.
    - A greeting followed by a real request ("Hi, I know Python and FastAPI") MUST go through the normal pipeline!
    - "hi" inside other words ("high salary jobs", "hire me") must NOT match.
    """
    if not normalized:
        return False, None

    st_cfg = CONFIG.get("smalltalk", {})
    msgs = CONFIG.get("messages", {})

    greetings = set(st_cfg.get("greetings", []))
    thanks_list = set(st_cfg.get("thanks", []))
    goodbyes_list = set(st_cfg.get("goodbyes", []))

    # Clean punctuation and check exact matches for single phrase
    stripped = re.sub(r'[^\w\s]', '', normalized).strip()

    # Exact matches for whole greeting
    if stripped in greetings:
        return True, msgs.get("greeting_reply")

    if stripped in thanks_list:
        return True, msgs.get("thanks_reply")

    if stripped in goodbyes_list:
        return True, msgs.get("goodbye_reply")

    # Check if message is ONLY a combination of greetings / pleasantries (e.g., "hello namaste", "hey there", "hi good morning")
    words = stripped.split()
    remaining_words = []
    i = 0
    while i < len(words):
        matched = False
        # Try matching two-word greetings (e.g. "good morning", "how are", "whats up")
        if i + 1 < len(words):
            two_word = f"{words[i]} {words[i+1]}"
            if two_word in greetings or two_word in thanks_list or two_word in goodbyes_list:
                i += 2
                matched = True
                continue
        # Try three-word (e.g. "how are you", "kya haal hai")
        if i + 2 < len(words):
            three_word = f"{words[i]} {words[i+1]} {words[i+2]}"
            if three_word in greetings or three_word in thanks_list or three_word in goodbyes_list:
                i += 3
                matched = True
                continue
        # Single word check
        if words[i] in greetings or words[i] in thanks_list or words[i] in goodbyes_list or words[i] in {"there", "bot", "assistant", "bhai", "sir", "madam", "ji", "team"}:
            i += 1
            matched = True
            continue

        remaining_words.append(words[i])
        i += 1

    # If nothing meaningful remains, return the greeting or thanks
    if len(remaining_words) == 0:
        if any(w in thanks_list for w in words):
            return True, msgs.get("thanks_reply")
        if any(w in goodbyes_list for w in words):
            return True, msgs.get("goodbye_reply")
        return True, msgs.get("greeting_reply")

    # If meaningful words remain (like "i know python and fastapi"), it is NOT just small talk
    return False, None

def is_gibberish(normalized: str) -> Tuple[bool, Optional[str]]:
    """
    Detect random/meaningless input (e.g. 'asdfjkl', 'qwerty123', 'xyzabc').
    Strategy:
    - Very short input (1-3 chars) with no recognizable word -> gibberish
    - Input where >60% of characters are consonant clusters (no vowels in any token) -> gibberish
    - Input matching purely random keyboard-mash patterns
    Returns greeting_reply so the user gets a helpful nudge.
    """
    if not normalized:
        return False, None

    msgs = CONFIG.get("messages", {})
    words = normalized.split()

    # Single token checks
    VOWELS = set('aeiou')

    def looks_like_gibberish_word(w: str) -> bool:
        if len(w) < 3:
            return False  # too short to judge
        letters = [c for c in w if c.isalpha()]
        if not letters:
            return False
        # No vowels at all in a word of 4+ letters -> gibberish
        if len(letters) >= 4 and not any(c in VOWELS for c in letters):
            return True
        # Ratio of consecutive consonants extremely high (keyboard-mash)
        consonant_run = 0
        max_run = 0
        for c in letters:
            if c not in VOWELS:
                consonant_run += 1
                max_run = max(max_run, consonant_run)
            else:
                consonant_run = 0
        # 5+ consecutive consonants in a word -> gibberish (e.g. "sdfjk", "qwrtp")
        if max_run >= 5:
            return True
        return False

    if not words:
        return False, None

    gibberish_count = sum(1 for w in words if looks_like_gibberish_word(w))

    # If ALL tokens look like gibberish (and there are 1-3 tokens), treat as gibberish
    if gibberish_count == len(words) and len(words) <= 3:
        return True, msgs.get("greeting_reply")

    # If more than half the words are gibberish in a short message -> gibberish
    if len(words) <= 4 and gibberish_count > len(words) / 2:
        return True, msgs.get("greeting_reply")

    return False, None

def is_out_of_scope(normalized: str) -> Tuple[bool, Optional[str]]:
    """
    STEP 4: SCOPE CHECK (cheap, rule-based first)
    Allowed topics: tech jobs and roles, skills and tech stacks, resumes and interviews for tech roles,
    salary ranges in tech, learning roadmaps, certifications, switching into tech, remote tech work in India.
    If message is clearly unrelated (cricket, movies, medical, legal, essays, etc.), reply with scope refusal.
    If message is ambiguous or tech-related, let it through.
    """
    scope_cfg = CONFIG.get("scope", {})
    msgs = CONFIG.get("messages", {})

    disallowed = scope_cfg.get("disallowed_domains", [])
    allowed_tech = scope_cfg.get("allowed_tech_keywords", [])

    # Check if any disallowed domain is explicitly present
    has_disallowed = False
    for bad in disallowed:
        pattern = r'\b' + re.escape(bad) + r'\b'
        if re.search(pattern, normalized):
            has_disallowed = True
            break

    # Check if any allowed tech keyword is present
    has_allowed_tech = False
    for tech in allowed_tech:
        pattern = r'\b' + re.escape(tech) + r'\b'
        if re.search(pattern, normalized):
            has_allowed_tech = True
            break

    # If it has a disallowed topic and NO tech keywords, block as out of scope
    if has_disallowed and not has_allowed_tech:
        return True, msgs.get("scope_refusal")

    return False, None

def check_output(model_reply: str) -> str:
    """
    STEP 6: OUTPUT CHECK
    Run the model reply through the same safety filter. If it fails, replace it with the fixed refusal message.
    """
    if not model_reply:
        return model_reply

    norm_reply = normalize_text(model_reply)
    is_blocked, refusal, _ = is_unsafe(norm_reply)
    if is_blocked:
        return CONFIG.get("messages", {}).get("safety_refusal", "I can only help with tech jobs, careers and learning roadmaps.")

    return model_reply

def run_guardrails_pipeline(
    user_input: str,
    user_or_session_id: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Runs the pre-LLM pipeline:
    1. Normalize
    2. Check rate limit
    3. Safety filter
    4. Small talk / greeting handler
    5. Scope check

    Returns:
    (should_stop, response_text, stage_name)
    If should_stop is False, response_text is None, and execution proceeds to Groq LLM.
    """
    stripped = user_input.strip()
    if not stripped:
        return False, None, None

    identifier = user_or_session_id or "anonymous"

    # Step 1: Normalize
    normalized = normalize_text(user_input)

    # Step 2: Safety filter (may record violation)
    blocked, refusal, category = is_unsafe(normalized)
    if blocked:
        record_violation(identifier, category or "unsafe_content")
        return True, refusal, "safety_filter"

    # Step 3: Rate limit check (after possible violation recording)
    is_limited, limit_msg = is_rate_limited(identifier)
    if is_limited:
        return True, limit_msg, "rate_limit"

    # Step 4: Greeting and small talk
    is_small_talk, reply = detect_small_talk(user_input, normalized)
    if is_small_talk:
        return True, reply, "small_talk"

    # Step 4b: Gibberish / keyboard-mash detection -> returns greeting nudge
    gibberish, gibberish_reply = is_gibberish(normalized)
    if gibberish:
        return True, gibberish_reply, "small_talk"

    # Step 5: Scope check
    out_of_scope, scope_refusal = is_out_of_scope(normalized)
    if out_of_scope:
        return True, scope_refusal, "scope_filter"

    return False, None, None
