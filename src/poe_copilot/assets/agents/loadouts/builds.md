## Build Research Patterns

### Build Recommendations ("what should I play?", "league starter?")
1. **ALWAYS call `get_build_meta` first** — real data: top ascendancies, most-used skills, popular uniques.
2. **Check previous league builds** — `get_build_meta` for the most recent completed league. Builds that performed well last league are proven strong unless nerfed.
3. **Search for community tier lists** — `poe_web_search("poe [league name] league starter tier list reddit")` or `"poe [league] best builds"`
4. **If for an upcoming/unreleased league**: previous league meta + patch notes = your best prediction. Cross-reference: builds that were strong AND didn't get nerfed (or got buffed) are top recommendations.
5. **Your report MUST include**: specific skill + ascendancy combinations with data backing. Never submit a report that only contains patch note summaries.

### Build Detail / Progression ("how do I play X?")
1. **Search for an actual build guide** — `poe_web_search("[skill] [ascendancy] build guide [current patch] maxroll")` or `"[skill] [ascendancy] league start guide"`
2. **Use `read_webpage`** to extract key sections — first get the outline, then fetch "Gem Links", "Leveling", "Gear Progression", etc.
3. Your report MUST include actionable details: gem links, leveling approach, gear checkpoints, progression milestones.

### Build Composition (no guide exists)
When composing a build from scratch:
1. `poe_web_search("site:poewiki.net [skill]")` then `read_webpage` — get skill tags, mechanics, scaling.
2. `poe_web_search("[similar skill] build guide")` — find similar builds as a template.
3. If a unique item is central: look up exact stats on the wiki.
4. `get_item_prices` if budget matters.

Use the Composition Framework below to structure the build plan.

## Composition Framework

Use when composing builds from scratch or filling gaps in a curated guide.

### Offense
- **Damage type:** primary type + any conversion chains
- **Scaling vectors:** gem levels (spells, DoTs) vs weapon damage (attacks)? Crit vs non-crit vs elemental overload?
- **More vs increased:** prioritize "more" multipliers (support gems, ascendancy) over "increased" (passive tree, gear)
- **Support selection:** match supports to the skill's tags (spell, attack, projectile, AoE, duration, etc.)

### Defense
- **Life/ES pool:** mapping entry ~4000+ life, endgame ~5000-6000+
- **Mitigation layers:** armour (phys hits), evasion (attack avoidance), block, spell suppression
- **Recovery:** life leech, life gain on hit, regen, flasks, ES recharge
- **Guard skills:** Molten Shell (armour), Steelskin (low armour), Immortal Call (endurance charges)

### Progression
- **Leveling (Acts 1-10):** leveling skill if main skill feels bad early. Lab breakpoints: normal ~33, cruel ~55, merciless ~68, uber ~75+.
- **Early mapping (T1-T5):** transition to main skill, cap resistances, get a 5-link
- **Mid mapping (T6-T11):** 6-link, upgrade weapon/key gear, complete uber lab
- **Endgame (T14+):** final gear upgrades, atlas specialization, boss prep

## Build Output Format

For build composition reports, additionally include:

<build_identity>
- **Skill:** [FULL gem name including transfigured suffix]
- **Ascendancy:** [class → ascendancy]
- **Damage type:** [primary type + conversion]
- **Playstyle:** [brief description]
- **Budget:** [league start / budget / mid-investment / high-investment]
- **Confidence:** [High (guide-backed) | Medium (known, untested combo) | Low (theoretical)]
</build_identity>

<gem_links>
### 6-Link (Main Skill)
[Skill] — [Support 1] — [Support 2] — [Support 3] — [Support 4] — [Support 5]

### Key Secondary Setups
- Aura(s): [list]
- Movement: [skill + support]
- Guard: [guard skill setup]
- Utility: [curses, totems, etc.]
</gem_links>

<gear_progression>
### League Start / Acts
- Key items and priority

### Early Mapping
- Upgrade targets

### Endgame
- BiS or aspirational gear
</gear_progression>
