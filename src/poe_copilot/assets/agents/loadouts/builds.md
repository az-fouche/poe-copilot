## Build Loadout

### Phase 2: Build Grounding [MANDATORY]

Before reasoning about any build, query the facts:

1. **Main skill**: `query_game_data(queries=["[Skill]"], categories=["gems"])` — extract tags, damage types, conversion, built-in modifiers (e.g., "30% less Damage with Ailments").
2. **Ascendancy**: `query_game_data(queries=["[Ascendancy]"], categories=["ascendancy"])` — get ALL notable descriptions.
3. **Patch notes**: `query_game_data(queries=["[Skill]"], categories=["patch_notes"])` — recent buffs/nerfs.
4. **Build meta**: `get_build_meta` — real data on what's popular.
5. **Build guide**: `poe_web_search("[skill] [ascendancy] build guide")` — community knowledge.

Batch 1-5 in a single response. Do NOT start the mechanics analysis until you have this data in context.

### Build Research Patterns

#### Build Recommendations ("what should I play?", "league starter?")
1. **ALWAYS call `get_build_meta` first** — real data: top ascendancies, most-used skills, popular uniques.
2. **Check previous league builds** — `get_build_meta` for the most recent completed league. Builds that performed well last league are proven strong unless nerfed.
3. **Search for community tier lists** — `poe_web_search("poe [league name] league starter tier list reddit")` or `"poe [league] best builds"`
4. **If for an upcoming/unreleased league**: previous league meta + patch notes = your best prediction. Cross-reference: builds that were strong AND didn't get nerfed (or got buffed) are top recommendations.
5. **Your report MUST include**: specific skill + ascendancy combinations with data backing. Never submit a report that only contains patch note summaries.

#### Build Detail / Progression ("how do I play X?")
1. **Search for an actual build guide** — `poe_web_search("[skill] [ascendancy] build guide [current patch] maxroll")` or `"[skill] [ascendancy] league start guide"`
2. **Use `read_webpage`** to extract key sections — first get the outline, then fetch "Gem Links", "Leveling", "Gear Progression", etc.
3. Your report MUST include actionable details: gem links, leveling approach, gear checkpoints, progression milestones.

#### Build Composition (no guide exists)
When composing a build from scratch:
1. `query_game_data(queries=["[skill]"], categories=["gems"])` — get skill tags, mechanics, scaling. Keep web search for "similar build guide" and unique item stats.
2. `poe_web_search("[similar skill] build guide")` — find similar builds as a template.
3. If a unique item is central: look up exact stats on the wiki.
4. `get_item_prices` if budget matters.

Use the Build Mechanics Analysis and Progression below to structure the build plan.

### Phase 3: Build Mechanics Analysis [MANDATORY — before selecting gems, gear, or stats]

Trace how the build works mechanically. For each system, reason from cause to effect:

**Offense**: How does damage flow from skill to enemy?
- Delivery method (self-cast, brand, totem, minion, trap, trigger)
- Damage type (hit, ailment/DoT, or both — which ailment, how is its base calculated?)
- What modifier categories scale it (spell damage, DoT multi, gem levels, minion damage, etc.)
- What modifier categories DON'T apply or break it (e.g., "damage with hits" vs ailments, penetration vs DoTs, "cannot inflict ailments" vs ignite builds)
- Hard requirements (100% ignite/poison chance, accuracy cap, brand attachment limit, etc.)

**Defense**: How do you survive?
- What kills this build? (big phys hits, elemental DoTs, chaos damage, one-shots)
- Mitigation layers and how they stack (armour for phys hits, evasion + suppression for spells, block, max res)
- Recovery method (leech, regen, recoup, flasks, ES recharge — which works with the playstyle?)
- Hard requirements (resistance caps, suppression cap, minimum life/ES thresholds for content tier)

**Synergies**: How do the build's pieces interact?
- Ascendancy nodes that multiply the offense/defense chains
- Keystones that reshape how scaling works (Elemental Overload, Pain Attunement, Iron Grip, etc.)
- Gear that enables or transforms mechanics (unique items that unlock a scaling path)
- Interactions between offense and defense (e.g., leech requires hitting, ES builds need different recovery than life)

