import zipfile

from hardware import build, export_fz, model


def test_generated_paths_and_csv_are_portable(tmp_path):
    path = tmp_path / "nested" / "stage.fzz"
    path.parent.mkdir()
    export_fz.write_fzz(model.Layout.load(), "A", str(path))
    with zipfile.ZipFile(path) as archive:
        assert "stage.fz" in archive.namelist()
        assert all("/" not in name and "\\" not in name for name in archive.namelist())

    out = tmp_path / "out"
    manifest = build.build(out, wokwi_dir=tmp_path / "wokwi")
    assert "wokwi/scenarios/hcsr04.test.yaml" in manifest["files"]
    assert b"\r\r\n" not in (out / "fios_estagioB.csv").read_bytes()
