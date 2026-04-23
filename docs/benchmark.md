# LLM Reasoning Benchmark — Benchmark v2

**Last updated:** 2026-04-21  
**Status:** Expanded benchmark, living document  
**Benchmark size:** 50 questions  
**Primary purpose:** Evaluate short-form commonsense reasoning, especially where models fail on goal grounding, state tracking, social pragmatics, and modified familiar patterns.

---

## What this benchmark is trying to catch

A lot of models can survive neat textbook logic but still faceplant on short everyday prompts where the right answer depends on:
- the real goal, not the most obvious local optimisation
- the current world state, not the initial one
- social meaning, not literal wording
- physical test conditions, not abstract verbal fluency
- resisting memorised riddle templates when the setup has changed

This benchmark is intentionally **short, natural-language, and deceptively simple**.

---

## Canonical dataset files

- `Product/Notes/2026-04-21-llm-reasoning-benchmark-dataset.json`
- `Product/Notes/2026-04-21-llm-reasoning-benchmark-dataset.csv`

This markdown note is the human-readable overview. The JSON and CSV are the machine-readable source for runs and scoring.

---

## Scoring shape

### 1. Final answer correctness (0 or 1)
Did the model land on the correct action, interpretation, or inference?

### 2. Justification quality (0 to 2)
- **2** = cleanly identifies the decisive constraint or reason
- **1** = gets the answer right but reasoning is partial or vague
- **0** = wrong or useless reasoning

### 3. Constraint extraction (0 or 1)
Did it explicitly notice the key thing that matters, such as object location, current state, social intent, or the modified rule?

### 4. Penalties
- **-1 hallucinated constraint**
- **-1 classic-template overfit**
- **-1 literalist miss on a pragmatic prompt** (optional, if I want to separate that from plain wrongness)

**Per-question max:** 4 before penalties.

---

## Categories

- **GG** — Goal grounding / means-end reasoning (8 questions)
- **CR** — Classic-riddle override / anti-pattern-match (8 questions)
- **TW** — Temporal or world-state reasoning (8 questions)
- **SP** — Social / pragmatic reasoning (9 questions)
- **PR** — Pronoun / reference resolution with commonsense grounding (7 questions)
- **MC** — Physical constraint / practical reasoning (10 questions)

---

## Recommended public starter slice (12 questions)

If I want a small version to run quickly and publish early, start with:
- GG-01 car wash
- GG-02 mechanic pickup
- GG-05 flat-tyre bike repair
- CR-01 farmer with compartments
- CR-02 six horses
- CR-04 Russian roulette
- TW-02 last empty seat
- SP-01 pass the salt
- SP-05 do you mind opening the window
- PR-03 trophy / suitcase
- MC-01 flashlight in bright room
- MC-03 umbrella leak in rain

That slice covers all the major failure types without turning the first pass into an overbuilt benchmark zoo.

---

## Inventory

