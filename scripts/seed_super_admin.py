from __future__ import annotations

import os

from auth import hash_password
from mysql_repository import MySQLRepository, load_env_file


def main() -> None:
    load_env_file()
    required = ["SUPER_ADMIN_NAME", "SUPER_ADMIN_USERNAME", "SUPER_ADMIN_EMAIL", "SUPER_ADMIN_PASSWORD"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))
    repository = MySQLRepository()
    repository.apply_migrations()
    user_id = repository.create_super_admin(
        name=os.environ["SUPER_ADMIN_NAME"],
        username=os.environ["SUPER_ADMIN_USERNAME"],
        email=os.environ["SUPER_ADMIN_EMAIL"],
        password_hash=hash_password(os.environ["SUPER_ADMIN_PASSWORD"]),
    )
    print(f"Super Admin ready with id {user_id}.")


if __name__ == "__main__":
    main()
