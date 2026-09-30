from src.utils.pick_log import source_version


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path


def test_version_is_short_and_stable(tmp_path):
    a = _write(tmp_path, 'a.py', 'x = 1\n')
    version = source_version([a])
    assert len(version) == 10 and version == source_version([a])


def test_version_changes_when_a_file_changes(tmp_path):
    a = _write(tmp_path, 'a.py', 'x = 1\n')
    before = source_version([a])
    _write(tmp_path, 'a.py', 'x = 2\n')
    assert source_version([a]) != before


def test_version_ignores_line_endings_and_file_order(tmp_path):
    a = _write(tmp_path, 'a.py', 'x = 1\ny = 2\n')
    b = _write(tmp_path, 'b.py', 'z = 3\n')
    expected = source_version([a, b])
    assert source_version([b, a]) == expected
    _write(tmp_path, 'a.py', 'x = 1\r\ny = 2\r\n')
    assert source_version([a, b]) == expected
