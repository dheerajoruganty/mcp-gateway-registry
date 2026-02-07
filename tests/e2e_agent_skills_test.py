#!/usr/bin/env python3
"""
End-to-End Test Script for Agent Skills API.

This script exercises all Agent Skills related API endpoints and produces
a report at the end. It uses a real SKILL.md file for testing and cleans
up by deleting the skill after tests complete.

Usage:
    # Run with defaults (localhost, .token)
    uv run python tests/e2e_agent_skills_test.py

    # Run with custom registry URL
    uv run python tests/e2e_agent_skills_test.py --registry-url https://myregistry.com

    # Run with custom token file
    uv run python tests/e2e_agent_skills_test.py --token-file /path/to/token

    # Run with both custom options
    uv run python tests/e2e_agent_skills_test.py --registry-url https://myregistry.com --token-file /path/to/token
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Test Constants
TEST_SKILL_MD_URL = "https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md"
TEST_SKILL_NAME = "e2e-test-mcp-builder"
TEST_SKILL_DESCRIPTION = "E2E Test: Build and configure MCP servers"
TEST_SKILL_TAGS = ["e2e-test", "mcp", "builder", "automation"]


class TestStatus(Enum):
    """Test result status."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class TestResult:
    """Individual test result."""

    name: str
    status: TestStatus
    duration_ms: float
    message: str = ""
    details: Optional[Dict[str, Any]] = None


