"""examples/batfish-pipeline: the docs show the example workflow verbatim, and findings map back to frr.conf lines."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples" / "batfish-pipeline"


def test_docs_workflow_is_the_example_file():
    page = (ROOT / "website" / "docs" / "batfish.md").read_text(encoding="utf-8")
    block = re.search(r'```yaml title="examples/batfish-pipeline/github-workflow.yml"\n(.*?)```', page, re.S)
    assert block, "batfish.md must show github-workflow.yml in a titled yaml block"
    assert block.group(1) == (EXAMPLE / "github-workflow.yml").read_text(encoding="utf-8")


def test_findings_point_at_the_original_frr_conf_line():
    sys.path.insert(0, str(EXAMPLE))
    try:
        import batfish_check
    finally:
        sys.path.remove(str(EXAMPLE))
    wrapped = batfish_check.wrap("r2", "line one\nline two\n").splitlines()
    assert wrapped[batfish_check.OFFSET] == "line one"
    assert batfish_check.origin("configs/r2.cfg", [batfish_check.OFFSET + 20]) == "r2.conf line 20"
    assert batfish_check.origin("configs/r2.cfg", batfish_check.OFFSET - 1) == "configs/r2.cfg (wrapper)"
