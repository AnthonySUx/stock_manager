import pytest

from stock_manager.api.db import require_database_url


def test_database_url_is_required() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        require_database_url(None)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        require_database_url("   ")


def test_database_url_is_never_replaced_with_a_local_default() -> None:
    url = "mysql+pymysql://stock_user:secret@127.0.0.1:3307/stock_manager"
    assert require_database_url(url) == url


def test_docker_port_must_match_database_url() -> None:
    url = "mysql+pymysql://stock_user:secret@127.0.0.1:3306/stock_manager"
    with pytest.raises(RuntimeError, match="must match MYSQL_HOST_PORT"):
        require_database_url(url, docker_host_port="3307")


def test_docker_port_must_be_an_integer() -> None:
    with pytest.raises(RuntimeError, match="must be an integer"):
        require_database_url("mysql+pymysql://localhost/stock_manager", docker_host_port="mysql")
