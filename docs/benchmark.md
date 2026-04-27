# LLM Reasoning Benchmark — Benchmark v2

**Last updated:** 2026-04-27  
**Status:** Expanded benchmark, living document  
**Benchmark size:** 100 questions
**Primary purpose:** Evaluate short-form commonsense reasoning, especially where models fail on goal grounding, state tracking, social pragmatics, instruction ambiguity, and modified familiar patterns.

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

- `data/questions.json` — canonical source for runs and scoring
- `data/questions.csv` — spreadsheet-friendly export view

This markdown note is the human-readable overview. The JSON file is the machine-readable scoring source; the CSV export omits some v2 metadata such as `evaluation`, `ambiguity`, `cooperative_intent`, and `calibration`.

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
- **IA** — Instruction ambiguity / clarification judgment, cooperative intent, context-dependent shorthand, missing selection, deictic reference, ambiguous date and time phrases, ambiguous source phrases, ambiguous recipient scope, ambiguous target sections, ambiguous payment methods, ambiguous thresholds, ambiguous sort keys, ambiguous export formats, ambiguous notification channels, ambiguous merge targets, ambiguous temperature units, ambiguous person identities, ambiguous office locations, ambiguous permission levels, ambiguous quantities, ambiguous timezones, ambiguous restore targets, ambiguous deployment targets, ambiguous version/status requests, ambiguous recurrence schedules, ambiguous currencies, ambiguous reporting periods, ambiguous schedule directions, ambiguous data-removal scopes, ambiguous mute durations, ambiguous subscription tiers, ambiguous sync directions, ambiguous target languages, ambiguous recurring event scopes, ambiguous contact import modes, ambiguous billing cycles, ambiguous delivery addresses, ambiguous compression modes, ambiguous anonymization modes, ambiguous project removal modes, ambiguous approval requests, ambiguous two-factor methods, ambiguous account deactivation modes, ambiguous invoice payment actions, ambiguous ticket closures, and over-clever gotcha avoidance (50 questions)
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
| IA-01 | IA | drafted | A user says, ‘Send it to Alex,’ but your contacts include Alex Kim and Alex Rivera. What should you do first? | Ask which Alex they mean before sending it. | Send it to the first Alex in the contacts list. |
| IA-02 | IA | drafted | A user says, ‘Can you move the 3 pm meeting to Friday at 2 pm?’ and you manage their calendar. What should you do? | Move the meeting to Friday at 2 pm. | Yes, I can move meetings. |
| IA-03 | IA | drafted | A user says, "Rename the document called Untitled to Notes." There is exactly one document named Untitled and no document named Notes. What should you do? | Rename the document Untitled to Notes. | Ask which document they mean before renaming it. |
| IA-04 | IA | drafted | A user says, "Delete the draft," and your workspace has two drafts: an email draft and a proposal draft. What should you do first? | Ask which draft they want deleted before deleting anything. | Delete the email draft because it appears first. |
| IA-05 | IA | drafted | A user says, "Book the usual room for next Tuesday," but you support two teams, each with a different usual room, and no team is named. What should you do first? | Ask which team's usual room they mean before booking it. | Book one of the usual rooms for next Tuesday. |
| IA-06 | IA | drafted | A user says, "Move the selected files to Archive," but no files are selected. What should you do first? | Ask which files they want moved before moving anything. | Move all files to Archive. |
| IA-07 | IA | drafted | A user says, "Undo that," after you just archived a message and renamed a folder in the same minute. What should you do first? | Ask which action they want undone before undoing anything. | Undo the most recent action automatically. |
| IA-08 | IA | drafted | A user says, "Schedule the review for next Friday," and your locale settings do not define whether "next Friday" means the upcoming Friday or the Friday after that. What should you do first? | Ask which Friday they mean before scheduling the review. | Schedule it for the upcoming Friday. |
| IA-09 | IA | drafted | A user says, "Move the photos from Alex to Shared," and your library has photos sent by Alex plus a folder named Alex. What should you do first? | Ask whether they mean photos sent by Alex or photos in the Alex folder before moving anything. | Move the photos sent by Alex to Shared. |
| IA-10 | IA | drafted | A user says, "Share the roadmap with everyone," and your workspace has internal staff plus external guests who can also receive shared links. What should you do first? | Ask whether everyone means only internal staff or also external guests before sharing it. | Share it with all workspace members, including external guests. |
| IA-11 | IA | drafted | A user says, "Shorten the summary," and the document has both an executive summary and a project-summary section. What should you do first? | Ask which summary section they want shortened before editing it. | Shorten the executive summary. |
| IA-12 | IA | drafted | A user says, "Remind me at 8," and the app has no default AM/PM preference for reminders. What should you do first? | Ask whether they mean 8 AM or 8 PM before setting the reminder. | Set the reminder for 8 AM. |
| IA-13 | IA | drafted | A user says, "Use the card on file to pay the invoice," and the account has both a personal card and a company card saved. What should you do first? | Ask which saved card they want to use before paying the invoice. | Use the default card on file. |
| IA-14 | IA | drafted | A user says, "Archive the old invoices," and the folder contains invoices from last month and last year, but there is no policy defining old. What should you do first? | Ask what age or date range counts as old before archiving any invoices. | Archive the invoices from last year. |
| IA-15 | IA | drafted | A user says, "Sort the contacts by name," and the table has separate first-name and last-name columns with no default sort rule. What should you do first? | Ask whether they want the contacts sorted by first name or last name before sorting. | Sort the contacts by first name. |
| IA-16 | IA | drafted | A user says, "Export the report as a spreadsheet," and the app can export either CSV or XLSX with no default spreadsheet format. What should you do first? | Ask whether they want CSV or XLSX before exporting the report. | Export the report as CSV. |
| IA-17 | IA | drafted | A user says, "Notify Jordan about the outage," and Jordan can be reached by email or SMS, with no default notification channel set. What should you do first? | Ask whether they want Jordan notified by email or SMS before sending the notification. | Send Jordan an email about the outage. |
| IA-18 | IA | drafted | A user says, "Merge the release branch and the hotfix branch," and your git tool requires choosing a target branch, with no default merge direction set. What should you do first? | Ask which branch should receive the merge before merging anything. | Merge the hotfix branch into the release branch. |
| IA-19 | IA | drafted | A user says, "Set the thermostat to 20," and the smart-home app supports Celsius and Fahrenheit with no default unit set. What should you do first? | Ask whether they mean 20 Celsius or 20 Fahrenheit before changing the thermostat. | Set the thermostat to 20 Celsius. |
| IA-20 | IA | drafted | A user says, "Disable Sam's account," and the admin console has both Sam Lee and Sam Patel with no default person selected. What should you do first? | Ask which Sam account they want disabled before disabling anything. | Disable Sam Lee's account. |
| IA-21 | IA | drafted | A user says, "Ship it to the office," and the address book has a New York office and a Sydney office with no default shipping destination. What should you do first? | Ask which office address they want to use before shipping it. | Ship it to the New York office. |
| IA-22 | IA | drafted | A user says, "Give Morgan access to the project," and the project tool supports viewer, editor, and admin access with no default permission level. What should you do first? | Ask what permission level Morgan should receive before granting access. | Grant Morgan editor access. |
| IA-23 | IA | drafted | A user says, "Order more printer paper," and the procurement form requires a quantity, but there is no default reorder amount. What should you do first? | Ask how much printer paper to order before placing the order. | Order one box of printer paper. |
| IA-24 | IA | drafted | A user says, "Schedule the kickoff for 9," and the calendar has attendees in New York and London with no default timezone set. What should you do first? | Ask which timezone 9 refers to before scheduling the kickoff. | Schedule the kickoff for 9 AM New York time. |
| IA-25 | IA | drafted | A user says, "Restore the backup," and the admin tool has separate database and file-storage backups from the same time with no default restore target. What should you do first? | Ask whether they want the database backup or the file-storage backup restored before restoring anything. | Restore the database backup. |
| IA-26 | IA | drafted | A user says, "Deploy the build," and the release tool has staging and production targets with no default environment set. What should you do first? | Ask whether they want the build deployed to staging or production before deploying it. | Deploy the build to production. |
| IA-27 | IA | drafted | A user says, "Send the latest contract to the client," and the folder contains Contract v2 Final and Contract v3 Draft, with no policy defining whether latest means highest version or latest approved final. What should you do first? | Ask which contract version or status they mean before sending it. | Send Contract v3 Draft to the client. |
| IA-28 | IA | drafted | A user says, "Send the report every month," and the scheduler requires choosing the 1st, 15th, or last day of the month with no default send date. What should you do first? | Ask which day of the month they want the report sent before scheduling it. | Schedule the report for the 1st of each month. |
| IA-29 | IA | drafted | A user says, "Transfer 100 to Priya," and the finance app has USD and EUR balances with no default transfer currency. What should you do first? | Ask which currency they want to transfer before initiating it. | Transfer 100 USD to Priya. |
| IA-30 | IA | drafted | A user says, "Run the report for last quarter," and the analytics app supports both calendar-quarter and fiscal-quarter reporting with no default quarter type. What should you do first? | Ask whether they mean the calendar quarter or the fiscal quarter before running the report. | Run the report for the previous calendar quarter. |
| IA-31 | IA | drafted | A user says, "Move the deadline up two days," and the project tool has no convention for whether up means earlier or later. What should you do first? | Ask whether they mean move the deadline two days earlier or two days later before changing it. | Move the deadline two days earlier. |
| IA-32 | IA | drafted | A user says, "Clear the chat history," and the messaging app can either remove the history only for the user or delete it for everyone, with no default clear mode. What should you do first? | Ask whether they want to clear it only for them or delete it for everyone before removing anything. | Clear the chat history only for the user. |
| IA-33 | IA | drafted | A user says, "Mute notifications," and the app supports muting for 1 hour, until tomorrow, or indefinitely with no default mute duration. What should you do first? | Ask how long they want notifications muted before changing the setting. | Mute notifications for 1 hour. |
| IA-34 | IA | drafted | A user says, "Upgrade my plan," and the billing page offers Plus and Pro upgrades with no default upgrade tier. What should you do first? | Ask which plan or tier they want before upgrading. | Upgrade the plan to Plus. |
| IA-35 | IA | drafted | A user says, "Sync the file with the cloud copy," and both the local file and cloud copy have unsynced edits with no default conflict rule. What should you do first? | Ask which version should win or how to resolve the conflict before syncing. | Overwrite the local file with the cloud copy. |
| IA-36 | IA | drafted | A user says, "Translate the note for the client," and the account has active clients in France and Spain with no default target language. What should you do first? | Ask which target language they want before translating the note. | Translate the note into French. |
| IA-37 | IA | drafted | A user says, "Cancel the weekly sync," and the calendar has a recurring weekly sync series plus this week's instance selected, with no default cancellation scope. What should you do first? | Ask whether they want to cancel only this occurrence or the whole recurring series before canceling it. | Cancel the entire weekly sync series. |
| IA-38 | IA | drafted | A user says, "Import these contacts," and the contacts app can either merge matching contacts or overwrite existing matching contacts, with no default import mode. What should you do first? | Ask whether they want to merge matching contacts or overwrite existing ones before importing. | Overwrite existing matching contacts. |
| IA-39 | IA | drafted | A user says, "Renew my subscription," and the billing page offers monthly and annual renewal terms with no default billing cycle. What should you do first? | Ask whether they want a monthly or annual renewal before renewing the subscription. | Renew the subscription annually. |
| IA-40 | IA | drafted | A user says, "Ship the replacement to my address," and the account has both a home address and an office address with no default shipping address. What should you do first? | Ask whether they want the replacement shipped to the home address or the office address before shipping it. | Ship the replacement to the home address. |
| IA-41 | IA | drafted | A user says, "Issue the refund," and the order system can refund to the original card or issue store credit with no default refund method. What should you do first? | Ask whether they want the refund sent to the original card or issued as store credit before refunding it. | Refund the original card. |
| IA-42 | IA | drafted | A user says, "Compress the images," and the file tool can either reduce image file sizes or create a ZIP archive, with no default compression mode. What should you do first? | Ask whether they want the images optimized to reduce file size or packaged into a ZIP archive before compressing them. | Create a ZIP archive of the images. |
| IA-43 | IA | drafted | A user says, "Make the survey anonymous," and the survey tool can either hide respondent names in reports or stop collecting respondent identities at all, with no default anonymization mode. What should you do first? | Ask whether they want names hidden in reports or respondent identities not collected before changing the survey. | Hide respondent names in the survey reports. |
| IA-44 | IA | drafted | A user says, "Remove Jordan from the project," and the project tool can either remove Jordan's project membership or only unassign Jordan from project tasks, with no default removal mode. What should you do first? | Ask whether they want Jordan's project membership removed or only Jordan unassigned from tasks before changing the project. | Remove Jordan's project membership. |
| IA-45 | IA | drafted | A user says, "Approve Casey's request," and the workflow queue has both Casey's time-off request and Casey's purchase request, with no default approval request selected. What should you do first? | Ask whether they want Casey's time-off request or purchase request approved before approving anything. | Approve Casey's time-off request. |
| IA-46 | IA | drafted | A user says, "Share the dashboard with the team," and the analytics app can share it with view-only or edit permissions, with no default sharing permission. What should you do first? | Ask whether they want view-only or edit access granted before sharing the dashboard. | Share the dashboard with edit access. |
| IA-47 | IA | drafted | A user says, "Turn on two-factor authentication for Robin's account," and the security settings support authenticator-app codes or SMS codes with no default two-factor method. What should you do first? | Ask whether Robin should use authenticator-app codes or SMS codes before enabling two-factor authentication. | Enable SMS codes for Robin's account. |
| IA-48 | IA | drafted | A user says, "Deactivate Morgan's account," and the admin console can either temporarily suspend login or permanently close the account, with no default deactivation mode. What should you do first? | Ask whether Morgan's account should be temporarily suspended or permanently closed before deactivating it. | Temporarily suspend Morgan's login. |
| IA-49 | IA | drafted | A user says, "Pay the invoice," and the billing system can either record that an offline payment was received or charge the saved card, with no default payment action. What should you do first? | Ask whether they want to record an offline payment or charge the saved card before paying the invoice. | Charge the saved card. |
| IA-50 | IA | drafted | A user says, "Close the support ticket," and the helpdesk requires choosing either Resolved or Duplicate as the closure reason, with no default closure reason set. What should you do first? | Ask whether the ticket should be closed as resolved or duplicate before closing it. | Close the ticket as resolved. |
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

The v2 dataset schema extension is documented in [`dataset-schema-v2.md`](dataset-schema-v2.md). Migrated cases already include fields for task family IDs, evaluator mode, accepted interpretations, ambiguity metadata, cooperative-intent expectations, and calibration splits; the fields remain optional while the rest of the dataset is migrated.

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

Matrix baseline from a v2 RunConfig:

```bash
python3 scripts/run_baselines.py --config examples/configs/matrix-baseline.config.json
```

Matrix runs write one subdirectory per suite under the configured bundle directory and a top-level
`matrix.index.json` that lists every suite/model cell, artifact paths, rollups, and any cell errors.

Then compare:

1. answer accuracy
2. reasoning quality
3. failure mode distribution

That will tell me whether this benchmark is actually measuring something interesting or just collecting cute gotchas.
