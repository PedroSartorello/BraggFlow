import importlib.util
from pathlib import Path

import pytest

import braggflow.webapp
from braggflow.paths import ENV_VAR, SUBDIRS, resolve_data_dir


def test_argument_wins_over_environment_and_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "env"))
    monkeypatch.chdir(tmp_path)
    assert resolve_data_dir(tmp_path / "arg", create=False) == (tmp_path / "arg").resolve()


def test_environment_wins_over_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "env"))
    monkeypatch.chdir(tmp_path)
    assert resolve_data_dir(create=False) == (tmp_path / "env").resolve()


def test_default_is_data_in_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_data_dir(create=False) == (tmp_path / "data").resolve()
    assert not (tmp_path / "data").exists(), "create=False não cria nada"


def test_subfolders_are_created(tmp_path):
    pasta = resolve_data_dir(tmp_path / "bf")
    assert sorted(p.name for p in pasta.iterdir()) == sorted(SUBDIRS)


@pytest.fixture
def app_module(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "braggflow_webapp_paths", Path(braggflow.webapp.__file__).with_name("app.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.set_data_dir(tmp_path / "outra_pasta")       # o nome não precisa ser "data"
    return module


def test_api_paths_use_the_virtual_data_prefix(app_module):
    arquivo = app_module.RAW_DIR / "ensaio.ASC"
    arquivo.write_text("x", encoding="utf-8")
    assert app_module._rel(arquivo) == "data/raw/ensaio.ASC"
    assert app_module._resolve_data_file("data/raw/ensaio.ASC") == arquivo.resolve()


@pytest.mark.parametrize("caminho", ["data/../fora.txt", "raw/ensaio.ASC", "../outra_pasta/raw/x"])
def test_paths_outside_the_data_folder_are_refused(app_module, tmp_path, caminho):
    (tmp_path / "fora.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="fora de data/"):
        app_module._resolve_data_file(caminho)
