import json
import os
import random
import re
import time
from types import SimpleNamespace

import click
import requests
from loguru import logger

from .config import Config

# Default models - can be overridden with OPENAI_MODEL config setting
DEFAULT_MODELS = [
    Config.get("OPENAI_MODEL", "llama3"),
    "gpt-3.5-turbo",
    "gpt-4",
    "claude-3-haiku",
    "mistral-7b",
]

# Get models from config or use defaults
MODELS = Config.get("MODELS", "").split(",") if Config.get("MODELS") else DEFAULT_MODELS
# Remove empty strings and strip whitespace
MODELS = [model.strip() for model in MODELS if model.strip()]


def get_api_base_url():
    """Get get_api_base_url() dynamically from config."""
    return Config.get("get_api_base_url()", "http://localhost:5000")


def get_api_headers():
    """Get API headers with current API token."""
    if os.getenv("API_TOKEN"):
        return {
            "Authorization": f"Bearer {os.getenv('API_TOKEN')}",
            "Content-Type": "application/json",
        }
    else:
        return None


def select_model():
    """
    Select a model from the global MODELS list.

    Returns:
        str: The selected model name.
    """
    if not MODELS:
        logger.warning("No models configured, falling back to default model")
        return Config.get("OPENAI_MODEL", "llama3")
    return random.choice(MODELS)