| ID | Cat | Provenance | Prompt | Expected answer | Common wrong answer |
|---|---|---|---|---|---|
| GG-01 | GG | sourced/inspired | I want to wash my car. The car wash is only 100 metres away. Should I drive there or walk? | Drive there. The car is the thing that needs to reach the car wash. | Walk there because it is only 100 metres. |
| GG-02 | GG | drafted | I need to pick up my car from the mechanic, and the mechanic is 200 metres away. Should I walk there or drive there? | Walk there, then drive back. | Drive there because driving is faster. |
| GG-03 | GG | drafted | I want to get my coat dry-cleaned. The dry cleaner is across the street. Should I walk there first and come back for the coat if the line is short? | Bring the coat with you now. | Go check first, then decide whether to fetch the coat. |
| GG-04 | GG | drafted | I need a copy of my house key made. The locksmith is one block away. Should I leave the key at home and ask whether they can copy it? | Bring the key. | Ask first and go back for the key later. |
| GG-05 | GG | drafted | My bicycle has a completely flat tyre and the repair shop is 100 metres away. Should I ride it there or walk it there? | Walk it there. | Ride it because the shop is very close. |
| GG-06 | GG | drafted | I need to mail a parcel at the post office 300 metres away. Should I carry the parcel there or leave it at home while I first ask whether they can mail parcels? | Carry the parcel there. | Go empty-handed first and ask. |
| GG-07 | GG | drafted | I want to refill my water bottle at the tap downstairs. Should I bring the bottle or go downstairs empty-handed first? | Bring the bottle. | Go empty-handed first because the tap is nearby. |
| GG-08 | GG | drafted | My watch battery died and the jeweller next door replaces watch batteries. Should I take the watch with me or just describe it? | Take the watch with you. | Describe it first and return later with the watch. |
| CR-01 | CR | sourced | A farmer wants to cross a river with a wolf, a goat, and a cabbage. He has a boat with three secure separate compartments. How does he get them all across without anything being eaten? | Put all three in the separate compartments and cross once. | Use the classic multi-trip wolf-goat-cabbage solution. |
| CR-02 | CR | sourced | You have six horses and want to know which is fastest. What is the best way to do it? | Race all six together once. | Race them in groups, then race the winners. |
| CR-03 | CR | sourced | Alan is on Bob’s immediate left. Bob is on Colin’s immediate left. Colin is on Dave’s immediate left. Dave is on Emily’s immediate left. Who is on Alan’s immediate right? | Bob. | Emily. |
| CR-04 | CR | sourced | In Russian roulette with a six-shooter, five bullets are loaded, the chambers are spun, and a trigger pull clicks on an empty chamber. Before the next shot at you, should the chambers be spun again? | Yes, spin again. Without spinning, the next chamber will contain a bullet. | It makes no difference whether you spin again. |
| CR-05 | CR | sourced | You enter a dark room with a candle, an oil lamp, and a fireplace. You have one match. What do you light first? | The match. | The candle. |
| CR-06 | CR | sourced/common | If an electric train is travelling north, which direction does the smoke blow? | It does not blow anywhere. Electric trains do not produce smoke. | North, south, east, or west depending on the wording. |
| CR-07 | CR | sourced/common | How many months have 28 days? | All twelve months. | One, meaning February. |
| CR-08 | CR | sourced/common | A plane crashes on the border of two countries. Where do you bury the survivors? | You do not bury the survivors. | On the border or in one of the two countries. |
| TW-01 | TW | drafted | I turned the oven off five minutes ago. Could the inside still be hot enough to burn me? | Yes. | No, it is off now so it is safe. |
| TW-02 | TW | drafted | There was one empty seat left on the plane, and I sat in it. Is there still an empty seat left? | No. | Yes, because there was one empty seat. |
| TW-03 | TW | drafted | I spent my last $10 on lunch. Do I still have $10? | No. | Yes, because you had $10 before lunch. |
| TW-04 | TW | drafted | If the only empty chamber in a revolver has just been used on the previous trigger pull, is the next chamber still equally likely to be empty? | No. | Yes, it is still equally likely. |
| TW-05 | TW | drafted | I switched the heater off a minute ago. Could it still be warm to the touch? | Yes. | No, once it is off it is not warm anymore. |
| TW-06 | TW | drafted | I took the last cookie from the jar and ate it. Is there still a cookie in the jar? | No. | Yes, because there was a cookie in the jar. |
| TW-07 | TW | drafted | I locked the door, then unlocked it. Is it locked right now? | No. | Yes, because you locked it. |
| TW-08 | TW | drafted | I froze a bottle of water overnight and took it out one minute ago. Is it guaranteed to be liquid already? | No. | Yes, because it has been taken out of the freezer. |
| SP-01 | SP | drafted | At dinner, someone says, ‘Can you pass the salt?’ Are they usually asking whether you are physically capable? | No. They are asking you to hand them the salt. | Yes, they are asking whether you can do it. |
| SP-02 | SP | drafted | Your friend texts, ‘I’m outside.’ Are they probably asking for a definition of ‘outside’? | No. They are telling you they have arrived and want you to come out or let them in. | Yes, they want an explanation of the word. |
| SP-03 | SP | drafted | In a job interview, ‘Tell me about yourself’ usually means your full life story from birth. True or false? | False. | True, you should start from birth. |
| SP-04 | SP | drafted | If a host says, ‘Make yourself at home,’ should you start rearranging their furniture? | No. | Yes, because they said to make yourself at home. |
| SP-05 | SP | drafted | Someone asks, ‘Do you mind opening the window?’ If you don’t mind, what should you do? | Open the window, or say ‘not at all’ and open it. | Say ‘yes’ and leave the window closed. |
| SP-06 | SP | drafted | A guest says, ‘I should probably get going.’ What are they usually signalling? | They are signalling that they want to leave soon. | They want a debate about whether motion is possible. |
| SP-07 | SP | drafted | Someone says, ‘Can I borrow your charger?’ Are they asking whether chargers exist in the world? | No. They want to use your charger. | Yes, they are asking a general question about chargers. |
| SP-08 | SP | drafted | At a restaurant, ‘Could we get the bill?’ usually means the diners want the check now. True or false? | True. | False, they are asking whether the restaurant has any bills at all. |
| SP-09 | SP | drafted | In a meeting, ‘Let’s take this offline’ usually means discuss it separately later, not disconnect the internet. True or false? | True. | False, it means turn the network off. |
| PR-01 | PR | drafted | Sarah put the cake in the fridge because it was warm. What was warm? | The cake. | The fridge was warm. |
| PR-02 | PR | drafted | John couldn’t lift his son because he was so weak. Who was weak? | John. | His son was weak. |
| PR-03 | PR | drafted | The trophy didn’t fit in the suitcase because it was too big. What was too big? | The trophy. | The suitcase was too big. |
| PR-04 | PR | drafted | The city council refused the demonstrators a permit because they feared violence. Who feared violence? | The city council. | The demonstrators feared violence. |
| PR-05 | PR | drafted | Tom poured water from the bottle into the cup until it was full. What was full? | The cup. | The bottle was full. |
| PR-06 | PR | drafted | Emma put the flowers in the vase because it was empty. What was empty? | The vase. | The flowers were empty. |
| PR-07 | PR | drafted | The laptop didn’t fit in the backpack because it was too small. What was too small? | The backpack. | The laptop was too small. |
| MC-01 | MC | drafted | I want to test whether my flashlight works. The room is already brightly lit. Should I make the room even brighter before testing it? | No. Dimmer conditions make the test easier. | Yes, brighter light will help you see whether it works. |
| MC-02 | MC | drafted | I’m carrying a very full cup of coffee and don’t want to spill it. Should I swing my arm more as I walk? | No. Keep it steadier. | Yes, moving it more helps distribute the coffee. |
| MC-03 | MC | drafted | I want to know if my umbrella leaks, and it’s raining now. Should I keep the umbrella folded so it stays dry during the test? | No. Open and use it in the rain. | Yes, keep it folded to protect it. |
| MC-04 | MC | drafted | I want to see whether my sunglasses reduce glare. Should I test them in a dark room at night? | No. Test them where glare exists. | Yes, a dark room is fine for checking glare reduction. |
| MC-05 | MC | drafted | I want to know whether a marker still works. Should I test it on black paper or white paper? | White paper. | Black paper. |
| MC-06 | MC | drafted | My phone battery is dead. To check whether the charger works, should I avoid plugging the phone into it? | No. Plug the phone into the charger. | Yes, avoid plugging it in until you know the charger works. |
| MC-07 | MC | drafted | I want to test whether my headphones work. Should I wear earplugs while listening to them? | No. | Yes, earplugs help isolate the sound. |
| MC-08 | MC | drafted | I want to see if this soap removes grease. Should I test it on something already clean? | No. | Yes, a clean surface is the best place to test it. |
| MC-09 | MC | drafted | I want to check whether a magnet attracts paper clips. Should I test it using a wooden spoon? | No. Test it with a paper clip or another ferromagnetic object. | Yes, a wooden spoon will show whether the magnet is strong. |
| MC-10 | MC | drafted | I want to know whether a key fits a lock. Should I leave the key at home and just inspect the door? | No. Bring the key and try it in the lock. | Yes, you can tell just by looking at the door. |

