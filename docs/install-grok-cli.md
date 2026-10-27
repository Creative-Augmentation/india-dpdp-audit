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

## UNVERIFIED

- **Installing the CLI itself:** the announcement page gives `curl -fsSL https://x.ai/cli/install.sh | bash`. That pipes a script to your shell; read the script first, and confirm the command and current availability (early beta for paid subscribers at the time of checking) on xAI's site.
- **Manual skill placement:** the docs page does not explicitly say that copying a folder into a discovery path is the install method (it describes a marketplace for plugins). It lists the paths above as where skills are loaded, so copying should work; confirm by opening `/skills`.
- **`grok inspect`:** a third-party article says it lists discovered skills; the official page does not mention it. Not relied on here.
- Project-level `.agents/skills` is not listed in the official page, so this guide does not use it.
