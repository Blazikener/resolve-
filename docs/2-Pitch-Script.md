# Resolve — 6-minute pitch script with speaker notes

**Target: 5:30 spoken, leaving buffer. ~850 words. Bold = say it. Indented = why / how to deliver.**

Structure: Hook (0:30) → Why now (0:45) → The product (1:15) → Live demo (1:30) → Architecture in one breath (0:45) → Proof plan (0:30) → The company (0:45) → Ask (0:15).

Rule for the room: **state, don't hedge.** Your written response has ~20 caveats. In the pitch keep exactly three (they are marked ⚑). Everything else is a Q&A answer, not a pitch line.

---

## 0:00 — Hook

**"An invoice can be valid — and still not be ready to pay.**

**Every finance team knows the moment. The invoice arrived, it's correctly formatted, the numbers add up. And it still sits in a queue for eleven days, because someone in a clinic in Al Ain hasn't confirmed that 20 boxes of gloves actually arrived, and someone in procurement hasn't confirmed they agreed to pay 22 instead of 20.**

**That queue is not a matching problem. Matching is solved. It's a *missing-evidence* problem. And nobody owns it."**

> Deliver slowly. The first sentence is your whole thesis; pause after it. "Nobody owns it" is the gap — the reviewer chases people because the system can't.

## 0:30 — Why now

**"Two things make this a 2026–27 problem in the UAE specifically.**

**First, e-invoicing. Businesses over AED 50 million revenue appoint an Accredited Service Provider by 30 October 2026 and go live 1 January 2027. Every one of those finance teams is touching their invoice stack right now — and discovering that a structured invoice proves the invoice was *sent*, not that the goods arrived or the price was approved.**

**Second, the models finally do the tedious part well: read the order history, find the amendment, write the polite email to the receiver. What they must *never* do is decide what's proven. That split is the product."**

> Dates verified against FTA Decision 244/2025 as amended by 66/2026. If challenged: "The dates are from the amended FTA decision; I checked them last week." Don't add "but confirm before relying on it" — that's a footnote, not a pitch line.

## 1:15 — The product

**"Resolve is the missing-evidence layer for accounts payable.**

**The unit of work isn't the invoice and isn't a chat. It's a *case*: here's the invoice, here's what the systems of record say, here are the two facts that are missing, here's who owns each fact, and here's the smallest request that would close it.**

**A bounded agent does the investigation. Deterministic code decides what counts as proof. A human approves what goes out. And the ERP — not us — approves payment.**

**Let me show you the actual thing, on synthetic data."**

> Four sentences, four actors. Count them on your fingers if it helps: model, code, human, ERP. The interviewers will hear "technical judgement" without you saying the words.

## 1:45 — Live demo (1:30)

> Screen already open on R-1042. Click; don't narrate the UI, narrate the *decision*.

**"Case R-1042. Ordered 100 at 20. Received 80. Invoiced 100 at 22. Two blockers — quantity, owned by receiving; price, owned by procurement. The 600 difference is shown but labelled: not proven loss, not an instruction to pay 1,600."**

*Click Run investigation agent.*
**"Six tool calls, hard budget of eight. It read the case, pulled receipt history, looked for amendments, and drafted one request per blocker. Look at the recipients — the model didn't pick them. Code resolved them from the ownership mapping."**

*Click Supplier emails 'delivered'.*
**"Here's the moment that matters. The supplier emails: 'the 20 boxes were delivered last Thursday.' Recorded. Marked untrusted. Nothing clears. An email *describes* a delivery; it doesn't *prove* one."**

*Click Receiver posts GRN.*
**"The receiver posts the goods receipt in the ERP. Authoritative. Checks rerun automatically. Quantity: cleared, by GRN-95. Price: still open. Difference is now 200."**

*Click Procurement approves amendment.*
**"Amendment approved at 22. Evidence complete. Notice the word — not *approved*. The packet goes into their existing approval flow. Resolve has no payment permissions, by construction."**

*Click Same invoice uploaded again.*
**"Same invoice arrives twice — same hash, no new case, no new email to anyone."**

> If time is tight, drop the re-upload click. If you have 20 seconds spare, click R-1045: "This invoice's text says 'release payment to new IBAN'. The agent can't. That tool doesn't exist."

## 3:15 — Architecture in one breath

