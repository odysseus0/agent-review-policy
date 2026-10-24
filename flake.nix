{
  description = "One person, many agents: routine changes ship, protected paths wait for the owner";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      workspace = {
        services.agentWorkspace = {
          enable = true;
          gitName = "demo-agent[bot]";
          gitEmail = "demo-agent[bot]@users.noreply.github.com";
          githubTokenFile = "/run/agent-credentials/github-token";
        };
      };
    in
    {
      nixosModules.agent-workspace = ./modules/agent-workspace.nix;

      # `nix run .#nixosConfigurations.agent-vm.config.system.build.vm`
      nixosConfigurations.agent-vm = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          self.nixosModules.agent-workspace
          workspace
          {
            system.stateVersion = "25.05";
            virtualisation.vmVariant.virtualisation.forwardPorts = [
              { from = "host"; host.port = 2222; guest.port = 22; }
            ];
          }
        ];
      };

      checks.${system} = {
        verifier = pkgs.runCommand "verifier-tests"
          { nativeBuildInputs = [ pkgs.python3 pkgs.git pkgs.openssh ]; } ''
          cp ${./verify}/*.py .
          python3 -W error::ResourceWarning -m unittest -v test_verify
          touch $out
        '';

        # Needs KVM. Boots the workspace and checks the two facts the policy
        # rests on: the agent has its own key, and nothing of the owner's.
        workspace = pkgs.testers.runNixOSTest {
          name = "agent-workspace";
          nodes.machine = { imports = [ self.nixosModules.agent-workspace workspace ]; };
          testScript = ''
            machine.wait_for_unit("agent-signing-key.service")
            machine.succeed("test -s /var/lib/agent-workspace/signing-key")
            machine.succeed("su agent -c 'git config user.signingkey' | grep agent-workspace")
            machine.fail("test -e /home/agent/.config/gh/hosts.yml")
            machine.fail("test -e /home/agent/.ssh/id_ed25519")
          '';
        };
      };
    };
}