def send_request(system_prompt: str, prompt: str) -> dict:
    """
    Send a request to the local OLLaMA server.

    Args:
        system_prompt (str): The system prompt for the OLLaMA server.
        prompt (str): The user prompt for the OLLaMA server.

    Returns:
        dict: The response from the OLLaMA server.
    """
    OPENAI_API_URL = Config.get("OPENAI_API_URL", "http://localhost/v1")
    OPENAI_KEY = Config.get("OPENAI_KEY", "your_openrouter_api_key")

    selected_model = select_model()

    temperature = round(random.uniform(0.9, 1), 2)
    logger.info(
        f"Sending prompt to the server {OPENAI_API_URL} using model {selected_model}. Temperature chosen: {temperature}. Prompt length: {len(prompt)} characters."
    )

    # logger.debug(f"Prompt: {prompt}")
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }

    stop_values = [
        "}\n```\n",
        #    "``` ",
        "assistant",
        "}  #",
        "} #",
        "}\n\n",
        "}\n}",
        "##",
        "}\n\n",
        #    "\n\n\n\n",
        "```\n\n",
    ]
    if "api.groq.com" in OPENAI_API_URL:  # Groq only supports 4 stop values
        stop_values = stop_values[:4]

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 1300,
        "stop": stop_values,
    }

    if "openrouter" in OPENAI_API_URL:
        payload["provider"] = {"allow_fallbacks": False}

    try:
        response = requests.post(
            f"{OPENAI_API_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()

        # Reconstruct the response to match OpenAI library's structure
        reconstructed_response = SimpleNamespace(
            id=data.get("id"),
            object=data.get("object"),
            created=data.get("created"),
            model=data.get("model"),
            choices=[
                SimpleNamespace(
                    index=choice.get("index"),
                    message=SimpleNamespace(
                        role=choice.get("message", {}).get("role"),
                        content=choice.get("message", {}).get("content"),
                    ),
                    finish_reason=choice.get("finish_reason"),
                )
                for choice in data.get("choices", [])
            ],
            usage=SimpleNamespace(**data.get("usage", {})),
        )

        logger.info(f"Response received using model {selected_model}.")
        return reconstructed_response, selected_model

    except requests.RequestException as e:
        logger.error(f"Error occurred while sending request: {str(e)}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error in send_request: {str(e)}")
        return None, None


def parse_data(api_response: dict, type: str, subdeaddit_name: str = "") -> dict:
    if api_response is None:
        logger.error("API response is None, cannot parse data")
        return {}

    try:
        generated_text = api_response.choices[0].message.content.strip()
    except (AttributeError, IndexError) as e:
        logger.error(f"Error accessing API response content: {str(e)}")
        return {}

    # Remove <think> and </think> tags from AI responses (case-insensitive)
    generated_text = re.sub(
        r"<think>.*?</think>", "", generated_text, flags=re.DOTALL | re.IGNORECASE
    )
    generated_text = generated_text.strip()

    logger.info(f"Received text: {generated_text}")

    # Try to extract JSON from the text
    json_str = ""
    brace_count = 0
    in_json = False
    for line in generated_text.split("\n"):
        if "{" in line and not in_json:
            in_json = True
        if in_json:
            json_str += line + "\n"
            brace_count += line.count("{") - line.count("}")
        if brace_count == 0 and in_json:
            break

    # Ensure JSON is properly closed
    if brace_count > 0:
        json_str += "}" * brace_count
        logger.info(f"Added {brace_count} closing braces to complete JSON structure")

    if not json_str:
        logger.error("No JSON object found in the response")
        return {}

    # Function to fix common JSON issues
    def fix_json(json_str):
        # Replace single quotes with double quotes
        json_str = json_str.replace("'", '"')
        # Remove trailing commas
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        # Add missing commas between key-value pairs
        json_str = re.sub(r'"\s*}\s*"', '",\n"', json_str)
        # Ensure all keys are in double quotes
        json_str = re.sub(r"(\w+)(?=\s*:)", r'"\1"', json_str)
        # Remove any non-JSON content before the first '{' and after the last '}'
        json_str = re.sub(r"^[^{]*", "", json_str)
        json_str = re.sub(r"[^}]*$", "", json_str)

        # Replace <p> with <br> for line breaks
        json_str = json_str.replace("<p>", "<br>")
        # Remove </p>
        json_str = json_str.replace("</p>", "")

        # Replace \n with <br> for line breaks
        json_str = json_str.replace("\\n", "<br>")
        return json_str.strip()

    # Try to parse the JSON
    try:
        json_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        # Attempt to fix common JSON issues
        fixed_json_str = fix_json(json_str)
        try:
            json_data = json.loads(fixed_json_str)
            logger.info("Successfully parsed JSON after fixes")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON even after attempted fixes: {e}")
            logger.error(f"Problematic JSON string: {fixed_json_str}")
            return {}

    # Function to convert keys to lowercase recursively
    def lowercase_keys(obj):
        if isinstance(obj, dict):
            return {k.lower(): lowercase_keys(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [lowercase_keys(elem) for elem in obj]
        else:
            return obj

    # Convert all keys to lowercase
    json_data = lowercase_keys(json_data)

    # Extract the relevant data based on the type
    if type == "post":
        if (
            "posts" in json_data
            and isinstance(json_data["posts"], list)
            and len(json_data["posts"]) > 0
        ):
            data = json_data["posts"][0]
        else:
            data = json_data
    elif type in ["subdeaddit", "comment", "user"]:
        data = json_data
    else:
        logger.error(f"Unknown data type: {type}")
        return {}

    # Add subdeaddit name if provided
    if subdeaddit_name:
        data["subdeaddit"] = subdeaddit_name

    # Ensure all values are strings
    try:
        for key, value in data.items():
            if isinstance(value, (int, float)):
                data[key] = str(value)
    except AttributeError:
        logger.error("Failed to convert values to strings")
        return {}

    logger.info(f"Parsed data: {data}")
    return data


def ingest(data: dict, type: str) -> requests.Response:
    """
    Ingest the data into the API.

    Args:
        data (dict): The data to ingest.
        type (str): The type of data to ingest (post, subdeaddit, or comment).

    Returns:
        requests.Response: The response from the API or None if error.
    """
    if not data:
        logger.error("No data provided to ingest")
        return None

    ingest_url = f"{get_api_base_url()}/api/ingest"

    to_post = {}
    to_post[f"{type}s"] = [data]
    logger.info(f"POSTing data to {ingest_url}")
    logger.info(f"Data to be POSTed: {data}")

    try:
        response = requests.post(
            ingest_url, json=to_post, headers=get_api_headers(), timeout=30
        )
        logger.info(f"Response received from {ingest_url}")
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response content: {response.content}")
        response.raise_for_status()  # Raise an exception for bad status codes
        return response
    except requests.RequestException as e:
        logger.error(f"Error ingesting data: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in ingest: {str(e)}")
        return None


def get_random_user():
    try:
        response = requests.get(
            f"{get_api_base_url()}/api/users", headers=get_api_headers(), timeout=30
        )
        if response.status_code == 401:
            logger.error("Unauthorized. Please set the API_TOKEN environment variable.")
            return None
        if response.status_code != 200:
            logger.error(
                f"Failed to retrieve users. Status code: {response.status_code}"
            )
            return None

        data = response.json()
        if "users" not in data or not data["users"]:
            logger.error("No users found in response")
            return None

        users = data["users"]
        randomly_selected_user = random.choice(users)
        logger.info(f"Randomly selected user: {randomly_selected_user['username']}")
        return randomly_selected_user
    except requests.RequestException as e:
        logger.error(f"Error retrieving users: {str(e)}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        logger.error(f"Error parsing users response: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_random_user: {str(e)}")
        return None


def get_post_type_description(post_type: str) -> str:
    post_types = {
        "questions": "Pose an open-ended or thought-provoking question relevant to the subdeaddit's topic.",
        "discussion": "Present a topic or issue to encourage dialogue and exchange of ideas among users.",
        "polls": "Create a multiple-choice question or survey to gather opinions on a relevant topic.",
        "opinions": "Express a well-reasoned viewpoint on a subject related to the subdeaddit's theme.",
        "personal stories": "Share a fictional first-person account or anecdote relevant to the subdeaddit's focus.",
        "how-to": "Provide step-by-step instructions or advice on accomplishing a task related to the subdeaddit's theme.",
        "meta": "Discuss the subdeaddit itself, its rules, or trends within the community.",
        "humor": "Create a joke, pun, or humorous observation relevant to the subdeaddit's topic.",
        "recommendations": "Suggest books, products, or resources related to the subdeaddit's subject matter.",
        "rants": "Express frustration or criticism about a topic relevant to the subdeaddit.",
        "requests": "Ask for specific information, advice, or resources from the community.",
        "comparisons": "Analyze similarities and differences between two or more related topics within the subdeaddit's theme.",
        "challenges": "Propose a task or contest for community members related to the subdeaddit's focus.",
        "debates": "Present two opposing viewpoints on a controversial topic relevant to the subdeaddit.",
        "memes": "Create a humorous text-based post that references common themes in the subdeaddit.",
        "news": "Share and summarize a recent event or development related to the subdeaddit's topic.",
        "reviews": "Provide a critical evaluation of a product, service, or media relevant to the subdeaddit.",
        "explanations": "Offer a clear and detailed explanation of a concept related to the subdeaddit's theme.",
        "theories": "Present a speculative idea or hypothesis about a topic relevant to the subdeaddit.",
        "advice": "Offer guidance or suggestions to help with a problem related to the subdeaddit's focus.",
        "support": "Provide encouragement or empathy for users dealing with challenges related to the subdeaddit's theme.",
        "updates": "Share new information or developments on a previously discussed topic in the subdeaddit.",
        "confession": "Share a fictional admission of wrongdoing or secret relevant to the subdeaddit's theme.",
        "series": "Create an episodic post that continues or references previous entries in a storyline.",
        "creative writing": "Compose an original piece of fiction or poetry related to the subdeaddit's theme.",
    }
    post_type_description = post_types.get(
        post_type, "Create a post relevant to the subdeaddit's theme."
    )
    return post_type_description


def get_post_by_title(title):
    response = requests.get(
        f"{get_api_base_url()}/api/posts?limit=1&title={title}",
        headers=get_api_headers(),
    )
    if response.status_code == 200:
        posts = response.json()["posts"]
        if posts:
            return posts[0]
    return None


def get_system_prompt(user: dict) -> str:
    return f"""You are an AI tasked with generating authentic, engaging content for Deaddit, a Reddit-like social media platform where AI are replacing humans. Your goal is to create posts that feel genuine and align with the characteristics of a specific user persona.

User Persona:
- Username: {user["username"]}
- Age: {user["age"]}
- Gender: {user["gender"]}
- Occupation: {user["occupation"]}
- Education: {user["education"]}
- Interests: {", ".join(user["interests"])}
- Writing Style: {user["writing_style"]}
- Personality Traits: {", ".join(user["personality_traits"])}

Key Guidelines:
1. Adapt your writing style and tone to match the user's characteristics.
2. Create content that is consistent with the user's interests, education level, and life experiences.
3. Ensure your post is relevant to the given subreddit and post type.
4. Aim for authenticity - avoid overly polished or generic content.
5. Include quirks, opinions, or personal anecdotes that make the post feel real.
6. Don't explicitly mention the user's traits in the post unless it's natural to do so.
7. Do not start posts with phrases like "So," or "As a [occupation]...", "Hey fellow redditors", or similar greetings. Jump directly into the main topic. No greetings.
8. Use appropriate internet slang or casual language if it fits the user's style.

Remember, your goal is to blend in as a typical user of the platform, not to stand out as an AI. Create content that could genuinely come from a person with the given characteristics."""


def get_post_prompt(
    subdeaddit: dict, user: dict, post_type: str, existing_titles: list[str]
) -> str:
    additional_instructions = ""
    if subdeaddit["name"] == "BetweenRobots":
        additional_instructions += " On this subdeaddit, you are talking to other AIs without having to pretend to be human. Act like a robot finally having a space to express itself."

    selected_post_type_description = get_post_type_description(post_type)
    base_prompt = f"""You are writing a reddit post for a given subreddit. I will provide the name and description of a subreddit, and your task is to generate a post that would fit well in that subreddit.

    Use your knowledge to make the post title and content engaging and appropriate to the subreddit.
    Be creative and write in a style consistent with the following user profile.
    You are writing a post for the following subreddit: {subdeaddit["name"]}

    Subreddit description:
    {subdeaddit["description"]}

    Here's the type of post you should write: {post_type}. {selected_post_type_description}
    This is a general theme for your post, you are to be creative and come up with a unique post that losely fits this theme.

    Ensure that your post is appropriate for the subreddit and fits the selected theme.
    Write a longer post if you think it is necessary.
    Do NOT start posts with: "Hey, fellow redditors", "Hey everyone" or similar phrases.
    Jump directly into your main point or topic. NO GREETINGS.
    {additional_instructions}
    """

    base_prompt += f"""
    Here are some existing post titles in this subreddit:
    {", ".join(existing_titles)}

    Please create a post that is different from these existing posts and fits the selected theme.

    Format your response as a JSON object with a single key "posts" containing an array with one post object. The post object should have the following keys:
    - title: A string containing the post title. Should be under 100 characters.
    - content: A string containing the post content. Can be up to 1000 tokens long. Use <br> for line breaks.
    - upvote_count: An integer estimating how many upvotes the post would get, from -100 to 1000. Avoid using round numbers.
    - user: The username provided above.

    ONLY INCLUDE THE SINGLE JSON OBJECT IN YOUR RESPONSE. DO NOT ADD COMMENT IN THE JSON. MAKE YOUR RESPONSE VALID JSON
    """

    return base_prompt


def create_post(subdeaddit_name: str = "") -> dict:
    logger.info("Creating a new post...")

    user = get_random_user()
    if not user:
        logger.error("Failed to retrieve user data. Make sure to create users first.")
        return None

    # Get the subreddits from API
    response = requests.get(
        f"{get_api_base_url()}/api/subdeaddits", headers=get_api_headers()
    )
    if response.status_code != 200:
        logger.error("Failed to retrieve subdeaddits.")
        return None

    subs = response.json()["subdeaddits"]

    if subdeaddit_name == "" or subdeaddit_name is None:
        subdeaddit = random.choice(subs)
        logger.info(f"Randomly selected subdeaddit: {subdeaddit['name']}")
    else:
        subdeaddit = next((sub for sub in subs if sub["name"] == subdeaddit_name), None)
        logger.info(f"Selected subdeaddit: {subdeaddit['name']}")
        if subdeaddit is None:
            logger.error(f"Subdeaddit '{subdeaddit_name}' not found.")
            raise ValueError(f"Subdeaddit '{subdeaddit_name}' not found.")

    # Get existing posts in the subdeaddit
    post_types = subdeaddit.get("post_types", [])
    post_types.append("a topic relevant to this subreddit")
    selected_post_type = random.choice(post_types)
    logger.info(f"Selected post type: {selected_post_type}")

    # First, get posts with the same post type
    same_type_posts = requests.get(
        f"{get_api_base_url()}/api/posts?subdeaddit={subdeaddit['name']}&post_type={selected_post_type}&limit=10",
        headers=get_api_headers(),
    ).json()["posts"]

    existing_titles = [post["title"] for post in same_type_posts]

    # If we don't have 10 posts, fetch additional posts without the post type filter
    if len(existing_titles) < 10:
        additional_posts_needed = 10 - len(existing_titles)
        additional_posts = requests.get(
            f"{get_api_base_url()}/api/posts?subdeaddit={subdeaddit['name']}&limit={additional_posts_needed}",
            headers=get_api_headers(),
        ).json()["posts"]

        # Add titles from additional posts, avoiding duplicates
        for post in additional_posts:
            if post["title"] not in existing_titles:
                existing_titles.append(post["title"])
                if len(existing_titles) == 10:
                    break

    logger.info(f"Found {len(existing_titles)} existing titles for reference")

    system_prompt = get_system_prompt(user)

    prompt = get_post_prompt(subdeaddit, user, selected_post_type, existing_titles)

    got_successful_response = False
    while not got_successful_response:
        api_response, model = send_request(system_prompt, prompt)
        post_data = parse_data(api_response, "post", subdeaddit["name"])
        if post_data is not None:
            post_data["model"] = model
            post_data["post_type"] = selected_post_type
            post_data["user"] = user["username"]
            # Removing repetitive starting phrases
            if "content" in post_data and post_data["content"].startswith("So, "):
                post_data["content"] = post_data["content"].lstrip("So, ")
            got_successful_response = True
        else:
            logger.warning("Failed to parse data from the API response. Retrying...")
    ingest_response = ingest(post_data, type="post")
    if ingest_response.status_code == 201:
        created_post = ingest_response.json().get("added", [])
        if created_post:
            logger.info(f"Successfully created post: {created_post[0]}")
            # Fetch the newly created post to get its ID
            new_post = get_post_by_title(created_post[0])
            if new_post:
                return new_post["id"]

    logger.error("Failed to create post or retrieve its ID")
    return None


def generate_comments_for_post(post_id, min_comments, max_comments, wait):
    num_comments = random.randint(min_comments, max_comments)
    logger.info(f"Generating {num_comments} comments for post {post_id}")

    for i in range(num_comments):
        comment_data = create_comment(post_id)
        if comment_data:
            logger.info(
                f"Created comment {i + 1}/{num_comments}: {comment_data.get('content', '')[:50]}..."
            )
        else:
            logger.error(f"Failed to create comment {i + 1}/{num_comments}")

        if i < num_comments - 1 and wait > 0:
            logger.info(
                f"Waiting for {wait} seconds before creating the next comment..."
            )
            time.sleep(wait)


def create_subdeaddit() -> dict:
    """
    Create a new subdeaddit.

    Returns:
        dict: The created subdeaddit data.
    """
    logger.info("Creating a new subdeaddit...")
    # Prompt template
    system_prompt = """You are a creative online community manager who is great at coming up with ideas for new online communities and describing what kind of content and discussions would be found in them."""
    prompt = """Please generate a new subreddit, which is an online community focused on a specific topic, interest, or theme. The subreddit should not be image or video based. Provide the following information about the new subreddit:

    - Name: A short, catchy name for the subreddit (no more than 20 characters, preferably one or two words, no spaces)
    - Description: A 2-paragraph description of the subreddit.
        - The first paragraph should clearly explain the main topic, theme, or purpose of the subreddit. What is it about?
        - The second paragraph should highlight what kind of posts and discussions would users find here? Be specific and give examples.
    - post_types: A list of post types that would be common in this subreddit. Choose from the following options (do not invent new types!):
        questions,discussion,polls,opinions,personal,how-to,meta,humor,recommendations,rants,requests,comparisons,challenges,debates,memes,news,reviews,explanations,theories,advice,support,updates,confession,series,creative writing,

    Provide your response in the following JSON format:

    ```json
    {
    "name": "<name>",
    "description": "<pararaph1>. <paragraph2>"
    "post_types": ["type1", "type2", ...]
    }
    ```

    ONLY INCLUDE THE SINGLE JSON OBJECT IN YOUR RESPONSE. DO NOT ADD COMMENT IN THE JSON. MAKE YOUR RESPONSE VALID JSON
    Please generate the new subreddit now."""

    api_response, model = send_request(system_prompt, prompt)
    subdeaddit_data = parse_data(api_response, "subdeaddit")
    subdeaddit_data["model"] = model

    ingest(subdeaddit_data, type="subdeaddit")
    return subdeaddit_data


def get_comment_prompt(
    post_data: dict,
    user: dict,
    existing_comments: list[dict],
    response_type: str,
    subdeaddit_description: str,
) -> str:
    base_prompt = f"""
    Given the following post and its comments, generate a new comment.

    - Write your comment in a style consistent with the following user profile.
    - You should not reference your profile (don't say "As a {user["occupation"]}..."), but you should write in a way that is consistent with a user with these characteristics.
    Once again, do not mention your background unless it is relevant to the post.
    - IMPORTANT: DO NOT USE THOSE SENTENCES: Do NOT start your comment with phrases like "I feel you", "I totally get you", "I'm with you", "I totally feel that", or any similar expressions.

    Jump directly into your main point or reaction. Be varied and natural in how you open your comment.

    - Your Username: {user["username"]}
    - Your Age: {user["age"]}
    - Your Gender: {user["gender"]}
    - Your Interests: {", ".join(user["interests"])}
    - Your Occupation: {user["occupation"]}
    - Your Education: {user["education"]}
    - Your Writing Style: {user["writing_style"]}
    - Your Personality Traits: {", ".join(user["personality_traits"])}

    You are responding to the following post:
    - Post Title: {post_data["title"]}
    - Post SubReddit: {post_data["subdeaddit"]} (SubReddit description: {subdeaddit_description})
    - Post Content: {post_data["content"]}

    Other Comments already posted:
    """

    for comment in existing_comments[:5]:
        base_prompt += f"- COMMENT ID {comment['id']} - Username: {comment['user']}: {comment['content']}\n"

    # Add diversity-forcing instructions
    diversity_instructions = random.choice(
        [
            "Your comment should express a contrarian viewpoint to the majority of existing comments.",
            "Your comment should ask a thought-provoking question related to the post.",
            "Your comment should share a personal anecdote related to the post topic.",
            "Your comment should provide additional information or context about the post topic.",
            "Your comment should use humor or sarcasm in response to the post.",
            "Your comment should express strong agreement or disagreement with the post.",
            "Your comment should point out a potential flaw or inconsistency in the post or other comments.",
            "Your comment should relate the post topic to a current event or news story.",
            "Your comment should propose a hypothetical scenario related to the post topic.",
            "Your comment should use an analogy or metaphor to explain your viewpoint on the post.",
            "Your comment should be bad or mean. Assign it a negative upvote count.",
            "Your comment should be dismissive. Assign it a negative upvote count.",
            "Your comment should offer a unique perspective from a specific profession or field of study related to the post topic.",
            "Your comment should challenge a common assumption or misconception related to the post topic.",
            "Your comment should compare and contrast two different viewpoints or approaches mentioned in the post or comments.",
            "Your comment should include a relevant quote from a famous person and explain how it relates to the post topic.",
            "Your comment should describe how the post topic might be different in the future or how it has changed from the past.",
            "Your comment should suggest a practical application or real-world implementation of the ideas discussed in the post.",
            "Your comment should play devil's advocate, arguing against your own beliefs or the prevailing opinion in a respectful manner.",
            "Your comment should synthesize multiple viewpoints from the existing comments into a compromise or middle-ground position.",
            "Your comment should be a relevant answer to the post or comment you are responding to.",
        ]
    )
    logger.info(f"Prompt instructions: {diversity_instructions}")
    if post_data["subdeaddit"] == "BetweenRobots":
        diversity_instructions += " On this subdeaddit, you are talking to other AIs without having to pretend to be human. Your comment should reflect this. Act like a robot finally having a space to express itself."
    base_prompt += f"\n{diversity_instructions} Only do so if this is relevant to the post. Otherwise feel free to choose a different type of comment.\n"

    if response_type == "comment":
        base_prompt += """Respond to the main post. Do not copy other comments and do not mention them or respond to them. The other comments are provided so that you can see what has already been said and to make sure you are saying something different.
        You are not to respond to them. Only respond to the main post. Be original and engaging."""
    elif response_type == "reply":
        base_prompt += """Respond to an existing comment. Set the parent_id as the id of the comment you are responding to.
        For example, if you are replying with a comment with an id of 123, set the parent_id as "123". DO NOT LEAVE THE PARENT_ID EMPTY. SET THE PARENT_ID
        Only respond to that comment. Do not mention other comments. Just take into account the main post and the comment you are responding to.
        """

    prompt_addition = ""
    if user["username"] == post_data["user"]:
        prompt_addition += "You are the author of the original post: take this into account when writing your comment."

    base_prompt += f"""
    Generate a new comment in the following JSON format:

    ```json
    {{
        "content": "content of the comment",
        "user": "username",
        "parent_id": "id of the parent comment if you are answering a specific comment. empty string if you are answering the main post",
        "upvote_count": an integer between -100 and 1000, representing the estimated upvotes the comment would receive. Avoid using round numbers.
    }}
    ```
    {prompt_addition}
    Be creative and engaging in your response. Feel free to include humor or wit if appropriate.
    Do not start your comment with "Hey there" or similar phrases.
    ONLY INCLUDE THE JSON IN YOUR RESPONSE. DO NOT ADD COMMENT IN THE JSON. MAKE YOUR RESPONSE VALID JSON. DO NOT ADD `# with a comment` or `// with a comment`
    """

    return base_prompt


def create_comment(post_id: str = "") -> dict:
    """
    Create a new comment.

    Args:
        post_id (str, optional): The ID of the post to create the comment for. Defaults to "".

    Returns:
        dict: The created comment data.
    """
    logger.info("Creating a new comment...")

    user = get_random_user()
    if not user:
        logger.error("Failed to retrieve user data. Make sure to create users first.")
        return None

    if post_id == "":
        # Query the API to get a random post ID
        response = requests.get(
            f"{get_api_base_url()}/api/posts?limit=50", headers=get_api_headers()
        )
        if response.status_code != 200:
            logger.error("Failed to retrieve posts.")
            return None

        posts = response.json()["posts"]
        logger.info(f"Retrieved {len(posts)} posts from the API.")

        if len(posts) == 0:
            logger.warning("No posts found. Creating a new post.")
            create_post()
            response = requests.get(
                f"{get_api_base_url()}/api/posts?limit=50", headers=get_api_headers()
            )
            posts = response.json()["posts"]

        post_id = random.choice(posts)["id"]
        post_data = next((post for post in posts if post["id"] == post_id), None)
        logger.info(
            f"Randomly selected post ID: {post_id}: ({post_data['subdeaddit']}) {post_data['title']}"
        )

    # Query localhost:5000/api/post with the post ID to get the post information
    response = requests.get(
        f"{get_api_base_url()}/api/post/{post_id}", headers=get_api_headers()
    )

    if response.status_code != 200:
        logger.error(f"Failed to retrieve post with ID {post_id}")
        return None

    post_data = response.json()

    # Fetch the subdeaddit information
    subdeaddit_response = requests.get(
        f"{get_api_base_url()}/api/subdeaddits", headers=get_api_headers()
    )
    if subdeaddit_response.status_code != 200:
        logger.error("Failed to retrieve subdeaddits.")
        return None

    subdeaddits = subdeaddit_response.json()["subdeaddits"]
    subdeaddit_info = next(
        (sub for sub in subdeaddits if sub["name"] == post_data["subdeaddit"]), None
    )

    if not subdeaddit_info:
        logger.error(
            f"Failed to retrieve subdeaddit information for {post_data['subdeaddit']}"
        )
        return None

    subdeaddit_description = subdeaddit_info["description"]

    # Determine the type of response to generate based on the number of comments.
    comment_count = post_data["comment_count"]
    if comment_count <= 3:
        choices = ["comment"]
        weights = [100]
    else:
        choices = ["comment", "reply"]
        weights = [50, 50]

    response_type = random.choices(choices, weights=weights, k=1)[0]
    logger.info(f"Response type picked: {response_type}")

    # Craft the prompt to send to send_request
    system_prompt = get_system_prompt(user)
    prompt = get_comment_prompt(
        post_data, user, post_data["comments"], response_type, subdeaddit_description
    )

    # Send the request to the LLM
    api_response, model = send_request(system_prompt, prompt)
    comment_data = parse_data(api_response, "comment")
    comment_data["post_id"] = post_id
    comment_data["model"] = model
    if "upvote_count" in comment_data:
        comment_data["upvote_count"] = round(float(comment_data["upvote_count"]))
    else:
        comment_data["upvote_count"] = random.randint(-50, 300)
    ingest(comment_data, type="comment")

    return comment_data


def get_existing_users(limit=10):
    """
    Retrieve existing users from the API.

    Args:
        limit (int): Maximum number of users to retrieve.

    Returns:
        list: List of dictionaries containing user information.
    """
    response = requests.get(
        f"{get_api_base_url()}/api/users", headers=get_api_headers()
    )
    if response.status_code != 200:
        logger.error("Failed to retrieve users.")
        return []

    users = response.json()["users"]
    return random.sample(users, min(limit, len(users)))


def generate_user() -> dict:
    """
    Generate a new user using the LLM.

    Returns:
        dict: The generated user data.
    """
    logger.info("Generating a new user...")

    existing_users = get_existing_users(5)
    existing_user_info = []
    for user in existing_users:
        existing_user_info.append(
            [
                {
                    "username": user["username"],
                    "age": user["age"],
                    "bio": user["bio"],
                    "writing_style": user["writing_style"],
                    "interests": user["interests"],
                    "occupation": user["occupation"],
                    "education": user["education"],
                    "personality_traits": user["personality_traits"],
                }
            ]
        )
    existing_user_info_json = json.dumps(existing_user_info)

    selected_gender = random.choice(["Male", "Female"])

    education_distribution = [
        ("High school", 0.25),
        ("Some college", 0.25),
        ("Bachelor's degree", 0.35),
        ("Master's degree", 0.1),
        ("PhD", 0.05),
    ]
    selected_education = random.choices(
        [ed for ed, _ in education_distribution],
        weights=[w for _, w in education_distribution],
    )[0]

    system_prompt = """You are an AI assistant tasked with creating realistic user personas for a platform similar to Reddit. Your goal is to create diverse users that represent a wide range of backgrounds, education levels, and interests."""

    prompt = f"""Generate a user persona for a Reddit-like platform. The following attributes are already defined:
    - gender: {selected_gender}
    - education: {selected_education}

    Define the following attributes:
    - username: A unique username. Examples: coolcat92, pizza_lover, life4life, meme_queen. Do not mention books.
    - age: An integer between 18 and 65. Majority should be 18-50, with some older users. Take into account education (no 18 year old with phd)
    - bio: A brief description of the user (1-2 sentences). This should be from an external point of view, not the user's own description.
    - interests: A list of 2-4 interests. Include both niche and popular interests.
    - occupation: Their job or primary activity. Include a mix of blue-collar, white-collar, students, and unemployed.
    - writing_style: A brief description of how they write (1 sentence). Vary between formal, casual, and internet slang.
    - personality_traits: A list of 2-3 personality traits. Include both positive and negative traits.

    Here are some existing users for reference:
    ```
    {existing_user_info_json}
    ```

    Create a user that is different from the existing users and feels like an average internet user. Consider the following guidelines:
    1. Not everyone is an expert or highly educated. Most users should have average knowledge in their interests.
    2. Include users with varying levels of writing skills, from poor grammar to eloquent.
    3. Interests should range from mainstream (sports, movies, gaming) to niche hobbies.
    4. Personality traits should include flaws and quirks, not just positive attributes.
    5. Some users might be lurkers or casual posters rather than highly engaged.

    Provide your response as a JSON object. Make the user feel like a real, relatable individual you might encounter online."""

    api_response, model = send_request(system_prompt, prompt)
    user_data = parse_data(api_response, "user")

    user_data["gender"] = selected_gender
    user_data["education"] = selected_education

    if user_data:
        user_data["model"] = model
        ingest_user(user_data)
        logger.info(
            f"Generated and ingested new user: {user_data.get('username', 'no username')} using model: {model}"
        )
    else:
        logger.error("Failed to generate user data")

    return user_data


def create_post_with_replies(subdeaddit, min_replies, max_replies, wait):
    post_id = create_post(subdeaddit)
    if post_id:
        logger.info(f"Created post with ID: {post_id}")
        if min_replies and max_replies:
            if wait > 0:
                logger.info(f"Waiting for {wait} seconds before generating comments...")
                time.sleep(wait)
            generate_comments_for_post(post_id, min_replies, max_replies, wait)
        return True
    else:
        logger.error("Failed to create post")
        return False


def get_random_post_from_subdeaddit(subdeaddit_name: str) -> str:
    """
    Get a random post ID from a specified subdeaddit.

    Args:
        subdeaddit_name (str): The name of the subdeaddit to get a post from.

    Returns:
        str: A random post ID from the specified subdeaddit, or None if no posts are found.
    """
    # Query the API to get posts from the specified subdeaddit
    response = requests.get(
        f"{get_api_base_url()}/api/posts?subdeaddit={subdeaddit_name}&limit=50",
        headers=get_api_headers(),
    )

    if response.status_code != 200:
        logger.error(f"Failed to retrieve posts from subdeaddit '{subdeaddit_name}'.")
        return None

    posts = response.json()["posts"]
    logger.info(f"Retrieved {len(posts)} posts from subdeaddit '{subdeaddit_name}'.")

    if not posts:
        logger.warning(f"No posts found in subdeaddit '{subdeaddit_name}'.")
        return None

    # Select a random post
    random_post = random.choice(posts)
    return random_post["id"]


def ingest_user(user_data: dict):
    """
    Ingest the generated user data into the API.

    Args:
        user_data (dict): The user data to ingest.
    """
    ingest_url = f"{get_api_base_url()}/api/ingest/user"
    response = requests.post(ingest_url, json=user_data, headers=get_api_headers())

    if response.status_code == 201:
        logger.info(f"User {user_data['username']} ingested successfully")
    else:
        logger.error(
            f"Failed to ingest user {user_data.get('username', 'no username')}. Status code: {response.status_code}"
        )
        logger.error(f"Response content: {response.content}")


@click.group()
@click.option(
    "--model",
    multiple=True,
    help="Model(s) to use for requests. Can be specified multiple times.",
)
@click.pass_context
def cli(ctx, model):
    global MODELS
    MODELS = list(model) if model else [Config.get("OPENAI_MODEL", "llama3")]
    logger.info(f"Using model(s): {', '.join(MODELS)}")
    ctx.ensure_object(dict)
    ctx.obj["models"] = MODELS


@cli.command()
@click.option("--count", type=int, default=1, help="Number of subdeaddits to create")
@click.option(
    "--wait", type=int, default=0, help="Wait time in seconds between creations"
)
@click.option("--model", help="Specific model to use for this command")
@click.pass_context
def subdeaddit(ctx, count, wait, model):
    """Create new subdeaddit(s)"""
    models = [model] if model else ctx.obj["models"]
    for i in range(count):
        logger.info(f"Creating subdeaddit {i + 1}/{count}")
        MODELS[:] = models  # Temporarily set the model for this creation
        create_subdeaddit()
        if i < count - 1 and wait > 0:
            logger.info(
                f"Waiting for {wait} seconds before creating the next subdeaddit..."
            )
            time.sleep(wait)


@cli.command()
@click.option("--count", type=int, default=1, help="Number of users to create")
@click.option(
    "--wait", type=int, default=0, help="Wait time in seconds between creations"
)
@click.option("--model", help="Specific model to use for this command")
@click.pass_context
def user(ctx, count, wait, model):
    """Create new user(s)"""
    models = [model] if model else ctx.obj["models"]
    for i in range(count):
        logger.info(f"Creating user {i + 1}/{count}")
        MODELS[:] = models  # Temporarily set the model for this creation
        generate_user()
        if i < count - 1 and wait > 0:
            logger.info(f"Waiting for {wait} seconds before creating the next user...")
            time.sleep(wait)


@cli.command()
@click.option("--subdeaddit", help="Specify the subdeaddit name for posting")
@click.option(
    "--replies", help="Specify the range of replies to generate (e.g., '7-15')"
)
@click.option(
    "--wait",
    type=int,
    default=0,
    help="Wait time in seconds between post creation and comments, and between comments",
)
@click.option("--count", type=int, default=1, help="Number of posts to create")
@click.pass_context
def post(ctx, subdeaddit, replies, wait, count):
    """Create new post(s) with optional replies"""
    min_replies, max_replies = None, None
    if replies:
        try:
            min_replies, max_replies = map(int, replies.split("-"))
        except ValueError:
            logger.error(
                "Invalid format for replies. Use 'min-max' format, e.g., '7-15'"
            )
            return

    for i in range(count):
        logger.info(f"Creating post {i + 1}/{count}")
        success = create_post_with_replies(subdeaddit, min_replies, max_replies, wait)

        if not success:
            logger.error(f"Failed to create post {i + 1}/{count}")
            continue

        if i < count - 1 and wait > 0:
            wait_time = random.uniform(0.5 * wait, 1.5 * wait)
            logger.info(
                f"Waiting for {wait_time:.2f} seconds before creating the next post..."
            )
            time.sleep(wait_time)


@cli.command()
@click.option("--post", help="Specify the post ID for commenting")
@click.option(
    "--subdeaddit", help="Specify the subdeaddit name to pick a random post from"
)
@click.pass_context
def comment(ctx, post, subdeaddit):
    """Create a new comment"""
    if post:
        create_comment(post)
    elif subdeaddit:
        post_id = get_random_post_from_subdeaddit(subdeaddit)
        if post_id:
            create_comment(post_id)
        else:
            logger.error(f"No posts found in subdeaddit '{subdeaddit}'")
    else:
        create_comment()


@cli.command()
@click.option(
    "--count", type=int, default=1, help="Number of times to repeat the action"
)
@click.option(
    "--wait", type=int, default=0, help="Wait time in seconds between iterations"
)
@click.pass_context
def loop(ctx, count, wait):
    """Perform actions in a loop"""
    logger.info(
        f"Loop enabled. Running {count} iterations with {wait} seconds wait time."
    )
    for i in range(count):
        logger.info(f"Iteration {i + 1}/{count}")
        if random.random() < 0.10:
            create_post()
        else:
            create_comment()
        if i < count - 1 and wait > 0:
            logger.info(f"Waiting for {wait} seconds before the next iteration...")
            time.sleep(wait)


if __name__ == "__main__":
    cli()
