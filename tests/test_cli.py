from urllib.parse import parse_qs, urlparse

from netdryrun import __version__
from netdryrun.cli import feedback_url, main


def test_feedback_url_prefills_only_version_and_platform():
    u = urlparse(feedback_url())
    q = parse_qs(u.query)
    assert u.netloc == "github.com" and u.path == "/netdryrun/netdryrun/issues/new"
    assert q["template"] == ["feedback.yml"] and q["version"] == [__version__]
    assert set(q) == {"template", "labels", "version", "platform"}


def test_feedback_print_only(capsys):
    assert main(["feedback", "--print-only"]) == 0
    out = capsys.readouterr().out
    assert "Nothing is sent until you submit it" in out and "issues/new?template=feedback.yml" in out
