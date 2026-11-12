
import re


POSITIVE_WORDS = {
    "good", "great", "excellent", "amazing",
    "love", "easy", "fast", "useful", "happy",
    "perfect", "best", "wonderful", "helpful",
    "smooth", "reliable", "intuitive", "enjoy",
    "beautiful", "efficient", "convenient",
}

NEGATIVE_WORDS = {
    "bad", "poor", "terrible", "slow",
    "hate", "difficult", "broken", "worst",
    "expensive", "crash", "problem", "bug",
    "confusing", "frustrating", "unusable",
    "unreliable", "failure", "error", "unstable",
    "lag", "stop", "issue", "annoying",
    "disappointing", "poorly",
}

WORD_NORMALIZATION = {
    "crashes": "crash",
    "crashing": "crash",
    "crashed": "crash",
    "downloads": "download",
    "downloading": "download",
    "options": "option",
    "features": "feature",
    "subtitles": "subtitle",
    "faster": "fast",
    "fastest": "fast",
    "slower": "slow",
    "slows": "slow",
    "stops": "stop",
    "stopped": "stop",
    "stopping": "stop",
    "errors": "error",
    "bugs": "bug",
    "issues": "issue",
    "payments": "payment",
    "subscriptions": "subscription",
    "improvements": "improvement",
    "searches": "search",
}

TOPIC_KEYWORDS = {
    "pricing": {
        "price", "cost", "expensive", "cheap",
        "payment", "billing", "subscription",
        "refund", "charge",
    },
    "performance": {
        "slow", "fast", "speed", "lag",
        "crash", "loading", "latency",
        "playback", "stop", "buffering",
        "download",
    },
    "usability": {
        "easy", "difficult", "confusing",
        "interface", "navigation", "workflow",
        "intuitive", "accessibility",
    },
    "design": {
        "design", "colour", "color", "layout",
        "appearance", "visual", "beautiful",
    },
    "support": {
        "support", "service", "help",
        "assistance", "customer",
    },
    "features": {
        "feature", "option", "function",
        "request", "functionality", "capability",
        "subtitle", "search", "add",
        "improvement",
    },
    "reliability": {
        "broken", "error", "bug", "failure",
        "crash", "unstable", "reliable",
        "unreliable", "issue",
    },
}

REQUEST_PHRASES = (
    "please add",
    "please improve",
    "would like",
    "wish there was",
    "wish there were",
    "feature request",
    "it would be nice",
    "could you add",
    "could you improve",
    "should add",
    "need a feature",
    "need the option",
)

QUESTION_WORDS = {
    "what", "why", "when", "where",
    "who", "how",
}


def _words(text: str) -> set[str]:
    raw_words = re.findall(r"\b[a-z0-9]+\b", text.lower())

    return {
        WORD_NORMALIZATION.get(word, word)
        for word in raw_words
    }


def analyze_feedback(text: str) -> dict:
    """
    Lightweight rule-based feedback analysis.

    Returns:
        sentiment: positive, negative, mixed, neutral, unknown
        topics: list of detected topics
        topic: first topic for compatibility
        feedback_type: complaint, feature_request,
                       praise, question, other

    This is a heuristic classifier, not a trained ML model.
    """

    if not isinstance(text, str) or not text.strip():
        return {
            "sentiment": "unknown",
            "topics": ["general"],
            "topic": "general",
            "feedback_type": "other",
        }

    normalized = text.lower()
    tokens = _words(normalized)

    positive_score = len(tokens.intersection(POSITIVE_WORDS))
    negative_score = len(tokens.intersection(NEGATIVE_WORDS))

    if positive_score > 0 and negative_score > 0:
        sentiment = "mixed"
    elif positive_score > negative_score:
        sentiment = "positive"
    elif negative_score > positive_score:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    matched_topics = []

    for category, keywords in TOPIC_KEYWORDS.items():
        if tokens.intersection(keywords):
            matched_topics.append(category)

    if not matched_topics:
        matched_topics = ["general"]

    is_feature_request = any(
        phrase in normalized
        for phrase in REQUEST_PHRASES
    )

    is_question = (
        "?" in text
        or bool(tokens.intersection(QUESTION_WORDS))
    )

    # Feedback type is classified independently from sentiment.
    if is_feature_request:
        feedback_type = "feature_request"
    elif is_question:
        feedback_type = "question"
    elif negative_score > 0:
        feedback_type = "complaint"
    elif positive_score > 0:
        feedback_type = "praise"
    else:
        feedback_type = "other"

    # For explicit feature requests, prioritize the features topic.
    if (
        feedback_type == "feature_request"
        and "features" in matched_topics
    ):
        matched_topics.remove("features")
        matched_topics.insert(0, "features")

    return {
        "sentiment": sentiment,
        "topics": matched_topics,
        "topic": matched_topics[0],
        "feedback_type": feedback_type,
    }
