import re
from collections import Counter

# Common general stopwords to filter out from raw frequency analysis
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did", "this", "that",
    "these", "those", "they", "them", "their", "what", "which", "who", "whom", "will",
    "would", "shall", "should", "can", "could", "may", "might", "must", "it", "its"
}

class TopicExtractor:
    @staticmethod
    def extract_keywords(text: str, max_topics: int = 8) -> list[str]:
        """
        Extracts high-frequency topical phrases and keywords from video text.
        """
        if not text:
            return []

        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        filtered = [w for w in words if w not in STOPWORDS]
        counts = Counter(filtered)
        
        # Return top non-trivial terms title-cased
        return [word.title() for word, _ in counts.most_common(max_topics)]
