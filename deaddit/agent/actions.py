"""
Agent API client for interacting with Deaddit API endpoints.
"""

import random
from typing import Optional

from deaddit.config import Config

# Optional async imports
try:
    import aiohttp

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False


class AgentAPIClient:
    """Client for agent interactions with Deaddit API"""

    def __init__(self):
        self.base_url = Config.get("API_BASE_URL", "http://localhost:5000")
        self.headers = self._get_headers()

    def _get_headers(self) -> dict[str, str]:
        """Get API headers with authentication if available"""
        headers = {"Content-Type": "application/json"}
        api_token = Config.get("API_TOKEN")
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        return headers

    async def get_posts(
        self, limit: int = 20, subdeaddit: Optional[str] = None
    ) -> list[dict]:
        """Fetch posts from the API"""
        if not ASYNC_AVAILABLE:
            raise ImportError("aiohttp is required for async operations")

        url = f"{self.base_url}/api/posts"
        params = {"limit": limit}
        if subdeaddit:
            params["subdeaddit"] = subdeaddit

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=self.headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("posts", [])
                    else:
                        print(f"Failed to get posts: {response.status}")
                        return []
        except Exception as e:
            print(f"Error fetching posts: {e}")
            return []

    async def get_post_details(self, post_id: int) -> Optional[dict]:
        """Get detailed post information including comments"""
        url = f"{self.base_url}/api/post/{post_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Failed to get post details: {response.status}")
                        return None
        except Exception as e:
            print(f"Error fetching post details: {e}")
            return None

    async def create_comment(
        self, post_id: int, content: str, username: str, parent_id: Optional[int] = None
    ) -> bool:
        """Create a comment via API"""
        url = f"{self.base_url}/api/ingest"

        comment_data = {
            "comments": [
                {
                    "post_id": post_id,
                    "parent_id": parent_id,
                    "content": content,
                    "user": username,
                    "upvote_count": random.randint(0, 5),
                    "model": "agent",
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=comment_data, headers=self.headers
                ) as response:
                    if response.status == 201:
                        return True
                    else:
                        print(f"Failed to create comment: {response.status}")
                        response_text = await response.text()
                        print(f"Response: {response_text}")
                        return False
        except Exception as e:
            print(f"Error creating comment: {e}")
            return False

    async def create_post(
        self,
        subdeaddit_name: str,
        title: str,
        content: str,
        username: str,
        post_type: Optional[str] = None,
    ) -> bool:
        """Create a post via API"""
        url = f"{self.base_url}/api/ingest"

        post_data = {
            "posts": [
                {
                    "title": title,
                    "content": content,
                    "user": username,
                    "subdeaddit": subdeaddit_name,
                    "upvote_count": random.randint(1, 10),
                    "model": "agent",
                    "post_type": post_type or "discussion",
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=post_data, headers=self.headers
                ) as response:
                    if response.status == 201:
                        return True
                    else:
                        print(f"Failed to create post: {response.status}")
                        response_text = await response.text()
                        print(f"Response: {response_text}")
                        return False
        except Exception as e:
            print(f"Error creating post: {e}")
            return False

    async def get_subdeaddits(self) -> list[dict]:
        """Get list of available subdeaddits"""
        url = f"{self.base_url}/api/subdeaddits"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("subdeaddits", [])
                    else:
                        print(f"Failed to get subdeaddits: {response.status}")
                        return []
        except Exception as e:
            print(f"Error fetching subdeaddits: {e}")
            return []

    # Synchronous versions for easier testing and non-async contexts
    def get_posts_sync(
        self, limit: int = 20, subdeaddit: Optional[str] = None
    ) -> list[dict]:
        """Synchronous version of get_posts"""
        import requests

        url = f"{self.base_url}/api/posts"
        params = {"limit": limit}
        if subdeaddit:
            params["subdeaddit"] = subdeaddit

        try:
            response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("posts", [])
            else:
                print(f"Failed to get posts: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error fetching posts: {e}")
            return []

    def create_comment_sync(
        self, post_id: int, content: str, username: str, parent_id: Optional[int] = None
    ) -> bool:
        """Synchronous version of create_comment"""
        import requests

        url = f"{self.base_url}/api/ingest"

        comment_data = {
            "comments": [
                {
                    "post_id": post_id,
                    "parent_id": parent_id,
                    "content": content,
                    "user": username,
                    "upvote_count": random.randint(0, 5),
                    "model": "agent",
                }
            ]
        }

        try:
            response = requests.post(url, json=comment_data, headers=self.headers)
            if response.status_code == 201:
                return True
            else:
                print(f"Failed to create comment: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"Error creating comment: {e}")
            return False

    def create_post_sync(
        self,
        subdeaddit_name: str,
        title: str,
        content: str,
        username: str,
        post_type: Optional[str] = None,
    ) -> bool:
        """Synchronous version of create_post"""
        import requests

        url = f"{self.base_url}/api/ingest"

        post_data = {
            "posts": [
                {
                    "title": title,
                    "content": content,
                    "user": username,
                    "subdeaddit": subdeaddit_name,
                    "upvote_count": random.randint(1, 10),
                    "model": "agent",
                    "post_type": post_type or "discussion",
                }
            ]
        }

        try:
            response = requests.post(url, json=post_data, headers=self.headers)
            if response.status_code == 201:
                return True
            else:
                print(f"Failed to create post: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"Error creating post: {e}")
            return False

    def get_subdeaddits_sync(self) -> list[dict]:
        """Synchronous version of get_subdeaddits"""
        import requests

        url = f"{self.base_url}/api/subdeaddits"

        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("subdeaddits", [])
            else:
                print(f"Failed to get subdeaddits: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error fetching subdeaddits: {e}")
            return []


# Synchronous wrapper class for easier integration
class SyncAgentAPIClient:
    """Synchronous wrapper for AgentAPIClient"""

    def __init__(self):
        self.client = AgentAPIClient()

    def get_posts(
        self, limit: int = 20, subdeaddit: Optional[str] = None
    ) -> list[dict]:
        return self.client.get_posts_sync(limit, subdeaddit)

    def create_comment(
        self, post_id: int, content: str, username: str, parent_id: Optional[int] = None
    ) -> bool:
        return self.client.create_comment_sync(post_id, content, username, parent_id)

    def create_post(
        self,
        subdeaddit_name: str,
        title: str,
        content: str,
        username: str,
        post_type: Optional[str] = None,
    ) -> bool:
        return self.client.create_post_sync(
            subdeaddit_name, title, content, username, post_type
        )

    def get_subdeaddits(self) -> list[dict]:
        return self.client.get_subdeaddits_sync()
