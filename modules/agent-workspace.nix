# A machine for one agent: its own signing key, its own GitHub token, none of
# the owner's credentials. Standalone, so other configurations can import it.
{ config, lib, pkgs, ... }:

let
  cfg = config.services.agentWorkspace;
  home = "/home/${cfg.user}";
  stateDir = "/var/lib/agent-workspace";
in
{
  options.services.agentWorkspace = {
    enable = lib.mkEnableOption "an agent workspace";

    user = lib.mkOption {
      type = lib.types.str;
      default = "agent";
      description = "The OS user the agent runs as.";
    };

    gitName = lib.mkOption {
      type = lib.types.str;
      default = "agent";
      description = "Author name on the agent's commits.";
    };

    gitEmail = lib.mkOption {
      type = lib.types.str;
      example = "123456+my-agent[bot]@users.noreply.github.com";
      description = "Author email on the agent's commits (the App's bot noreply address).";
    };

    attachKeys = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "SSH public keys allowed to attach to the agent's session (the owner's).";
    };

    githubTokenFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      example = "/run/agent-credentials/github-token";
      description = ''
        File holding a short-lived GitHub App installation token, written by
        the host. The App's private key never enters the workspace.
      '';
    };

    packages = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = [ ];
      description = "The agent itself and its tools.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = {
      isNormalUser = true;
      openssh.authorizedKeys.keys = cfg.attachKeys;
    };

    services.openssh = {
      enable = true;
      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "no";
      };
    };

    environment.systemPackages = [ pkgs.git pkgs.openssh pkgs.tmux ] ++ cfg.packages;

    # The agent's signing key is born here and never leaves. Its public half is
    # printed so the owner can add it to the repository's allowed_signers.
    systemd.services.agent-signing-key = {
      description = "Generate the agent's commit signing key on first boot";
      wantedBy = [ "multi-user.target" ];
      unitConfig.ConditionPathExists = "!${stateDir}/signing-key";
      serviceConfig.Type = "oneshot";
      path = [ pkgs.openssh pkgs.coreutils ];
      script = ''
        install -d -m 0700 -o ${cfg.user} ${stateDir}
        ssh-keygen -q -t ed25519 -N "" -C "${cfg.gitEmail}" -f ${stateDir}/signing-key
        chown ${cfg.user} ${stateDir}/signing-key ${stateDir}/signing-key.pub
        echo "agent signing key: $(cat ${stateDir}/signing-key.pub)"
      '';
    };

    environment.etc."gitconfig".text = ''
      [user]
        name = ${cfg.gitName}
        email = ${cfg.gitEmail}
        signingkey = ${stateDir}/signing-key
      [gpg]
        format = ssh
      [commit]
        gpgsign = true
      [tag]
        gpgsign = true
    '' + lib.optionalString (cfg.githubTokenFile != null) ''
      [credential "https://github.com"]
        helper = "!f() { echo username=x-access-token; echo password=$(cat ${cfg.githubTokenFile}); }; f"
    '';

    systemd.tmpfiles.rules = [ "d ${home}/work 0755 ${cfg.user} users -" ];
  };
}
