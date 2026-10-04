from __future__ import annotations

from mysql_repository import MySQLRepository


def main() -> None:
    repository = MySQLRepository()
    applied = repository.apply_migrations()
    repository.seed_roles_permissions()
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database is already up to date.")


if __name__ == "__main__":
    main()