class AgentSkillsE2ETest:
    """End-to-end test runner for Agent Skills API."""

    def __init__(
        self,
        registry_url: str,
        token: str,
    ):
        """Initialize the test runner.

        Args:
            registry_url: Base URL of the registry
            token: JWT authentication token
        """
        self.registry_url = registry_url.rstrip("/")
        self.token = token
        self.results: List[TestResult] = []
        self.skill_path: Optional[str] = None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _record_result(
        self,
        name: str,
        status: TestStatus,
        duration_ms: float,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a test result."""
        result = TestResult(
            name=name,
            status=status,
            duration_ms=duration_ms,
            message=message,
            details=details,
        )
        self.results.append(result)

        status_symbol = {
            TestStatus.PASSED: "[PASS]",
            TestStatus.FAILED: "[FAIL]",
            TestStatus.SKIPPED: "[SKIP]",
        }[status]

        logger.info(f"{status_symbol} {name}: {message} ({duration_ms:.2f}ms)")

    def test_register_skill(self) -> bool:
        """Test skill registration."""
        test_name = "Register Skill"
        start_time = time.time()

        try:
            payload = {
                "name": TEST_SKILL_NAME,
                "description": TEST_SKILL_DESCRIPTION,
                "skill_md_url": TEST_SKILL_MD_URL,
                "tags": TEST_SKILL_TAGS,
                "visibility": "public",
            }

            response = requests.post(
                f"{self.registry_url}/api/skills",
                headers=self._get_headers(),
                json=payload,
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 201:
                data = response.json()
                self.skill_path = data.get("path", f"/skills/{TEST_SKILL_NAME}")
                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    f"Skill registered at {self.skill_path}",
                    {"response": data},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_list_skills(self) -> bool:
        """Test listing skills."""
        test_name = "List Skills"
        start_time = time.time()

        try:
            response = requests.get(
                f"{self.registry_url}/api/skills",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                skills = data.get("skills", [])
                found = any(s.get("name") == TEST_SKILL_NAME for s in skills)

                if found:
                    self._record_result(
                        test_name,
                        TestStatus.PASSED,
                        duration_ms,
                        f"Found {len(skills)} skills, test skill present",
                        {"total_count": data.get("total_count", len(skills))},
                    )
                    return True
                else:
                    self._record_result(
                        test_name,
                        TestStatus.FAILED,
                        duration_ms,
                        f"Test skill not found in {len(skills)} skills",
                    )
                    return False
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_get_skill(self) -> bool:
        """Test getting skill details."""
        test_name = "Get Skill Details"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            # skill_path is like /skills/name, API is /api/skills/{path}
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.get(
                f"{self.registry_url}/api/skills{api_path}",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    f"Retrieved skill: {data.get('name')}",
                    {"skill": data},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_update_skill(self) -> bool:
        """Test updating skill."""
        test_name = "Update Skill"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            payload = {
                "description": f"{TEST_SKILL_DESCRIPTION} (updated)",
                "tags": TEST_SKILL_TAGS + ["updated"],
            }

            response = requests.put(
                f"{self.registry_url}/api/skills{api_path}",
                headers=self._get_headers(),
                json=payload,
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    "Skill updated successfully",
                    {"response": data},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_disable_skill(self) -> bool:
        """Test disabling skill."""
        test_name = "Disable Skill"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.put(
                f"{self.registry_url}/api/skills{api_path}/disable",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    "Skill disabled successfully",
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_enable_skill(self) -> bool:
        """Test enabling skill."""
        test_name = "Enable Skill"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.put(
                f"{self.registry_url}/api/skills{api_path}/enable",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    "Skill enabled successfully",
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_health_check(self) -> bool:
        """Test skill health check."""
        test_name = "Health Check"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.get(
                f"{self.registry_url}/api/skills{api_path}/health",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                healthy = data.get("healthy", False)
                status = TestStatus.PASSED if healthy else TestStatus.FAILED
                message = "SKILL.md is accessible" if healthy else f"Health check failed: {data.get('error', 'unknown')}"

                self._record_result(
                    test_name,
                    status,
                    duration_ms,
                    message,
                    {"response": data},
                )
                return healthy
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_get_content(self) -> bool:
        """Test getting SKILL.md content."""
        test_name = "Get SKILL.md Content"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.get(
                f"{self.registry_url}/api/skills{api_path}/content",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                content = data.get("content", "")
                content_length = len(content)

                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    f"Retrieved {content_length} characters of content",
                    {"content_length": content_length, "url": data.get("url")},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_rate_skill(self) -> bool:
        """Test rating a skill."""
        test_name = "Rate Skill"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            payload = {"rating": 5}

            response = requests.post(
                f"{self.registry_url}/api/skills{api_path}/rate",
                headers=self._get_headers(),
                json=payload,
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                avg_rating = data.get("average_rating", 0)

                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    f"Rated 5 stars, average: {avg_rating:.1f}",
                    {"response": data},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_get_rating(self) -> bool:
        """Test getting skill rating."""
        test_name = "Get Rating"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.get(
                f"{self.registry_url}/api/skills{api_path}/rating",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                num_stars = data.get("num_stars", 0)
                rating_count = len(data.get("rating_details", []))

                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    f"Rating: {num_stars:.1f} stars from {rating_count} ratings",
                    {"response": data},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_search_skills(self) -> bool:
        """Test searching for skills."""
        test_name = "Search Skills"
        start_time = time.time()

        try:
            response = requests.get(
                f"{self.registry_url}/api/skills/search",
                headers=self._get_headers(),
                params={"q": "mcp builder"},
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                skills = data.get("skills", [])

                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    f"Search returned {len(skills)} results",
                    {"total_count": data.get("total_count", len(skills))},
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def test_delete_skill(self) -> bool:
        """Test deleting skill (cleanup)."""
        test_name = "Delete Skill (Cleanup)"
        start_time = time.time()

        if not self.skill_path:
            self._record_result(
                test_name,
                TestStatus.SKIPPED,
                0,
                "No skill path available",
            )
            return False

        try:
            api_path = self.skill_path.replace("/skills/", "/")
            response = requests.delete(
                f"{self.registry_url}/api/skills{api_path}",
                headers=self._get_headers(),
                timeout=30,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code in [200, 204]:
                self._record_result(
                    test_name,
                    TestStatus.PASSED,
                    duration_ms,
                    "Skill deleted successfully",
                )
                return True
            else:
                self._record_result(
                    test_name,
                    TestStatus.FAILED,
                    duration_ms,
                    f"HTTP {response.status_code}: {response.text}",
                )
                return False

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._record_result(
                test_name,
                TestStatus.FAILED,
                duration_ms,
                f"Exception: {str(e)}",
            )
            return False

    def run_all_tests(self) -> None:
        """Run all tests in sequence."""
        logger.info("=" * 60)
        logger.info("Starting Agent Skills E2E Tests")
        logger.info(f"Registry URL: {self.registry_url}")
        logger.info(f"Test Skill URL: {TEST_SKILL_MD_URL}")
        logger.info("=" * 60)

        # Run tests in order
        self.test_register_skill()
        self.test_list_skills()
        self.test_get_skill()
        self.test_update_skill()
        self.test_disable_skill()
        self.test_enable_skill()
        self.test_health_check()
        self.test_get_content()
        self.test_rate_skill()
        self.test_get_rating()
        self.test_search_skills()

        # Always try to cleanup
        self.test_delete_skill()

    def print_report(self) -> int:
        """Print test report and return exit code."""
        print("\n")
        print("=" * 70)
        print("                    AGENT SKILLS E2E TEST REPORT")
        print("=" * 70)
        print(f"  Registry URL: {self.registry_url}")
        print(f"  Test Run:     {datetime.now().isoformat()}")
        print("=" * 70)

        passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self.results if r.status == TestStatus.SKIPPED)
        total = len(self.results)
        total_time = sum(r.duration_ms for r in self.results)

        print("\n  TEST RESULTS:")
        print("  " + "-" * 66)

        for result in self.results:
            status_icon = {
                TestStatus.PASSED: "[PASS]",
                TestStatus.FAILED: "[FAIL]",
                TestStatus.SKIPPED: "[SKIP]",
            }[result.status]

            status_color = {
                TestStatus.PASSED: "\033[92m",  # Green
                TestStatus.FAILED: "\033[91m",  # Red
                TestStatus.SKIPPED: "\033[93m",  # Yellow
            }[result.status]
            reset_color = "\033[0m"

            print(f"  {status_color}{status_icon}{reset_color} {result.name:<35} {result.duration_ms:>8.2f}ms")
            if result.message:
                print(f"       {result.message}")

        print("  " + "-" * 66)
        print(f"\n  SUMMARY:")
        print(f"    Total Tests:  {total}")
        print(f"    \033[92mPassed:\033[0m       {passed}")
        print(f"    \033[91mFailed:\033[0m       {failed}")
        print(f"    \033[93mSkipped:\033[0m      {skipped}")
        print(f"    Total Time:   {total_time:.2f}ms ({total_time/1000:.2f}s)")

        if failed == 0 and passed > 0:
            print("\n  \033[92m*** ALL TESTS PASSED ***\033[0m")
            exit_code = 0
        elif failed > 0:
            print(f"\n  \033[91m*** {failed} TEST(S) FAILED ***\033[0m")
            exit_code = 1
        else:
            print("\n  \033[93m*** NO TESTS EXECUTED ***\033[0m")
            exit_code = 1

        print("=" * 70)

        return exit_code


def _load_token(
    token_file: str,
) -> str:
    """Load JWT token from file.

    Args:
        token_file: Path to token file

    Returns:
        JWT token string

    Raises:
        FileNotFoundError: If token file not found
        ValueError: If token file is empty or invalid
    """
    token_path = Path(token_file)

    if not token_path.exists():
        raise FileNotFoundError(f"Token file not found: {token_file}")

    content = token_path.read_text().strip()

    if not content:
        raise ValueError(f"Token file is empty: {token_file}")

    # Handle JSON token files (like ingress.json)
    if content.startswith("{"):
        try:
            data = json.loads(content)
            # Try different possible token field names
            for key in ["access_token", "token", "jwt"]:
                if key in data:
                    return data[key]
            raise ValueError(f"No token field found in JSON file: {token_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in token file: {e}") from e

    # Plain text token
    return content


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="End-to-End Test Script for Agent Skills API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with defaults
    uv run python tests/e2e_agent_skills_test.py

    # Run with custom registry
    uv run python tests/e2e_agent_skills_test.py --registry-url https://myregistry.com

    # Run with custom token file
    uv run python tests/e2e_agent_skills_test.py --token-file /path/to/token
        """,
    )

    parser.add_argument(
        "--registry-url",
        default="http://localhost",
        help="Registry base URL (default: http://localhost)",
    )

    parser.add_argument(
        "--token-file",
        default=".token",
        help="Path to file containing JWT token (default: .token)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = _parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load token
    try:
        token = _load_token(args.token_file)
        logger.info(f"Loaded token from {args.token_file}")
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load token: {e}")
        print(f"\nError: {e}")
        print(f"\nPlease ensure the token file exists at: {args.token_file}")
        print("You can generate a token using the credentials provider or copy")
        print("your JWT token to a file named '.token' in the repository root.")
        return 1

    # Run tests
    tester = AgentSkillsE2ETest(
        registry_url=args.registry_url,
        token=token,
    )

    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        logger.warning("Test run interrupted by user")
    except Exception as e:
        logger.exception(f"Unexpected error during test run: {e}")

    # Print report and return exit code
    return tester.print_report()


if __name__ == "__main__":
    sys.exit(main())
