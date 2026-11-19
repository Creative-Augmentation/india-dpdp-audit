# Install in Cursor

Sources checked, date checked 2026-10-27:

- Agent skills: <https://cursor.com/docs/context/skills>
- Rules and AGENTS.md: <https://cursor.com/docs/context/rules>

Cursor supports Agent Skills (a folder with `SKILL.md`; `name` must match the folder name):

| Scope | Path |
|---|---|
| Project | `.agents/skills/` or `.cursor/skills/` in the repository |
| User (global) | `~/.agents/skills/` or `~/.cursor/skills/` |

For compatibility Cursor also loads `.claude/skills/`, `.codex/skills/`, `~/.claude/skills/` and `~/.codex/skills/`, so a copy installed for Claude Code or Codex may already be visible.

## Steps (user install)

From the root of this repository:

```
mkdir -p ~/.cursor/skills
cp -r skills/india-dpdp-audit ~/.cursor/skills/
```

## Steps (single project)

```
mkdir -p .cursor/skills
cp -r /path/to/this/repo/skills/india-dpdp-audit .cursor/skills/
```

## Use

In Agent chat, type `/` and search for `india-dpdp-audit` to attach it to a message, or ask for a DPDP audit and let the agent apply the skill when it judges it relevant.

## Workaround if your Cursor version has no skills feature

Not needed if the steps above work. **Untested workaround:** keep the entire skill folder at `skills/india-dpdp-audit/` in your project, including its references, assets, scripts and licence. Create `.cursor/rules/india-dpdp-audit.mdc` with a `description` line and `alwaysApply: false`. Its body should instruct the agent to read `skills/india-dpdp-audit/SKILL.md` when the user requests a DPDP audit, and resolve that skill's relative links from its folder. Do not flatten the skill into the rule or retain only the legal reference; the platform and output-contract links need the complete package. Attach this rule explicitly if automatic selection is unavailable. This fallback has not been runtime-tested in Cursor.

## Verification limits

Runtime discovery and relative-reference loading in Cursor have not been tested for this release. After copying, check that the skill appears in Agent chat and its references can be read. A restart, window reload or version-specific setting may be needed; consult the current Cursor documentation if discovery fails. The rules workaround above remains untested.

## Auditing a repository safely

Launch the agent from a separate trusted workspace. Inspect a read-only copy of the target outside the agent's project root; decline folder trust and do not enable the target's hooks, project settings or MCP servers. Do not start the agent inside the repository being audited. The skill cannot prevent host configuration that executes before it is loaded.
