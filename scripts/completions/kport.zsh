#compdef kport

_kport() {
    local line
    _arguments -C \
        '--json[Output machine-readable JSON]' \
        '--dry-run[Show actions without executing]' \
        '(-y --yes)'{-y,--yes}'[Skip confirmation prompts]' \
        '--debug[Verbose internal logs]' \
        '--config[Path to JSON config file]' \
        '--bypass-safety[Bypass safety shields on protected ports/processes]' \
        '--wait-for-exit[Wait for port to be free after killing (seconds)]' \
        '--proto[Protocol type tcp|udp|both]' \
        '(-v --version)'{-v,--version}'[Show version]' \
        '1: :->cmds' \
        '*:: :->args'

    case $state in
        cmds)
            _values "subcommand" \
                'inspect[Inspect a port (docker-aware)]' \
                'explain[Explain why a port is blocked]' \
                'kill[Safely free a port (docker-aware)]' \
                'kill-process[Kill processes by name]' \
                'list[List active ports (local + docker)]' \
                'docker[List Docker-published ports]' \
                'conflicts[Detect docker/local port conflicts]' \
                'watch[Live monitoring of port ownership]' \
                'mcp[Start the stdio Model Context Protocol (MCP) server]' \
                'completion[Generate shell autocompletion]'
            ;;
    esac
}
