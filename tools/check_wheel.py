"""Install a built wheel in a fresh environment and smoke-test both entry points."""

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


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
            (["status"], 4),
            (["remote", "unknown-action"], 2),
        ]:
            results = [
                subprocess.run(command + argv, capture_output=True, cwd=base, env=env)
                for command in entrypoints
            ]
            assert all(result.returncode == expected for result in results), results
            assert results[0].stdout == results[1].stdout
            assert all(not result.stderr for result in results)
            if expected:
                data = json.loads(results[0].stdout)
                assert data["ok"] is False
                assert set(data) == {
                    "schema_version",
                    "ok",
                    "command",
                    "device_id",
                    "data",
                    "error",
                }
        subprocess.run(
            [
                str(python),
                "-c",
                "from importlib.resources import files; import json; "
                "schema = json.loads(files('apple_tv_agent').joinpath('response-v1.json').read_text()); "
                "assert schema['$schema'].endswith('/2020-12/schema')",
            ],
            check=True,
            cwd=base,
            env=env,
        )
    print(
        "Clean wheel installation and both entry points passed (working directory contains spaces)."
    )


if __name__ == "__main__":
    main()
