#!/usr/bin/env bash
# Deploy the `remit` chaincode to a local Drunix test network.
# Assumes you cloned the vendor repo next to this project:  git clone https://github.com/npci/drunix.git drunix
# Command names below follow the Drunix sample network; run `./net.sh help` and adjust if they differ.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NET="$ROOT/drunix/drunix-network/test-network"
cd "$NET"
./net.sh up            # start orderer + peers + validation services (needs Docker)
./net.sh create-channel 2>/dev/null || true
# Chaincode language is Go; the ccenv image (npcioss/drunix-ccenv:1.0) is pulled by the network script.
./net.sh deploy-cc -ccn remit -ccp "$ROOT/chaincode/remit" -ccl go
echo "Now export per-org env files (see hub/env.example) and start the hub with LEDGER_MODE=drunix"
