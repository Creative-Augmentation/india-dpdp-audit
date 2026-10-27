# Install in OpenAI Codex CLI

Source checked: <https://developers.openai.com/codex/skills>, which redirects (HTTP 308) to <https://learn.chatgpt.com/docs/build-skills> ("Build skills"). Date checked: 2026-10-27. The redirect target is server-supplied; the page links back to developers.openai.com, but confirm you are reading OpenAI's official documentation.

Codex reads skills (a folder with `SKILL.md`, optional `references/`, `scripts/`, `assets/`) from:

| Scope | Path |
|---|---|
| User | `$HOME/.agents/skills` |
| Repository | `$CWD/.agents/skills`, and each parent up to `$REPO_ROOT/.agents/skills` |
| Admin | `/etc/codex/skills` |

`SKILL.md` needs `name` and `description` in its frontmatter, which this skill has.

## Steps (user install)

From the root of this repository:

```
mkdir -p ~/.agents/skills
cp -r skills/india-dpdp-audit ~/.agents/skills/
```

## Steps (single repository)

```
mkdir -p .agents/skills
cp -r /path/to/this/repo/skills/india-dpdp-audit .agents/skills/
```

## Use

In Codex CLI run `/skills`, or type `$` and pick `india-dpdp-audit`. Codex may also select it from the description. Per the docs, Codex detects skill changes automatically; if the skill does not appear, restart Codex.

## UNVERIFIED

- Codex also has an `AGENTS.md` instruction mechanism (documented under "Agent configuration"). I did not read that page and this guide does not use it.
- The docs mention a `$skill-installer` for curated skills only; there is no documented command to install from this repository, so the copy steps above are the method.
- I did not run Codex to confirm the skill is listed. After copying, run `/skills` and check.
