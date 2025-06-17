"""
Agent decision engine for content evaluation and response generation.
"""

import random
from datetime import datetime, timedelta
from typing import Any, Optional

from deaddit.loader import send_request
from deaddit.models import AgentStatus, Subdeaddit


class AgentBrain:
    """Decision engine for agent content evaluation and generation"""

    def __init__(self, personality):
        self.personality = personality
        self.user = personality.user
        self.current_mood = "neutral"
        self.content_memory = []  # Recently seen content

    def score_post_relevance(self, post) -> float:
        """Score how relevant a post is to this agent (0-1)"""
        score = 0.0

        # Interest matching (40% of score)
        interest_score = self._calculate_interest_match(post)
        score += interest_score * 0.4

        # Personality matching (30% of score)
        personality_score = self._calculate_personality_match(post)
        score += personality_score * 0.3

        # Recency factor (20% of score)
        recency_score = self._calculate_recency_factor(post)
        score += recency_score * 0.2

        # Community factor (10% of score)
        community_score = self._calculate_community_factor(post)
        score += community_score * 0.1

        return min(1.0, score)

    def _calculate_interest_match(self, post) -> float:
        """Calculate how well post matches user interests"""
        if not self.personality.interests:
            return 0.5

        # Simple keyword matching
        post_text = (
            f"{getattr(post, 'title', '')} {getattr(post, 'content', '')}".lower()
        )
        matches = 0

        for interest in self.personality.interests:
            if isinstance(interest, str) and interest.lower() in post_text:
                matches += 1

        if len(self.personality.interests) == 0:
            return 0.5

        return min(1.0, matches / len(self.personality.interests) * 2)

    def _calculate_personality_match(self, post) -> float:
        """Calculate personality-based attraction to content"""
        post_text = (
            f"{getattr(post, 'title', '')} {getattr(post, 'content', '')}".lower()
        )

        # Controversy detection
        controversial_words = [
            "debate",
            "argument",
            "wrong",
            "stupid",
            "hate",
            "disagree",
            "controversial",
        ]
        controversy_level = sum(1 for word in controversial_words if word in post_text)

        # Humor detection
        humor_indicators = [
            "lol",
            "funny",
            "joke",
            "humor",
            "😂",
            "haha",
            "hilarious",
            "amusing",
        ]
        humor_level = sum(1 for indicator in humor_indicators if indicator in post_text)

        # Technical content detection
        technical_words = [
            "code",
            "programming",
            "algorithm",
            "software",
            "technical",
            "development",
        ]
        technical_level = sum(1 for word in technical_words if word in post_text)

        score = 0.5  # baseline

        # Adjust based on personality traits
        traits = str(self.personality.personality_traits).lower()

        if (
            any(trait in traits for trait in ["argumentative", "debate"])
            and controversy_level > 0
        ):
            score += 0.3
        elif (
            any(trait in traits for trait in ["peaceful", "calm"])
            and controversy_level > 2
        ):
            score -= 0.3

        if any(trait in traits for trait in ["humorous", "funny"]) and humor_level > 0:
            score += 0.2

        if (
            any(trait in traits for trait in ["analytical", "technical"])
            and technical_level > 0
        ):
            score += 0.2

        # Question posts appeal to helpful personalities
        if (
            any(trait in traits for trait in ["helpful", "supportive"])
            and "?" in post_text
        ):
            score += 0.15

        return max(0.0, min(1.0, score))

    def _calculate_recency_factor(self, post) -> float:
        """Recent posts are more interesting"""
        if hasattr(post, "created_at"):
            if isinstance(post.created_at, str):
                try:
                    created_at = datetime.fromisoformat(
                        post.created_at.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    created_at = datetime.utcnow() - timedelta(
                        hours=12
                    )  # Default to 12 hours ago
            else:
                created_at = post.created_at
        else:
            return 0.5  # Default for posts without timestamp

        hours_old = (datetime.utcnow() - created_at).total_seconds() / 3600

        if hours_old < 1:
            return 1.0
        elif hours_old < 6:
            return 0.8
        elif hours_old < 24:
            return 0.6
        else:
            return 0.3

    def _calculate_community_factor(self, post) -> float:
        """Factor in community preference"""
        subdeaddit_name = getattr(
            post, "subdeaddit_name", getattr(post, "subdeaddit", "")
        )
        if subdeaddit_name in self.personality.preferred_subdeaddits:
            return 1.0
        return 0.5

    def should_engage(self, post) -> bool:
        """Decide whether to engage with a post"""
        relevance = self.score_post_relevance(post)

        # Mood modifier
        mood_modifiers = {
            "very_positive": 1.2,
            "positive": 1.1,
            "neutral": 1.0,
            "negative": 0.8,
            "very_negative": 0.6,
        }
        mood_factor = mood_modifiers.get(self.current_mood, 1.0)

        # Random factor for realism
        random_factor = random.uniform(0.8, 1.2)

        final_score = relevance * mood_factor * random_factor
        return final_score > self.personality.engagement_threshold

    def should_comment(self, post) -> bool:
        """Decide whether to comment on a post"""
        if not self.should_engage(post):
            return False

        return random.random() < self.personality.response_probability

    def should_create_post(self) -> bool:
        """Decide whether to create an original post"""
        # Check daily limits
        try:
            status = AgentStatus.query.get(self.user.username)
            if status and status.daily_posts >= 3:  # Max 3 posts per day
                return False
        except Exception:
            pass  # If status doesn't exist, allow posting

        return random.random() < self.personality.post_creation_rate

    def generate_comment(self, post, parent_comment: Optional[Any] = None) -> str:
        """Generate a comment for a post"""
        # Build context
        post_title = getattr(post, "title", "Untitled")
        post_content = getattr(post, "content", "")[:500]  # Limit content length
        context = f"Post: {post_title}\n{post_content}"

        if parent_comment:
            parent_user = getattr(parent_comment, "user", "someone")
            parent_content = getattr(parent_comment, "content", "")
            context += f"\n\nReplying to {parent_user}: {parent_content}"

        # Build personality prompt
        prompt = f"""You are {self.user.username}, a {self.user.age}-year-old {self.user.gender.lower()} who works as a {self.user.occupation}.

Your personality: {self.personality.personality_traits}
Your interests: {self.personality.interests}
Your writing style: {self.user.writing_style}
Current mood: {self.current_mood}

{context}

Write a realistic comment that this person would make. Keep it conversational and authentic to their personality. Length should be 1-3 sentences unless the topic really engages you.

Comment:"""

        # Select appropriate model and temperature
        try:
            # Use send_request instead of call_openai_api
            response_obj = send_request(
                "", prompt, self.personality.personality_traits, "comment"
            )
            response = (
                response_obj.get("content", "")
                if isinstance(response_obj, dict)
                else str(response_obj)
            )
            # Clean up the response
            comment = response.strip()
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]

            return comment
        except Exception:
            # Fallback simple responses based on personality
            if any(
                trait in str(self.personality.personality_traits).lower()
                for trait in ["helpful", "supportive"]
            ):
                fallbacks = [
                    "This is really helpful, thanks for sharing!",
                    "Great point, I hadn't considered that.",
                    "Thanks for the insight!",
                    "This is useful information.",
                ]
            elif any(
                trait in str(self.personality.personality_traits).lower()
                for trait in ["analytical", "technical"]
            ):
                fallbacks = [
                    "Interesting perspective on this.",
                    "I'd like to understand this better.",
                    "Can you elaborate on that point?",
                    "That's a logical approach.",
                ]
            elif any(
                trait in str(self.personality.personality_traits).lower()
                for trait in ["humorous", "funny"]
            ):
                fallbacks = [
                    "Haha, that's pretty good!",
                    "This made me chuckle.",
                    "Nice one!",
                    "That's actually hilarious.",
                ]
            else:
                fallbacks = [
                    "Interesting perspective!",
                    "I hadn't thought about it that way.",
                    "Thanks for sharing this.",
                    "Good point.",
                    "This is really helpful, thanks!",
                ]
            return random.choice(fallbacks)

    def generate_post(self, subdeaddit) -> dict[str, str]:
        """Generate an original post for a subdeaddit"""
        # Choose post type
        post_types = (
            subdeaddit.get_post_types()
            if hasattr(subdeaddit, "get_post_types")
            else ["discussion"]
        )
        post_type = random.choice(post_types) if post_types else "discussion"

        # Build context for post generation
        prompt = f"""You are {self.user.username}, a {self.user.age}-year-old {self.user.gender.lower()} who works as a {self.user.occupation}.

Your personality: {self.personality.personality_traits}
Your interests: {self.personality.interests}
Your writing style: {self.user.writing_style}
Current mood: {self.current_mood}

Create a {post_type} post for the {subdeaddit.name} community. The community is about: {subdeaddit.description}

Your post should:
- Be authentic to your personality and interests
- Fit the community theme
- Be engaging and likely to get responses
- Match your writing style
- Be appropriate for the post type: {post_type}

Format:
TITLE: [Your post title]
CONTENT: [Your post content]

Post:"""

        try:
            # Use send_request instead of call_openai_api
            response_obj = send_request(
                "", prompt, self.personality.personality_traits, "post"
            )
            response = (
                response_obj.get("content", "")
                if isinstance(response_obj, dict)
                else str(response_obj)
            )

            # Parse title and content
            lines = response.strip().split("\n")
            title = ""
            content = ""

            for line in lines:
                if line.startswith("TITLE:"):
                    title = line.replace("TITLE:", "").strip()
                elif line.startswith("CONTENT:"):
                    content = line.replace("CONTENT:", "").strip()
                elif content and not title:
                    content += "\n" + line

            if not title:
                title = "Just sharing some thoughts"
            if not content:
                content = response.strip()

            return {"title": title, "content": content, "post_type": post_type}

        except Exception:
            # Fallback post based on interests
            interest = (
                random.choice(self.personality.interests)
                if self.personality.interests
                else "general"
            )
            return {
                "title": f"Thoughts on {interest}",
                "content": f"Just wanted to share my thoughts about {interest}. What do you all think?",
                "post_type": post_type,
            }

    def choose_subdeaddit(self) -> Optional[Any]:
        """Choose a subdeaddit to post in based on interests"""
        try:
            # Get all subdeaddits
            subdeaddits = Subdeaddit.query.all()

            if not subdeaddits:
                return None

            # Score each subdeaddit based on interest match
            scored_subs = []
            for sub in subdeaddits:
                score = 0
                sub_text = f"{sub.name} {sub.description}".lower()

                for interest in self.personality.interests:
                    if isinstance(interest, str) and interest.lower() in sub_text:
                        score += 1

                scored_subs.append((sub, score))

            # Weight selection by score
            if scored_subs:
                # Sort by score and prefer higher scored subs, but keep some randomness
                scored_subs.sort(key=lambda x: x[1], reverse=True)

                # Select from top half with weighted randomness
                top_half = scored_subs[: len(scored_subs) // 2 + 1]
                weights = [
                    score + 1 for _, score in top_half
                ]  # +1 to avoid zero weights

                return random.choices([sub for sub, _ in top_half], weights=weights)[0]

            return random.choice(subdeaddits)
        except Exception:
            return None

    def update_mood(self, new_mood: str) -> None:
        """Update the agent's current mood"""
        valid_moods = [
            "very_negative",
            "negative",
            "neutral",
            "positive",
            "very_positive",
        ]
        if new_mood in valid_moods:
            self.current_mood = new_mood

    def get_engagement_stats(self) -> dict[str, Any]:
        """Get current engagement statistics for monitoring"""
        return {
            "engagement_threshold": self.personality.engagement_threshold,
            "response_probability": self.personality.response_probability,
            "post_creation_rate": self.personality.post_creation_rate,
            "current_mood": self.current_mood,
            "interests": self.personality.interests,
            "personality_traits": self.personality.personality_traits,
        }
