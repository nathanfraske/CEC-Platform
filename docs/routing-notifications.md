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

## Notes

- The comment is posted by the workflow. If the built-in `GITHUB_TOKEN` comment does not
  trigger the session webhook (GitHub can suppress webhooks for `GITHUB_TOKEN` actions),
  the `Notify` step falls back to a `ROUTE_NOTIFY_TOKEN` PAT secret if one is set.
- The target PR number is the repo Actions variable `ROUTE_NOTIFY_PR` (this PR).
