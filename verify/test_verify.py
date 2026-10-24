import os
import subprocess
import tempfile
import unittest

import verify


# Isolate from the machine's Git config (signing defaults, signing programs).
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = d = self.tmp.name
        self.keys = {}
        for who in ("agent", "george"):
            key = os.path.join(d, f"{who}_key")
            run(d, "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", who, "-f", key)
            self.keys[who] = key
        self.repo = os.path.join(d, "repo")
        os.mkdir(self.repo)
        run(self.repo, "git", "init", "-q", "-b", "main")
        run(self.repo, "git", "config", "user.name", "demo")
        run(self.repo, "git", "config", "user.email", "demo@example.com")
        run(self.repo, "git", "config", "gpg.format", "ssh")
        run(self.repo, "git", "config", "gpg.ssh.program", "ssh-keygen")
        signers = ""
        for who, key in self.keys.items():
            with open(key + ".pub") as f:
                kind, blob, _ = f.read().split(" ", 2)
            signers += f"{who}@demo {kind} {blob}\n"
        self.write("allowed_signers", signers)
        self.write("policy.toml", 'approver = "george"\nprotected = ["policy.toml", "allowed_signers", ".github/**", "migrations/**"]\n')
        self.write("src/app.txt", "v1\n")
        self.base = self.commit("george", "initial")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)

    def commit(self, who, msg):
        run(self.repo, "git", "add", "-A")
        args = ["git", "commit", "-q", "-m", msg]
        if who is not None:
            args[2:2] = ["-S"]
            args = args[:1] + ["-c", f"user.signingkey={self.keys[who]}"] + args[1:]
        run(self.repo, *args)
        return run(self.repo, "git", "rev-parse", "HEAD").strip()

    def decide(self, head, approved=()):
        return verify.decide(self.repo, self.base, head, lambda: set(approved))

    def test_routine_change_by_agent_ships(self):
        self.write("src/app.txt", "v2\n")
        ok, notes = self.decide(self.commit("agent", "routine"))
        self.assertTrue(ok, notes)

    def test_unsigned_commit_is_rejected(self):
        self.write("src/app.txt", "v2\n")
        ok, _ = self.decide(self.commit(None, "unsigned"))
        self.assertFalse(ok)

    def test_protected_change_waits_for_owner(self):
        self.write(".github/workflows/x.yml", "on: push\n")
        ok, notes = self.decide(self.commit("agent", "touch workflow"))
        self.assertFalse(ok)
        self.assertIn("waiting for george", notes[-1])

    def test_protected_change_passes_after_owner_approval(self):
        self.write(".github/workflows/x.yml", "on: push\n")
        ok, notes = self.decide(self.commit("agent", "touch workflow"), approved={"george"})
        self.assertTrue(ok, notes)

    def test_someone_elses_approval_does_not_count(self):
        self.write(".github/workflows/x.yml", "on: push\n")
        ok, _ = self.decide(self.commit("agent", "touch workflow"), approved={"agent-bot"})
        self.assertFalse(ok)

    def test_a_change_cannot_loosen_the_rule_that_judges_it(self):
        self.write("policy.toml", 'approver = "george"\nprotected = []\n')
        self.write(".github/workflows/x.yml", "on: push\n")
        ok, _ = self.decide(self.commit("agent", "loosen policy"))
        self.assertFalse(ok)

    def test_migration_waits_for_owner(self):
        self.write("migrations/0002_drop_users.sql", "DROP TABLE users;\n")
        ok, _ = self.decide(self.commit("agent", "migration"))
        self.assertFalse(ok)

    def test_agent_cannot_add_a_key_without_approval(self):
        self.write("allowed_signers", "george@demo ssh-ed25519 AAAA-agent-controlled\n")
        ok, _ = self.decide(self.commit("agent", "swap keys"))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
