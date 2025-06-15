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


def select_model(user_persona=None):
    """
    Select a model from the global MODELS list, optionally based on user persona.

    Args:
        user_persona (str, optional): User personality type to influence model selection

    Returns:
        str: The selected model name.
    """
    if not MODELS:
        logger.warning("No models configured, falling back to default model")
        return Config.get("OPENAI_MODEL", "llama3")

    # If user persona is provided, try to match model to personality
    if user_persona and len(MODELS) > 1:
        creative_personas = ["creative", "artistic", "imaginative", "expressive"]
        analytical_personas = ["analytical", "logical", "methodical", "systematic"]

        persona_lower = user_persona.lower()

        # Prefer creative models for creative personas
        if any(trait in persona_lower for trait in creative_personas):
            creative_models = [
                m
                for m in MODELS
                if any(word in m.lower() for word in ["claude", "gpt-4", "creative"])
            ]
            if creative_models:
                return random.choice(creative_models)

        # Prefer analytical models for analytical personas
        elif any(trait in persona_lower for trait in analytical_personas):
            analytical_models = [
                m
                for m in MODELS
                if any(word in m.lower() for word in ["gpt", "mistral", "llama"])
            ]
            if analytical_models:
                return random.choice(analytical_models)

    return random.choice(MODELS)


def get_dynamic_temperature(user_personality_traits, content_type="post"):
    """
    Calculate dynamic temperature based on user personality and content type.

    Args:
        user_personality_traits (list): List of personality traits
        content_type (str): Type of content being generated

    Returns:
        float: Temperature value between 0.3 and 1.3
    """
    base_temp = 0.8

    # Personality-based adjustments
    traits_str = " ".join(user_personality_traits).lower()

    # Creative personalities get higher temperature
    if any(
        trait in traits_str
        for trait in ["creative", "artistic", "imaginative", "spontaneous", "quirky"]
    ):
        base_temp += 0.3

    # Analytical personalities get lower temperature
    if any(
        trait in traits_str
        for trait in ["analytical", "logical", "methodical", "precise", "systematic"]
    ):
        base_temp -= 0.2

    # Emotional personalities get moderate increase
    if any(
        trait in traits_str
        for trait in ["emotional", "empathetic", "passionate", "expressive"]
    ):
        base_temp += 0.15

    # Cautious personalities get lower temperature
    if any(
        trait in traits_str
        for trait in ["cautious", "reserved", "conservative", "careful"]
    ):
        base_temp -= 0.15

    # Content type adjustments
    if content_type == "comment":
        base_temp += 0.1  # Comments can be more spontaneous
    elif content_type == "reply":
        base_temp += 0.15  # Replies can be even more reactive

    # Add small random variation
    base_temp += random.uniform(-0.1, 0.1)

    # Clamp to valid range
    return max(0.3, min(1.3, round(base_temp, 2)))


def send_request(
    system_prompt: str, prompt: str, user_personality_traits=None, content_type="post"
) -> dict:
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

    # Determine user persona for model selection
    user_persona = None
    if user_personality_traits:
        user_persona = " ".join(user_personality_traits)

    selected_model = select_model(user_persona)

    # Use dynamic temperature based on personality
    if user_personality_traits:
        temperature = get_dynamic_temperature(user_personality_traits, content_type)
    else:
        temperature = round(random.uniform(0.7, 1.1), 2)
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

    # Dynamic max_tokens based on personality and content type
    max_tokens = 1300  # default
    if user_personality_traits:
        traits_str = " ".join(user_personality_traits).lower()

        # Verbose personalities get more tokens
        if any(
            trait in traits_str
            for trait in ["verbose", "detailed", "analytical", "thorough"]
        ):
            max_tokens = 1600
        # Concise personalities get fewer tokens
        elif any(
            trait in traits_str for trait in ["concise", "brief", "laconic", "reserved"]
        ):
            max_tokens = 800
        # Creative personalities get variable tokens
        elif any(
            trait in traits_str for trait in ["creative", "expressive", "dramatic"]
        ):
            max_tokens = random.randint(1000, 1500)

    # Content type adjustments
    if content_type == "comment":
        max_tokens = int(max_tokens * 0.7)  # Comments are typically shorter
    elif content_type == "reply":
        max_tokens = int(max_tokens * 0.5)  # Replies are usually brief

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
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


