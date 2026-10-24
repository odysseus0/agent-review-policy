# agent-review-policy

A worked example for the essay *One Person, Many Agents*.

One policy, enforced: **routine changes ship on their own; a few paths wait
for the owner.** The one requirement under it: the system can tell the owner
from the owner's agent, so the agent cannot approve as the owner.

| Piece | What it does |
| --- | --- |
| `policy.toml` | Which paths are protected and whose review they need. |
| `allowed_signers` | One SSH key per actor: the owner, and each agent. |
| `verify/verify.py` | Every commit signed by an allowed key; protected paths also need the owner's approving review of the exact head commit. Reads the policy, the keys and itself from the base commit, so a pull request can't loosen the rule that judges it. |
| `.github/workflows/policy.yml` | Runs the verifier as a required check on every pull request and review. |
| `modules/agent-workspace.nix` | A NixOS module for the agent's machine: its own signing key (made on first boot), its own GitHub App token, none of the owner's logins or keys. |

## Setup

1. Create a GitHub App for the agent, with **Contents** and **Pull
   requests** read and write and **no Workflows permission**. GitHub then
   refuses any push from the agent that touches `.github/workflows/`.
   Install it on this repository only.
2. Boot the workspace: `nix run .#nixosConfigurations.agent-vm.config.system.build.vm`.
   It prints `agent signing key: ...`. Add that line to `allowed_signers`,
   with your own key, in a commit you make yourself.
3. Have the host write a fresh installation token to
   `/run/agent-credentials/github-token`. The App's private key stays on the
   host.
4. Protect `main`: require pull requests, require the `policy` check, and
   allow auto-merge. Set the required approvals to zero. The verifier decides
   when your review is needed.

## The two runs

- **Routine:** the agent edits `app/notes.py` and opens a pull request. The
  check passes and auto-merge ships it.
- **Protected:** the agent adds `migrations/0002_*.sql`. The check fails with
  "waiting for the owner", and passes once you approve that commit, from
  your phone if you like.

## What this doesn't do

The forge never learns that the agent acts for you. "Owner via agent" is
approximated by separate keys and accounts plus a verifier you control. A
delegated token that names both of you (RFC 8693 `act`) would carry it
directly, but no forge reads one.

Tests: `nix build .#checks.x86_64-linux.verifier` (the verifier) and
`.#checks.x86_64-linux.workspace` (boots the workspace; needs KVM).
