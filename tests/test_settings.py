from supportkit.settings import Settings


def test_sqlalchemy_url_uses_psycopg3_driver():
    s = Settings(database_url="postgresql://u:p@localhost:5432/db")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@localhost:5432/db"


def test_sqlalchemy_url_accepts_postgres_scheme():
    s = Settings(database_url="postgres://u:p@h/db")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@h/db"


def test_sqlalchemy_url_leaves_explicit_driver_alone():
    url = "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url=url).sqlalchemy_url == url


def test_new_setting_defaults(monkeypatch):
    monkeypatch.delenv("SUPPORTKIT_MODEL", raising=False)
    monkeypatch.delenv("SUPPORTKIT_DEMO_MODE", raising=False)
    s = Settings(_env_file=None, database_url="postgresql://u:p@h/db")
    assert s.supportkit_model == "fake:rules"
    assert s.supportkit_demo_mode is False


def test_demo_mode_env(monkeypatch):
    monkeypatch.setenv("SUPPORTKIT_DEMO_MODE", "true")
    assert Settings(_env_file=None).supportkit_demo_mode is True