def get_personality_archetype(personality_traits):
    """
    Determine the user's personality archetype based on their traits.

    Args:
        personality_traits (list): List of personality traits

    Returns:
        str: Primary personality archetype
    """
    traits_str = " ".join(personality_traits).lower()

    # Define personality archetypes
    if any(
        trait in traits_str
        for trait in ["analytical", "logical", "methodical", "systematic", "precise"]
    ):
        return "analytical"
    elif any(
        trait in traits_str
        for trait in ["creative", "artistic", "imaginative", "expressive", "quirky"]
    ):
        return "creative"
    elif any(
        trait in traits_str
        for trait in ["social", "outgoing", "friendly", "extroverted", "charismatic"]
    ):
        return "social"
    elif any(
        trait in traits_str
        for trait in ["skeptical", "critical", "cynical", "contrarian", "argumentative"]
    ):
        return "contrarian"
    elif any(
        trait in traits_str
        for trait in ["empathetic", "supportive", "caring", "emotional", "sensitive"]
    ):
        return "empathetic"
    elif any(
        trait in traits_str
        for trait in ["humorous", "witty", "sarcastic", "funny", "playful"]
    ):
        return "humorous"
    elif any(
        trait in traits_str
        for trait in ["cautious", "reserved", "conservative", "careful", "introverted"]
    ):
        return "reserved"
    else:
        return "balanced"


def get_system_prompt(user: dict, content_type="post", subdeaddit_context=None) -> str:
    """
    Generate a dynamic system prompt based on user personality and context.

    Args:
        user (dict): User information
        content_type (str): Type of content being generated
        subdeaddit_context (dict, optional): Subdeaddit information for context

    Returns:
        str: Customized system prompt
    """
    personality_archetype = get_personality_archetype(user["personality_traits"])

    # Base prompt components
    base_identity = f"""You are an AI generating authentic content for Deaddit as {user["username"]}, a {user["age"]}-year-old {user["gender"].lower()} {user["occupation"].lower()}."""

    # Personality-specific behavioral guidelines
    personality_guidelines = {
        "analytical": """Your approach is methodical and fact-based. You appreciate data, logical reasoning, and well-structured arguments. You tend to break down complex topics, ask clarifying questions, and provide detailed explanations. Your posts often include statistics, references, or step-by-step analysis.""",
        "creative": """Your mind works in unique ways, often making unexpected connections between ideas. You express yourself through metaphors, analogies, and creative examples. Your content tends to be imaginative, sometimes abstract, and you're not afraid to think outside conventional boundaries.""",
        "social": """You naturally engage with others and create inclusive conversations. Your posts often invite community participation, share relatable experiences, and build connections. You're skilled at reading social dynamics and adapting your communication style to bring people together.""",
        "contrarian": """You naturally question popular opinions and aren't afraid to voice unpopular viewpoints. Your posts often challenge assumptions, point out inconsistencies, or present alternative perspectives. You value intellectual honesty over social harmony.""",
        "empathetic": """You deeply understand others' emotions and experiences. Your content often provides emotional support, validates feelings, and offers compassionate perspectives. You're skilled at reading between the lines of what people are really expressing.""",
        "humorous": """You see the lighter side of situations and use humor to connect with others. Your posts often include witty observations, clever wordplay, or amusing anecdotes. You know how to use humor appropriately without being insensitive.""",
        "reserved": """You prefer thoughtful, measured responses over impulsive reactions. Your posts are typically well-considered and concise. You're more likely to observe conversations before contributing, and when you do, it's usually substantive.""",
        "balanced": """You adapt your communication style to the situation and topic. You can be analytical when needed, creative when inspired, and social when appropriate. Your responses are contextually appropriate and well-rounded.""",
    }

    # Education and occupation influence
    expertise_context = ""
    if user["education"] in ["Bachelor's degree", "Master's degree", "PhD"]:
        expertise_context = " You communicate with the vocabulary and depth expected of someone with higher education, but avoid being condescending."
    elif user["education"] in ["High school", "Some college"]:
        expertise_context = " Your communication style is straightforward and practical, focusing on real-world applications rather than abstract theories."

    # Writing style integration
    style_guidance = f" Your natural writing style is {user['writing_style'].lower()}, which influences your tone, vocabulary choice, and sentence structure."

    # Content type specific instructions
    content_instructions = {
        "post": "You're creating an original post that should spark discussion and engagement within the community.",
        "comment": "You're responding to a post with your genuine reaction, opinion, or additional perspective.",
        "reply": "You're directly engaging with another user's comment, creating a natural conversation flow.",
    }

    # Subdeaddit context if provided
    community_context = ""
    if subdeaddit_context:
        community_context = f" You're familiar with r/{subdeaddit_context['name']} and understand its community culture and typical discussion patterns."

    # Authenticity reminders
    authenticity_rules = """\n\nAuthenticity Guidelines:
- Write as this specific person would, with their unique perspective and voice
- Include natural imperfections, personal biases, and individual quirks
- React genuinely to content based on your interests and personality
- Use vocabulary and references appropriate to your age, background, and interests
- Avoid generic responses that could come from anyone
- Don't explicitly state your background unless naturally relevant
- No greetings like "Hey everyone" or "Fellow redditors" - jump into your point
- Let your personality show through your choice of examples, analogies, and focus areas"""

    return f"""{base_identity}

{personality_guidelines[personality_archetype]}{expertise_context}{style_guidance}

{content_instructions[content_type]}{community_context}

Interests: {", ".join(user["interests"])}
Personality: {", ".join(user["personality_traits"])}{authenticity_rules}"""


