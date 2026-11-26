# `pob` command reference

Every subcommand with its flags, in one place. For when to use which, start with the recipes in [skills/pob/SKILL.md](../../skills/pob/SKILL.md); `pob <command> --help` is authoritative when this list and the CLI disagree.

```powershell
# Optimization flow: pob audit (dewater & gaps) -> weights / rank-nodes / rank-gems / anoint / bench -> pob trade search (verified via PoB)
# Global output & slot targeting: --target <slug> (alias --slot where non-conflicting; default POB_SLOT or main); --compact (1-line JSON); --out <file> (UTF-8 no-BOM).
# Before the subcommand: pob --offline <command> (no engine update check, same as POB_OFFLINE=1); pob -V | --version.
# Exit codes: 0 ok; 1 bad request (bad arguments, PoE2 input, or a build code the engine rejects while it keeps running); 2 usage error from the option parser (unknown option, missing or out-of-range value); 5 daemon or engine fault (timeout, crash, any other engine error: `pob stop` and retry); `pob trade` uses 0..6 (docs/guides/trade.md).

# Lifecycle, Foreground Daemon, Engine Bootstrap/Update & Build I/O (127.0.0.1 + X-PoB-Token)
pob help [--brief|-b] [COMMAND]... [--json]                                            # Compact 1-screen CLI cheat-sheet (`--brief`, <20ms) or subcommand help
pob serve [--offline] [--proxy <url>] [--mirror <url>] [--port N] [--runtime-dir <dir>]               # Foreground persistent daemon (use IsDaemon:true in job-reaped shells)
pob bootstrap [--proxy <url>] [--mirror <url>] [--no-zh] [--from-dir <dir>] [--json]   # Install/seed slim managed engine (native LuaJIT _lua-host on Windows, zero pob-zh.exe; PobTools-zh bridge + zh-rCN/zh-rTW + PoB master)
pob update [--check] [--force] [--proxy <url>] [--mirror <url>] [--offline] [--json]   # Incremental SHA1 update (hot-reloads live daemon slots)
pob status [--json]                                                                    # Daemon PID, PoB/PobTools/Data versions, active lang, caps/winLuaHost, boolean Auth env status, updateStatus, all named slots (a slot whose saved build failed to restore at boot carries `restoreFailed`: error, codeFile, skipped)
pob lang [zh-CN|zh-TW|en] [--json]                                                     # Get or persist display language (default zh-CN Simplified, switchable to fixed zh-TW Traditional or en; POB_LANG env overrides). Exit 1 for a locale the engine lacks, 5 when a running daemon does not answer; --json has dictLoaded, daemonSynced, envIgnored
pob self-update [--check] [--version X.Y.Z] [--proxy <url>] [--mirror <url>] [--json]  # Update pob itself (standalone builds; signed release only); --check reports latest + the update command for this install; network/disk/swap failure exits 5
pob profile [ACCOUNT_OR_URL] [--realm pc|xbox|sony|cn] [--league L] [--proxy U] [--json] # 0-engine official profile character list (pathofexile.com public no-cookie, or poe.game.qq.com via env POE_CN_SESSID)
pob new [--class C] [--asc A] [--secondary-asc S] [--level N] [--target <slug>] [--json]
pob load [SOURCE] [--char "<name>"] [--league L] [--realm pc|xbox|sony|cn] [--target <slug>] [--json] # XML, Base64, 8 share sites, poe.ninja char URL, or official Intl/CN profile URL
pob save <out.xml> | pob export-code [--target <slug>] [--json]                        # Export XML (CLI disk write, R11) or Base64 code
pob switch-main [--spec S] [--skill-group G] [--skill N] [--part N] [--item-set I] [--skill-set S] [--config-set C] [--loadout L]
pob undo | pob redo | pob stop [--json]

# Read-Only Inspection, Grounding & One-Shot Diagnosis
pob ground "<prompt_text>" [--limit 8] [--json]                                        # <15ms daemon-free 3.30 entity cards + PoE2/patch trap alerts
pob diagnose [SOURCE] [-c|--compare REF] [-q|--ask "<text>"] [--char "<name>"] [--league L] [--realm pc|xbox|sony|cn] [--keep <spec>]... [--no-auto-keep] [--rank|--no-rank] [--section all|summary|gaps|items|skills|cards|upgrades] [--top 5] [--target <slug>] [--ref-target <slug>] [--json] # One-shot: [Env (NOT PoE2) | rev=N] + Pinnacle audit + gaps/bricks/dead-supports/triggers + 3.30 cards + optional --rank upgrades (or dual-build 3-baseline compare)
pob summary [--target <slug>] [--json]                                                 # [Env | rev=N] + Offence (Hit/DoT/FullDPS/Minion*), Defence (EHP/MaxHit/Res), Warnings
pob audit [--keep <spec>]... [--no-auto-keep] [--no-attribution] [--target <slug>] [--json] # [Env | rev=N] + Hard gaps + 4-dim water audit -> Pinnacle (per-item PoB attribution; --keep var|Flask N|flasks|gem|customMods|party)
pob map-regex [SOURCE] [--tier t16|t17|both] [--mode brick|safe] [--avoid TEXT] [--allow TEXT] [--preset-only] [--min-quant N] [--min-pack N] [--client-lang auto|en|zh-CN|zh-TW] [--max-len 250] [--target <slug>] [--json] # PoB-aware <=250-char 0-false-positive T16/T17 map filter regex (supports `--preset-only` daemon-free)
# Note: `pob map-regex` only outputs passive text for manual copy-paste into the stash search box and never interacts with the game client, game files, or overlays.
pob config list [--all] [--search "<sub >"] [--with-options] [--target <slug>] [--json] # Active/filtered ConfigTab vars + raw customMods
pob items [--slot "Weapon 1"|"#1"] [--all] [--raw] [--target <slug>] [--json]          # Equipped table, single slot, or all equipped + allocated jewels raw
pob item inspect (--slot S | --raw "<item text>" | --file f) [--want "Cold Resistance"]... [--limit 8] [--target <slug>] [--json] # Rare-item affix occupancy and bench candidates (unclamped --limit >= 1); uncertain matches never claim free slots
pob skills [--group main|1|"label"] [--target <slug>] [--json]                         # Skill groups or per-gem DPS tooltips
pob tree [--search "<kw>" ...] [--type Keystone|Notable|Mastery|Socket|Ascendancy ...] [--allocated|--unallocated] [--max-cost N] [--show-path] [--masteries] [--socket-radius <id|#1>] [--limit 100] [--json] # --limit 0 returns all matching nodes
pob calc "<kw1>" ["<kw2>" ...] [--group G] [--skill S] [--limit 20] [--max-breakdowns 30] [--no-breakdown] [--target <slug>] [--json] # Variadic EN/ZH get_calcs + calcs_breakdown formulas/tables (--max-breakdowns 0 expands all); rows are for `calcsSkill`. --group (index, main or name) with --skill (index, main or gem name) reads another group's active skill; --skill alone takes a gem or group name looked up in every group, or a group number. The Calcs tab is put back as it was

# What-If Simulation (0-residue rollback by default) & Persistent Mutation (--apply)
pob item try [--slot S] (--raw "<text>" | --file f) [--tooltip-only] [--apply]
pob item edit --slot S [--replace-mod <old> <new>]... [--add-mod <ln>]... [--remove-mod <sub >]... [--allow-illegal-affixes] [--apply] # Enforces the affix cap by default (Rare 3P/3S, Rare jewel 2P/2S, Magic 1P/1S); --allow-illegal-affixes bypasses for synthetic tests (batch/sweep item_edit op: "allowIllegalAffixes": true)
pob item unequip --slot S [--apply]
pob item db "<query>" [--type UNIQUE|RARE] [--slot S] [--index N] [--equip] [--with-tooltips] [--with-raw] [--apply] [--limit 15]
pob item flask <1..5|all> <on|off> [--apply]
pob item anoint [--slot Amulet] --notable "<name>" [--index 1..4] [--apply]
pob skill set --group main [--gem <idx|name>] [--new-gem "<name>"] [--level N] [--quality N] [--enabled true|false] [--count N] [--full-dps true|false] [--allow-legacy] [--allow-illegal-level] [--apply]
pob skill add --group main --gem "<name>" [--level N] [--quality 20] [--allow-legacy] [--allow-illegal-level] [--apply]
pob skill rm --group main --gem <idx|name> [--apply]
pob skill new-group [--label L] [--slot S] [--gem "Name[:lvl[:qual]]"]... [--full-dps true|false] [--enabled true|false] [--allow-legacy] [--allow-illegal-level] [--apply]
pob skill replace-group --group main (--gems '<json>' | --gem "Name[:lvl[:qual]]"...) [--label L] [--slot S] [--full-dps true|false] [--allow-legacy] [--allow-illegal-level] [--apply]
pob tree change [--allocate id1,id2:effectId]... [--deallocate id3]... [--allow-cascade|--no-allow-cascade] [--apply] # --allocate / --deallocate repeat and take comma lists; a node already in the asked state is reported as a no-op, one that cannot be reached is an error
pob tree set-class [Class] [Ascendancy] [--secondary-asc <Bloodline|None>] [--apply]
pob config set [<var>=<val|reset> ...] [--custom-mods "<text|clear>"] [--append-mods "<text>"] [--apply]
pob batch (--file <ops.json|-> | --json-ops '[...]') [--apply] [--no-undo] [--keep <spec>]... [--return summary,audit,audit:full,matrix,calc:DPS;Mana,export] [--compact] [--out f]
# Batch ops: config, flask, item, item_db, item_edit, unequip, anoint, tree, tree_reset, import_tree_url, skill, add_group, delete_group, set_group, replace_group, new_build, set_level, set_class, switch_main
# An op with a key it does not know is refused (a typo used to be ignored); remarks go in comment / note / why / desc / description / reason or any key starting with _. config variables go inside "set": {...}. A gem in "gems" is a 'Name[:level[:quality]]' string or an object (name | gemId, level, quality, enabled, count, skillPart, stageCount, enableGlobal1, enableGlobal2, allowIllegalLevel, allowLegacy); a gem object copied from `pob skills [--group G] --json` is accepted as is. replace_group keeps each kept gem's skill part, stage count and minion choice; skill / skill_add take skillPart and stageCount too.
pob sweep (--file <vars.json|-> | --json-variants '[...]') [--base-ops '[...]'] [--calc K]... [--scenario Pinnacle] [--keep <spec>]... [--compact] [--out f] [--json]
pob matrix [Original Pinnacle Uber FlasksOff "Label:Pinnacle,k=v"] [-s <spec>]... [--keep <spec>]... [--no-auto-keep] [--full] [--json]  # Compact default; --full for raw 200-key stats

# ROI Ranking, 3-Baseline A/B Comparison & Transplant
pob rank-nodes [--stat CombinedDPS|TotalEHP|Life] [--score STAT=W[,STAT=W]]... [--floor "STAT>=N|STAT<=N"]... [--max-dist 5] [--top 15] [--json]  # --score ranks by Σ W×Δ% over PoB stats (one node_power pass each; names ignore case and accept the --refund summary names primaryDps/totalEhp); --floor drops nodes breaking a limit (alone it keeps --stat as the objective)
pob rank-nodes --refund [--score STAT=W,...] [--floor "STAT>=N"]... [--top 15] [--json]  # Allocated passives by score lost per refunded point (cheapest respec first; default primaryDps=1,totalEhp=1); one sweep variant per node, 0-residue; start/ascendancy nodes skipped, branch-orphaning nodes listed as notRefundable
pob respec [--score STAT=W,...] [--floor "STAT>=N"]... [--rounds 3] [--max-dist 5] [--target <slug>] [--json]  # Greedy refund-cheapest + allocate-best swaps, each kept only on a PoB-verified net gain with no broken floor and no extra points; build restored, prints `pob batch --json-ops` to apply
pob rank-gems [--group main] [--slot N | --add-link] [--field CombinedDPS|FullDPS] [--top 15] [--include-legacy] [--json]
pob rank-gems --optimize [--group main] [--field CombinedDPS] [--passes 2] [--include-legacy] [--json]  # Swap each support slot to its best gem given the others, repeat until no swap helps; every swap re-checked by PoB (top 3 tried per slot), build restored, prints `pob batch --json-ops`
pob weights [--mod "<custom mod line>"]... [--preset bandit|pantheon-major|pantheon-minor|jewels] [--scenario Pinnacle] [--keep <spec>]... [--score STAT=W[,STAT=W]]... [--floor "STAT>=N|STAT<=N"]... [--target <slug>] [--json]       # PoB-verified DPS/EHP gain per probe mod (16 defaults; --mod replaces), 0-residue rollback; --score/--floor read sweep summary stats (CombinedDPS, TotalEHP, Life, FullDPS, ...; case-insensitive); --preset compares every option of that build choice instead (Pantheon avoidance PoB does not score shows Δ 0; bandit None does not allocate its 2 points; jewels unequips each equipped tree/abyssal jewel in turn, so Δ is what that jewel is worth)
pob compare [<ref_source>] [--keep <spec>]... [--no-auto-keep] [--target <slug>] [--ref-target <slug>] [--json] # 3 baselines: Original / Target Env Aligned / Pinnacle Dewatered
pob borrow [--item-slot "Weapon 1,Amulet"] [--skill-group main] [--ref-target ref] [--apply] [--json]

# Local 0ms Game Data (Daemon-Free, Variadic) & External Economy/PoEDB/Wiki (Cached, Variadic)
pob data <gem|unique|mod|base|translate|tattoo|runegraft|tree|tick> ["<q1>" ...] [--slot S] [--ilvl N] [--mod "<stat>"] [--kind all|tattoo|runegraft] [--legacy] [--type T] [--asc A] [--cdr N] [--aps R] [--spells N] [--quality-breakpoints] [--search-quality Q] [--active-only] [--limit 25 (0 = all)] [--rebuild] [--json]
# tattoo / runegraft: passive overrides from PoB's TattooPassives (runegraft lists runegrafts only; tattoo --kind narrows; --legacy adds retired tattoos; --slot is the passive it replaces, e.g. "Small Strength", Mastery, Keystone; --mod filters by stat). tree also takes a node id. mod lists Vestigial implicits (source Vestigial) with the donor unique; --slot follows PoB: only on a unique of the donor's item type (helmet, body armour, gloves, boots, shield)
pob poedb "<q1>" ["<q2>" ...] [--mods] [--filter "<kw>"] [--lang cn|us] [--proxy <url>] [--limit 150] [--json]
pob price "<q1>" ["<q2>" ...] [--league L] [--category all|unique|gem|imbuedgem|...] [--variant S] [--limit 20] [--detailed] [--proxy <url>] [--json]
pob meta [--league L] [--skill "<EN|中文>"] [--class "<EN|中文>"] [--top 15] [--proxy <url>] [--json] # poe.ninja league meta share (accepts EN substring, ZH/TW names, and slang like 正火/酋长)
pob research "<q1>" ["<q2>" ...] [--mods] [--filter "<kw>"] [--lang cn|us|en] [--proxy <url>] [--limit 150] [--max-chars 12000] [--json] # Concurrent poedb.tw + poewiki.net dual-source research (--limit 0 = every mod row, --max-chars 0 = unlimited)
pob wiki "<q1>" ["<q2>" ...] [--max-chars 12000] [--proxy <url>] [--json]               # Local PoEDB bilingual index exact match + Mechanics/Interactions priority extraction (--max-chars 0 = unlimited)

# Official PoE1 Trade (Read-Only, PoB-Verified) & Crafting Bench
pob trade stats "<text|中文>" [--slot S] [--limit 5] [--proxy U] [--refresh] [--json]            # Local TradeSiteStats.lua (0ms) or API fallback
pob trade search --slot S [--stat "text|中文=min"]... [--sum "a[*w]|b[*w]>=min"]... [--want T]... [--bench-craft "<stat>"]... [--budget N] [--currency chaos_equiv|chaos|divine] [--status available|securable|online|onlineleague|any] [--securable] [--max-age HOURS] [--bargain PCT] [--max-per-seller 2] [--search-sort asc|desc|sum] [--sort score|price|pob|sum] [--fetch-limit 10] [--pob-limit 5] [--normalize-quality auto|on|off] [--surrogate-k K] [--allow-conversion [--convert-to E]] [--open-prefix|--open-suffix|--open-affix] [--pob auto|on|off] [--auto-query] [--target <slug>] [--dump-query] [--proxy U] [--json] # more options (--weight, --league, --rarity, --ilvl-min, --category, --allow-corrupted, --max-results, --no-bench-hint, --current-item-file, --no-compare, --verbose) are in trade.md; --securable is shorthand for --status securable (Faustus Merchant's Tab instant Gold buyout; listings tag Instant/Gold fee vs Whisper, and `available` reports price-floor divergence); --max-per-seller defaults to 2 per account before PoB eval (0 = unlimited; exact clones collapse, hidden count surfaces as `sellerCappedDropped` / `Seller cap:`); --bargain uses a 1-seller-1-vote median preferring `securable` listings on `available`; --normalize-quality defaults to `auto` (active when PoB runs): evaluates modifiable <20%Q weapons/armour/flasks/tinctures at +20%Q in PoB (preserving Sacred Orb base percentiles) and tags every normalized row `[+20%Q]`; --fetch-limit up to 100 (10-ID GGG chunks); --surrogate-k prefilters the fetched pool via grad-Build before PoB eval (the pool is max(50, K) listings, at most 100, unless --fetch-limit is given); --auto-query trims lowest weights within complexity 160; --slot also takes a jewel socket (`Jewel <nodeId>`, or `#N` for the Nth socket) and an abyssal socket by PoB's name (`Helmet Abyssal Socket 1`, `Weapon 1 Swap Abyssal Socket 2`; sockets 1-6 of weapons, helmet, gloves, body armour, boots and belt)
pob trade plan <search.json>... --budget N [--score dps=W,ehp=W] [--top 10] [--json]  # Offline: at most one PoB-verified listing per slot from saved `trade search --json` files, max Σ score within budget (default dps=1,ehp=0.25); per-slot deltas are verified alone, the sum is an estimate
pob trade upgrade --budget N [--slot S]... [--top-slots 3] [--per-slot 5] [--score dps=W,ehp=W] [--league L] [--proxy U] [--target <slug>] [--json]  # Reference list: free moves (1 respec round + 1 gem pass), then the weakest gear slots (empty first, else least score lost when unequipped) -> live `trade search --auto-query --pob on` -> `trade plan` knapsack; failed slots go to skippedSlots (all failed: exits with the trade code, 4 first); a listing found for two slots is bought once; build left unchanged; the sum is an estimate
pob trade convert (--text T | --file f) --to fire|cold|lightning [--force] [--out f] [--json]  # Harvest 3.30 swap preview (same tier, rerolled)
pob bench list --slot S [--search "<text|中文>"] [--affix prefix|suffix] [--limit 25] [--json]
pob bench suggest --slot S --stat "<text|中文>" [--affix prefix|suffix] [--limit 5] [--json]

# Timeless Jewel Seed Search (hybrid PRNG+mmap in-engine synthesis for Legion & 3.30 Abyss, PoB-verified; other Historic jewels removed)
pob timeless list [--target <slug>] [--json]                                           # 11 timeless jewels (EN/ZH) + build's allocated sockets
pob timeless search --jewel "<name|中文>" --socket <nodeId|id1,id2|all> [--conqueror C] [--stat CombinedDPS|FullDPS|TotalEHP|...] [--mod "<ln>"]... [--top 15] [--workers N] [--exact] [--idle] [--target <slug>] [--json]
```
