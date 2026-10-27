# Agent evaluation

How well does an AI agent use Netdryrun with only its public docs? Ten tickets on the example labs, each with a hidden grader; a fresh headless Claude Code agent works each ticket alone. The design and the expected outcomes are in [PREREGISTRATION.md](PREREGISTRATION.md), committed before any run. The results, failures included, are in [RESULTS.md](RESULTS.md).

- `tickets/<id>/ticket/`: everything the agent gets (plus a copy of the repository's `AGENTS.md`).
- `tickets/<id>/grader.yml`: the hidden answer: right verdict, accepted decisions, which file the agent may change, and extra checks for an independent rerun of the agent's final folder.
- `validation/`: the tickets' ground truth, checked in a lab before any agent ran.
- `run_eval.py`: runs the agents and grades them. `grade_rerun.sh`: the grader's independent rerun, in WSL.
- `results/<run>/<id>/`: per ticket, the agent's full stream-json transcript (`transcript.jsonl`), its final answer, its final folder (`final/`), the last Netdryrun report it produced, and `grade.json`. `results/<run>/summary.md` is the table.

## Reproduce

The harness was written for the setup the runs used: Windows 11 with Claude Code 2.1.116 (logged in), and WSL 2 (Ubuntu 22.04) with Docker, containerlab 0.81.1 and the `quay.io/frrouting/frr:10.4.1` image. Agents call the MCP server through `wsl.exe`; the grader's reruns run in WSL too.

1. In WSL, install the Netdryrun to test into its own virtualenv:

   ```bash
   python3 -m venv ~/.venvs/ndr-eval && ~/.venvs/ndr-eval/bin/pip install netdryrun==0.3.0
   ```

2. In Git Bash on Windows, from the repository root (Python 3.10+ with PyYAML on Windows):

   ```bash
   export MSYS_NO_PATHCONV=1 NDR_EVAL_NETDRYRUN=/home/<you>/.venvs/ndr-eval/bin/netdryrun NDR_EVAL_AGENTS_REF=096bcf6
   python examples/agent-eval/run_eval.py run --run myrun --parallel 2
   ```

   `MSYS_NO_PATHCONV=1` matters: without it Git Bash rewrites `/home/...` to a Windows path and the MCP server never starts (the harness now refuses such a path). `NDR_EVAL_AGENTS_REF` is the commit whose `AGENTS.md` the agents get (`096bcf6` for the pre-registered runs). Add `--model haiku` for another model, and `--path-style windows` to give the agent the folder's Windows path instead of its WSL path (the server accepts both only from 0.3.1 on). `NDR_EVAL_DISTRO` sets the WSL distribution (default `Ubuntu-22.04`).

3. Grade again without rerunning the agents: `python examples/agent-eval/run_eval.py grade --run myrun --parallel 1`.

Each ticket takes 1 to 6 minutes; ten tickets with `--parallel 2` took about 15 minutes. Each agent runs in a new folder under `%LOCALAPPDATA%\Temp\ndr-eval`, outside any repository, with Read, Edit and Write allowed only inside that folder, WebFetch only for `netdryrun.com`, and no shell. Labs are named `ndr-eval-tNN`, so two runs of the same ticket must not overlap.

The harness also sets `NETDRYRUN_MCP_ROOT` to the ticket folder. Netdryrun 0.3.0 ignores that variable, so in the runs on 0.3.0 the MCP server was not confined to the folder (the agents had no shell). It takes effect from 0.3.1.
