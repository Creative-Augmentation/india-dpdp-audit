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

Not needed if the steps above work. Otherwise, Cursor rules are `.mdc` files in `.cursor/rules/` (a plain `.md` there is ignored) with `description`, `globs`, `alwaysApply` frontmatter, and Cursor also reads `AGENTS.md` in the project root. **Workaround:** create `.cursor/rules/india-dpdp-audit.mdc` with a `description` line and `alwaysApply: false`, and put the contents of `skills/india-dpdp-audit/SKILL.md` (without its own frontmatter) in the body; keep `legal-baseline.md` in the project and point to it by path. This is untested.

## UNVERIFIED

- I did not run Cursor; check that `/india-dpdp-audit` appears in Agent chat after copying (a restart or window reload may be needed).
- The skills page did not say whether Cursor needs a setting enabled for skills; check Cursor's settings if the skill does not appear.
- The relative link from `SKILL.md` to `references/legal-baseline.md` is expected to resolve inside the skill folder; not tested.
