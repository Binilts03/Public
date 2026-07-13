#!/usr/bin/env bash
set -euo pipefail

test -f codex-rs/Cargo.toml || {
  echo "run this script from an openai/codex checkout" >&2
  exit 2
}

cd codex-rs
cargo fmt --all -- --check
cargo test -p codex-core-skills
cargo test -p codex-skills-extension
cargo check -p codex-core -p codex-app-server
cd ..
git diff --check

