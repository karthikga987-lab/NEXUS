
def analyze_feedback(text):
    text = text.lower()

    positive_words = [
        "good", "great", "excellent", "amazing",
        "love", "easy", "fast", "useful", "happy",
        "perfect", "best", "wonderful"
    ]

    negative_words = [
        "bad", "poor", "terrible", "slow",
        "hate", "difficult", "broken", "worst",
        "expensive", "crash", "problem", "bug"
    ]

    positive_score = sum(word in text for word in positive_words)
    negative_score = sum(word in text for word in negative_words)

    if positive_score > negative_score:
        sentiment = "positive"
    elif negative_score > positive_score:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    topics = {
        "pricing": ["price", "cost", "expensive", "cheap", "payment"],
        "performance": ["slow", "fast", "speed", "lag", "crash"],
        "usability": ["easy", "difficult", "confusing", "interface"],
        "design": ["design", "colour", "color", "layout", "appearance"],
        "support": ["support", "service", "help", "customer care"],
        "features": ["feature", "option", "function", "request"],
        "reliability": ["broken", "error", "bug", "failure"]
    }

    topic = "general"

    for category, keywords in topics.items():
        if any(word in text for word in keywords):
            topic = category
            break

    return {
        "sentiment": sentiment,
        "topic": topic
    }
