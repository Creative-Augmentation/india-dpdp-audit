# Install in Claude Code

Source checked: <https://code.claude.com/docs/en/skills> (the older docs.claude.com address redirects here). Date checked: 2026-10-27.

Claude Code loads a skill from a folder that contains `SKILL.md`:

| Scope | Path |
|---|---|
| Personal (all your projects) | `~/.claude/skills/<skill-name>/SKILL.md` |
| Project (commit to share with a team) | `.claude/skills/<skill-name>/SKILL.md` |

## Steps (personal install)

From the root of this repository:

```
mkdir -p ~/.claude/skills
cp -r skills/india-dpdp-audit ~/.claude/skills/
```

The result is `~/.claude/skills/india-dpdp-audit/SKILL.md` and `~/.claude/skills/india-dpdp-audit/references/legal-baseline.md`. The skill's `name` is `india-dpdp-audit`, which matches the folder name.

## Steps (single project)

```
mkdir -p .claude/skills
cp -r /path/to/this/repo/skills/india-dpdp-audit .claude/skills/
```

## Use

Start Claude Code and either ask for a DPDP audit (Claude loads the skill when the description matches) or type `/india-dpdp-audit`. See the example prompt in the [README](../README.md).

Per the docs, changes under `~/.claude/skills/` or `.claude/skills/` are picked up without a restart; a skills folder created after Claude Code started may need a restart.

## UNVERIFIED

- The restart note above: the docs say live edits are picked up; I did not verify the case of a brand-new top-level `skills` folder. If the skill does not appear, restart Claude Code.
- I read the first 100,000 of about 118,000 characters of the docs page; check the page if you rely on anything not listed here (for example enterprise paths).
