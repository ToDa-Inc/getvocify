from app.services.whatsapp.split import split_text


def test_split_keeps_short_text():
    assert split_text("hola") == ["hola"]


def test_split_on_blank_lines_when_over_limit():
    a = "A" * 3000
    b = "B" * 3000
    parts = split_text(a + "\n\n" + b)
    assert len(parts) == 2
    assert all(len(p) <= 4096 for p in parts)
