# fish completion for kport
complete -c kport -f
complete -c kport -a "inspect explain kill kill-process list docker conflicts watch mcp completion"
complete -c kport -s y -l yes -d "Skip confirmation prompts"
complete -c kport -l json -d "Output machine-readable JSON"
complete -c kport -l dry-run -d "Show actions without executing"
complete -c kport -l debug -d "Verbose internal logs"
complete -c kport -l config -d "Path to JSON config file"
complete -c kport -l bypass-safety -d "Bypass safety shields on protected ports/processes"
complete -c kport -l wait-for-exit -d "Wait for port to be free after killing (seconds)"
complete -c kport -l proto -r -f -a "tcp udp both" -d "Protocol type tcp|udp|both"
complete -c kport -s v -l version -d "Show version"
