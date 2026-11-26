# Official PoE1 Trade Search & Crafting Bench (`pob trade` / `pob bench`)

`pob trade` and `pob bench` extend `pob` with a **read-only** official Path of Exile 1 market upgrade workflow verified through the local headless PoB engine.

- **Read-only**: never whispers sellers, buys items, sends game input, or mutates your build unless you explicitly run `pob item try --apply`.
- **PoB is ground truth**: real DPS/EHP deltas come strictly from headless PoB (`trade_eval_items` single-snapshot batch verification); `-` means **not verified**, never `0` upgrade.
- **Optimization order**: run `pob audit` / `pob summary` (and check `rank-nodes`, `rank-gems`, `anoint`, `bench`) before shopping so you target real gaps rather than inflated config numbers.

---

## Quick Start

```powershell
# 1. Inspect your build and diagnose real gaps
pob status
pob audit

# 2. Resolve a stat ID offline (0ms via local TradeSiteStats.lua; EN or ZH, slot-aware)
pob trade stats "攻击速度" --slot weapon1
pob trade stats "to Cold Resistance" --slot gloves

# 3. Search one slot and batch-verify top candidates in headless PoB
pob trade search --slot gloves --budget 20 `
  --stat "冰霜抗性=40" `
  --want "Attack Speed" `
  --pob auto --pob-limit 5

# 4. Inspect the exact trade payload offline without hitting the network
pob trade search --slot gloves --stat "to Cold Resistance=40" --allow-conversion --dump-query

