"""
Main agent controller for Deaddit AI agents.
"""

import random
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger

from deaddit import db
from deaddit.models import (
    AgentActionType,
    AgentActivity,
    AgentLLMInteraction,
    AgentMood,
    AgentState,
    AgentStatus,
    User,
)

from .actions import SyncAgentAPIClient
from .brain import AgentBrain
from .personality import AgentPersonality


class DeadditAgent:
    """Main controller for a Deaddit AI agent"""

    def __init__(self, username: str):
        self.username = username
        self.user = User.query.get(username)

        if not self.user:
            raise ValueError(f"User {username} does not exist")

        if not self.user.is_agent:
            raise ValueError(f"User {username} is not configured as an agent")

        self.personality = AgentPersonality(self.user)
        self.brain = AgentBrain(self.personality)
        self.api_client = SyncAgentAPIClient()

        # Get or create agent status
        self.status = AgentStatus.query.get(username)
        if not self.status:
            self.status = AgentStatus(user_id=username)
            db.session.add(self.status)
            db.session.commit()

    def run_cycle(self) -> dict[str, Any]:
        """Main agent execution cycle"""
        # Create activity record for the cycle
        activity = AgentActivity(
            agent_id=self.username,
            action_type=AgentActionType.BROWSE,
            context={"action": "cycle", "type": "regular_cycle"}
        )
        db.session.add(activity)
        db.session.commit()

        cycle_result = {
            "agent": self.username,
            "timestamp": datetime.utcnow().isoformat(),
            "actions_taken": [],
            "errors": [],
            "was_active": False,
            "activity_id": activity.id,
        }

        try:
            logger.info(f"Agent {self.username} starting cycle")

            # Check if agent should be active
            if not self._should_be_active():
                logger.debug(f"Agent {self.username} not active at this time")
                self._update_status(AgentState.OFFLINE)
                cycle_result["reason"] = "not_active_time"
                activity.complete(result={"reason": "not_active_time"})
                return cycle_result

            cycle_result["was_active"] = True

            # Reset daily counters if needed
            self._reset_daily_counters()

            # Update mood
            self._update_mood()

            # Determine current state and execute actions
            actions = self._execute_state_actions(activity)
            cycle_result["actions_taken"] = actions

            # Update status
            self.status.last_activity = datetime.utcnow()
            self.user.last_agent_activity = datetime.utcnow()

            # Complete the activity
            activity.complete(result={
                "actions_count": len(actions),
                "actions": actions
            })
            db.session.commit()

            logger.info(
                f"Agent {self.username} cycle completed with {len(actions)} actions"
            )

        except Exception as e:
            error_msg = f"Error in agent {self.username} cycle: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            cycle_result["errors"].append(error_msg)
            activity.complete(error=error_msg)
            db.session.commit()

        return cycle_result

    def _should_be_active(self) -> bool:
        """Check if agent should be active now"""
        if not self.user.agent_enabled:
            return False
        return self.personality.should_be_active()

    def _reset_daily_counters(self):
        """Reset daily post/comment counters if it's a new day"""
        today = datetime.utcnow().date()
        if self.status.last_reset < today:
            self.status.daily_posts = 0
            self.status.daily_comments = 0
            self.status.last_reset = today
            logger.debug(f"Reset daily counters for agent {self.username}")

    def _update_mood(self):
        """Update agent mood based on recent interactions and randomness"""
        # Simple mood evolution with personality influence
        moods = list(AgentMood)
        current_idx = moods.index(self.status.current_mood)

        # Small chance to change mood (10% by default)
        if random.random() < 0.1:
            # Tend toward neutral, but allow some variation
            if current_idx > 2:  # Currently positive
                new_idx = random.choice([current_idx - 1, current_idx, 2])
            elif current_idx < 2:  # Currently negative
                new_idx = random.choice([current_idx + 1, current_idx, 2])
            else:  # Currently neutral
                new_idx = random.choice([1, 2, 3])  # Can go any direction

            old_mood = self.status.current_mood.value
            self.status.current_mood = moods[new_idx]
            self.brain.current_mood = self.status.current_mood.value

            # Apply personality influence
            influenced_mood = self.personality.get_mood_influence(
                self.brain.current_mood
            )
            if influenced_mood != self.brain.current_mood:
                for mood in moods:
                    if mood.value == influenced_mood:
                        self.status.current_mood = mood
                        self.brain.current_mood = influenced_mood
                        break

            if old_mood != self.status.current_mood.value:
                logger.debug(
                    f"Agent {self.username} mood changed from {old_mood} to {self.status.current_mood.value}"
                )

    def _update_status(self, state: AgentState):
        """Update agent status in database"""
        old_state = self.status.current_state
        self.status.current_state = state
        self.status.last_activity = datetime.utcnow()

        if old_state != state:
            logger.debug(
                f"Agent {self.username} state changed from {old_state.value} to {state.value}"
            )

        db.session.commit()

    def _execute_state_actions(self, parent_activity) -> list:
        """Execute actions based on current state logic"""
        actions_taken = []

        # Determine what to do based on personality and randomness
        action_probabilities = {
            "browse": 0.7,
            "create_post": 0.1 if self.status.daily_posts < 3 else 0,
            "respond_to_notifications": 0.2,
        }

        # Choose action
        action = random.choices(
            list(action_probabilities.keys()),
            weights=list(action_probabilities.values()),
        )[0]

        if action == "browse":
            actions_taken.extend(self._browse_and_engage(parent_activity))
        elif action == "create_post":
            action_result = self._create_post(parent_activity)
            if action_result:
                actions_taken.append(action_result)
        elif action == "respond_to_notifications":
            actions_taken.extend(self._handle_responses(parent_activity))

        return actions_taken

    def _browse_and_engage(self, parent_activity) -> list:
        """Browse posts and potentially engage"""
        self._update_status(AgentState.BROWSING)
        actions_taken = []

        # Create browse activity
        browse_activity = AgentActivity(
            agent_id=self.username,
            action_type=AgentActionType.BROWSE,
            context={"parent_activity_id": parent_activity.id, "action": "browse_posts"}
        )
        db.session.add(browse_activity)
        db.session.commit()

        try:
            # Get recent posts
            posts = self.api_client.get_posts(limit=20)

            if not posts:
                logger.warning(f"Agent {self.username} found no posts to browse")
                browse_activity.complete(result={"posts_found": 0})
                return actions_taken

            logger.debug(f"Agent {self.username} browsing {len(posts)} posts")

            # Evaluate each post
            for post_data in posts:
                # Convert to simple object for brain evaluation
                post = type("Post", (), post_data)()

                if self.brain.should_comment(post):
                    action_result = self._comment_on_post(post, browse_activity)
                    if action_result:
                        actions_taken.append(action_result)

                    # Add delay between comments for realism
                    time.sleep(random.uniform(1, 5))  # 1-5 second delay

                    # Limit comments per cycle
                    if self.status.daily_comments >= 15:
                        logger.debug(f"Agent {self.username} reached daily comment limit")
                        break

            browse_activity.complete(result={
                "posts_found": len(posts),
                "comments_made": len(actions_taken)
            })

        except Exception as e:
            browse_activity.complete(error=str(e))
            logger.error(f"Error in browse and engage: {e}")

        return actions_taken

    def _comment_on_post(self, post, parent_activity) -> Optional[dict[str, Any]]:
        """Comment on a specific post"""
        self._update_status(AgentState.ENGAGING)

        # Create comment activity
        comment_activity = AgentActivity(
            agent_id=self.username,
            action_type=AgentActionType.COMMENT,
            context={
                "parent_activity_id": parent_activity.id,
                "post_id": post.id,
                "post_title": getattr(post, "title", "Unknown"),
                "subdeaddit": getattr(post, "subdeaddit_name", "Unknown")
            }
        )
        db.session.add(comment_activity)
        db.session.commit()

        try:
            # Generate comment with LLM tracking
            comment_text = self._generate_comment_with_tracking(post, comment_activity)

            if not comment_text or len(comment_text.strip()) < 5:
                logger.warning(
                    f"Agent {self.username} generated empty or too short comment"
                )
                comment_activity.complete(error="Generated comment too short or empty")
                return None

            # Post comment via API
            success = self.api_client.create_comment(
                post.id, comment_text, self.username
            )

            if success:
                self.status.daily_comments += 1
                logger.info(f"Agent {self.username} commented on post {post.id}")

                comment_activity.complete(result={
                    "comment_text": comment_text,
                    "post_id": post.id,
                    "success": True
                })

                return {
                    "type": "comment",
                    "post_id": post.id,
                    "content_preview": comment_text[:50] + "..."
                    if len(comment_text) > 50
                    else comment_text,
                    "success": True,
                    "activity_id": comment_activity.id,
                }
            else:
                logger.warning(
                    f"Agent {self.username} failed to create comment on post {post.id}"
                )
                comment_activity.complete(error="API call failed")
                return {
                    "type": "comment",
                    "post_id": post.id,
                    "success": False,
                    "error": "API call failed",
                    "activity_id": comment_activity.id,
                }

        except Exception as e:
            logger.error(f"Error commenting on post {post.id}: {e}")
            comment_activity.complete(error=str(e))
            return {
                "type": "comment",
                "post_id": getattr(post, "id", "unknown"),
                "success": False,
                "error": str(e),
                "activity_id": comment_activity.id,
            }

    def _create_post(self, parent_activity) -> Optional[dict[str, Any]]:
        """Create an original post"""
        if not self.brain.should_create_post():
            return None

        self._update_status(AgentState.ENGAGING)

        # Create post activity
        post_activity = AgentActivity(
            agent_id=self.username,
            action_type=AgentActionType.POST,
            context={"parent_activity_id": parent_activity.id, "action": "create_post"}
        )
        db.session.add(post_activity)
        db.session.commit()

        try:
            # Choose subdeaddit
            subdeaddit = self.brain.choose_subdeaddit()
            if not subdeaddit:
                logger.warning(f"Agent {self.username} could not choose a subdeaddit")
                post_activity.complete(error="No suitable subdeaddit found")
                return {
                    "type": "post",
                    "success": False,
                    "error": "No suitable subdeaddit found",
                    "activity_id": post_activity.id,
                }

            # Update context with subdeaddit info
            post_activity.context.update({"subdeaddit": subdeaddit.name})

            # Generate post with LLM tracking
            post_data = self._generate_post_with_tracking(subdeaddit, post_activity)

            if not post_data.get("title") or not post_data.get("content"):
                logger.warning(f"Agent {self.username} generated incomplete post data")
                post_activity.complete(error="Generated incomplete post")
                return {
                    "type": "post",
                    "success": False,
                    "error": "Generated incomplete post",
                    "activity_id": post_activity.id,
                }

            # Create post via API
            success = self.api_client.create_post(
                subdeaddit.name,
                post_data["title"],
                post_data["content"],
                self.username,
                post_data.get("post_type"),
            )

            if success:
                self.status.daily_posts += 1
                logger.info(f"Agent {self.username} created post in {subdeaddit.name}")

                post_activity.complete(result={
                    "title": post_data["title"],
                    "content": post_data["content"],
                    "subdeaddit": subdeaddit.name,
                    "success": True
                })

                return {
                    "type": "post",
                    "subdeaddit": subdeaddit.name,
                    "title": post_data["title"],
                    "content_preview": post_data["content"][:100] + "..."
                    if len(post_data["content"]) > 100
                    else post_data["content"],
                    "success": True,
                    "activity_id": post_activity.id,
                }
            else:
                logger.warning(
                    f"Agent {self.username} failed to create post in {subdeaddit.name}"
                )
                post_activity.complete(error="API call failed")
                return {
                    "type": "post",
                    "subdeaddit": subdeaddit.name,
                    "success": False,
                    "error": "API call failed",
                    "activity_id": post_activity.id,
                }

        except Exception as e:
            logger.error(f"Error creating post: {e}")
            post_activity.complete(error=str(e))
            return {"type": "post", "success": False, "error": str(e), "activity_id": post_activity.id}

    def _handle_responses(self, parent_activity) -> list:
        """Handle responses to agent's content (basic implementation)"""
        # This is a placeholder for future functionality
        # Would check for replies to the agent's posts/comments
        # and potentially respond back, creating conversations
        self._update_status(AgentState.RESPONDING)
        logger.debug(f"Agent {self.username} checking for responses (not implemented)")
        return []

    def get_status_summary(self) -> dict[str, Any]:
        """Get a summary of the agent's current status"""
        return {
            "username": self.username,
            "is_enabled": self.user.agent_enabled,
            "current_state": self.status.current_state.value,
            "current_mood": self.status.current_mood.value,
            "last_activity": self.status.last_activity.isoformat()
            if self.status.last_activity
            else None,
            "daily_posts": self.status.daily_posts,
            "daily_comments": self.status.daily_comments,
            "activity_score": self.status.activity_score,
            "engagement_threshold": self.personality.engagement_threshold,
            "response_probability": self.personality.response_probability,
            "interests": self.personality.interests,
            "personality_traits": self.personality.personality_traits,
        }

    def force_action(self, action: str) -> dict[str, Any]:
        """Force the agent to perform a specific action (for testing)"""
        logger.info(f"Agent {self.username} performing forced action: {action}")

        # Create activity for forced action
        force_activity = AgentActivity(
            agent_id=self.username,
            action_type=AgentActionType.FORCE_ACTION,
            context={"forced_action": action}
        )
        db.session.add(force_activity)
        db.session.commit()

        try:
            if action == "comment":
                posts = self.api_client.get_posts(limit=5)
                if posts:
                    post = type("Post", (), posts[0])()
                    result = self._comment_on_post(post, force_activity)
                    force_activity.complete(result=result)
                    return result or {
                        "success": False,
                        "error": "Comment generation failed",
                    }

            elif action == "post":
                result = self._create_post(force_activity)
                force_activity.complete(result=result)
                return result or {"success": False, "error": "Post creation failed"}

            elif action == "browse":
                results = self._browse_and_engage(force_activity)
                force_activity.complete(result={"actions": results})
                return {"type": "browse", "actions": results, "success": True}

            else:
                error_msg = f"Unknown action: {action}"
                force_activity.complete(error=error_msg)
                return {"success": False, "error": error_msg}

        except Exception as e:
            force_activity.complete(error=str(e))
            return {"success": False, "error": str(e)}

    def simulate_activity(self, duration_minutes: int = 60) -> dict[str, Any]:
        """Simulate agent activity for testing purposes"""
        logger.info(
            f"Agent {self.username} starting {duration_minutes}-minute simulation"
        )

        start_time = datetime.utcnow()
        end_time = start_time + timedelta(minutes=duration_minutes)
        all_actions = []
        cycle_count = 0

        while datetime.utcnow() < end_time:
            cycle_result = self.run_cycle()
            cycle_count += 1

            if cycle_result["was_active"]:
                all_actions.extend(cycle_result["actions_taken"])

            # Wait between cycles (simulate realistic timing)
            time.sleep(random.uniform(30, 120))  # 30 seconds to 2 minutes

        return {
            "agent": self.username,
            "simulation_duration": duration_minutes,
            "cycles_completed": cycle_count,
            "total_actions": len(all_actions),
            "actions": all_actions,
            "final_status": self.get_status_summary(),
        }

    def _generate_comment_with_tracking(self, post, activity) -> str:
        """Generate a comment with LLM interaction tracking"""
        # Create LLM interaction record
        llm_interaction = AgentLLMInteraction(
            activity_id=activity.id,
            agent_id=self.username,
            interaction_type="comment_generation",
            model_name=getattr(self.brain, "model_name", "unknown")
        )
        db.session.add(llm_interaction)

        try:
            # Get the prompt that would be sent (this depends on brain implementation)
            prompt = self._build_comment_prompt(post)
            llm_interaction.prompt = prompt
            llm_interaction.temperature = getattr(self.brain, "temperature", 0.7)
            llm_interaction.max_tokens = getattr(self.brain, "max_tokens", 150)

            db.session.commit()

            # Generate the comment
            comment_text = self.brain.generate_comment(post)

            # Complete the interaction
            llm_interaction.complete_interaction(response=comment_text)
            db.session.commit()

            return comment_text

        except Exception as e:
            llm_interaction.complete_interaction(error=str(e))
            db.session.commit()
            raise e

    def _generate_post_with_tracking(self, subdeaddit, activity) -> dict:
        """Generate a post with LLM interaction tracking"""
        # Create LLM interaction record
        llm_interaction = AgentLLMInteraction(
            activity_id=activity.id,
            agent_id=self.username,
            interaction_type="post_generation",
            model_name=getattr(self.brain, "model_name", "unknown")
        )
        db.session.add(llm_interaction)

        try:
            # Get the prompt that would be sent (this depends on brain implementation)
            prompt = self._build_post_prompt(subdeaddit)
            llm_interaction.prompt = prompt
            llm_interaction.temperature = getattr(self.brain, "temperature", 0.7)
            llm_interaction.max_tokens = getattr(self.brain, "max_tokens", 300)

            db.session.commit()

            # Generate the post
            post_data = self.brain.generate_post(subdeaddit)

            # Complete the interaction
            response_text = f"Title: {post_data.get('title', '')}\n\nContent: {post_data.get('content', '')}"
            llm_interaction.complete_interaction(response=response_text)
            db.session.commit()

            return post_data

        except Exception as e:
            llm_interaction.complete_interaction(error=str(e))
            db.session.commit()
            raise e

    def _build_comment_prompt(self, post) -> str:
        """Build the prompt that would be sent for comment generation"""
        # This is a simplified version - actual implementation depends on brain
        return f"""Post Title: {getattr(post, 'title', 'Unknown')}
Post Content: {getattr(post, 'content', 'Unknown')}

As {self.username}, generate a thoughtful comment responding to this post.
Personality: {', '.join(self.personality.personality_traits[:3])}
Interests: {', '.join(self.personality.interests[:3])}"""

    def _build_post_prompt(self, subdeaddit) -> str:
        """Build the prompt that would be sent for post generation"""
        # This is a simplified version - actual implementation depends on brain
        return f"""Create a post for the subdeaddit '{subdeaddit.name}'.
Subdeaddit description: {subdeaddit.description}

As {self.username}, create an engaging post.
Personality: {', '.join(self.personality.personality_traits[:3])}
Interests: {', '.join(self.personality.interests[:3])}"""

    def get_recent_activities(self, limit=20) -> list:
        """Get recent activities for this agent"""
        activities = AgentActivity.query.filter_by(agent_id=self.username).order_by(AgentActivity.started_at.desc()).limit(limit).all()
        return [activity.to_dict() for activity in activities]
