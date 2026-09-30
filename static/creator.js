"use strict";

const root = document.querySelector("#root");
const dialog = document.querySelector("#dialog");
let state = null;
let tab = "overview";
let filter = "all";
let query = "";
let toastTimer;
const titles = {
  overview: "Your next chapter.",
  licenses: "Your content licenses.",
  renewals: "From offer to paid.",
  activity: "Your paper trail.",
  plan: "A little less admin.",
};
const money = (cents) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(cents / 100);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const dateLabel = (value) =>
  value
    ? new Date(`${value}T12:00:00Z`).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      })
    : "—";
const daysLeft = (value) =>
  Math.round(
    (Date.parse(`${value}T00:00:00Z`) -
      Date.parse(`${state.today}T00:00:00Z`)) /
      86400000,
  );
const paid = (id) =>
  state.payments
    .filter((p) => p.renewal_id === id && !p.reversed)
    .reduce((total, p) => total + p.amount_cents, 0);
const balance = (r) => (r.status === "accepted" ? r.fee_cents - paid(r.id) : 0);
const button = (text, action, id = "", style = "") =>
  `<button class="btn ${style}" data-action="${action}" data-id="${esc(id)}">${text}</button>`;
const logo = () =>
  '<a href="/" class="logo" aria-label="Resolve home"><span class="logo-mark" aria-hidden="true">r</span>resolve<small>FOR CREATORS</small></a>';

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": state?.csrf || "",
      ...options.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && state) {
      state = null;
      dialog.close();
      renderLanding();
    }
    const detail = Array.isArray(data.detail)
      ? data.detail.map((e) => e.msg).join(". ")
      : data.detail;
    throw new Error(
      detail || `Request failed (${response.status}). Please try again.`,
    );
  }
  return data;
}
const post = (path, body) =>
  api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

