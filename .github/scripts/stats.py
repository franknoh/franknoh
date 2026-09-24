"""Render GitHub stats and top-language cards as SVGs into profile/.

Reads GITHUB_TOKEN (a PAT with repo scope counts private repos too; the
default Actions token only sees public data) and GITHUB_USER.
"""
import json
import math
import os
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("GITHUB_USER", "franknoh")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(__file__).resolve().parents[2] / "profile"
EXCLUDE_LANGS = {"HTML", "CSS", "Jupyter Notebook", "Makefile", "Dockerfile", "Shell", "Batchfile", "SCSS", "CMake", "PowerShell"}
TOP_N = 6

BG, BORDER, FG, MUTED, ACCENT = "#0d1117", "#30363d", "#e6edf3", "#8b949e", "#16a34a"
FONT = "font-family='Segoe UI, Ubuntu, Helvetica, Arial, sans-serif'"
MONO = "font-family='SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace'"


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch():
    user = gql(
        """query($login: String!) { user(login: $login) {
             followers { totalCount }
             contributionsCollection {
               totalCommitContributions restrictedContributionsCount
               totalPullRequestContributions totalIssueContributions
               contributionCalendar { totalContributions } }
             repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
           } }""",
        login=USER,
    )["user"]

    repos, cursor = [], None
    while True:
        page = gql(
            """query($login: String!, $after: String) { user(login: $login) {
                 repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false) {
                   pageInfo { hasNextPage endCursor }
                   nodes { stargazerCount
                     languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
                       edges { size node { name color } } } } } } }""",
            login=USER,
            after=cursor,
        )["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return user, repos


def card(width, height, title, body):
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<rect x='0.5' y='0.5' width='{width - 1}' height='{height - 1}' rx='8' fill='{BG}' stroke='{BORDER}'/>"
        f"<text x='24' y='36' {MONO} font-size='13' fill='{ACCENT}'>{escape(title)}</text>"
        f"{body}</svg>\n"
    )


def stats_svg(user, repos):
    c = user["contributionsCollection"]
    rows = [
        ("Stars earned", sum(r["stargazerCount"] for r in repos)),
        ("Commits (last year)", c["totalCommitContributions"] + c["restrictedContributionsCount"]),
        ("Contributions (last year)", c["contributionCalendar"]["totalContributions"]),
        ("Pull requests", c["totalPullRequestContributions"]),
        ("Repos contributed to", user["repositoriesContributedTo"]["totalCount"]),
        ("Repositories", len(repos)),
    ]
    body = ""
    for i, (label, value) in enumerate(rows):
        y = 70 + i * 25
        body += (
            f"<text x='24' y='{y}' {FONT} font-size='14' fill='{MUTED}'>{escape(label)}</text>"
            f"<text x='326' y='{y}' {MONO} font-size='14' font-weight='600' fill='{FG}' text-anchor='end'>{value:,}</text>"
        )
    return card(350, 70 + len(rows) * 25, "$ gh stats", body)


def langs_svg(repos):
    totals, colors = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            if name in EXCLUDE_LANGS:
                continue
            # sqrt keeps one huge vendored repo from drowning out the rest
            totals[name] = totals.get(name, 0) + math.sqrt(e["size"])
            colors[name] = e["node"]["color"] or MUTED
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
    total = sum(v for _, v in top) or 1

    bar, x = "", 24.0
    bar += "<clipPath id='bar'><rect x='24' y='54' width='302' height='8' rx='4'/></clipPath><g clip-path='url(#bar)'>"
    for name, size in top:
        w = 302 * size / total
        bar += f"<rect x='{x:.2f}' y='54' width='{w + 0.5:.2f}' height='8' fill='{colors[name]}'/>"
        x += w
    bar += "</g>"

    legend = ""
    for i, (name, size) in enumerate(top):
        cx, cy = 24, 92 + i * 23
        legend += (
            f"<circle cx='{cx + 5}' cy='{cy - 4}' r='5' fill='{colors[name]}'/>"
            f"<text x='{cx + 16}' y='{cy}' {FONT} font-size='14' fill='{FG}'>{escape(name)}</text>"
            f"<text x='326' y='{cy}' {MONO} font-size='13' fill='{MUTED}' text-anchor='end'>{100 * size / total:.1f}%</text>"
        )
    return card(350, 220, "$ gh langs --top", bar + legend)


def main():
    user, repos = fetch()
    OUT.mkdir(exist_ok=True)
    (OUT / "stats.svg").write_text(stats_svg(user, repos), encoding="utf-8")
    (OUT / "langs.svg").write_text(langs_svg(repos), encoding="utf-8")


if __name__ == "__main__":
    main()
