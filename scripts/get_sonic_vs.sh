#!/usr/bin/env bash
# Download the official SONiC virtual-switch container (docker-sonic-vs) from the SONiC project's CI
# and load it into Docker as docker-sonic-vs:latest.
set -euo pipefail
mkdir -p "$HOME/sonic-download" && cd "$HOME/sonic-download"
URL="https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=master&platform=vs&target=target/docker-sonic-vs.gz"
curl -fL --retry 3 -o docker-sonic-vs.gz "$URL"
ls -la docker-sonic-vs.gz
docker load < docker-sonic-vs.gz | tail -2
docker images | grep -i sonic