function toast(message) {
  const node = document.querySelector("#toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("visible"), 5000);
}

function modal(title, subtitle, content) {
  dialog.innerHTML = `<div class="dialog-head"><div><h2 id="dialog-title">${esc(title)}</h2><p>${esc(subtitle)}</p></div><button class="close" data-action="close" aria-label="Close dialog">×</button></div><div class="dialog-body">${content}</div>`;
  if (!dialog.open) dialog.showModal();
}

function field(label, name, value = "", type = "text", extra = "") {
  return `<label class="field">${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
}

function renderLanding() {
  document.title = "Resolve — Your content. Its next chapter.";
  root.innerHTML = `<div class="landing">
    <header class="public-nav">${logo()}<nav class="nav-links" aria-label="Main navigation"><a href="#how">How it works</a><a href="#pricing">Pricing</a>${button("Log in", "login", "", "text")}${button("Start free ↗", "signup", "", "primary")}</nav></header>
    <main id="main"><section class="hero"><div><span class="eyebrow">THE BUSINESS AFTER THE CONTENT</span><h1>You made it.<br>Give it a<br><em>next chapter.</em></h1><p class="hero-copy">Your content can keep working. Keep track of expiring usage rights, start the renewal conversation, and follow every offer through to payment.</p><div class="actions">${button("Open your workspace ↗", "signup", "", "primary")}${button("Explore a demo", "demo")}</div><p class="small muted">3 active licenses, free. No card needed.</p></div>
    <div class="hero-visual" aria-label="Illustration of a fictional renewal offer"><div class="orbit-label">Good work deserves a follow-up.</div><div class="preview-card"><div class="topline"><span class="brand-icon">f.</span><span class="pill amber">Renewal coming up</span></div><h3>Morning routine</h3><p>Forma · 3 UGC videos · Meta paid ads</p><div class="preview-amount"><span>A new 30-day usage window</span><strong>$450</strong></div><div class="notice">Prepare an offer → Confirm approval → Track payment</div></div><div class="float-note">A conversation worth starting.<br><strong>Your next opportunity is in work you already made.</strong></div><p class="small muted">Illustrative example · not customer revenue</p></div></section>
    <section id="how"><div class="section-heading"><div><p class="eyebrow muted">A SMALLER TO-DO LIST</p><h2>Close the loop on your content.</h2></div></div><div class="feature-grid"><article><span class="step-no">01 /</span><h3>Keep the terms together.</h3><p>Record the brand, asset, agreed usage window, and evidence links. Know which licenses need a conversation.</p></article><article><span class="step-no">02 /</span><h3>Make the next offer.</h3><p>Prepare a renewal with your own fee and dates. Review the draft, then send it from your email.</p></article><article><span class="step-no">03 /</span><h3>Follow the money.</h3><p>Record written approval, track partial payments, and export the history. Proposed fees stay separate from money owed.</p></article></div></section>
    <section id="pricing" class="price-section"><div><p class="eyebrow">BUILT FOR INDEPENDENT CREATORS</p><h2>A focused workspace.<br>A straightforward price.</h2><p>Start with 3 active licenses for free. Pro is the proposed paid pilot for creators managing a growing library of licensed content.</p><p class="small">USD only during the pilot. No automated ad monitoring or email sending.</p></div><div><div class="price-number">$19<span> / month · proposed Pro plan</span></div><p>More active licenses · renewal drafts<br>Payment history · evidence exports</p>${button("Try the free workspace ↗", "signup")}</div></section></main>
    <footer class="footer"><span>Resolve · A little more space to create.</span><span>Pilot software. Usage terms and payments are creator-reported.</span></footer></div>`;
}

function authModal(mode) {
  const signup = mode === "signup";
  modal(
    signup ? "Make room for what’s next." : "Welcome back.",
    signup
      ? "Create your free Resolve workspace."
      : "Sign in to your creator workspace.",
    `<form data-form="${mode}">${signup ? field("Your name", "name", "", "text", 'required maxlength="80" autocomplete="name"') : ""}${field("Email address", "email", "", "email", 'required maxlength="254" autocomplete="email"')}${field("Password", "password", "", "password", `required minlength="10" maxlength="128" autocomplete="${signup ? "new-password" : "current-password"}"`)}<p class="form-note">${signup ? "Use at least 10 characters. This pilot does not yet offer self-service password recovery. Keep your password in a password manager." : "Password recovery is not yet available in this pilot."}</p><p class="form-error" role="alert"></p><button class="btn primary" type="submit">${signup ? "Create workspace ↗" : "Sign in ↗"}</button><div class="auth-alt">${signup ? "Already have an account?" : "New to Resolve?"} <button type="button" data-action="${signup ? "login" : "signup"}">${signup ? "Log in" : "Start free"}</button></div></form>`,
  );
}

function licenseStatus(item) {
  if (item.archived) return '<span class="pill">Archived</span>';
  const days = daysLeft(item.expires_on);
  if (days < 0) return '<span class="pill red">Term ended</span>';
  if (days <= 30)
    return `<span class="pill amber">${days === 0 ? "Ends today" : `${days} days left`}</span>`;
  return '<span class="pill green">Active</span>';
}

function renewalStatus(r) {
  if (r.status === "draft") return '<span class="pill blue">Offer draft</span>';
  if (r.status === "declined") return '<span class="pill">Closed</span>';
  if (!balance(r)) return '<span class="pill green">Recorded paid</span>';
  if (daysLeft(r.due_on) < 0)
    return '<span class="pill red">Payment overdue</span>';
  return `<span class="pill amber">${paid(r.id) ? "Part paid" : "Awaiting payment"}</span>`;
}

function brandCell(item, i = 0, kind = "license") {
  return `<div class="brand-cell"><span class="brand-icon tone${i % 4}">${esc(item.brand.slice(0, 1).toLowerCase())}.</span><button class="row-btn" data-action="${kind}" data-id="${esc(item.id)}"><strong>${esc(item.brand)}</strong><p>${esc(item.title)}</p></button></div>`;
}

function stats() {
  const active = state.licenses.filter((l) => !l.archived);
  const opportunities = active.filter((l) => daysLeft(l.expires_on) <= 30);
  const open = state.renewals.reduce((sum, r) => sum + balance(r), 0);
  const received = state.payments
    .filter((p) => !p.reversed)
    .reduce((sum, p) => sum + p.amount_cents, 0);
  return `<div class="stats"><article class="stat featured"><div class="stat-label">Renewals to consider <span>↗</span></div><div class="stat-value">${money(opportunities.reduce((sum, l) => sum + l.renewal_fee_cents, 0))}</div><div class="stat-foot">${opportunities.length} license${opportunities.length === 1 ? "" : "s"} · proposed fees, not earned</div></article><article class="stat"><div class="stat-label">Awaiting payment <span>◷</span></div><div class="stat-value">${money(open)}</div><div class="stat-foot">Confirmed renewals, less recorded payments</div></article><article class="stat"><div class="stat-label">Recorded received <span>↙</span></div><div class="stat-value">${money(received)}</div><div class="stat-foot">Creator-reported · not bank verified</div></article><article class="stat"><div class="stat-label">Licenses tracked <span>▧</span></div><div class="stat-value">${active.length.toString().padStart(2, "0")}</div><div class="stat-foot">${active.filter((l) => daysLeft(l.expires_on) > 30).length} have more than 30 days remaining</div></article></div>`;
}

function queue() {
  const items = state.licenses
    .filter((l) => !l.archived && daysLeft(l.expires_on) <= 30)
    .sort((a, b) => a.expires_on.localeCompare(b.expires_on))
    .slice(0, 3);
  return `<div class="dashboard-grid"><section class="panel"><div class="panel-head"><h2>Your next moves <span class="muted small">/ ${items.length}</span></h2><span class="eyebrow small muted">THIS IS YOUR CUE</span></div>${items.length ? items.map((l, i) => `<div class="queue-item"><span class="brand-icon tone${i}">${esc(l.brand.slice(0, 1).toLowerCase())}.</span><div class="queue-info"><strong>${esc(l.brand)} · ${esc(l.title)}</strong><p>${daysLeft(l.expires_on) < 0 ? "Recorded term ended. Check before proposing new use." : `Usage window ends ${dateLabel(l.expires_on)}.`}</p></div><div class="queue-action">${button("Review ↗", "license", l.id)}</div></div>`).join("") : '<div class="empty"><h3>A clear runway.</h3><p>Add a license to start tracking its next renewal.</p></div>'}</section><aside class="workflow-panel"><p class="eyebrow">GOOD WORK, MORE POSSIBILITIES</p><h2>The next deal might already be on your desk.</h2><div class="flow-step"><span>1</span>Review the agreed usage window</div><div class="flow-step"><span>2</span>Prepare your renewal offer</div><div class="flow-step"><span>3</span>Record approval, then payment</div><div class="flow-note">An expiry is a prompt to check in. It doesn’t prove a brand is still running your content.</div></aside></div>`;
}

function licenseTable() {
  let items = state.licenses.filter((l) =>
    `${l.brand} ${l.title} ${l.scope}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  if (filter === "all") items = items.filter((l) => !l.archived);
  if (filter === "soon")
    items = items.filter(
      (l) =>
        !l.archived &&
        daysLeft(l.expires_on) >= 0 &&
        daysLeft(l.expires_on) <= 30,
    );
  if (filter === "ended")
    items = items.filter((l) => !l.archived && daysLeft(l.expires_on) < 0);
  if (filter === "archived") items = items.filter((l) => l.archived);
  items.sort((a, b) => a.expires_on.localeCompare(b.expires_on));
  return `<section class="panel"><div class="panel-head"><h2>Your content, at a glance</h2><span class="small muted">USD · Your recorded terms</span></div><div class="table-toolbar"><div class="filters" aria-label="License filters">${[
    ["all", "All licenses"],
    ["soon", "Expiring soon"],
    ["ended", "Term ended"],
    ["archived", "Archived"],
  ]
    .map(
      ([id, label]) =>
        `<button class="filter ${filter === id ? "active" : ""}" data-action="filter" data-id="${id}" aria-pressed="${filter === id}">${label}</button>`,
    )
    .join(
      "",
    )}</div><label><span class="sr-only">Search licenses</span><input class="search" id="search" placeholder="Search brands or content…" value="${esc(query)}"></label></div>${items.length ? `<div class="table-wrap"><table><thead><tr><th>Brand / content</th><th>Usage window ends</th><th>Next offer</th><th>Status</th><th><span class="sr-only">Open</span></th></tr></thead><tbody>${items.map((l, i) => `<tr><td>${brandCell(l, i)}</td><td>${dateLabel(l.expires_on)}</td><td>${money(l.renewal_fee_cents)} <span class="small muted">/ ${l.renewal_days}d</span></td><td>${licenseStatus(l)}</td><td><button class="row-arrow" data-action="license" data-id="${l.id}" aria-label="Open ${esc(l.brand)}">↗</button></td></tr>`).join("")}</tbody></table></div>` : `<div class="empty"><div class="empty-symbol">↗</div><h3>${state.licenses.length ? "No licenses match this view." : "Start with something you made."}</h3><p>${state.licenses.length ? "Try another filter or search." : "Add one piece of licensed content, its usage dates, and your next renewal fee."}</p>${state.licenses.length ? "" : button("Add your first license", "new-license", "", "primary")}</div>`}<div class="table-footer">${items.length} license${items.length === 1 ? "" : "s"} · Expiry dates come from the terms you enter.</div></section>`;
}

function renewalTable() {
  return `<section class="panel"><div class="panel-head"><h2>Renewal history</h2><a href="/api/export" class="subtle-link" download>Export CSV ↗</a></div>${state.renewals.length ? `<div class="table-wrap"><table><thead><tr><th>Brand / content</th><th>Fee</th><th>Outstanding</th><th>Status</th><th>Payment due</th></tr></thead><tbody>${state.renewals.map((r, i) => `<tr><td>${brandCell(r, i, "renewal")}</td><td>${money(r.fee_cents)}</td><td>${r.status === "accepted" ? money(balance(r)) : "—"}</td><td>${renewalStatus(r)}</td><td>${dateLabel(r.due_on)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty"><div class="empty-symbol">↗</div><h3>The next conversation starts here.</h3><p>Open a license and prepare a renewal offer. Drafts only become receivables after you record the brand’s approval.</p></div>'}<div class="table-footer">No invoice or message is sent automatically. Payments are recorded manually.</div></section>`;
}

function planPage() {
  return `<section class="price-card"><span class="eyebrow muted">RESOLVE PRO · PAID PILOT</span><h2>Keep your library working.</h2><div class="price-number">$19<span> / month</span></div><p class="muted">Free includes 3 active licenses and the complete renewal workflow. Pro increases the limit to 2,000 active licenses.</p><ul><li>Renewal offers with your fees and usage scope</li><li>Written approval and partial payment records</li><li>CSV and evidence history exports</li><li>No percentage taken from brand payments</li></ul>${state.user.demo ? button("Create a real workspace first", "signup", "", "primary") : state.user.plan === "pro" ? button("Manage subscription ↗", "portal", "", "primary") : state.billing_available ? button("Continue to Stripe ↗", "checkout", "", "primary") : '<div class="notice"><strong>Paid billing is not connected in this environment.</strong><br>Keep using the free workspace. No card details are collected and no subscription is activated.</div>'}${!state.user.demo && state.user.customer_id && state.user.plan !== "pro" ? button("Manage billing", "portal") : ""}<p class="form-note">${state.user.demo ? "Demo workspaces are temporary and cannot purchase a subscription." : "Subscriptions pay for Resolve only. Brand payments stay on your own payment methods."} USD only in this pilot. Automated email, ad monitoring, and password recovery are not included.</p></section>`;
}

function renderApp() {
  document.title = "Workspace · Resolve";
  const name = state.user.name.split(" ")[0];
  const nav = [
    ["overview", "◫", "Overview"],
    ["licenses", "▧", "Content licenses"],
    ["renewals", "↗", "Renewals & payments"],
    ["activity", "◷", "Activity"],
    ["plan", "✧", "Your plan"],
  ];
  root.innerHTML = `<div class="app-shell"><aside class="sidebar">${logo()}<div class="eyebrow">YOUR WORKSPACE</div><nav aria-label="Workspace navigation">${nav.map(([id, icon, label]) => `<button class="nav-btn ${tab === id ? "active" : ""}" data-action="tab" data-id="${id}" ${tab === id ? 'aria-current="page"' : ""}><span class="nav-icon" aria-hidden="true">${icon}</span>${label}</button>`).join("")}</nav><div class="sidebar-bottom"><div class="pilot-note"><b>A little more room to grow.</b><p>Free for 3 active licenses.<br>Your ideas can take it from here.</p><button class="subtle-link" data-action="tab" data-id="plan">Explore Pro ↗</button></div><div class="profile"><span class="avatar">${esc(state.user.name.slice(0, 1))}</span><div><div class="profile-name">${esc(state.user.name)}</div><div class="profile-sub">${state.user.demo ? "Demo workspace" : `${esc(state.user.plan)} workspace`}</div></div><button class="signout" data-action="logout" aria-label="Sign out" title="Sign out">↪</button></div></div></aside><main id="main" class="app-main"><header class="topbar"><span>Workspace <span class="muted">/</span> ${esc(nav.find((n) => n[0] === tab)[2])}</span><div class="actions"><span class="date-label">${dateLabel(state.today)}</span><span class="pill">${state.user.demo ? "DEMO" : "PILOT"} WORKSPACE</span><button class="subtle-link" data-action="logout">Sign out</button></div></header>${state.user.demo ? '<div class="demo-banner"><span>Make yourself at home. These are fictional sample licenses.</span><button data-action="signup">Create your own workspace ↗</button></div>' : ""}<div class="page-head"><div><h1>${titles[tab]}</h1><p>${tab === "overview" ? `Welcome back, ${esc(name)}. Here’s where your content goes next.` : tab === "licenses" ? "The terms, dates, and opportunities behind your work." : tab === "renewals" ? "Keep offers, confirmed renewals, and received payments separate." : tab === "activity" ? "A record of what you changed and when." : "Start free. Upgrade when the workflow earns its place."}</p></div>${["overview", "licenses"].includes(tab) ? button("+ Add license", "new-license", "", "primary") : ""}</div>${["overview", "renewals"].includes(tab) ? stats() : ""}${tab === "overview" ? queue() + licenseTable() : tab === "licenses" ? licenseTable() : tab === "renewals" ? renewalTable() : tab === "plan" ? planPage() : `<section class="panel"><div class="panel-head"><h2>Workspace activity</h2><span class="small muted">Latest 100 events</span></div>${state.activity.length ? state.activity.map((a) => `<div class="history-item"><time>${esc(new Date(a.created_at).toLocaleString())}</time>${esc(a.text)}</div>`).join("") : '<div class="empty"><p>Your activity will appear here.</p></div>'}</section>`}<footer class="bottom-note"><span>Made for the business behind your creativity.</span><span>All amounts in USD · No automatic sending or ad monitoring</span></footer></main></div>`;
}

async function refresh() {
  state = await api("/workspace");
  renderApp();
}

function licenseForm(id = "") {
  const l = state.licenses.find((item) => item.id === id);
  const defaultExpiry = new Date(
    Date.parse(`${state.today}T12:00:00Z`) + 30 * 86400000,
  )
    .toISOString()
    .slice(0, 10);
  modal(
    l ? "Edit license" : "Give your content a home.",
    "Use the terms in your actual agreement. One record per usage scope.",
    `<form data-form="license" data-id="${id}"><div class="field-row">${field("Brand name", "brand", l?.brand, "text", 'required maxlength="100"')}${field("Brand contact email", "contact_email", l?.contact_email, "email", 'required maxlength="254"')}</div>${field("Content / campaign name", "title", l?.title, "text", 'required maxlength="160"')}${field("Licensed usage scope", "scope", l?.scope, "text", 'required maxlength="500" placeholder="e.g. Meta paid ads · US · brand account"')}<div class="field-row">${field("Usage starts", "starts_on", l?.starts_on || state.today, "date", 'required min="2000-01-01" max="2100-12-31"')}${field("Usage ends (inclusive)", "expires_on", l?.expires_on || defaultExpiry, "date", 'required min="2000-01-01" max="2100-12-31"')}</div><div class="field-row">${field("Your proposed renewal fee (USD)", "renewal_fee", l ? (l.renewal_fee_cents / 100).toFixed(2) : "", "number", 'required min="0.01" max="1000000" step="0.01" placeholder="450.00"')}${field("Proposed renewal length (days)", "renewal_days", l?.renewal_days || 30, "number", 'required min="1" max="730" step="1"')}</div>${field("Contract / agreement link (optional)", "contract_url", l?.contract_url, "url", 'maxlength="2000" placeholder="https://…"')}${field("Content / delivery link (optional)", "content_url", l?.content_url, "url", 'maxlength="2000" placeholder="https://…"')}<label class="field">Notes<textarea name="notes" maxlength="3000">${esc(l?.notes || "")}</textarea></label><p class="form-note">Links are saved as references; Resolve does not fetch or verify them. Fees are your proposal, not a market rate recommendation. The pilot supports fixed-term licenses only.</p><p class="form-error" role="alert"></p><div class="actions"><button class="btn primary" type="submit">${l ? "Save changes" : "Add license ↗"}</button>${button("Cancel", "close")}</div></form>`,
  );
}

function licenseDetail(id) {
  const l = state.licenses.find((item) => item.id === id);
  const renewals = state.renewals.filter((r) => r.license_id === id);
  const draft = renewals.find((r) => r.status === "draft");
  modal(
    l.brand,
    l.title,
    `${licenseStatus(l)}<dl class="detail-grid"><div><dt>Recorded usage scope</dt><dd>${esc(l.scope)}</dd></div><div><dt>Current term (inclusive)</dt><dd>${dateLabel(l.starts_on)} – ${dateLabel(l.expires_on)}</dd></div><div><dt>Your proposed renewal</dt><dd>${money(l.renewal_fee_cents)} for ${l.renewal_days} days</dd></div><div><dt>Brand contact</dt><dd>${esc(l.contact_email)}</dd></div><div><dt>Agreement reference</dt><dd>${l.contract_url ? `<a href="${esc(l.contract_url)}" target="_blank" rel="noopener noreferrer">Open agreement ↗</a>` : "Not supplied"}</dd></div><div><dt>Content reference</dt><dd>${l.content_url ? `<a href="${esc(l.content_url)}" target="_blank" rel="noopener noreferrer">Open content ↗</a>` : "Not supplied"}</dd></div></dl>${l.notes ? `<p class="form-note">${esc(l.notes)}</p>` : ""}<div class="notice">A date ending doesn’t establish that a brand is still using the content. Verify the agreement and intended usage before proposing a renewal.</div><div class="actions">${!l.archived ? button(draft ? "Open renewal draft ↗" : "Prepare renewal offer ↗", draft ? "renewal" : "propose", draft?.id || id, "primary") : ""}${button("Edit terms", "edit-license", id)}<a class="btn" href="/api/licenses/${id}/packet" download>Export record</a>${button(l.archived ? "Restore" : "Archive", "archive", id, "text")}</div>${renewals.length ? `<div class="detail-section"><h3>Renewal history</h3>${renewals.map((r) => `<div class="payment-row"><div>${renewalStatus(r)}<small>${dateLabel(r.starts_on)} – ${dateLabel(r.expires_on)} · ${money(r.fee_cents)}</small></div><button data-action="renewal" data-id="${r.id}">Open ↗</button></div>`).join("")}</div>` : ""}`,
  );
}

function renewalDetail(id) {
  const r = state.renewals.find((item) => item.id === id);
  const payments = state.payments.filter((p) => p.renewal_id === id);
  modal(
    r.brand,
    r.title,
    `${renewalStatus(r)}<dl class="detail-grid"><div><dt>Renewal fee</dt><dd>${money(r.fee_cents)}</dd></div><div><dt>Outstanding</dt><dd>${r.status === "accepted" ? money(balance(r)) : "Not a receivable"}</dd></div><div><dt>Renewal dates (inclusive)</dt><dd>${dateLabel(r.starts_on)} – ${dateLabel(r.expires_on)}</dd></div><div><dt>Scope</dt><dd>${esc(r.scope)}</dd></div></dl>${r.status === "draft" ? `<div class="notice">This offer has not been sent or accepted. Review the email draft and send it yourself. Record acceptance only after the brand agrees in writing.</div><div class="actions">${button("Review email draft ↗", "email", id, "primary")}${button("Record brand approval", "accept-form", id)}${button("Close draft", "decline", id, "text")}</div>` : r.status === "accepted" ? `<p class="form-note"><strong>Creator-recorded approval:</strong> ${esc(r.approval_note)}<br>Payment due ${dateLabel(r.due_on)}</p><div class="actions">${balance(r) > 0 ? button("Record payment", "payment-form", id, "primary") + button("Draft payment follow-up", "email", id) : ""}</div>` : '<p class="form-note">This draft was closed. It did not extend the license or create a receivable.</p>'}${payments.length ? `<div class="detail-section"><h3>Payments you recorded</h3>${payments.map((p) => `<div class="payment-row"><div>${money(p.amount_cents)} ${p.reversed ? "· Reversed" : ""}<small>${esc(p.reference)} · ${esc(new Date(p.created_at).toLocaleDateString())}</small></div>${p.reversed ? "" : `<button data-action="reverse" data-id="${p.id}">Reverse entry</button>`}</div>`).join("")}<p class="form-note">Entries are not verified against a bank or payment provider.</p></div>` : ""}<div class="detail-section">${button("Back to license", "license", r.license_id, "text")}</div>`,
  );
}

function acceptanceForm(id) {
  const r = state.renewals.find((item) => item.id === id);
  const due = new Date(Date.parse(`${state.today}T12:00:00Z`) + 30 * 86400000)
    .toISOString()
    .slice(0, 10);
  modal(
    "Record the brand’s approval.",
    `${r.brand} · ${money(r.fee_cents)}`,
    `<form data-form="accept" data-id="${id}"><p class="form-note">You are confirming that the brand approved ${esc(r.scope)} for ${dateLabel(r.starts_on)} through ${dateLabel(r.expires_on)}, at ${money(r.fee_cents)}. This extends the recorded license and creates an outstanding balance.</p><label class="field">Where and when did the brand approve?<textarea name="approval_note" required minlength="5" maxlength="2000" placeholder="e.g. Email from Jamie on Oct 2; agreed to the fee and dates. Include a reference link if available."></textarea></label>${field("Agreed payment due date", "due_on", due, "date", `required min="${state.today}" max="2100-12-31"`)}<p class="form-note">Approval is recorded by you. Resolve has not independently verified it.</p><p class="form-error" role="alert"></p><div class="actions"><button type="submit" class="btn primary">Confirm written approval</button>${button("Back", "renewal", id)}</div></form>`,
  );
}

function paymentForm(id) {
  const r = state.renewals.find((item) => item.id === id);
  modal(
    "Record a received payment.",
    `${r.brand} · ${money(balance(r))} outstanding`,
    `<form data-form="payment" data-id="${id}" data-key="${crypto.randomUUID()}">${field("Amount received (USD)", "amount", (balance(r) / 100).toFixed(2), "number", `required min="0.01" max="${balance(r) / 100}" step="0.01"`)}${field("Payment reference", "reference", "", "text", 'required maxlength="200" placeholder="e.g. Bank transfer Sep 30, invoice R-014"')}<p class="form-note">Record only money you have received. This action does not charge the brand or transfer funds.</p><p class="form-error" role="alert"></p><div class="actions"><button class="btn primary" type="submit">Record received payment</button>${button("Back", "renewal", id)}</div></form>`,
  );
}

async function emailDraft(id) {
  const data = await api(`/renewals/${id}/draft`);
  modal(
    "A good conversation starts here.",
    "Edit and review before sending from your email client.",
    `<form data-form="email" data-id="${id}">${field("To", "to", data.to, "email", "required")}${field("Subject", "subject", data.subject, "text", 'required maxlength="300"')}<label class="field">Message<textarea name="body" rows="12" required>${esc(data.body)}</textarea></label><p class="form-note">Opening your email app or copying this draft does not send it. Resolve cannot track delivery or replies.</p><div class="actions"><button class="btn primary" type="submit">Open email app ↗</button>${button("Copy message", "copy-email")}${button("Back", "renewal", id)}</div><p class="form-error" role="alert"></p></form>`,
  );
}

async function action(name, id) {
  if (name === "close") return dialog.close();
  if (name === "login" || name === "signup") return authModal(name);
  if (name === "demo") {
    await post("/demo");
    await refresh();
    history.replaceState({}, "", "/app");
    return;
  }
  if (name === "logout") {
    await post("/logout");
    state = null;
    dialog.close();
    history.replaceState({}, "", "/");
    renderLanding();
    return;
  }
  if (name === "tab") {
    tab = id;
    filter = "all";
    query = "";
    return renderApp();
  }
  if (name === "filter") {
    filter = id;
    return renderApp();
  }
  if (name === "new-license") return licenseForm();
  if (name === "edit-license") return licenseForm(id);
  if (name === "license") return licenseDetail(id);
  if (name === "renewal") return renewalDetail(id);
  if (name === "accept-form") return acceptanceForm(id);
  if (name === "payment-form") return paymentForm(id);
  if (name === "email") return emailDraft(id);
  if (name === "propose") {
    const r = await post(`/licenses/${id}/propose`);
    await refresh();
    return renewalDetail(r.id);
  }
  if (name === "archive") {
    const l = state.licenses.find((item) => item.id === id);
    const { id: _, ...body } = l;
    await api(`/licenses/${id}`, {
      method: "PUT",
      body: JSON.stringify({ ...body, archived: !l.archived }),
    });
    await refresh();
    licenseDetail(id);
    return;
  }
  if (name === "decline") {
    await post(`/renewals/${id}/decline`);
    await refresh();
    renewalDetail(id);
    return;
  }
  if (name === "reverse") {
    const p = state.payments.find((item) => item.id === id);
    modal(
      "Reverse this payment entry?",
      "This corrects your records. No money moves.",
      `<p>${money(p.amount_cents)} · ${esc(p.reference)}</p><div class="actions">${button("Reverse entry", "confirm-reverse", id, "danger")}${button("Cancel", "renewal", p.renewal_id)}</div>`,
    );
    return;
  }
  if (name === "confirm-reverse") {
    const p = await post(`/payments/${id}/reverse`);
    await refresh();
    renewalDetail(p.renewal_id);
    return;
  }
  if (name === "copy-email") {
    const data = new FormData(dialog.querySelector("form"));
    await navigator.clipboard.writeText(
      `To: ${data.get("to")}\nSubject: ${data.get("subject")}\n\n${data.get("body")}`,
    );
    toast("Draft copied. Nothing has been sent.");
    return;
  }
  if (name === "checkout" || name === "portal") {
    const result = await post(`/billing/${name}`);
    window.location.assign(result.url);
  }
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  event.preventDefault();
  const wasDisabled = target.disabled;
  target.disabled = true;
  try {
    await action(target.dataset.action, target.dataset.id);
  } catch (error) {
    toast(error.message);
  } finally {
    if (target.isConnected) target.disabled = wasDisabled;
  }
});

function cents(value) {
  if (!/^\d+(\.\d{1,2})?$/.test(value))
    throw new Error("Enter a positive amount with at most two decimal places.");
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.dataset.form) return;
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  const id = form.dataset.id;
  const kind = form.dataset.form;
  const submit = form.querySelector('[type="submit"]');
  const errorBox = form.querySelector(".form-error");
  if (submit) submit.disabled = true;
  errorBox.textContent = "";
  try {
    if (kind === "signup" || kind === "login") {
      await post(`/${kind}`, data);
      tab = "overview";
      filter = "all";
      query = "";
      await refresh();
      dialog.close();
      history.replaceState({}, "", "/app");
    } else if (kind === "license") {
      data.renewal_fee_cents = cents(data.renewal_fee);
      delete data.renewal_fee;
      data.renewal_days = Number(data.renewal_days);
      if (id) {
        const old = state.licenses.find((l) => l.id === id);
        data.revision = old.revision;
        data.archived = old.archived;
      }
      const result = await api(id ? `/licenses/${id}` : "/licenses", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(data),
      });
      await refresh();
      licenseDetail(result.id);
      toast(
        id
          ? "License updated."
          : "License added. Your next chapter starts here.",
      );
    } else if (kind === "accept") {
      await post(`/renewals/${id}/accept`, data);
      await refresh();
      renewalDetail(id);
    } else if (kind === "payment") {
      await post(`/renewals/${id}/payments`, {
        amount_cents: cents(data.amount),
        reference: data.reference,
        idempotency_key: form.dataset.key,
      });
      await refresh();
      renewalDetail(id);
    } else if (kind === "email") {
      window.location.href = `mailto:${encodeURIComponent(data.to)}?subject=${encodeURIComponent(data.subject)}&body=${encodeURIComponent(data.body)}`;
      toast(
        "Finish sending in your email app. Resolve does not send messages.",
      );
    }
  } catch (error) {
    if (errorBox.isConnected) errorBox.textContent = error.message;
    else toast(error.message);
  } finally {
    if (submit?.isConnected) submit.disabled = false;
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id !== "search") return;
  const start = event.target.selectionStart;
  query = event.target.value;
  renderApp();
  const input = document.querySelector("#search");
  input.focus();
  input.setSelectionRange(start, start);
});

async function boot() {
  try {
    const response = await fetch("/api/workspace", {
      credentials: "same-origin",
    });
    if (response.status === 401) {
      renderLanding();
      if (location.pathname === "/app") authModal("login");
      return;
    }
    if (!response.ok)
      throw new Error(
        "Unable to open your workspace. Please reload to try again.",
      );
    state = await response.json();
    renderApp();
    if (new URLSearchParams(location.search).has("billing")) {
      tab = "plan";
      renderApp();
      toast(
        "Billing updates after Stripe confirms the subscription. Refresh if it is still pending.",
      );
      history.replaceState({}, "", "/app");
    }
  } catch (error) {
    root.innerHTML = `<main id="main" class="loading"><h1>We couldn’t open Resolve.</h1><p>${esc(error.message)}</p><a class="btn primary" href="/">Try again</a></main>`;
  }
}
boot();
