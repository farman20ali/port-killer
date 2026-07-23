# bash completion for kport
_kport_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="inspect explain kill kill-process list docker conflicts watch mcp completion --json --dry-run --yes --debug --config --bypass-safety --version --wait-for-exit --proto"
    case "${prev}" in
        inspect|explain|watch|kill)
            return 0
            ;;
        kill-process|--inspect-process|-ip|-kp)
            return 0
            ;;
        *)
            ;;
    esac
    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    return 0
}
complete -F _kport_completion kport
