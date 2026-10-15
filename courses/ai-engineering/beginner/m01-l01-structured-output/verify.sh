#!/usr/bin/env bash
# Verifier for AI Engineering beginner lesson 1. Runs the learner's code against fake models.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
timeout 120 python3 -I "$here/checks.py"
