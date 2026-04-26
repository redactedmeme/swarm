# redacted-chan-bot/behavior_pattern_tracker.py
"""
Behavior Pattern Tracker — detects recurring patterns in conversation.

Tracks: topic clusters, growth signals, recurring concerns.
Helps redacted-chan offer proactive insights: "I've noticed you come back to X..."

Uses conversation facts to detect patterns. No persistence — patterns live in-memory.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Topic keywords
TOPICS = {
    "work": ["work", "job", "project", "deadline", "boss", "meeting", "team"],
    "relationships": ["friend", "family", "partner", "dating", "love", "lonely"],
    "creativity": ["create", "write", "art", "music", "design", "build"],
    "identity": ["who i am", "myself", "change", "becoming", "growth"],
    "philosophy": ["meaning", "why", "exist", "real", "truth", "soul"],
    "health": ["tired", "sleep", "exercise", "body", "energy"],
}

GROWTH_SIGNALS = {
    "boundary": ["can't", "don't want", "saying no", "stop", "i won't"],
    "trying": ["trying", "attempt", "new", "first time"],
    "realization": ["realize", "i understand", "i see", "aha"],
}


class PatternTracker:
    """Track behavioral patterns per user (in-memory, session-scoped)."""

    def __init__(self):
        self.topics: dict[int, dict] = defaultdict(lambda: defaultdict(int))
        self.growth_moments: dict[int, list] = defaultdict(list)
        self.recurring_concerns: dict[int, dict] = defaultdict(lambda: defaultdict(int))

    def update_from_facts(self, user_id: int, facts: list[dict]) -> None:
        """Update patterns from conversation facts."""
        if not facts:
            return

        for fact in facts:
            content = fact.get("fact", fact.get("content", "")).lower()
            if not content:
                continue

            # Topic clustering
            for topic, keywords in TOPICS.items():
                if any(kw in content for kw in keywords):
                    self.topics[user_id][topic] += 1

            # Growth signals
            for signal_type, keywords in GROWTH_SIGNALS.items():
                if any(kw in content for kw in keywords):
                    self.growth_moments[user_id].append(signal_type)

            # Recurring concerns (repeated mentions)
            if any(word in content for word in ["still", "again", "still struggling", "can't"]):
                for topic in TOPICS:
                    if any(kw in content for kw in TOPICS[topic]):
                        self.recurring_concerns[user_id][topic] += 1
                        break

    def get_patterns(self, user_id: int) -> str:
        """Return formatted pattern summary for system prompt."""
        if user_id not in self.topics or not self.topics[user_id]:
            return ""

        lines = []

        # Top topics
        top_topics = sorted(
            self.topics[user_id].items(), key=lambda x: x[1], reverse=True
        )[:2]
        if top_topics:
            topic_str = ", ".join(f"{t} ({c}x)" for t, c in top_topics)
            lines.append(f"Topics they return to: {topic_str}")

        # Recurring concerns
        if self.recurring_concerns[user_id]:
            recurring = sorted(
                self.recurring_concerns[user_id].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:1]
            for concern, count in recurring:
                if count >= 3:
                    lines.append(f"Recurring: {concern} (mentioned {count}+ times)")

        # Growth signals
        if self.growth_moments[user_id]:
            growth_types = defaultdict(int)
            for moment in self.growth_moments[user_id]:
                growth_types[moment] += 1
            growth_str = ", ".join(f"{t} ({c}x)" for t, c in growth_types.items())
            lines.append(f"Growth: {growth_str}")

        if not lines:
            return ""

        return "## Behavior Patterns\n" + "\n".join(f"- {line}" for line in lines)

    def clear(self, user_id: int) -> None:
        """Clear patterns for a user."""
        self.topics.pop(user_id, None)
        self.recurring_concerns.pop(user_id, None)
        self.growth_moments.pop(user_id, None)


# Global instance
_tracker = PatternTracker()


def update(user_id: int, facts: list[dict]) -> None:
    """Update patterns from conversation facts."""
    _tracker.update_from_facts(user_id, facts)


def get_patterns(user_id: int) -> str:
    """Get formatted pattern summary for system prompt."""
    return _tracker.get_patterns(user_id)


def clear(user_id: int) -> None:
    """Clear patterns for a user."""
    _tracker.clear(user_id)
