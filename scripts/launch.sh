#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
mode=${SSH_IT_LAUNCH_MODE:-auto}

case "$mode" in
    auto|bundle|source) ;;
    *)
        printf '%s\n' "SSH_IT_LAUNCH_MODE must be auto, bundle, or source" >&2
        exit 64
        ;;
esac

bundle_path=""
case "$(uname -s)" in
    Darwin) bundle_path="$repo_root/dist/SSH It.app/Contents/MacOS/SSH It" ;;
    Linux) bundle_path="$repo_root/dist/SSH It/SSH It" ;;
esac

if [ "$mode" != source ] && [ -n "$bundle_path" ] && [ -x "$bundle_path" ]; then
    exec "$bundle_path" "$@"
fi

if [ "$mode" = bundle ]; then
    printf '%s\n' "SSH It native bundle not found for this operating system: $bundle_path" >&2
    exit 69
fi

venv_python="$repo_root/.venv/bin/python"
if [ -x "$venv_python" ]; then
    cd -- "$repo_root"
    exec "$venv_python" -m ssh_it "$@"
fi

if command -v uv >/dev/null 2>&1; then
    cd -- "$repo_root"
    exec uv run --frozen --no-sync ssh-it "$@"
fi

printf '%s\n' "SSH It is not built and no prepared source environment was found." >&2
printf '%s\n' "Run: uv sync --locked" >&2
exit 69
