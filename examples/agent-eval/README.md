# Agent evaluation

How well does an AI agent use Netdryrun with only its public docs? Ten tickets on the example labs, each with a hidden grader; a fresh headless Claude Code agent works each ticket alone. The design and the expected outcomes are in [PREREGISTRATION.md](PREREGISTRATION.md), committed before any run. The results, failures included, are in [RESULTS.md](RESULTS.md).

- `tickets/<id>/ticket/`: everything the agent gets (plus a copy of the repository's `AGENTS.md`).
- `tickets/<id>/grader.yml`: the hidden answer: right verdict, accepted decisions, which file the agent may change, and extra checks for an independent rerun of the agent's final folder.
- `run_eval.py`: runs the agents and grades them. `grade_rerun.sh`: the grader's independent rerun, in WSL.
- `results/<run>/<id>/`: per ticket, the agent's full stream-json transcript, its final answer, its final folder, and `grade.json`.

To reproduce (Windows with Claude Code; Netdryrun, Docker and containerlab in WSL):

```bash
python examples/agent-eval/run_eval.py run --run myrun --parallel 3
```

Set `NDR_EVAL_NETDRYRUN` to the `netdryrun` binary inside WSL and `NDR_EVAL_DISTRO` to the WSL distribution. Each agent runs in a new folder under `%LOCALAPPDATA%\Temp\ndr-eval`, outside any repository.
