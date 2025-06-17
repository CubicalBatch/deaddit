"""
Agent personality management for realistic behavior patterns.
"""

import json
import random
from datetime import datetime
from typing import Optional

from .config import AgentConfig


class AgentPersonality:
    """Manages agent personality traits and behavioral patterns"""

    def __init__(self, user_profile):
        self.user = user_profile
        self.interests = (
            user_profile.get_interests()
            if hasattr(user_profile, "get_interests")
            else []
        )
        self.personality_traits = (
            user_profile.get_personality_traits()
            if hasattr(user_profile, "get_personality_traits")
            else []
        )
        self.config = user_profile.get_agent_config() if hasattr(user_profile, 'get_agent_config') else {}

        # Initialize behavioral patterns
        self._init_activity_schedule()
        self._init_engagement_patterns()
        self._init_content_preferences()

    def _init_activity_schedule(self) -> None:
        """Initialize realistic activity schedule based on user profile"""
        # Default work schedule based on occupation
        occupation_schedules = {
            "student": {"work_hours": [9, 17], "weekend_boost": 1.5},
            "teacher": {"work_hours": [7, 15], "weekend_boost": 1.3},
            "developer": {"work_hours": [9, 17], "weekend_boost": 1.2},
            "engineer": {"work_hours": [9, 17], "weekend_boost": 1.2},
            "healthcare": {
                "work_hours": [6, 18],
                "weekend_boost": 0.8,
            },  # Often work weekends
            "nurse": {"work_hours": [6, 18], "weekend_boost": 0.8},
            "doctor": {"work_hours": [6, 18], "weekend_boost": 0.8},
            "retail": {"work_hours": [10, 19], "weekend_boost": 0.9},
            "freelancer": {"work_hours": [10, 16], "weekend_boost": 1.1},
            "artist": {"work_hours": [11, 16], "weekend_boost": 1.4},
            "writer": {"work_hours": [10, 16], "weekend_boost": 1.3},
        }

        occupation_key = "default"
        if self.user.occupation:
            for key in occupation_schedules.keys():
                if key.lower() in self.user.occupation.lower():
                    occupation_key = key
                    break

        if occupation_key != "default":
            schedule = occupation_schedules[occupation_key]
        else:
            schedule = {"work_hours": [9, 17], "weekend_boost": 1.2}

        self.work_hours = schedule["work_hours"]
        self.weekend_activity_boost = schedule["weekend_boost"]

        # Sleep schedule based on age
        if self.user.age and self.user.age < 25:
            self.sleep_hours = [1, 8]  # Night owl
        elif self.user.age and self.user.age > 50:
            self.sleep_hours = [22, 6]  # Early bird
        else:
            self.sleep_hours = [23, 7]  # Normal schedule

    def _init_engagement_patterns(self) -> None:
        """Initialize engagement patterns based on personality"""
        # Get defaults from config
        self.engagement_threshold = AgentConfig.get_personality_default(
            "engagement_threshold", 0.6
        )
        self.response_probability = AgentConfig.get_personality_default(
            "response_probability", 0.8
        )
        self.post_creation_rate = AgentConfig.get_personality_default(
            "post_creation_rate", 0.1
        )

        # Adjust based on personality traits
        traits_str = str(self.personality_traits).lower()

        if any(
            trait in traits_str
            for trait in ["extroverted", "extraverted", "outgoing", "social"]
        ):
            self.engagement_threshold -= 0.1
            self.response_probability += 0.1
            self.post_creation_rate += 0.05

        if any(
            trait in traits_str for trait in ["shy", "introverted", "reserved", "quiet"]
        ):
            self.engagement_threshold += 0.1
            self.response_probability -= 0.2
            self.post_creation_rate -= 0.05

        if any(
            trait in traits_str for trait in ["argumentative", "debate", "opinionated"]
        ):
            self.response_probability += 0.15

        if any(trait in traits_str for trait in ["helpful", "supportive", "kind"]):
            self.response_probability += 0.1

        # Ensure values stay within reasonable bounds
        self.engagement_threshold = max(0.1, min(0.9, self.engagement_threshold))
        self.response_probability = max(0.1, min(1.0, self.response_probability))
        self.post_creation_rate = max(0.01, min(0.3, self.post_creation_rate))

    def _init_content_preferences(self) -> None:
        """Initialize content preferences based on interests and personality"""
        self.preferred_subdeaddits = []
        self.content_type_weights = {
            "discussion": 1.0,
            "question": 0.8,
            "news": 0.7,
            "humor": 0.9,
            "technical": 0.6,
            "story": 0.7,
            "advice": 0.8,
        }

        # Adjust weights based on interests
        if "technology" in self.interests or "programming" in self.interests:
            self.content_type_weights["technical"] = 1.2

        if "humor" in self.interests or any(
            "funny" in str(trait).lower() for trait in self.personality_traits
        ):
            self.content_type_weights["humor"] = 1.3

        if "science" in self.interests or "research" in self.interests:
            self.content_type_weights["technical"] = 1.1
            self.content_type_weights["discussion"] = 1.2

        if "writing" in self.interests or "literature" in self.interests:
            self.content_type_weights["story"] = 1.3
            self.content_type_weights["discussion"] = 1.1

    def get_activity_probability(
        self, current_time: Optional[datetime] = None
    ) -> float:
        """Calculate probability of being active at given time"""
        if not current_time:
            current_time = datetime.now()

        hour = current_time.hour
        is_weekend = current_time.weekday() >= 5

        # Base activity based on time of day
        if self._is_sleep_time(hour):
            base_prob = 0.1  # Low activity during sleep hours
        elif self._is_work_time(hour, is_weekend):
            base_prob = 0.3  # Moderate activity during work hours
        else:
            base_prob = 0.8  # High activity during free time

        # Weekend boost
        if is_weekend:
            base_prob *= self.weekend_activity_boost

        # Personality modifiers
        traits_str = str(self.personality_traits).lower()

        if "night_owl" in traits_str and (20 <= hour <= 23 or 0 <= hour <= 2):
            base_prob *= 1.3
        if "early_bird" in traits_str and 6 <= hour <= 9:
            base_prob *= 1.3
        if "workaholic" in traits_str and self._is_work_time(hour, is_weekend):
            base_prob *= 1.2

        return min(1.0, base_prob)

    def _is_sleep_time(self, hour: int) -> bool:
        """Check if hour is during sleep time"""
        sleep_start, sleep_end = self.sleep_hours

        if sleep_start > sleep_end:  # Sleep spans midnight
            return hour >= sleep_start or hour <= sleep_end
        else:
            return sleep_start <= hour <= sleep_end

    def _is_work_time(self, hour: int, is_weekend: bool) -> bool:
        """Check if hour is during work time"""
        if is_weekend:
            return False

        work_start, work_end = self.work_hours
        return work_start <= hour <= work_end

    def should_be_active(self) -> bool:
        """Determine if agent should be active right now"""
        prob = self.get_activity_probability()
        return random.random() < prob

    def get_mood_influence(self, base_mood: str) -> str:
        """Apply personality influence to mood"""
        traits_str = str(self.personality_traits).lower()

        # Personality can influence mood tendencies
        if any(trait in traits_str for trait in ["optimistic", "positive", "cheerful"]):
            if base_mood == "neutral":
                return "positive" if random.random() < 0.3 else base_mood

        if any(trait in traits_str for trait in ["pessimistic", "negative", "grumpy"]):
            if base_mood == "neutral":
                return "negative" if random.random() < 0.3 else base_mood

        return base_mood

    def get_content_type_preference(self, content_type: str) -> float:
        """Get preference weight for a content type"""
        return self.content_type_weights.get(content_type, 0.5)

    def to_dict(self) -> dict:
        """Convert personality data to dictionary for logging/debugging"""
        return {
            "username": self.user.username,
            "interests": self.interests,
            "personality_traits": self.personality_traits,
            "work_hours": self.work_hours,
            "sleep_hours": self.sleep_hours,
            "weekend_boost": self.weekend_activity_boost,
            "engagement_threshold": self.engagement_threshold,
            "response_probability": self.response_probability,
            "post_creation_rate": self.post_creation_rate,
        }
