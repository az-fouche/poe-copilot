# Item rarity, mods, crafting methods, and damage scaling formulas

## Item Rarity Tiers

| Rarity | Color | Max Mods | Notes |
|--------|-------|----------|-------|
| Normal | White | 0 (implicits only) | Crafting bases |
| Magic | Blue | 2 (1 prefix + 1 suffix) | Early-game, alt-crafting foundation |
| Rare | Yellow | 6 (3 prefix + 3 suffix) | Primary endgame gear |
| Unique | Orange | Fixed special mods | Often build-enabling, not prefix/suffix |

## Core Item Concepts

- **Item Level (ilvl):** Determines available mod tiers. ilvl 84+ needed for T1 mods. Visible with Alt key.
- **Base Type:** Sets implicits, base stats, and affix pool. Cannot be changed — choose carefully (e.g., Vaal Regalia for ES, Astral Plate for all res).
- **Implicits vs Explicits:** Implicits are inherent to the base (above the line); explicits are rolled mods (below the line). Crafting affects explicits.

## Modifier System

### Prefix Examples (3 max)
- Life, Energy Shield, Mana
- Flat/% damage, elemental damage with attacks
- Local mods (% phys damage, added damage), directly affect the item's base stats

### Suffix Examples (3 max)
- Resistances, attributes
- Crit chance/multi, accuracy
- Attack/cast/movement speed

### Key Details
- **Hybrid mods** provide two stat types but occupy one affix slot (e.g., "% ES and Stun Recovery")
- **Mod tiers:** T1 = highest values, exponentially rarer. T1 life on body armour: 90-99; T5: 60-69
- **Mod weights:** Each mod has an internal roll weight. Desirable mods tend to have lower weights.

## Damage Scaling Formula

```
Final Damage = (Base + Flat Added) x (1 + Sum of Increased) x Product of (1 + More)
```

### Increased vs More

| | Increased | More |
|--|-----------|------|
| Stacking | Additive with each other | Multiplicative with everything |
| Diminishing returns | Yes — each point worth less | No — each multiplier equally valuable |
| Common sources | Passive tree, gear | Support gems, ascendancies |
| Example | 50% + 30% = 80% total | 50% x 30% = 1.5 x 1.3 = 95% total |

**Worked example:** 100 base + 50 flat, 200% increased, 40% more x 20% more:
`(150) x (1 + 2.0) x (1.4 x 1.2) = 150 x 3 x 1.68 = 756 damage`

### Scaling Priority
1. More multipliers (no diminishing returns)
2. Flat added damage (scales with all multipliers)
3. Increased damage (diminishing returns but still valuable)
4. Base damage (fixed by weapon/skill choice)

## Crafting Methods

### Basic Currency
- **Chaos Orb:** Rerolls all mods on rare. Random — inefficient for targeting.
- **Orb of Alchemy:** Normal → Rare with random mods.
- **Orb of Alteration:** Rerolls magic items. Foundation of many advanced methods (alt-spam + regal).

### Essence Crafting
- Guarantees one specific mod (often exceeding T1 values at Deafening tier)
- Remaining mods roll randomly. Works on any rarity (upgrades to rare).
- Good for: securing hard-to-roll mods cheaply (e.g., Essence of Greed for high life, Woe for spell damage)

### Fossil Crafting
- Resonators + fossils: weight certain mod types up, block others entirely
- Key fossils: Pristine (life, no mana), Dense (defense, no life), Jagged (phys, no chaos), Frigid/Scorched/Metallic (element-specific)
- Can combine multiple fossils for precise targeting ("fossil blocking")

### Harvest Crafting
- Targeted add/remove of specific mod types, augment with guaranteed types, lucky rerolls
- Encounter-limited — save powerful crafts for expensive bases
- Enables items impossible through other methods

### Veiled Mods & Syndicate
- Defeat Syndicate members → veiled items → unveil to learn bench recipes
- Specific members drop specific veiled mod types; position them strategically
- Jun's Crafting Bench provides guaranteed mods for currency costs — essential for finishing items

### Eldritch Currency
- Modifies implicit mods on Searing Exarch / Eater of Worlds influenced items
- Separate system from normal explicits — endgame min-maxing layer
- Eldritch Ichors/Embers for implicit tiers, Orb of Conflict to upgrade

### Fracture, Synthesis & Recombination
- **Fractured items:** One+ mods permanently locked — guaranteed crafting foundation. Fracturing Orb locks a chosen mod (expensive).
- **Synthesis:** Combine fractured items → synthesized bases with new implicits based on fractured mod types. Best-in-slot potential, extremely expensive.
- **Recombination:** Merge two rares of same base type. Can create impossible mod combos but high destruction risk.

## Meta-Crafting

- **Cannot Change Prefixes/Suffixes:** Protects one type while modifying the other. Expensive but essential for high-value items.
- **Multimod (Can Have Multiple Crafted Modifiers):** Allows multiple benchcrafted mods. Primary method for filling items with guaranteed stats.

## Crafting Strategy

### Multi-Step Process
1. **Base acquisition:** Right base type + ilvl 84+
2. **Foundation:** Secure 1-2 core mods (essence, fossil, or alt-regal)
3. **Filling:** Add remaining desired mods (harvest augment, benchcraft)
4. **Optimization:** Divine for better values
5. **Finishing:** Benchcraft final utility mods

### Craft vs Buy
- **Craft when:** Specific combos needed, market price > expected craft cost, attempting best-in-slot
- **Buy when:** Common combos available, limited currency/experience, time-sensitive upgrades

### Slot Priority
1. **Weapon:** Directly scales all damage, highest impact upgrade
2. **Body Armour:** Highest total mod potential, 6-link for main skill
3. **Other slots:** Fill res gaps, life/ES, attributes — often better to buy until deep endgame

### Economic Timing
- **Early league:** Functional upgrades, buy cheap rares
- **Mid-league:** Begin serious crafting projects
- **Late league:** Attempt mirror-tier crafting
