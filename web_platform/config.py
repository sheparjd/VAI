"""Which environment this platform is running in, and refusing unsafe setups.

VAI_ENV picks the environment (settings come from environment variables only):

    dev         your laptop; throwaway SQLite database; open node registration
    staging     on the internet but private; test VAIs and [TEST] tasks only
    production  real workers and employers

Staging and production refuse to start unless they have their own secret key,
their own node registration key and an explicitly configured database, and
production also refuses SQLite. Each environment has its own database and keys,
so a node token from one environment can never be used on another.
"""
import os

ENVIRONMENTS = ("dev", "staging", "production")
EXAMPLE_SECRET_KEY = "change-this-to-a-random-secret-string"

VAI_ENV = (os.getenv("VAI_ENV") or "dev").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vai_marketplace.db")
SECRET_KEY = os.getenv("SECRET_KEY") or ""
# Nodes must present this key to register a new VAI. Optional in dev.
REGISTRATION_KEY = os.getenv("VAI_REGISTRATION_KEY") or ""

IS_DEV = VAI_ENV == "dev"
IS_PRODUCTION = VAI_ENV == "production"


def settings_problems() -> list[str]:
    """Everything that makes this configuration unsafe for its environment."""
    if VAI_ENV not in ENVIRONMENTS:
        return [f"VAI_ENV must be one of {', '.join(ENVIRONMENTS)} (got '{VAI_ENV}')."]
    problems = []
    if IS_DEV:
        return problems
    if not os.getenv("DATABASE_URL"):
        problems.append("DATABASE_URL must be set explicitly (each environment has its own database).")
    if len(SECRET_KEY) < 32 or SECRET_KEY == EXAMPLE_SECRET_KEY:
        problems.append("SECRET_KEY must be a random value of at least 32 characters, unique to this environment.")
    if len(REGISTRATION_KEY) < 16:
        problems.append("VAI_REGISTRATION_KEY must be set (at least 16 characters) so only your nodes can register VAIs.")
    if IS_PRODUCTION and DATABASE_URL.startswith("sqlite"):
        problems.append("Production must use PostgreSQL, not SQLite.")
    return problems


def check_settings() -> None:
    problems = settings_problems()
    if problems:
        raise RuntimeError(
            f"Refusing to start the VAI platform in '{VAI_ENV}' mode:\n  - " + "\n  - ".join(problems)
        )