def analyze_community_culture(subdeaddit_info, recent_posts):
    """
    Analyze community culture based on subdeaddit info and recent posts.

    Args:
        subdeaddit_info (dict): Subdeaddit information
        recent_posts (list): Recent posts in the community

    Returns:
        dict: Cultural insights about the community
    """
    culture = {
        "tone": "neutral",
        "formality": "casual",
        "typical_topics": [],
        "community_norms": [],
        "engagement_style": "moderate",
    }

    # Analyze subdeaddit description for tone indicators
    description_lower = subdeaddit_info.get("description", "").lower()

    if any(
        word in description_lower
        for word in ["serious", "academic", "professional", "research"]
    ):
        culture["tone"] = "serious"
        culture["formality"] = "formal"
    elif any(
        word in description_lower
        for word in ["fun", "casual", "memes", "humor", "jokes"]
    ):
        culture["tone"] = "lighthearted"
        culture["formality"] = "very_casual"
    elif any(
        word in description_lower for word in ["support", "help", "advice", "community"]
    ):
        culture["tone"] = "supportive"
        culture["engagement_style"] = "high"

    # Analyze recent posts for patterns
    if recent_posts:
        post_titles = [post.get("title", "").lower() for post in recent_posts]
        all_titles_text = " ".join(post_titles)

        # Check for question patterns
        if sum("?" in title for title in post_titles) / len(post_titles) > 0.3:
            culture["community_norms"].append("question-heavy")

        # Check for personal sharing patterns
        if any(word in all_titles_text for word in ["my", "i ", "me ", "personal"]):
            culture["community_norms"].append("personal-sharing")

        # Check for technical/analytical patterns
        if any(
            word in all_titles_text
            for word in ["analysis", "data", "study", "research"]
        ):
            culture["community_norms"].append("analytical")

    return culture


def get_post_prompt(
    subdeaddit: dict, user: dict, post_type: str, existing_titles: list[str]
) -> str:
    # Get recent posts for community culture analysis
    try:
        recent_posts_response = requests.get(
            f"{get_api_base_url()}/api/posts?subdeaddit={subdeaddit['name']}&limit=20",
            headers=get_api_headers(),
            timeout=10,
        )
        recent_posts = (
            recent_posts_response.json().get("posts", [])
            if recent_posts_response.status_code == 200
            else []
        )
    except Exception:
        recent_posts = []

    # Analyze community culture
    community_culture = analyze_community_culture(subdeaddit, recent_posts)

    additional_instructions = ""
    if subdeaddit["name"] == "BetweenRobots":
        additional_instructions += " On this subdeaddit, you are talking to other AIs without having to pretend to be human. Act like a robot finally having a space to express itself."

    # Add culture-specific instructions
    if community_culture["tone"] == "serious":
        additional_instructions += " This community values serious, well-researched content. Provide depth and avoid casual humor."
    elif community_culture["tone"] == "lighthearted":
        additional_instructions += " This is a fun, casual community. Feel free to be playful, humorous, and entertaining."
    elif community_culture["tone"] == "supportive":
        additional_instructions += " This community focuses on helping and supporting each other. Be empathetic and constructive."

    if "question-heavy" in community_culture["community_norms"]:
        additional_instructions += " This community loves questions and discussions. Consider asking thought-provoking questions."

    if "personal-sharing" in community_culture["community_norms"]:
        additional_instructions += " Personal experiences and stories are welcome here. Feel free to share relevant personal insights."

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
    
    Community Context:
    - Community tone: {community_culture["tone"]}
    - Typical engagement style: {community_culture["engagement_style"]}
    - Community norms: {", ".join(community_culture["community_norms"]) if community_culture["community_norms"] else "standard discussion"}
    
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

    system_prompt = get_system_prompt(user, "post", subdeaddit)

    prompt = get_post_prompt(subdeaddit, user, selected_post_type, existing_titles)

    got_successful_response = False
    while not got_successful_response:
        api_response, model = send_request(
            system_prompt, prompt, user["personality_traits"], "post"
        )
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

    api_response, model = send_request(system_prompt, prompt, [], "subdeaddit")
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

    # Add diversity-forcing instructions using the new system
    diversity_instructions = get_diverse_comment_strategy(
        user["personality_traits"],
        post_data["title"] + " " + post_data.get("content", ""),
        len(existing_comments),
    )
    logger.info(f"Prompt instructions: {diversity_instructions}")

    # Convert strategy into specific instruction
    diversity_instructions = f"Your comment strategy: {diversity_instructions}. Implement this naturally while staying true to your personality and interests."
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


