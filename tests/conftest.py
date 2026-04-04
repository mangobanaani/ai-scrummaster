import os

os.environ.setdefault("GITHUB_TOKEN", "ghp_test_token_for_tests_only")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test_webhook_secret")
os.environ.setdefault("API_KEY", "test-api-key-for-tests-only")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")
os.environ.setdefault("MCP_SERVER_URL", "http://localhost:3000")
os.environ.setdefault("POLICIES_PATH", "policies/rules.yaml")
