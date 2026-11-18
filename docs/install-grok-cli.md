# Install in Grok Build CLI (xAI)

Sources checked, date checked 2026-10-27:

- Skills, plugins and marketplaces: <https://docs.x.ai/build/features/skills-plugins-marketplaces>
- Install and AGENTS.md/skills statement: <https://x.ai/news/grok-build-cli>

Grok Build discovers skills (a folder with `SKILL.md`) from:

| Scope | Path |
|---|---|
| Project | `./.grok/skills/`, walked up to the repo root |
| User | `~/.grok/skills/` (and `~/.agents/skills/`, per the docs' AGENTS.md compatibility section) |
| Extra | paths set under `[skills] paths` in `~/.grok/config.toml` |

`name` defaults to the folder name; extra frontmatter keys are ignored.

## Steps (user install)

From the root of this repository:

```
mkdir -p ~/.grok/skills
cp -r skills/india-dpdp-audit ~/.grok/skills/
```

## Steps (single project)

```
mkdir -p .grok/skills
cp -r /path/to/this/repo/skills/india-dpdp-audit .grok/skills/
```

## Use

Start `grok` and ask for a DPDP audit, or open `/skills` to see it and invoke `/india-dpdp-audit` as a slash command.

## Verification limits

CLI installation, runtime skill discovery and relative-reference loading have not been tested for this release. The copy procedure follows the documented discovery paths; confirm the result in `/skills`. Use xAI's current official installation guidance for CLI availability and setup. This guide does not rely on undocumented inspection commands or a project-level `.agents/skills` path.

## Auditing a repository safely

Launch the agent from a separate trusted workspace. Inspect a read-only copy of the target outside the agent's project root; decline folder trust and do not enable the target's hooks, project settings or MCP servers. Do not start the agent inside the repository being audited. The skill cannot prevent host configuration that executes before it is loaded.
