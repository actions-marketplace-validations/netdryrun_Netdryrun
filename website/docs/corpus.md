---
title: Network Change Verdict Corpus
description: 30 realistic BGP changes with expected verdicts committed before any run, tested with ping-only checks, session-only checks and Netdryrun intent checks in a real containerlab lab. Losses published.
---

# Network Change Verdict Corpus

How much does a typical "ping after the change" test miss? This corpus answers that with data anyone can rerun.

## Method

- **The network:** a small provider (AS65000, two routers) with a customer, an upstream transit and a settlement-free peer, running FRR in containerlab. Its written intent is in [INTENT.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/INTENT.md).
- **The changes:** 30 realistic edits ([cases](https://github.com/netdryrun/netdryrun/tree/main/corpus/cases)): route leaks, filter typos, mass withdrawals, fat-fingered ASNs, latent risks, and safe changes that must not be blocked.
- **Pre-registered verdicts:** each case's expected verdict (would an experienced operator reject it?) was **committed to git before any run**. Verdicts are never edited afterwards; findings after the run are listed separately below.
- **Three strategies, same running lab per case:**
    1. **Ping only:** the customer pings the upstream and the peer.
    2. **All BGP sessions up:** every session established.
    3. **Netdryrun intent checks:** one [intent spec](https://github.com/netdryrun/netdryrun/blob/main/corpus/specs/intent.yml), written once and used unchanged for every case, so it can't be tuned to win.
- **Rerun it:** `python corpus/run.py` on any Linux or WSL2 machine with Docker and containerlab.

## Results

<!-- RESULTS -->
