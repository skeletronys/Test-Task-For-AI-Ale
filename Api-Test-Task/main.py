from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import openai
import os
from dotenv import load_dotenv


load_dotenv()

app = FastAPI()


class ReviewRequest(BaseModel):
    assignment_description: str
    github_repo_url: str
    candidate_level: str


class ReviewResponse(BaseModel):
    found_files: list
    downsides_comments: list
    rating: int
    conclusion: str


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

if not GITHUB_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("API keys are missing. Please check your .env file or environment variables.")


@app.post("/review", response_model=ReviewResponse)
async def review_code(request: ReviewRequest):
    # aunt to GitHub API
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    repo_api_url = request.github_repo_url.replace("https://github.com/", "https://api.github.com/repos/") + "/contents"

    # response file in rep
    try:
        repo_response = requests.get(repo_api_url, headers=headers)
        repo_response.raise_for_status()
        repo_contents = repo_response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"GitHub API error: {str(e)}")

    # response file
    file_contents = ""
    for file in repo_contents:
        if file["type"] == "file":
            file_response = requests.get(file["download_url"], headers=headers)
            file_response.raise_for_status()
            file_contents += f"### {file['name']} ###\n{file_response.text}\n\n"

    # create prompt
    prompt = (
        f"You are an AI code reviewer. The following is a coding assignment for a {request.candidate_level} candidate.\n"
        f"Please analyze the code in the provided files, identify potential issues, suggest improvements, and rate the overall quality.\n\n"
        f"{file_contents}"
    )

    # analysis OpenAI API
    try:
        ai_response = openai.chat.completions.create(
            model="gpt-4",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are an AI assistant analyzing code quality."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        review_text = ai_response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

    downsides = [line for line in review_text.split("\n") if line.strip()][:5]  # Візьміть перші 5 рядків
    if "improvement" in review_text.lower():
        conclusion = "The candidate has potential but needs improvement in specific areas."
    else:
        conclusion = "The candidate has demonstrated strong coding skills."

    num_issues = len(downsides)
    rating = 5

    review_text_lower = review_text.lower()
    if "critical" in review_text_lower or "serious issue" in review_text_lower:
        rating -= 2
    elif "needs improvement" in review_text_lower:
        rating -= 1

    if num_issues > 5:
        rating -= 2
    elif num_issues > 3:
        rating -= 1

    rating = max(1, min(5, rating))

    return ReviewResponse(
        found_files=[file["name"] for file in repo_contents if file["type"] == "file"],
        downsides_comments=downsides,
        rating=rating,
        conclusion=conclusion
    )


