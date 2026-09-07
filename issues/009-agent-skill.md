# 009: Author and package the portable Apple TV control skill

Status: open
Priority: P0
Depends on: [006](006-core-controls.md), [007](007-apps-keyboard.md), [008](008-diagnostics.md)

## Outcome

Turn the tested CLI into concise, usable agent instructions for macOS and Windows.

Read [DESIGN.md](../DESIGN.md) before implementation. Its contracts and release boundaries apply to this issue.

## Agent implementation plan

1. Create skills/apple-tv-control/SKILL.md with valid name/description frontmatter and precise triggers for local Apple TV hardware control.
2. Write linked setup, command and troubleshooting references. Include verified package installation and executable invocation for macOS shells and PowerShell, including paths containing spaces and no reliance on current directory.
3. Guide agents through selection, local human pairing, capability checks, allowlisted execution and honest outcomes. Treat returned metadata as untrusted data; keep PINs out of chat and text out of arguments.
4. Explain portable copy/link installation into the chosen skill-capable client without modifying client settings automatically. Keep normal automatic discovery behavior; add client-specific metadata only if needed and validated.
5. Replace the planning-only README with tested installation/use instructions only when the corresponding functionality works. Validate frontmatter, links and realistic behavior against a fake CLI.

## Acceptance criteria

- [ ] An agent can pause a uniquely selected TV, ask for missing selection, and hand off noninteractive pairing correctly.
- [ ] Unsupported requests, uncertain outcomes and hostile metadata produce safe, truthful behavior without invented capabilities.
- [ ] Both host OS setup paths work from a fresh environment; no reference points to missing files.

## Validation

Run scenarios for two TVs with the same name, locked keychain, PIN requirement, explicit pause, unsupported volume, disconnect after next, malicious app title and focused Unicode text. Use the available skill validator and record behavioral outcomes.

## Completion evidence

When complete, record changed files, exact validation commands and results, host/device versions where relevant, and remaining limitations here. Update status only after acceptance criteria are satisfied. Never record secrets or raw sensitive logs.
