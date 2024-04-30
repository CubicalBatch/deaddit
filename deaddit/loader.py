from openai import OpenAI
import requests
import json
import random
import click

import time
from loguru import logger
import os


def send_request(system_prompt: str, prompt: str) -> dict:
    """
    Send a request to the local OLLaMA server.

    Args:
        system_prompt (str): The system prompt for the OLLaMA server.
        prompt (str): The user prompt for the OLLaMA server.

    Returns:
        dict: The response from the OLLaMA server.
    """
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "http://127.0.0.1:5001/v1")
    logger.info(
        f"Sending prompt to the server {OPENAI_API_URL}... Set environment variable OPENAI_API_URL to change the server URL."
    )
    # Set up the OpenAI client with the local OLLaMA server URL
    client = OpenAI(base_url=OPENAI_API_URL, api_key="not needed")
    response = client.chat.completions.create(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        model="llama3",
        temperature=1,
        max_tokens=1300,
        stop=["}\n```\n", "``` ", "assistant", "}  #", "} #", "}\n\n", "}\n}", "##", "**", "}\n\n", "\n\n\n\n"],
    )
    logger.info("Response received from the local OLLaMA server.")
    return response


def parse_data(api_response: dict, type: str, subdeaddit_name: str = "") -> dict:
    """
    Parse the API response and extract the relevant data.

    Args:
        api_response (dict): The response from the OLLaMA server.
        type (str): The type of data to parse (post, subdeaddit, or comment).
        subdeaddit_name (str, optional): The name of the subdeaddit. Defaults to "".

    Returns:
        dict: The parsed data.
    """
    generated_text = api_response.choices[0].message.content.strip()
    generated_text = generated_text.replace("```json", "").replace("```", "")
    if generated_text[-1] != "}":
        generated_text += "}"
    logger.info(f"Received {generated_text}")

    json_data = None
    try:
        json_data = json.loads(generated_text)
        logger.info("Parsed JSON data from the API response.")
    except:
        firstValue = generated_text.index("{")
        lastValue = len(generated_text) - generated_text[::-1].index("}")
        try:
            json_data = json.loads(generated_text[firstValue:lastValue])
        except:
            pass

    if not json_data:
        logger.warning("Failed to parse JSON data from the API response.")
        return {}

    if type == "post":
        data = json_data[f"posts"][0]
    else:
        data = json_data
    logger.info("Parsed JSON data from the API response.")

    if subdeaddit_name != "":
        data["subdeaddit"] = subdeaddit_name
    logger.info(f"Parsed {data}")
    return data


def ingest(data: dict, type: str) -> requests.Response:
    """
    Ingest the data into the API.

    Args:
        data (dict): The data to ingest.
        type (str): The type of data to ingest (post, subdeaddit, or comment).

    Returns:
        requests.Response: The response from the API.
    """
    ingest_url = "http://localhost:5000/api/ingest"

    to_post = {}
    to_post[f"{type}s"] = [data]
    logger.info(f"POSTing data to {ingest_url}")
    headers = {"Content-Type": "application/json"}
    logger.info(f"Data to be POSTed: {data}")
    response = requests.post(ingest_url, json=to_post, headers=headers)
    logger.info(f"Response received from {ingest_url}")
    logger.info(f"Status code: {response.status_code}")
    logger.info(f"Response content: {response.content}")
    return response


