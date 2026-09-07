"""Install a built wheel in a fresh environment and smoke-test both entry points."""

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def check_results(results, expected):
    if len(results) != 2 or any(result.returncode != expected for result in results):
        raise RuntimeError("Entry point returned an unexpected exit code.")
    if results[0].stdout != results[1].stdout:
        raise RuntimeError("Entry point output differs.")
    if any(result.stderr for result in results):
        raise RuntimeError("Entry point wrote unexpected stderr.")
    if expected:
        data = json.loads(results[0].stdout)
        if data.get("ok") is not False:
            raise RuntimeError("Expected a failure envelope.")
        if set(data) != {"schema_version", "ok", "command", "device_id", "data", "error"}:
            raise RuntimeError("Envelope fields differ from the contract.")


def check_schema(schema):
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise RuntimeError("Bundled schema has an unexpected dialect.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    wheels = list((root / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one wheel in dist/ before running this check.")
    wheel = wheels[0].resolve()
    requirements = args.requirements.resolve()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    with tempfile.TemporaryDirectory(prefix="apple tv wheel ") as directory:
        base = Path(directory)
        venv.EnvBuilder(with_pip=True).create(base / "venv")
        scripts = base / "venv" / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(requirements)],
            check=True,
            cwd=base,
            env=env,
        )
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
            check=True,
            cwd=base,
            env=env,
        )
        subprocess.run([str(python), "-m", "pip", "check"], check=True, cwd=base, env=env)
        console = scripts / ("apple-tv-agent.exe" if os.name == "nt" else "apple-tv-agent")
        entrypoints = [[str(console)], [str(python), "-m", "apple_tv_agent"]]
        for argv, expected in [
            (["--version"], 0),
            (["--help"], 0),
            (["doctor"], 0),
            (["remote", "unknown-action"], 2),
        ]:
            results = [
                subprocess.run(command + argv, capture_output=True, cwd=base, env=env)
                for command in entrypoints
            ]
            check_results(results, expected)
        resource_result = subprocess.run(
            [
                str(python),
                "-c",
                "import json; from importlib.resources import files; "
                "root = files('apple_tv_agent'); "
                "print(json.dumps({name: root.joinpath(name).read_text(encoding='utf-8') "
                "for name in ['response-v1.json', 'docs/registry.md', 'docs/pairing.md', 'docs/sessions.md', 'docs/controls.md', 'docs/troubleshooting.md']}))",
            ],
            check=True,
            capture_output=True,
            cwd=base,
            env=env,
        )
        resources = json.loads(resource_result.stdout)
        check_schema(json.loads(resources["response-v1.json"]))
        for guide in (
            "docs/registry.md",
            "docs/pairing.md",
            "docs/sessions.md",
            "docs/controls.md",
            "docs/troubleshooting.md",
        ):
            if resources[guide] != (root / guide).read_text(encoding="utf-8"):
                raise RuntimeError("Bundled recovery guide differs from the source.")
    print(
        "Clean wheel installation and both entry points passed (working directory contains spaces)."
    )


if __name__ == "__main__":
    main()
