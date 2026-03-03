## Build-Specific Checks

### MECHANICAL CORRECTNESS (CRITICAL — reject if wrong)

4. **Support gem tags**: For each support gem recommended, check that the report queried its data. The support's "Supports..." restriction must match the main skill's tags. Flag if:
   - A support requires "attack" or "melee" tags on a Spell skill
   - A support says "cannot inflict [Ailment]" when the build relies on that ailment
   - A support was never queried via `query_game_data`

5. **Scaling coherence**: Check that stat priorities match the damage type. Flag if:
   - Attack modifiers recommended for a Spell build
   - Spell modifiers recommended for an Attack build
   - Hit damage scaling recommended for a DoT/ailment build

### STRUCTURAL COMPLETENESS (WARNING — note but do not reject)

6. **Ascendancy completeness**: Build reports must include exactly 4 ascendancy notables (normal, cruel, merciless, uber lab). Note if fewer than 4 without explanation. Verify each node name appears in the ascendancy data from the report.

7. **Gear specificity**: Note if gear recommendations are only "life and resistances" without naming specific items, uniques, or crafted affix targets.
