import pytest
from fastapi.testclient import TestClient
from main import app
import requests
from unittest.mock import patch

client = TestClient(app)


class MockResponse:
    def __init__(self, json_data=None, text_data=None, status_code=200):
        self._json_data = json_data
        self._text_data = text_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    @property
    def text(self):
        return self._text_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP Error: {self.status_code}")


def test_review_success():
    def mock_github_get(*args, **kwargs):
        if "contents" in args[0]:
            return MockResponse(json_data=[
                {"name": "file1.py", "type": "file", "download_url": "https://mock_url/file1.py"},
                {"name": "file2.py", "type": "file", "download_url": "https://mock_url/file2.py"},
            ])
        else:
            return MockResponse(text_data="def test_function(): pass")

    def mock_openai_create(*args, **kwargs):
        return {"choices": [{"message": {"content": "The code looks good overall."}}]}

    with patch("requests.get", side_effect=mock_github_get), \
         patch("openai.ChatCompletion.create", side_effect=mock_openai_create):

        request_data = {
            "assignment_description": "Analyze the code",
            "github_repo_url": "https://github.com/example/repo",
            "candidate_level": "Junior",
        }

        response = client.post("/review", json=request_data)
        assert response.status_code == 200
        response_data = response.json()
        assert "found_files" in response_data
        assert len(response_data["found_files"]) == 2
        assert "downsides_comments" in response_data
        assert "rating" in response_data
        assert response_data["rating"] == 4


@pytest.mark.parametrize("github_url", ["", "invalid-url", "not-a-url"])
def test_invalid_github_url(github_url):
    request_data = {
        "assignment_description": "Analyze the code",
        "github_repo_url": github_url,
        "candidate_level": "Junior",
    }
    response = client.post("/review", json=request_data)
    assert response.status_code == 400
    assert "GitHub API error" in response.json()["detail"]


def test_empty_request():
    response = client.post("/review", json={})
    assert response.status_code == 422


def test_openai_error():
    with patch("openai.ChatCompletion.create", side_effect=Exception("Mock OpenAI error")):
        request_data = {
            "assignment_description": "Analyze the code",
            "github_repo_url": "https://github.com/example/repo",
            "candidate_level": "Junior",
        }
        response = client.post("/review", json=request_data)
        assert response.status_code == 400


def test_empty_github_repo():
    def mock_github_empty_repo(*args, **kwargs):
        return MockResponse(json_data=[])

    with patch("requests.get", side_effect=mock_github_empty_repo):
        request_data = {
            "assignment_description": "Analyze the code",
            "github_repo_url": "https://github.com/example/empty-repo",
            "candidate_level": "Junior",
        }
        response = client.post("/review", json=request_data)
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["found_files"] == []
