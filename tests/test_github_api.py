"""Tests für GitHubAPI."""

from unittest.mock import MagicMock, patch

from core.github_api import GitHubAPI


class TestGitHubAPI:
    """Tests für GitHub API Client."""

    @patch("core.github_api.get_gh_cli_token", return_value=None)
    def test_no_token_returns_empty(self, mock_cli):
        """Ohne Token gibt get_repos leere Liste zurück."""
        api = GitHubAPI(token=None)
        repos = api.get_repos()
        assert repos == []

    def test_headers_with_token(self):
        """Headers enthalten Authorization wenn Token gesetzt."""
        api = GitHubAPI(token="test_token_123")
        headers = api._headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_token_123"
        assert headers["Accept"] == "application/vnd.github+json"

    @patch("core.github_api.get_gh_cli_token", return_value=None)
    def test_headers_without_token(self, mock_cli):
        """Headers ohne Authorization wenn kein Token."""
        api = GitHubAPI(token=None)
        headers = api._headers()

        assert "Authorization" not in headers
        assert "Accept" in headers

    @patch("core.github_api.get_gh_cli_token", return_value=None)
    def test_set_token(self, mock_cli):
        """Token setzen funktioniert."""
        api = GitHubAPI()
        assert api.token is None

        api.set_token("new_token")
        assert api.token == "new_token"

    @patch("core.github_api.requests.get")
    def test_get_user_success(self, mock_get):
        """get_user bei erfolgreicher Antwort."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"login": "testuser", "id": 12345}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        api = GitHubAPI(token="valid_token")
        user = api.get_user()

        assert user is not None
        assert user["login"] == "testuser"

    @patch("core.github_api.requests.get")
    def test_get_repos_success(self, mock_get):
        """get_repos parst Antwort korrekt."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "name": "test-repo",
                "full_name": "user/test-repo",
                "owner": {"login": "user"},
                "private": False,
                "html_url": "https://github.com/user/test-repo",
                "clone_url": "https://github.com/user/test-repo.git",
                "ssh_url": "git@github.com:user/test-repo.git",
                "description": "A test repo",
                "updated_at": "2024-01-01T00:00:00Z",
                "archived": False,
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        api = GitHubAPI(token="valid_token")
        repos = api.get_repos()

        assert len(repos) == 1
        assert repos[0]["name"] == "test-repo"
        assert repos[0]["owner"] == "user"
        assert repos[0]["ssh_url"] == "git@github.com:user/test-repo.git"

    @patch("core.github_api.requests.get")
    def test_get_repos_excludes_private(self, mock_get):
        """get_repos kann private Repos ausschließen."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "name": "public-repo",
                "full_name": "user/public-repo",
                "owner": {"login": "user"},
                "private": False,
                "html_url": "",
                "clone_url": "",
                "ssh_url": "",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "name": "private-repo",
                "full_name": "user/private-repo",
                "owner": {"login": "user"},
                "private": True,
                "html_url": "",
                "clone_url": "",
                "ssh_url": "",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        api = GitHubAPI(token="valid_token")
        repos = api.get_repos(include_private=False)

        assert len(repos) == 1
        assert repos[0]["name"] == "public-repo"

    @patch("core.github_api.get_gh_cli_token", return_value=None)
    def test_test_connection_no_token(self, mock_cli):
        """test_connection ohne Token gibt Fehler."""
        api = GitHubAPI(token=None)
        success, message = api.test_connection()

        assert success is False
        assert "Token" in message

    @patch("core.github_api.requests.get")
    def test_test_connection_success(self, mock_get):
        """test_connection bei Erfolg."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"login": "testuser"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        api = GitHubAPI(token="valid_token")
        success, message = api.test_connection()

        assert success is True
        assert "testuser" in message

    @patch("core.github_api.get_gh_cli_token", return_value="gh_cli_token_123")
    def test_gh_cli_token_fallback(self, mock_cli):
        """Token wird von gh CLI geladen wenn kein anderer verfügbar."""
        api = GitHubAPI(token=None, db=None)
        assert api.token == "gh_cli_token_123"
