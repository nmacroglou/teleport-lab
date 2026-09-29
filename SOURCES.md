# Sources

Official documentation this project was checked against (2026-09-28):

- Teleport, Docker installation: https://goteleport.com/docs/installation/docker/
- Machine & Workload Identity: https://goteleport.com/docs/reference/machine-workload-identity/
- Deploy tbot: https://goteleport.com/docs/machine-workload-identity/deployment/
- Infrastructure access using tbot: https://goteleport.com/docs/machine-workload-identity/access-guides/
- MCP access with Machine & Workload Identity: https://goteleport.com/docs/machine-workload-identity/access-guides/mcp/
- tbot configuration: https://goteleport.com/docs/reference/machine-workload-identity/machine-id/configuration/
- Claude Code and CLAUDE.md: https://support.claude.com/en/articles/14553240-give-claude-context-claude-md-and-better-prompts

Notes:

- Teleport Community `18.11.2` is pinned because it is what runs in this lab.
- Teleport's MCP plus tbot guide expects a hostname with a valid TLS certificate for a non-local cluster.
- The "before and after" customer story on the scorecard summarises a public Teleport customer story (PPI Financial Services); check the source before quoting it.