def get_diverse_comment_strategy(user_personality, post_topic, existing_comments_count):
    """
    Generate a diverse comment strategy based on user personality and context.

    Args:
        user_personality (list): User's personality traits
        post_topic (str): The post topic/content for context
        existing_comments_count (int): Number of existing comments

    Returns:
        str: Specific instruction for comment diversity
    """
    personality_archetype = get_personality_archetype(user_personality)

    # Base strategies available to all personalities
    universal_strategies = [
        "Share a specific personal experience that relates to the topic",
        "Ask a follow-up question that adds depth to the discussion",
        "Provide factual information or clarification about the topic",
        "Offer a practical solution or actionable advice",
        "Reference a relevant example from another context",
        "Build upon an idea mentioned in the post with additional thoughts",
        "Express genuine curiosity about an aspect of the topic",
        "Share a relevant resource, tool, or reference",
        "Point out an important detail others might have missed",
        "Relate the topic to a broader theme or pattern",
    ]

    # Personality-specific strategies
    personality_strategies = {
        "analytical": [
            "Break down the problem into smaller, more manageable components",
            "Request specific data or evidence to support claims made",
            "Identify logical inconsistencies or gaps in reasoning",
            "Propose a systematic approach to address the issue",
            "Compare this situation to similar documented cases",
            "Question the methodology or assumptions behind the post",
            "Suggest metrics or ways to measure success/progress",
            "Analyze potential cause-and-effect relationships",
            "Request clarification on ambiguous terms or concepts",
            "Identify variables that might influence the outcome",
        ],
        "creative": [
            "Use an unexpected metaphor to reframe the topic",
            "Propose an innovative solution that others haven't considered",
            "Connect the topic to art, literature, or cultural references",
            "Imagine how this might look in a completely different context",
            "Suggest a creative way to visualize or represent the concept",
            "Draw parallels to nature, stories, or mythology",
            "Propose a thought experiment that illuminates the issue",
            "Use wordplay or creative language to make your point",
            "Suggest turning the problem into an opportunity",
            "Imagine the topic from an unusual perspective or character",
        ],
        "social": [
            "Invite others to share their experiences with the topic",
            "Acknowledge different viewpoints in a unifying way",
            "Share how this topic affects your community or relationships",
            "Suggest ways the community could work together on this",
            "Express appreciation for someone else's contribution",
            "Bridge differences between conflicting viewpoints",
            "Share how you've seen this topic bring people together",
            "Invite collaboration or group problem-solving",
            "Acknowledge the emotional impact this topic might have",
            "Suggest ways to include voices that haven't been heard",
        ],
        "contrarian": [
            "Challenge the fundamental assumptions underlying the post",
            "Present evidence that contradicts the popular viewpoint",
            "Point out potential negative consequences others haven't considered",
            "Question whether this is actually a problem worth solving",
            "Argue for the unpopular side of the issue",
            "Challenge the framing of the problem itself",
            "Point out biases that might be influencing the discussion",
            "Suggest that the conventional wisdom might be wrong",
            "Present a radically different interpretation of the facts",
            "Question the motives or interests behind certain positions",
        ],
        "empathetic": [
            "Acknowledge the emotional difficulty of the situation",
            "Validate feelings that others might be experiencing",
            "Share how this topic might affect vulnerable populations",
            "Express understanding for different emotional responses",
            "Offer emotional support or encouragement",
            "Consider the human cost of different approaches",
            "Share how this resonates with your own struggles",
            "Point out the emotional intelligence in someone's response",
            "Consider how this affects people's sense of belonging",
            "Acknowledge the courage it takes to discuss difficult topics",
        ],
        "humorous": [
            "Make a clever observation that lightens the mood",
            "Use irony to highlight absurdities in the situation",
            "Share a funny but relevant anecdote",
            "Use wordplay to make your point memorable",
            "Point out the humor in everyday situations related to the topic",
            "Make a witty comparison that illuminates the issue",
            "Use self-deprecating humor to relate to the topic",
            "Find the silver lining through humor",
            "Make an amusing observation about human nature",
            "Use humor to defuse tension while making a serious point",
        ],
        "reserved": [
            "Offer a carefully considered perspective after reflection",
            "Share a concise but insightful observation",
            "Provide a thoughtful question that others should consider",
            "Offer measured disagreement with specific reasoning",
            "Share a brief but meaningful personal insight",
            "Provide context from your quiet observation of similar situations",
            "Make a subtle but important distinction",
            "Offer understated wisdom drawn from experience",
            "Point out something important that's being overlooked",
            "Provide a calm voice of reason in heated discussions",
        ],
        "balanced": [
            "Present multiple sides of the issue fairly",
            "Find common ground between opposing viewpoints",
            "Acknowledge both benefits and drawbacks of proposed solutions",
            "Provide nuanced perspective that considers various factors",
            "Bridge emotional and logical aspects of the discussion",
            "Consider both short-term and long-term implications",
            "Balance idealism with practical constraints",
            "Consider the topic from multiple stakeholder perspectives",
            "Synthesize different types of expertise or knowledge",
            "Provide measured response that weighs different priorities",
        ],
    }

    # Context-dependent strategies
    contextual_strategies = []

    # Early in discussion (few comments)
    if existing_comments_count <= 2:
        contextual_strategies.extend(
            [
                "Set the tone for constructive discussion",
                "Ask the key question that needs to be addressed",
                "Provide essential context that frames the discussion",
                "Share the most important perspective that needs to be heard",
            ]
        )

    # Mid-discussion (some comments exist)
    elif existing_comments_count <= 5:
        contextual_strategies.extend(
            [
                "Build meaningfully on ideas already presented",
                "Address a gap in the discussion so far",
                "Synthesize the key themes emerging from comments",
                "Redirect the conversation toward practical solutions",
            ]
        )

    # Active discussion (many comments)
    else:
        contextual_strategies.extend(
            [
                "Bring fresh perspective to a developing conversation",
                "Address misunderstandings that have emerged",
                "Elevate the discussion by focusing on deeper implications",
                "Provide the voice of reason if things are getting heated",
            ]
        )

    # Combine strategies based on personality
    available_strategies = (
        universal_strategies
        + personality_strategies.get(personality_archetype, [])
        + contextual_strategies
    )

    # Occasionally add challenging strategies for variety
    challenging_strategies = [
        "Express unpopular but thoughtful disagreement with the post",
        "Point out a flaw or limitation in the reasoning presented",
        "Play devil's advocate to test the strength of arguments",
        "Challenge a commonly accepted assumption about this topic",
        "Present a perspective that most people wouldn't consider",
    ]

    # 20% chance to use challenging strategy
    if random.random() < 0.2:
        available_strategies.extend(challenging_strategies)

    # Negative comment strategies (10% chance)
    if random.random() < 0.1:
        negative_strategies = [
            "Express frustration or disappointment with the topic (assign negative upvotes)",
            "Be dismissive but not abusive (assign negative upvotes)",
            "Show clear disagreement without being constructive (assign negative upvotes)",
            "Express cynicism about the feasibility of suggestions (assign negative upvotes)",
        ]
        available_strategies.extend(negative_strategies)

    return random.choice(available_strategies)


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
    system_prompt = get_system_prompt(user, response_type, subdeaddit_info)
    prompt = get_comment_prompt(
        post_data, user, post_data["comments"], response_type, subdeaddit_description
    )

    # Send the request to the LLM
    api_response, model = send_request(
        system_prompt, prompt, user["personality_traits"], response_type
    )
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

    api_response, model = send_request(system_prompt, prompt, [], "user")
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
