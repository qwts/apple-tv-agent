# Setup and local pairing

The skill needs a local execution-capable agent, native macOS or Windows, Python 3.12+, LAN access to the TV and the user's native credential store. Each computer pairs independently. The project is a development package, not a published package-index release. Install from a reviewed checkout of https://github.com/qwts/apple-tv-agent; use the committed uv.lock and keep that checkout at a stable path.

## Package installation

The following commands intentionally name the checkout and interpreter. Replace the example path with the actual reviewed checkout. Python 3.14 is shown; CI also checks 3.12. No shell activation is required.

macOS (zsh/bash):

```sh
repo='/absolute/path/Apple TV Agent'
python3.14 -m venv "$repo/.venv"
"$repo/.venv/bin/python" -m pip install uv==0.12.10
"$repo/.venv/bin/uv" sync --locked --project "$repo" --python 3.14
"$repo/.venv/bin/apple-tv-agent" --version
"$repo/.venv/bin/apple-tv-agent" doctor
```

Windows PowerShell:

```powershell
$Repo = (Resolve-Path 'C:\path\Apple TV Agent').Path
py -3.14 -m venv "$Repo\.venv"
& "$Repo\.venv\Scripts\python.exe" -m pip install uv==0.12.10
& "$Repo\.venv\Scripts\uv.exe" sync --locked --project "$Repo" --python 3.14
& "$Repo\.venv\Scripts\apple-tv-agent.exe" --version
& "$Repo\.venv\Scripts\apple-tv-agent.exe" doctor
```

Give the agent the resulting absolute executable path. It can be invoked from any working directory. An equivalent fallback is the absolute virtual-environment Python path followed by `-m apple_tv_agent`. Installing/copying the skill alone does not install the CLI. Re-run locked sync after updating the checkout; do not hand-edit dependency versions to clear a doctor failure.

## Register and pair a TV

Run `discover` with that executable. A discovery candidate is not a registered device. Choose its exact candidate ID; duplicate display names require user disambiguation. In the user's own interactive terminal, run:

```sh
"/absolute/path/Apple TV Agent/.venv/bin/apple-tv-agent" pair --device CANDIDATE_ID
```

```powershell
& 'C:\path\Apple TV Agent\.venv\Scripts\apple-tv-agent.exe' pair --device CANDIDATE_ID
```

The CLI displays local pairing prompts and reads the TV PIN with hidden input. It verifies protocol credentials before storing them in macOS Keychain or Windows Credential Manager. Pairing may have per-protocol partial results; read them before claiming completion. Agents running without a TTY must hand this step to the user, not pipe a PIN or create a fake terminal to collect it in chat.

After pairing, use `devices list` to obtain the registered UUID. Verify `status --device UUID`, then run the requested action after checking capabilities. Aliases/defaults are explicit preferences, changed only when requested via `devices alias --device UUID --name living-room` or `devices default --device UUID`.

## Install the portable skill

Copy the entire `apple-tv-control` directory, including its references, into the chosen client's supported skill directory. Current Codex local discovery supports a user directory at `~/.agents/skills` and repository directories at `.agents/skills`. Avoid duplicate installations with the same skill name. Codex normally detects updates; restart it if the skill does not appear. [Official skill documentation](https://learn.chatgpt.com/docs/build-skills)

Example explicit user installation from a checkout, refusing to overwrite an existing skill:

```sh
repo='/absolute/path/Apple TV Agent'
dest="$HOME/.agents/skills/apple-tv-control"
if [ -e "$dest" ]; then
  echo 'Skill already exists; inspect it before updating.'
else
  mkdir -p "$HOME/.agents/skills"
  cp -R "$repo/skills/apple-tv-control" "$dest"
fi
```

```powershell
$Repo = (Resolve-Path 'C:\path\Apple TV Agent').Path
$Dest = Join-Path $HOME '.agents\skills\apple-tv-control'
if (Test-Path $Dest) { throw 'Skill already exists; inspect it before updating.' }
New-Item -ItemType Directory -Force (Split-Path $Dest) | Out-Null
Copy-Item -Recurse "$Repo\skills\apple-tv-control" $Dest
```

An explicitly chosen directory symlink is also possible where the OS/client supports it; a plain copy is portable and does not require Windows symlink privileges. For other skill-capable clients, use their documented directory without changing unrelated configuration. Normal implicit skill selection stays enabled. Neither building the package nor running doctor installs a skill or modifies client settings.

The wheel also bundles the directory under `apple_tv_agent/skills/apple-tv-control`; maintainers can export it with Python importlib.resources. The source checkout and sdist include `skills/apple-tv-control` directly.

## Support evidence

Automated installation/package tests cover macOS and Windows Server with Python 3.12/3.14, including fresh environments and paths containing spaces. Real Apple TV checks have macOS evidence. Windows 11 TV/native-vault validation remains a release gate; CI is not a claim that this hardware workflow has passed there.
