from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str
    charset: str = "utf8mb4"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        missing = [
            name
            for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "Missing MySQL environment variables: "
                + ", ".join(missing)
                + ". See .env.example."
            )
        return cls(
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "3306")),
            name=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{quote_plus(self.name)}?charset={self.charset}"
        )

    @property
    def pymysql_kwargs(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.name,
            "charset": self.charset,
            "cursorclass": None,
            "autocommit": False,
        }