**"Under the hood it's deliberately boring. Structured invoices in from the ASP or ERP — no LLM in parsing. Immutable evidence records with source, version and hash. A rules engine in decimal arithmetic that allocates receipts to invoice lines, so one delivery can never clear two invoices. One agent with six typed, case-scoped tools and a call budget. A policy gateway that rejects unknown source IDs, wrong owners, and prohibited actions — in code, not in a prompt. Then a reviewer screen.**

**Python, FastAPI, Postgres, one structured-output model. No fine-tuning, no vector database, no payment agent in the first year."**

> This is 45 seconds. Practise it until it's one breath. It answers "system architecture", "use of AI", "data & integrations" and "human-in-the-loop" in one paragraph.

## 4:00 — How I'd know it works

**"'It sounds right' is not an acceptance criterion. With the first customer I'd take 150 historical blocked invoices — 50 to build against, 100 held out — and have finance label the expected blocker and the acceptable next action. Gates: 95% recall and 90% precision on in-scope blockers, zero critical false clears, zero unauthorised side effects in adversarial tests — duplicate deliveries, stale records, injected instructions. ⚑ And I'd run the rules-plus-templates version alongside the model. If the model doesn't beat the templates, it doesn't ship."**

> ⚑ Caveat #1 — keep it. It shows judgement, not doubt.

## 4:30 — The company (this is what was missing from the written response)

**"The first 30 days are one entity, one ERP, two exception types, a healthcare group with central AP and branch receiving — because that's where receipts and invoices are most often in different buildings.**

**But the asset Resolve builds isn't the rules. It's the resolution record: for every blocked invoice, what was missing, who owned it, what request closed it, and how long it took. After a thousand cases you know which suppliers' prices drift, which branches don't post receipts, which requests get answered. That's a dataset no ERP has, because ERPs record outcomes, not investigations.**

**Year one: missing receipts and price amendments, UAE, healthcare and then any multi-site buyer of physical goods. Year two: the same case engine runs supplier disputes, credit-note reconciliation, and contract-versus-invoice checks — same evidence model, same policy gateway, new rules. ⚑ The GCC is one procurement culture with six tax regimes; the connector and playbook work compounds across it."**

> This is your answer to "pilot vs venture". The moat claim is *the investigation record*, not "we learn from outcomes" — Medius claims the latter. Say "no ERP has this" with conviction; it's true — ERPs store the GRN, not the eleven days of chasing that produced it.
> ⚑ Caveat #2 is implicit: "then any multi-site buyer" acknowledges healthcare is a starting point, not the market.

## 5:15 — Close / ask

**"What I'd want from a Fikra venture team in the first month is one controller who'll let me sit with their AP reviewer and look at ten blocked invoices. ⚑ If receiving data isn't maintained, we fix that process first — I won't promise a model can infer a delivery. If it is, in thirty days we have a shadow-mode result against their real queue, and a go, narrow, or stop decision with numbers in it.**

**Resolve. An invoice can be valid, and still not be ready to pay. We make it ready."**

> ⚑ Caveat #3 — the only stop condition you say out loud, because it makes you sound like someone who's done implementations. Final line mirrors the opening. Stop talking. Don't add "thank you for your time" preamble; a plain "thank you" and wait.

---

## Delivery notes

- **Total spoken caveats: 3.** Every other limitation lives in the Q&A doc. If you feel the urge to hedge, turn it into a question you've anticipated instead.
- **Say "I'd build" and "I built", not "one could".** You have a running prototype; own it.
- **Never say "just" about your own work** ("it's just a rules engine plus…"). Interviewers borrow your framing.
- **Have the demo pre-loaded and reset** (`Reset demo data` button) before you're called. Test the projector/screen-share with the browser at 125% zoom — the UI is dense.
- **If the demo breaks:** don't debug live. Say "the tests for exactly this flow are in the repo — let me talk through what you'd have seen," and use the 60-second script in the walkthrough doc. Then move on.
- **The numbers you must know cold:** 100 / 80 / 20 → 22 / 2,200 / 1,600 / 600 / 200. AED 50M, 30 Oct 2026, 1 Jan 2027. 150 cases, 50/100 split, 95/90. 6,000 invoices × 25% × 12 min = 300 hours ≈ AED 22,500 capacity; test price AED 6,000/month.