def create_post(subdeaddit_name: str = "") -> dict:
    """
    Create a new post.

    Args:
        subdeaddit_name (str, optional): The name of the subdeaddit to create the post in. Defaults to "".

    Returns:
        dict: The created post data.
    """
    logger.info("Creating a new post...")
    # Get the subreddits from API
    subs = requests.get("http://localhost:5000/api/subdeaddits").json()["subdeaddits"]

    if subdeaddit_name == "":
        subdeaddit = random.choice(subs)
        logger.info(f"Randomly selected subdeaddit: {subdeaddit}")
    else:
        subdeaddit = next((sub for sub in subs if sub["name"] == subdeaddit_name), None)
        if subdeaddit is None:
            # Handle the case when the specified subdeaddit is not found
            # You can raise an exception, return an error message, or take any other appropriate action
            logger.error(f"Subdeaddit '{subdeaddit_name}' not found.")
            raise ValueError(f"Subdeaddit '{subdeaddit_name}' not found.")

    system_prompt = """You are a typical redditor."""
    prompt = f"""You are a bot that generates reddit posts for a given subreddit. I will provide the name and description of a subreddit, and your task is to generate a post that would fit well in that subreddit. 

    Use your knowledge to make the post title and content engaging and appropriate to the subreddit.
    Be creative.
    Do not hesitate to write a longer post if you think it is necessary.
    Do NOT start posts with "Hey, fellow redditors" or similar phrases.

    Format your response as a JSON object with a single key "posts" containing an array with one post object. The post object should have the following keys:
    - title: A string containing the post title. Should be under 100 characters.
    - content: A string containing the post content. Can be up to 1000 tokens long. Use <br> for line breaks.
    - upvote_count: An integer estimating how many upvotes the post would get, from -100 to 1000. 
    - user: A made up username for the post author.

    Subreddit name: {subdeaddit["name"]}

    Subreddit description: 
    {subdeaddit["description"]}
    
    ONLY INCLUDE THE SINGLE JSON OBJECT IN YOUR RESPONSE. DO NOT ADD COMMENT IN THE JSON. MAKE YOUR RESPONSE VALID JSON"""

    got_successful_response = False
    while not got_successful_response:
        api_response = send_request(system_prompt, prompt)
        post_data = parse_data(api_response, "post", subdeaddit["name"])
        if post_data is not None:
            got_successful_response = True
        else:
            logger.warning("Failed to parse data from the API response. Retrying...")
    ingest(post_data, type="post")

    return post_data


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

    Provide your response in the following JSON format:

    ```json
    {{
    "name": "<name>",
    "description": "<paragraph1>\\n\\n<paragraph2>"
    }}
    ```
    
    ONLY INCLUDE THE SINGLE JSON OBJECT IN YOUR RESPONSE. DO NOT ADD COMMENT IN THE JSON. MAKE YOUR RESPONSE VALID JSON
    Please generate the new subreddit now."""

    api_response = send_request(system_prompt, prompt)
    subdeaddit_data = parse_data(api_response, "subdeaddit")

    ingest(subdeaddit_data, type="subdeaddit")
    return subdeaddit_data


def create_comment(post_id: str = "") -> dict:
    """
    Create a new comment.

    Args:
        post_id (str, optional): The ID of the post to create the comment for. Defaults to "".

    Returns:
        dict: The created comment data.
    """
    logger.info("Creating a new comment...")
    if post_id == "":
        # Query the API to get a random post ID
        response = requests.get("http://localhost:5000/api/posts?limit=50")
        if response.status_code != 200:
            logger.error("Failed to retrieve posts.")
            return None

        posts = response.json()["posts"]
        logger.info(f"Retrieved {len(posts)} posts from the API.")

        if response.json()["posts"] == 0:
            logger.warning("No posts found. Creating a new post.")
            create_post()
            response = requests.get("http://localhost:5000/api/posts?limit=50")
            posts = response.json()["posts"]

        post_id = random.choice(posts)["id"]
        post_data = next((post for post in posts if post["id"] == post_id), None)
        logger.info(f"Randomly selected post ID: {post_id}: ({post_data['subdeaddit']}) {post_data['title']}")

    # Query localhost:5000/api/post with the post ID to get the post information
    response = requests.get(f"http://localhost:5000/api/post/{post_id}")

    if response.status_code != 200:
        logger.error(f"Failed to retrieve post with ID {post_id}")
        return None

    post_data = response.json()

    # Determine the type of response to generate based on the number of comments.
    comment_count = post_data["comment_count"]
    if comment_count <= 3:
        choices = ["comment", "bad_comment"]
        weights = [80, 20]
    else:
        choices = ["comment", "reply", "bad_reply", "bad_comment"]
        weights = [40, 40, 10, 10]

    response_type = random.choices(choices, weights=weights, k=1)[0]
    logger.info(f"Response type picked: {response_type}")

    if response_type == "comment":
        prompt_addition = "Respond to the main post."
    elif response_type == "reply":
        prompt_addition = """Respond to an existing comment. Set the parent_id as the id of the comment you are responding to.
        For example, if you are replying with a comment with an id of 123, set the parent_id as "123". DO NOT LEAVE THE PARENT_ID EMPTY. SET THE PARENT_ID"""
    elif response_type == "bad_reply":
        prompt_addition = """Respond to an existing comment. but make it a bad or mean response, assign it a negative upvote count. Set the parent_id as the id of the comment you are responding to.
            For example, if you are replying with a comment with an id of 123, set the parent_id as "123". DO NOT LEAVE THE PARENT_ID EMPTY. SET THE PARENT_ID"""
    elif response_type == "bad_comment":
        prompt_addition = (
            "Respond to the main post. Make it a bad, mean or low-effort comment, assign it a negative upvote count."
        )

    # Craft the prompt to send to send_request
    system_prompt = "You are a typical redditor."
    prompt = f"""
    Given the following post and its comments, generate a new comment. {prompt_addition}

    Post Title: {post_data['title']}
    
    Post Content: {post_data['content']}
    
    Comments:
    """

    for comment in post_data["comments"][:10]:
        prompt += f"- COMMENT ID {comment['id']} - Username: {comment['user']}: {comment['content']}\n"

    prompt += """
    Generate a new comment in the following JSON format:
    
    ```json
    {
        "content": "content of the comment",
        "user": "a made up username",
        "parent_id": "id of the parent comment if you are answering a specific comment. empty string if you are answering the main post",
        "upvote_count": a number between -100 and 1000, representing the estimated upvotes the comment would receive
    }
    ```
    
    Be creative and engaging in your response. Feel free to include humor or wit if appropriate.
    Do not start your comment with "Hey there" or similar phrases.
    ONLY INCLUDE THE JSON IN YOUR RESPONSE. DO NOT ADD COMMENT IN THE JSON. MAKE YOUR RESPONSE VALID JSON. DO NOT ADD `# with a comment` or `// with a comment`
    """

    # Send the request to the LLM
    api_response = send_request(system_prompt, prompt)

    # Parse the response and extract the comment data
    comment_data = parse_data(api_response, "comment")
    comment_data["post_id"] = post_id
    # Ingest the comment data
    ingest(comment_data, type="comment")

    return comment_data


@click.command()
@click.option("--subdeaddit", is_flag=True, help="Create a new subdeaddit")
@click.option("--post", is_flag=True, help="Create a new post")
@click.option("--comment", is_flag=True, help="Create a new comment")
@click.option("--loop", is_flag=True, help="Perform the action in a loop")
@click.pass_context
def main(ctx, subdeaddit, post, comment, loop):
    if subdeaddit:
        create_subdeaddit()
    elif post:
        create_post()
    elif comment:
        create_comment()
    elif loop:
        while True:
            logger.info("Loop enabled. 5% chance of creating a post, 95% chance of creating a comment.")
            if random.random() < 0.05:
                create_post()
            else:
                create_comment()
            time.sleep(1)
    else:
        print("Invalid option. Please choose either --subdeaddit, --post, or --comment.")


if __name__ == "__main__":
    main()