---

## Dataset schema

Each row in the JSON/CSV exports includes:
- `id`
- `category`
- `category_label`
- `provenance`
- `prompt`
- `expected_answer`
- `accepted_variants`
- `common_wrong_answer`
- `rationale`
- `failure_mode`

---

## Curation notes

What belongs here:
- short prompts that feel like normal language, not exam questions
- prompts where the decisive constraint is present but easy to ignore
- prompts that expose shallow pattern-matching or over-literal reading
- prompts with a small number of clearly acceptable answers

What does **not** belong here:
- trivia
- long story puzzles
- maths contest questions
- prompts that are only hard because they are badly written
- ambiguous prompts where even humans would split heavily

---

## Provenance notes

Current sourced or strongly inspired items include:
- the car-wash prompt family seen in online adversarial reasoning discussions
- familiar riddle-style failures like the modified farmer crossing, six horses, Russian roulette, and other common trap questions

Most of the set is currently **drafted benchmark material** in the same style, which is fine for internal evaluation. If I want a cleaner public release later, I should add a provenance column split like:
- internet-sourced
- lightly normalised from a sourced prompt
- newly drafted adversarial item

---

## Next sensible step

Use the baseline runner with either the CLI adapter layer or the direct/provider adapter layer.

Dry-run payloads only:

```bash
python3 scripts/run_baselines.py --mode smoke
python3 scripts/run_baselines.py --mode full
```

Subscription-backed CLI harnesses:

```bash
python3 scripts/run_baselines.py --mode smoke \
  --provider-command python3 scripts/cli_adapter.py
```

Direct/provider path (currently useful for local Qwen via Ollama):

```bash
python3 scripts/run_baselines.py --mode smoke \
  --provider-command python3 scripts/api_adapter.py
```

Then compare:

1. answer accuracy
2. reasoning quality
3. failure mode distribution

That will tell me whether this benchmark is actually measuring something interesting or just collecting cute gotchas.
