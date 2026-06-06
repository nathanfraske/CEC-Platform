# Routing-run notifications channel

This pull request is the **notification channel** for the self-hosted route workflow
(`.github/workflows/route.yml`). It is infrastructure — **keep it open; do not merge.**

## How it works

`route.yml`'s final `Notify` step (`if: always()`) reads the run's decision log and posts
the **verdict as a comment on this PR** when the route finishes — success or failure. A
Claude session subscribed to this PR is then woken by the comment webhook the moment a
route completes, with the result in hand — no polling, no timer estimates.

Each comment carries: board, the hard gates (`kelvin_ok` / `diffpair_ok`), structural DRC,
tracks / vias, and links to the run + the artifact.

## Notes — the token must be a SEPARATE account (proven)

The `Notify` step posts with `secrets.ROUTE_NOTIFY_TOKEN` if set, else `GITHUB_TOKEN`. A Claude
session is woken by a PR comment ONLY when the comment's author is a **third party** — neither the
built-in Actions bot nor the repo owner:

- `github-actions[bot]` (the built-in `GITHUB_TOKEN`) is suppressed by GitHub → no webhook.
- The **repo owner's own identity is filtered too**: the session's GitHub integration authenticates
  *as the owner*, and the session is not pinged for its own activity (verified — a comment posted as
  the owner produced no `<github-webhook-activity>` in 60 s).

So `ROUTE_NOTIFY_TOKEN` must be a token from a **separate GitHub account** (a throwaway "router bot").
Because this repo is **public**, that bot does **not** need to be a collaborator — a **classic PAT with
the `public_repo` scope** lets it comment. Set the bot's PAT as the repo Actions secret
`ROUTE_NOTIFY_TOKEN`. The target PR number is the repo Actions variable `ROUTE_NOTIFY_PR` (this PR,
default `11`).
