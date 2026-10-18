from dotenv import dotenv_values
from scripts import configure


def test_configure_only_deepseek(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(configure,"ROOT",tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY",raising=False)
    monkeypatch.setattr(configure.getpass,"getpass",lambda _:"fake-demo-key")
    monkeypatch.setattr("builtins.input",lambda _:"n")
    configure.main()
    assert dotenv_values(tmp_path/".env")["DEEPSEEK_API_KEY"]=="fake-demo-key"
    assert "fake-demo-key" not in capsys.readouterr().out


def test_configure_optional_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(configure,"ROOT",tmp_path)
    for name in ["DEEPSEEK_API_KEY","DEEPSEEK_MODEL","DEEPSEEK_BASE_URL","MAX_ROUNDS","DATA_DIR"]:
        monkeypatch.delenv(name,raising=False)
    answers=iter(["y","deepseek-chat","https://api.deepseek.com","data folder","15"])
    secrets=iter(["fake-demo-key","fake-tavily-key"])
    monkeypatch.setattr("builtins.input",lambda _:next(answers))
    monkeypatch.setattr(configure.getpass,"getpass",lambda _:next(secrets))
    configure.main()
    values=dotenv_values(tmp_path/".env")
    assert values["DATA_DIR"]=="data folder"
    assert values["MAX_ROUNDS"]=="15"
    assert values["SEARCH_API_KEY"]=="fake-tavily-key"
