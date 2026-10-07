# Resolve — 6-minute pitch script with speaker notes

**Target: 5:30 spoken, leaving buffer. ~850 words. Bold = say it. Indented = why / how to deliver.**

Structure: Hook (0:30) → Why now (0:45) → The product (1:15) → Live demo (1:30) → Architecture in one breath (0:45) → Proof plan (0:30) → The company (0:45) → Ask (0:15).

Rule for the room: **state, don't hedge.** Your written response has ~20 caveats. In the pitch keep exactly three (they are marked ⚑). Everything else is a Q&A answer, not a pitch line.

---

## 0:00 — Hook

**"An invoice can be valid — and still not be ready to pay.**

**In the UAE, about two in five B2B invoices are settled late. Cash is the biggest reason, but two of the top four are internal approval delays and goods not as agreed. Those aren't cash problems. They're invoices nobody can *prove* are right: 20 boxes of gloves a clinic in Al Ain never confirmed, a price of 22 that procurement never approved.**

**Matching is solved. Missing evidence isn't. And nobody owns it."**

> Deliver slowly. The first sentence is your whole thesis; pause after it. The Atradius figure is UAE-specific; the founders will notice you didn't open with a US benchmark.

## 0:30 — Why now

**"Two things make this a 2026–27 problem, and a UAE one.**

**First, the category is proven. In July, Freehand raised a 75-million-dollar seed for AI agents that decide whether to pay, dispute or negotiate invoices — at Meta, Unilever, Pfizer. Their bet is 'AI takes responsibility'. Mine is the opposite: the AI does the proving, the controller keeps the authority. That's the version a Gulf CFO signs.**

**Second, e-invoicing. Businesses over AED 50 million appoint an ASP by 30 October and go live on 1 January 2027. And under PINT AE, a partial dispute can only end one way: a credit note with a mandatory reason code. So the end of an exception is no longer an email thread. It's a structured document. Resolve produces it."**

> Name Freehand yourself before they do. It turns the toughest competition question into your positioning.

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

*Switch to R-1054. Click Draft credit-note request.*
**"Now the case where procurement says no. Resolve doesn't stop at a refusal. It computes the credit-note request: 10 units billed and never received, 480; the price above the PO on the 50 that did arrive, 150; total 630, reason code proposed, tax confirms. Code computed it. AP approves it. The supplier's credit note comes back through their ASP, Resolve checks it against the request, and both blockers clear. Nobody paid anything."**

> If time is tight, drop the re-upload click. If you have 20 seconds spare, click R-1045: "This invoice's text says 'release payment to new IBAN'. The agent can't. That tool doesn't exist."

## 3:15 — Architecture in one breath

**"Under the hood it's deliberately boring. Structured invoices in from the ASP or ERP — no LLM in parsing. Immutable evidence records with source, version and hash. A rules engine in decimal arithmetic that allocates receipts to invoice lines, so one delivery can never clear two invoices. One agent with six typed, case-scoped tools and a call budget. A policy gateway that rejects unknown source IDs, wrong owners, and prohibited actions — in code, not in a prompt. Then a reviewer screen.**

**Python, FastAPI, Postgres, one structured-output model. No fine-tuning, no vector database, no payment agent in the first year.**

**Your own essay puts it best: deterministic software is constrained by construction; an agent is constrained by declaration. Resolve keeps money on the construction side."**

> This is 45 seconds. Practise it until it's one breath. It answers "system architecture", "use of AI", "data & integrations" and "human-in-the-loop" in one paragraph.

## 4:00 — How I'd know it works

**"'It sounds right' is not an acceptance criterion. With the first customer I'd take 150 historical blocked invoices — 50 to build against, 100 held out — and have finance label the expected blocker and the acceptable next action. Gates: 95% recall and 90% precision on in-scope blockers, zero critical false clears, zero unauthorised side effects in adversarial tests — duplicate deliveries, stale records, injected instructions. ⚑ And I'd run the rules-plus-templates version alongside the model. If the model doesn't beat the templates, it doesn't ship."**

> ⚑ Caveat #1 — keep it. It shows judgement, not doubt.

## 4:30 — The company

**"The first customer is a multi-site UAE buyer over AED 50 million — a hospital group, a retail chain, a distributor — with central AP and receiving at the branches, because that's where the receipt and the invoice are in different buildings.**

**Zero to six months: two blockers, missing receipts and price changes. Six to eighteen months: the dispute rail — PINT AE credit notes, resold by the ASPs, who sell compliance but not resolution; then rule packs for freight and construction claims. Eighteen to thirty-six: both sides of the invoice on one case record, then KSA and the rest of the GCC.**

**What compounds is the resolution record: for every blocked invoice, what was missing, who owned it, what closed it, how long it took. No ERP has that, because ERPs record outcomes, not investigations. It's the same idea as Prism56 — every claim checked against evidence, judgment stays with the human — pointed at cash going out instead of capital going in."**

> This is your answer to "pilot vs venture". ⚑ Caveat #2 is implicit: "a hospital group, a retail chain, a distributor" says the first vertical is a choice, not the market. If they ask about Track 2: the 2026 amendment to MD 64/2025 lets a local company deliver e-invoicing with an international partner — a global AP-agent player entering the GCC needs exactly that.

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
- **The numbers you must know cold:** 100 / 80 / 20 → 22 / 2,200 / 1,600 / 600 / 200. AED 50M, 30 Oct 2026, 1 Jan 2027. 150 cases, 50/100 split, 95/90. 6,000 invoices × 18.4% × 12 min ≈ 220 hours ≈ AED 16,500 capacity a month; test price AED 6,000/month. R-1054: 10 × 48 = 480 + 50 × 3 = 150 → AED 630, DL8.61.1.C. Freehand $75M, Jul 2026. ~2 in 5 UAE invoices late (Atradius 2026); 18.4% exception rate, $9.84/invoice (Ardent 2026).
