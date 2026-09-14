import os


# Set deterministic, non-production configuration before application modules are
# imported during test collection.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-only-secret-that-is-at-least-32-bytes"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "admin@example.com"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "change-me-now"