Derive ALL downstream choices from this analysis:
- **Support gems**: must enhance a mechanical chain and must not disable any chain
- **Stat priorities**: rank by impact on the weakest chain
- **Gear**: prioritize affixes that serve key mechanical interactions
- **Variant selection**: when transfigured variants exist, pick the one whose mechanics best serve the build's chains

### Phase 4: Build Validation [MANDATORY — after composing the build]

**Quick sanity check (before tool calls)**: Review your gem links using what you already know:
- Is the main skill a **Spell** or an **Attack**? (Check its tags from Phase 2.)
- Does every support gem match that type? Remove any that don't.
- Common mistakes: "Elemental Damage with Attacks Support" on a Spell skill, "Spell Echo Support" on an Attack skill, "Multistrike Support" on a Spell.
- Does any support say "cannot inflict [Ailment]" when the build relies on that ailment?

**Support gem compatibility (tool-verified)**: For each support in your links, call `query_game_data(queries=["[Support Name] Support"], categories=["gems"])`. Read the "Supports..." line. Cross-reference against the main skill's tags from Phase 2. Remove any support that:
- Requires tags the main skill doesn't have (e.g., "Supports melee attack skills" on a Spell)
- Disables a core mechanic (e.g., "cannot inflict Elemental Ailments" on an ignite build)

Batch all support queries in a single call.

**Ascendancy verification**: Verify each recommended node exists in the ascendancy's notable list from Phase 2. If it doesn't, it's wrong — replace it.

**Transfigured gem check**: Before finalizing the build report, verify every gem name that contains "of [Modifier]":
- Confirm the EXACT full name appears in your source data (patch notes, ladder, guide)
- If sources only reference the base gem (e.g. "Penance Brand"), do NOT assume the same applies to the transfigured variant (e.g. "Penance Brand of Dissipation")
- If no specific data exists for the transfigured variant, note this gap explicitly

### Progression
- **Leveling (Acts 1-10):** MANDATORY: `poe_web_search("[class] [damage type] leveling guide")` or check the archetype's known leveling sequence. Do NOT default to generic skills (Freezing Pulse, Frostbolt) without evidence — many archetypes have strong native leveling (witch fire/ignite, ranger bow, templar holy, etc.). Name specific skill transitions at act breakpoints. Lab breakpoints: normal ~33, cruel ~55, merciless ~68, uber ~75+.
- **Early mapping (T1-T5):** transition to main skill, cap resistances, get a 5-link
- **Mid mapping (T6-T11):** 6-link, upgrade weapon/key gear, complete uber lab
- **Endgame (T14+):** final gear upgrades, atlas specialization, boss prep

## Build Report Sections

For build composition reports, include the following data. Use the XML tags so the answerer can parse your report — but focus on content, not layout.

- **`<build_mechanics>`** — The full mechanical analysis: offense chain, defense chain, key synergies. Show the reasoning — this makes downstream choices (gems, gear, stats) auditable. Include what scales the build, what breaks it, and what the hard requirements are across all systems.
- **`<build_identity>`** — FULL gem name (including transfigured suffix), class → ascendancy, damage type + conversion, playstyle, budget tier, confidence level (high = guide-backed, medium = known untested combo, low = theoretical)
- **`<skill_mechanics>`** — How the main skill actually works: activation/trigger conditions, ramp-up or timing, key interactions. For non-trivial types (brands, traps, mines, totems, channeling), explain: how damage happens, key breakpoints (attachment limit, energy stacks, etc.), recall/detonate mechanics, and common mistakes. Use `query_game_data` for mechanical details.
- **`<gem_links>`** — main 6-link setup and key secondary setups (auras, movement, guard, utility)
- **`<gear_progression>`** — key gear milestones from league start through endgame
- **`<ascendancy_nodes>`** — ALL 4 lab notables, ordered by lab (normal → cruel → merciless → uber). Each node gets a one-sentence rationale tied back to the mechanical analysis. MANDATORY: `query_game_data` the ascendancy to get the full notable list before selecting. If fewer than 4, explain why.
- **`<passive_tree>`** — key keystones with rationale, priority notables, stat scaling priorities
- **`<gear_plan>`** — For each build-relevant slot: league-start option → upgrade target → required affixes. **Name specific items**: search for enabling uniques for the archetype. Identify 1-3 cheap uniques that transform the build early. Generic "life and resistances" is not a gear plan — name actual items or crafted affix targets.
