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

The result is the complete `~/.claude/skills/india-dpdp-audit/` package: `SKILL.md`, references, assets, scripts and licence. Keep the folder intact. The skill's `name` is `india-dpdp-audit`, which matches the folder name.

## Steps (single project)

```
mkdir -p .claude/skills
cp -r /path/to/this/repo/skills/india-dpdp-audit .claude/skills/
```

## Use

Start Claude Code and either ask for a DPDP audit (Claude loads the skill when the description matches) or type `/india-dpdp-audit`. See the example prompt in the [README](../README.md).

Per the docs, changes under `~/.claude/skills/` or `.claude/skills/` are picked up without a restart; a skills folder created after Claude Code started may need a restart.

## Verification limits

These paths were checked against the documentation on the recorded date. Runtime discovery, including a newly created top-level skills folder, has not been tested for this release. Restart Claude Code if the skill does not appear. Enterprise paths and other installation modes are outside this guide's verified scope.

## Auditing a repository safely

Launch the agent from a separate trusted workspace. Inspect a read-only copy of the target outside the agent's project root; decline folder trust and do not enable the target's hooks, project settings or MCP servers. Do not start the agent inside the repository being audited. The skill cannot prevent host configuration that executes before it is loaded.