# 5. Open-affix base + crafting bench fallback
pob trade search --slot gloves --budget 10 --stat "最大生命=60" --open-suffix --pob auto
pob bench suggest --slot gloves --stat "冰霜抗性"
```

---

## Commands

### `pob trade stats "<text|中文>" [--slot S] [--limit 5] [--proxy U] [--refresh] [--json]`

Resolves English or Chinese modifier text to an official PoE1 trade stat ID with slot-aware `(Local)` / `(Shields)` routing:

- Weapon slots (`weapon1`, `bow`, `wand`, `claw`, `dagger`, `sceptre`, `staff`, `one_handed_*`, `two_handed_*`) automatically route weapon-local modifiers (e.g., `increased Attack Speed` -> `explicit.stat_210067635 (#% increased Attack Speed (Local))`).
- Non-weapon slots (`gloves`, `ring1`, `amulet`, `quiver`, etc.) route to global equivalents (`explicit.stat_681332047 (#% increased Attack Speed)`).
- Reads local `PoE1/Data/TradeSiteStats.lua` (18,375 stats, updated automatically by `pob update`) in `<20ms` with zero network calls; falls back to `/api/trade/data/stats` (7-day cache; `--refresh` fetches it again) when no local engine is installed.

### `pob trade search`

| Option | Default | Meaning |
|---|---|---|
| `--slot` | — | `helmet`, `body_armour`, `gloves`, `boots`, `shield`, `quiver`, `amulet`, `belt`, `ring1..3`, `weapon1..2`, `bow`, `wand`, `claw`, `dagger`, `sceptre`, `staff`, `flask1..5`, `jewel`, `abyss_jewel`, `cluster_jewel` |
| `--stat "text\|中文=min"` | — | Hard filter (`=min` optional; defaults to `1`). Supports EN & ZH queries. |
| `--want "text\|中文"` | — | Soft preference boosting comparison score (no trade filter). |
| `--weight cat=val` | — | Override mod scoring weights (`life`, `resist`, `damage`, `speed`, `crit`, `skill_level`, ...). |
| `--budget` / `--currency` | `chaos_equiv` | Price cap. `chaos_equiv` omits `price.option` so GGG evaluates Chaos Orb Equivalent across Chaos/Divine/Alch; pass `chaos` or `divine` for exact currency. |
| `--status` | `available` | PoE1 3.30 trade status: `available` (instant buyout + online), `securable` (instant buyout only), `online`, `onlineleague`, `any`. |
| `--securable` | off | Shortcut for `--status securable` (Faustus Merchant's Tab instant Gold buyout). Listings display `[一口价 · N,NNNG]` / `[Instant · N,NNNG]` vs `[私聊]` / `[Whisper]`, and `available` searches report a `Price floor:` note (`priceFloorNote`) when Whisper-only listings sit below 70% of the Instant Buyout floor. |
| `--max-age` | off | Only listings indexed within this many hours, e.g. `15`. Sends the smallest site "Listed" window that covers it, drops the rest (and any listing with no readable time) locally, and keeps fetching (up to 5 pages, or 10 with a `--fetch-limit` above 50) until `--fetch-limit` fresh listings are found. If nothing is that fresh, the older listings are shown instead and the report says so (`staleFallback` in `--json`). The report shows each listing's seller and how long ago it was listed. |
| `--bargain` | off | Percent, e.g. `30`. Flags listings at least that far below the going price (1-seller-1-vote median of the 10 cheapest listings of the same search, any age; on `available`, prefers `securable` Instant Buyout listings when >=5 distinct sellers exist) and lists them first. A search that matches 10,000 or more listings (the site's cap) has no reliable floor, so nothing is flagged and the `Market:` line says to narrow it. Price only: judge the item itself by the PoB columns. Costs one more search, unless the main search already is cheapest-first with no `--max-age`. Pair with `--max-age` to catch underpriced fresh listings. |
| `--max-per-seller` | `2` | Maximum distinct listings retained per seller account before PoB verification (`0` = unlimited). Exact same-seller clones (identical normalized mods & price) collapse automatically (`(+N dup)` / `sellerDuplicatesCollapsed`), and any capped 3rd+ listings are reported via `Seller cap:` in Markdown and `sellerCappedDropped` in JSON. |
| `--league` | auto | Defaults to current softcore trade league via `poe.ninja` / trade API. |
| `--rarity` / `--ilvl-min` | `nonunique` / `0` | Rarity (`nonunique`, `rare`, `unique`; `any` disables) and minimum item level. |
| `--category` / `--no-category` | from `--slot` | Override trade category (e.g. `weapon.bow`, `armour.gloves`). |
| `--allow-conversion` | off | Expand convertible single-element stats into a `count (min: 1)` group across `fire`/`cold`/`lightning` and auto-exclude `corrupted`/`mirrored` (unless `--allow-corrupted`). |
| `--convert-to` | from `--stat` | Explicit target element (`fire`, `cold`, `lightning`). |
| `--open-prefix` / `--open-suffix` / `--open-affix` | off | Filter via `pseudo.pseudo_number_of_empty_*_mods` for bench-craft fallback. |
| `--bench-hint/--no-bench-hint` | on | Include matching crafting-bench options for the slot in the report. |
| `--pob auto\|on\|off` | `auto` | Batch-verify top `--pob-limit` candidates via daemon `trade_eval_items` (`on` exits `6` on failure; `auto` degrades to mod deltas). |
| `--pob-limit` | `5` | Number of top candidates evaluated in PoB. |
| `--normalize-quality` | `auto` | `auto` (default) / `on` / `off`. Active by default whenever PoB verification runs: PoB trade comparisons evaluate modifiable `<20%` quality weapons, armour, flasks, and tinctures at `+20%` quality using lossless two-step parsing (locks Sacred Orb base percentiles before raising quality; skips Corrupted/Mirrored/Unmodifiable, `>=20%` over-quality, and jewellery/jewels/quivers), keep `item_text` unmodified, and tag every normalized row `[+20%Q]` (`listedQuality`/`evaluatedQuality`/`qualityNormalized` in `--json`). Pass `--normalize-quality off` to evaluate at exact listed quality. |
| `--surrogate-k` | off | Rank the fetched listings with a linear surrogate (`compute_grad_build`; `0` disables) and send only the best `--pob-limit` to exact PoB evaluation. Unless `--fetch-limit` is given, fetches `max(50, K)` listings, at most `100`. |
| `--fetch-limit` / `--max-results` | `10` / `8` | Listings fetched (max `100`, chunked in 10-ID GGG requests) / rows displayed. |
| `--sort score\|price\|pob` | `score` | Report ranking order (`pob` ranks by finite DPS + 0.25*EHP, `inf`/`NaN`-safe). `price` compares chaos values using poe.ninja currency rates, so `1 divine` sorts after `50 chaos`. |
| `--dump-query` | off | Print trade query JSON and exit without calling `/api/trade/search`. |
| `--proxy` | env | Explicit HTTP/SOCKS5 proxy (also honors `POB_PROXY` / `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY`). |
| `--json` / `--verbose` | off | RFC-8259 strict JSON output / HTTP request logging (cookies never logged). |

Each candidate's `Trade listing` link is the same search narrowed to that listing's seller account, so it opens on that item instead of the whole result list (a seller with several matching listings gets a link showing all of them).

### `pob trade plan <search.json>... --budget N [--score dps=W,ehp=W] [--top 10] [--json]`

Plans one budget across several slots without calling the trade API again. Save each slot's `pob trade search --pob on --json --out <slot>.json`, then pass the files: the plan keeps listings with a chaos price and a PoB result, scores each as `Σ W × Δ%` (default `dps=1,ehp=0.25`, the same blend as `--sort pob`), and picks at most one listing per slot so the total score is highest within `--budget` chaos. It also lists the best score per chaos across all slots. Each delta was verified alone against the current build, so the combined gain is an estimate: apply the picks one at a time with `pob item try` to confirm.

### `pob trade upgrade --budget N [--slot S]... [--top-slots 3] [--per-slot 5] [--score dps=W,ehp=W] [--league L] [--proxy U] [--json]`

A one-shot **reference** list for "where should the next N chaos go?". It chains the steps above:

1. **Free moves first**: one round of `pob respec` and one pass of `pob rank-gems --optimize` on the main group, listed apart from the chaos plan.
2. **Weakest slots**: unless `--slot` is given, empty gear slots come first, then the slots whose item loses the least score when unequipped (a what-if `item unequip` per slot); the first `--top-slots` are searched.
3. **Live trade**: each slot runs `pob trade search --auto-query --pob on --pob-limit <--per-slot>`. A slot that fails (rate limit, no results, or no PoB query) is listed under `skippedSlots` and the rest carry on. When every searched slot fails, the command still prints its output and then exits with the most urgent trade exit code it saw (`4` before `3`, `5`, `6`, `2`).
4. **Plan**: the results go through the same knapsack as `pob trade plan`. A listing found for two slots (Ring 1 and Ring 2) is bought once, for the slot where it scores best.

Expect about 1–3 minutes for three slots, mostly trade API rate limits. Nothing is applied to the build, and the plan's total is an estimate (each listing was verified alone).

### `pob trade convert (--text T | --file f) --to fire|cold|lightning [--out f] [--force] [--json]`

Rewrites Harvest-convertible explicit single-element modifiers in PoB item text and prints conversion rules, 3.30 costs, warnings, and skipped reasons.

### `pob bench list` / `pob bench suggest`

```powershell
pob bench list --slot gloves [--search "冰霜抗性"] [--affix suffix] [--limit 25] [--json]
pob bench suggest --slot gloves --stat "to Cold Resistance" [--affix suffix] [--json]
```

- **Dual-source design**: uses PoB's auto-updated `ModMaster.lua` (via the local `game_data/` SQLite index — 100% authoritative `prefix`/`suffix`, `group`, `level`, multi-line stats, and `zh-rCN` translations) overlaid with `pob_cli/src/pob_cli/data/bench_costs.json` for currency `cost` and `unlock` location. When no local engine is installed, transparently falls back to the clean embedded `ModMaster.lua` snapshot inside `bench_costs.json`.
- Always quotes the **minimum** roll as the safe floor and provides ready-to-paste `craftedLinesMin` (`{crafted}+16% to Cold Resistance`) for verification with `pob item try`.
- Refresh costs/unlocks after a patch with `python pob_cli/scripts/update_bench_costs.py [--proxy <url>]`.

---

## Harvest Same-Tier Conversion Rules (PoE1 3.30)

| Group | Elements | Craft (3.30) | Cost |
|---|---|---|---|
| `resistance` | `fire` / `cold` / `lightning` | Change X Resistance into similar-tier Y Resistance | `300 Lifeforce (Primal/Vivid/Wild matching target)` |
| `elemental_damage` | `fire` / `cold` / `lightning` (added / increased) | Change X Damage into similar-tier Y Damage | `300 Lifeforce + 1 Crystallised Rancour` |

Enforced hard guards (`trade_item/`):
- Only **identified** `MAGIC` / `RARE` items; `UNIQUE`, `NORMAL`, `Corrupted`, `Mirrored`, and `Unidentified` are refused.
- Only pure `explicit` single-element lines; `implicit`, `enchant`, `fractured`, `crafted`, `scourge`, `crucible`, `mutated`, `veiled`, dual-element, `all Elemental Resistances`, maximum resistance, penetration, chaos, and physical mods are refused.
- **Same-group conflict guard**: refuses converting into an element the item already has as an explicit or fractured mod in the same group/subkind, converts at most **one** mod per `(group, subkind)` (highest value first), and warns if a `{crafted}` target mod must be removed at the bench first.
- **Re-roll caveat**: Harvest preserves **tier** (`S3`, `P2`, ...) and randomizes the value inside that tier. JSON always marks `"rerolled": true`; listed values are best-case references.

---

## High-Fidelity PoE1 3.30 Item Reconstruction & PoB Verification

`trade_item.build_item_text` mirrors PoB `TradeQueryRequests.lua` + `Item.lua`:
- Reconstructs `properties` (Quality, Armour/Evasion/ES/Ward, Physical/Elemental/Chaos Damage, Crit, Attacks per Second, Block), `Item Level`, group-linked `Sockets` (`R-G-B R-B W`), multiline `{enchant}`/`{scourge}`/`implicit` lines with exact physical `Implicits: N` counts, 3.30 `explicitMods[].flags` (`{crafted}`, `{fractured}`, `{mutated}`) and legacy arrays, 8 influences (`Shaper`, `Elder`, `Warlord`, `Hunter`, `Crusader`, `Redeemer`, `Searing Exarch`, `Eater of Worlds`), plus `Synthesised Item`, `Fractured Item`, `Split`, `Mirrored`, `Corrupted`, `Unidentified`, with GGG rich-text stripping (`[Critical|Critical Hit]`, `<augmented>{...}`).
- Batch verification runs inside a single daemon RPC (`trade_eval_items`): captures one build snapshot (`export_code` + baseline digest), isolates each candidate against that snapshot, and restores cleanly in `finally`.

---

## Rate Limits, Cookies, Security & Exit Codes

- **Dynamic GGG Rate Limiter**: parses `X-Rate-Limit-Policy`, `X-Rate-Limit-Rules`, `X-Rate-Limit-<rule>`, `X-Rate-Limit-<rule>-State`, and `Retry-After` (with `limitMargin=1`), persisting bucket state atomically in `<POB_RUNTIME_DIR>/cache/trade_ratelimit.json` across CLI invocations with zero blind sleep on cold requests.
- **Cookies**: read strictly from `POE_COOKIE` or `POESESSID` environment variables (never CLI arguments), never printed or logged, and redacted from error snippets.
- **Untrusted listing text**: control characters stripped and lengths truncated before display.

| Exit Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Usage / slot / stat-mapping / invalid flag combination error |
| `2` | No matching listings on trade |
| `3` | HTTP 401/403 — `POESESSID` / `POE_COOKIE` or Cloudflare check required |
| `4` | Rate limited (`Retry-After` / bucket exhausted) |
| `5` | Network or trade API error |
| `6` | `--pob on` verification failed |
