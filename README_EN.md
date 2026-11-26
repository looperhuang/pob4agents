# pob4agents (`pob`)

[简体中文](README.md) | **English**

[![YouTube](https://img.shields.io/badge/YouTube-Walkthrough-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=3HX5Uvi7-XM)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/tejgNrhjn)

> [!TIP]
> **Questions or feedback?** Drop by our [Discord server](https://discord.gg/tejgNrhjn) anytime!

`pob4agents` is a [**PathOfBuilding**](https://github.com/PathOfBuildingCommunity/PathOfBuilding) toolkit built specifically for AI agents.

Just import your build through a normal chat and let your agent actually run it through PoB.

When it runs into a mechanic it isn't sure about, it checks [PoEDB](https://poedb.tw) and [PoE Wiki](https://www.poewiki.net) instead of making things up.

It gives real upgrade suggestions, automatically builds trade queries around your build's gaps (with instant Gold buyout `--securable` filtering, seller deduplication, and lossless `+20%` quality normalization in PoB) with direct trade links, hunts Timeless Jewel seeds (including Abyss jewels) in seconds, and generates build-aware 0-false-positive T16/T17 map regexes (`pob map-regex`)!

It can also plan free and paid upgrades, each verified in PoB: passive respec swaps (`pob respec`), stat weights for your gear (`pob weights`), the best support-gem set (`pob rank-gems --optimize`), and the best gear combo within a chaos budget (`pob trade upgrade` / `pob trade plan`).

---

## How do I install it?

Just tell your agent:

> I want to install exilemoulei/pob4agents, please install it along with all required dependencies.

When new versions come out, there's no need to reinstall — just tell your agent to update `pob4agents` and its Skill.

## What is an agent?

Popular clients include Claude Code, Codex (ChatGPT), and DeepSeek Harness (DSH).

If you've never used one before, search YouTube for a quick setup tutorial.

## How do I use it?

> **Watch the walkthrough**: [YouTube — pob4agents Best-Practice Demo](https://www.youtube.com/watch?v=3HX5Uvi7-XM)

Once installed, open a fresh chat and drop in your `poe.ninja` link, official PoE profile link, or PoB export link/code — it recognizes all of them.

(Note that the official profile API doesn't include Bandits or Pantheon, so double-check those with your agent after importing.)

English, Traditional Chinese, and Simplified Chinese are all supported — if you ever see Chinese output, just tell your agent to switch `pob` to English.

Pick a smarter model if you can (e.g. Claude Opus / Gemini Neon / GPT Sol), though lighter models like DeepSeek work fine too.

**Best practices that work well** (walked through in the video):

- **Give it reference anchors instead of starting cold**: drop in a working PoB, a mechanics thread (e.g. Reddit), or a showcase video alongside your build — the richer the context, the better its decisions.
- **Call out tricky mechanics and ask it to ask you questions**: tell it what build you're playing and what's easy to get wrong; having it ask follow-up questions makes its answers dramatically more accurate!
- **Offload the tedious PoB work while you stay in the loop**: let it handle bulk tattooing, scanning niche ascendancies/notables, and gear swaps, then open the updated PoB, flag anything off, and iterate.
- **Pick `poe.ninja` characters yourself and paste their links**: to respect platform limits, the agent won't scrape leaderboards on its own — browse `poe.ninja`, copy a few strong character links, and drop them in for side-by-side comparison.

It automatically strips out inflated PoB settings to show realistic numbers.

Sometimes it strips a bit too aggressively, so always double-check what it turned off.

Don't let a single chat drag on too long — start a fresh chat window every 4–5 turns.

If it struggles on a weird build, don't stress — PoE is a wildly complex game. Send us feedback and we'll keep expanding support so agents can handle more builds.

## Want it to search trade gear and Timeless Jewels?

You'll need to provide your `POESESSID` to unlock full functionality (also needed for importing a private profile).

### How to grab it:

Open DevTools (`F12`) on the official PoE site or trade page, go to the **Application** tab → **Storage** → **Cookies**, find `POESESSID`, and copy its value.

Paste it directly to your agent and ask it to save it to your local `POESESSID` environment variable.

> [!CAUTION]
> Never share your `POESESSID` with anyone or show it on stream or in screenshots! It works like your account login credential — keep it private.

---

## Credits and License

- **Upstream & Inspiration**: [**ianderse/pob-mcp**](https://github.com/ianderse/pob-mcp) (GPL-3.0), [**shalayiding/POEMCP**](https://github.com/shalayiding/POEMCP), [**Hsiung-Shao/PobTools-zh**](https://github.com/Hsiung-Shao/PobTools-zh) (Chinese translation data & early headless bridge), and [**PathOfBuildingCommunity/PathOfBuilding**](https://github.com/PathOfBuildingCommunity/PathOfBuilding).
- **Community Contributors**:
  - [**@ChangMenQAQ**](https://github.com/ChangMenQAQ) ([PR #1](https://github.com/exilemoulei/pob4agents/pull/1)): official trade search, Harvest resistance swap, and crafting bench evaluation.
  - [**@restartgr**](https://github.com/restartgr) ([PR #2](https://github.com/exilemoulei/pob4agents/pull/2), [PR #4](https://github.com/exilemoulei/pob4agents/pull/4), [PR #6](https://github.com/exilemoulei/pob4agents/pull/6)): PoB inflation audit, `--keep` condition retention, restore verification, exit codes, and bilingual doc polish.
  - [**@Capoouo**](https://github.com/Capoouo) ([PR #3](https://github.com/exilemoulei/pob4agents/pull/3), [PR #30](https://github.com/exilemoulei/pob4agents/pull/30)): Timeless Jewel seed search, candidate prefiltering, and audit / Traditional Chinese input fixes.
  - [**@luyahan**](https://github.com/luyahan) ([PR #31](https://github.com/exilemoulei/pob4agents/pull/31)): shared helper module deduplication and refactoring.
- **Contributing**: please read [CONTRIBUTING.md](CONTRIBUTING.md) first.
- **License**: **GNU General Public License v3.0 (GPL-3.0)** — see [LICENSE](LICENSE).

---

## Setup Guide for AI Agents (Required — Human Users Can Skip)

When a user asks you to install `exilemoulei/pob4agents`, **complete all 4 steps below**. Do not stop after installing the CLI alone:

### 1. Install `pob4agents` (command: `pob`, no Python required)

- **Windows x64**:
  ```powershell
  irm https://raw.githubusercontent.com/exilemoulei/pob4agents/main/install.ps1 | iex
  ```
- **macOS / Linux**:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/exilemoulei/pob4agents/main/install.sh | bash
  ```

Both installers verify the release's Ed25519 signature and SHA-256 checksums automatically. If direct GitHub access fails, ask the user for their proxy URL and set `POB_PROXY` (e.g. `http://127.0.0.1:<port>`) or `POB_GITHUB_MIRROR` before retrying. For future updates, run `pob self-update` (and refresh `skills/pob` from this repo on minor/major upgrades).

### 2. Bootstrap the Local PoB Engine & Language

```powershell
pob bootstrap
pob lang en
pob status
```

- Pass `--proxy http://127.0.0.1:<port>` if a proxy is needed, `--no-zh` for an English-only engine without Chinese dictionaries, or `--from-dir "<local-path>"` to seed from an existing `PobTools` folder.
- Windows uses a slim native LuaJIT engine host (zero `pob-zh.exe`, zero bulky Timeless `.zip*` LUT downloads); macOS and Linux standalone builds automatically use the bundled or Ed25519-verified prebuilt LuaJIT runtime — no manual compilation needed.
- `pob` defaults to Simplified Chinese (`zh-CN`), so **run `pob lang en` for English users** (or `pob lang zh-TW` for Traditional Chinese; `POB_LANG` overrides with instant hot-reload).
- Verify that `pob status` reports the version and a ready engine before continuing.

### 3. Install the Skill (Mandatory — Do Not Skip)

`install.ps1` and `install.sh` only install the `pob` binary; they do **not** install the Skill. Fetch this repository (e.g. `git clone --depth 1 https://github.com/exilemoulei/pob4agents.git` into a temp directory) and copy the entire [`skills/pob`](skills/pob) directory (including `SKILL.md` and `references/`) into your client's skills folder:

| Client | Target Path |
| :--- | :--- |
| Claude Code | `~/.claude/skills/pob` |
| Codex / Antigravity / OpenCode / Generic | `~/.agents/skills/pob` |
| DeepSeek Harness (DSH) | Your client's `skills/pob` directory |

For every subsequent Path of Exile 1 build conversation, you must load and follow [`skills/pob/SKILL.md`](skills/pob/SKILL.md).

### 4. Final Verification & Cookie Security Rules

- **Verify & finish**: once `pob status` is healthy and `skills/pob` is in place, **remind the user to open a new chat window** so the new Skill takes effect.
- **When the user sends a `POESESSID`**:
  - Save it to the local user-level environment variable **`POESESSID`** (Windows PowerShell: `[Environment]::SetEnvironmentVariable("POESESSID", "<value>", "User")`; macOS/Linux: write to shell profile).
  - **NEVER** pass cookies in CLI arguments, commit them to files/repos, or write them to logs. **NEVER** run `Get-ChildItem Env:` / `printenv` to inspect or print environment variables, and never echo the raw value back in your reply. To check whether credentials are configured, run `pob status` only.

<details>
<summary>Fallback Install Methods (Scoop / PyPI / Release Archives) & Docs Index (Expand if Default Setup Fails)</summary>

### Fallback Install Methods

- **Windows Scoop**:
  ```powershell
  scoop bucket add pob https://github.com/exilemoulei/pob4agents
  scoop install pob
  ```
- **PyPI (Python 3.11+)**:
  ```powershell
  uv tool install pob4agents
  # or: pip install pob4agents
  ```
- **GitHub Releases portable archives**: download the archive for your OS from the [latest Release](https://github.com/exilemoulei/pob4agents/releases/latest) (ships with `SHA256SUMS.txt` and Ed25519 signature `SHA256SUMS.txt.sig`), extract it, and add the directory containing `pob` to `PATH`.
- **macOS / Linux source-build fallback**: if the prebuilt runtime does not fit the host, compile with [`pob_cli/packaging/build_posix_runtime.sh`](pob_cli/packaging/build_posix_runtime.sh).

### Troubleshooting Env Vars & Repository Docs

- Common env vars: `POB_LANG` (display language: `en` / `zh-CN` / `zh-TW`), `POB_PROXY` (network proxy), `POB_GITHUB_MIRROR` (GitHub mirror prefix; file replacements still verify hashes/signatures), `POB_OFFLINE=1` (skip update checks), `POESESSID` (trade / private profile).
- Documentation index: [`docs/README.md`](docs/README.md)
- Full CLI command reference: [`docs/guides/commands.md`](docs/guides/commands.md)
- Trade search & crafting bench guide: [`docs/guides/trade.md`](docs/guides/trade.md)
- Architecture & contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md), [`AGENTS.md`](AGENTS.md)

</details>
