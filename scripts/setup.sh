#!/usr/bin/env bash
# First-time setup for Ka on a fresh machine (macOS or Linux).
# Safe to run again: every step checks first and only does what is missing.
#
#   ./scripts/setup.sh                 data repo at ~/ka-data
#   KA_DATA=/srv/ka-data ./scripts/setup.sh
#
# It never overwrites config.yaml, .env or an existing data repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${KA_DATA:-$HOME/ka-data}"
PORT="${KA_PORT:-8000}"
NODE_MAJOR=22

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  ok: %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
die() { printf '\nerror: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  *) die "unsupported system $(uname -s); use macOS or Linux" ;;
esac

linux_install() {
  if have apt-get; then sudo apt-get update -qq && sudo apt-get install -y -qq "$@"
  elif have dnf; then sudo dnf install -y -q "$@"
  else die "no apt-get or dnf; install $* yourself and run again"
  fi
}

say "1. Basic tools ($OS)"
for tool in git curl; do
  if have "$tool"; then ok "$tool"
  elif [ "$OS" = mac ]; then die "$tool missing; run 'xcode-select --install' and run again"
  else linux_install "$tool"; ok "$tool installed"
  fi
done

say "2. uv and Python 3.13"
if ! have uv; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv $(uv --version | cut -d' ' -f2)"
uv python install 3.13 >/dev/null
ok "Python 3.13"

say "3. Node $NODE_MAJOR or newer"
node_ok() { have node && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge "$NODE_MAJOR" ]; }
if ! node_ok; then
  if [ "$OS" = mac ]; then
    have brew || die "Node missing and no Homebrew; install Homebrew (https://brew.sh) and run again"
    brew install node
  elif have apt-get; then
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | sudo -E bash -
    sudo apt-get install -y -qq nodejs
  else
    linux_install nodejs npm
  fi
  node_ok || die "Node $(node -v 2>/dev/null || echo missing) is older than $NODE_MAJOR"
fi
ok "node $(node -v)"

say "4. Python packages and the web UI"
cd "$ROOT"
uv sync --quiet
ok "uv sync"
(cd ui && npm ci --silent --no-audit --no-fund && npm run build --silent >/dev/null)
ok "ui built into ui/dist"

say "5. Data repo at $DATA"
if [ -d "$DATA" ]; then
  ok "exists, left as it is"
else
  mkdir -p "$DATA/rules" "$DATA/local"
  cd "$DATA"
  printf 'name: ""\n' > profile.yaml
  printf 'entries: []\n' > education.yaml
  printf 'domains: []\njobs: []\n' > jobs.yaml
  printf 'rules: []\n' > guardrails.yaml
  printf 'entries: []\n' > memory.yaml
  printf 'accounts: []\n' > accounts.yaml
  printf 'categories: [groceries, dining, transport, fuel, shopping, subscriptions, phone, travel, entertainment, health, fees, e_transfer, other]\n' > categories.yaml
  printf 'rules: []\n' > rules/merchants.yaml
  printf 'types: []\n' > rules/transaction_types.yaml
  printf 'types: [project]\nrecords: []\n' > other.yaml
  printf 'next: {E: 1, D: 1, H: 1, G: 1, M: 1, A: 1, R: 1, O: 1}\n' > ids.yaml
  printf 'local/\n.DS_Store\n.ka.lock\n' > .gitignore
  touch local/denylist.txt
  git init -q
  git add -A
  git -c user.name=Ka -c user.email=ka@localhost commit -q -m "data: empty Ka data repo"
  cd "$ROOT"
  ok "created and committed"
fi
# Ka commits every approved change here; a fresh machine often has no git identity.
if ! git -C "$DATA" config user.email >/dev/null; then
  git -C "$DATA" config user.name Ka
  git -C "$DATA" config user.email ka@localhost
  ok "git identity for the data repo set to Ka"
fi

say "6. config.yaml"
if [ -f config.yaml ]; then
  ok "exists, left as it is"
else
  cat > config.yaml <<EOF
data_repo: $DATA
flags:
  web_ui: true
  intake: true
  private_routing: true
  nightly_extraction: false
  category_suggestions: false
  google: false
ui_hosts: []  # filled in by this script when Tailscale is running
models:
  default: {provider: openai, model: "gpt-5.4-mini"}  # key: OPENAI_API_KEY in .env
private_models:  # money conversations; key: OPENROUTER_API_KEY in .env
  - {provider: openrouter, model: "anthropic/claude-haiku-5.5", zdr: true, only: [amazon-bedrock]}
EOF
  ok "created"
fi

say "7. .env"
if [ -f .env ]; then
  ok "exists, left as it is"
else
  printf 'OPENAI_API_KEY=\nOPENROUTER_API_KEY=\n' > .env
  chmod 600 .env
  ok "created with empty keys"
fi

say "8. Tailscale (optional)"
if [ -n "${KA_SKIP_TAILSCALE:-}" ]; then
  printf '  skipped: KA_SKIP_TAILSCALE is set\n'
elif have tailscale && tailscale status >/dev/null 2>&1; then
  TS="$(tailscale status --json)"
  HOST="$(printf '%s' "$TS" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  HTTPS="$(printf '%s' "$TS" | uv run python -c 'import json,sys; print("yes" if json.load(sys.stdin).get("CertDomains") else "")')"
  uv run python - "$HOST" <<'EOF'
import sys
from pathlib import Path
from ruamel.yaml import YAML

yaml = YAML()
path = Path("config.yaml")
cfg = yaml.load(path.read_text())
hosts = cfg.setdefault("ui_hosts", [])
if sys.argv[1] not in hosts:
    hosts.append(sys.argv[1])
    yaml.dump(cfg, path)
EOF
  ok "ui_hosts has $HOST"
  # Without HTTPS on the tailnet, `tailscale serve` stops and waits for a browser prompt.
  if [ -z "$HTTPS" ]; then
    printf '  skipped serve: turn on HTTPS in the Tailscale admin page (DNS tab), then run again\n'
  elif tailscale serve --bg "$PORT" </dev/null >/dev/null 2>&1; then
    ok "phone URL: https://$HOST"
  else
    printf '  skipped: tailscale serve failed; run "tailscale serve --bg %s" to see why\n' "$PORT"
  fi
else
  printf '  skipped: Tailscale not installed or not logged in; the phone step can wait\n'
fi

say "9. Check"
uv run ka check
missing=$(grep -E '^[A-Z_]+=$' .env | cut -d= -f1 | tr '\n' ' ' || true)
if [ -n "$missing" ]; then
  printf '\nNext: paste your keys into %s/.env (%s), then start Ka:\n' "$ROOT" "$missing"
else
  printf '\nReady. Start Ka:\n'
fi
printf '  cd %s && uv run ka serve --port %s\n' "$ROOT" "$PORT"
