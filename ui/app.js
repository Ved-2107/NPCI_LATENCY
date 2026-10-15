const $ = id => document.getElementById(id);
let currentQuote = null;

// Routing / Tabs
document.querySelectorAll('.nav-link').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    e.target.classList.add('active');
    const tabId = e.target.dataset.tab;
    $(`tab-${tabId}`).classList.add('active');
    $('breadcrumb').innerText = `Home / ${e.target.innerText}`;
    
    // Reset wizard if going to Send tab
    if (tabId === 'send') {
      wizardNext(1);
      $('amount').value = '1000';
      $('confirm-check').checked = false;
      $('btn-submit').disabled = false;
      $('btn-submit').innerText = 'Submit Transfer';
    }
    
    // Lazy load data based on tab
    if (tabId === 'track') {
      if (!document.getElementById('track-detail-view').style.display || document.getElementById('track-detail-view').style.display === 'none') {
        loadTransferList();
      }
    }
    if (tabId === 'compliance') loadComplianceDesk();
    if (tabId === 'insights') loadInsights();
    
    // Close mobile menu if open
    document.querySelector('.primary-nav').classList.remove('open');
  });
});

document.querySelector('.mobile-menu-btn').addEventListener('click', () => {
  document.querySelector('.primary-nav').classList.toggle('open');
});

// Utility
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail || "API Error");
  return j;
}

const formatAmt = (minor, decimals) => (minor / Math.pow(10, decimals)).toLocaleString('en-US', {minimumFractionDigits: decimals});
const formatInr = paise => "₹" + (paise / 100).toLocaleString('en-IN', {minimumFractionDigits: 2});

// Init
async function init() {
  try {
    const h = await api("/api/health");
    $('f-mode').innerText = h.ledgerMode === 'drunix' ? 'Connected to Drunix Network' : 'Demo Mode (In-Memory Ledger)';
    
    const corridors = await api("/api/corridors");
    const cSelect = $('corridor');
    cSelect.innerHTML = Object.entries(corridors).map(([k,v]) => `<option value="${k}" data-ccy="${v.ccy}" data-dec="${v.decimals}">${k} - ${v.name}</option>`).join("");
    cSelect.addEventListener('change', (e) => {
      const opt = e.target.options[e.target.selectedIndex];
      $('amt-ccy').innerText = opt.dataset.ccy;
    });
    $('amt-ccy').innerText = corridors[cSelect.value].ccy;
    
  } catch (e) {
    console.error("Init error", e);
    $('f-mode').innerText = "System Offline";
    $('f-mode').previousElementSibling.style.background = "var(--err-txt)";
  }
}

function debounce(f, ms) { let t; return ()=> { clearTimeout(t); t=setTimeout(f,ms); }; }

$('amount').addEventListener('input', debounce(() => {
  if (document.getElementById('panel-2').classList.contains('active')) {
    fetchQuote();
  }
}, 500));

// Toast Notification System
function showToast(message, type = "info", duration = 4000) {
  let container = $('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Wizard Logic
function wizardNext(step) {
  if (step === 2) {
    if (!$('corridor').checkValidity() || !$('sender').checkValidity() || !$('benName').checkValidity() || !$('vpa').checkValidity()) {
      showToast("Please fill all mandatory fields.", "warn");
      return;
    }
    fetchQuote();
  }
  if (step === 3) {
    if (!$('amount').checkValidity()) { 
      showToast("Please enter a valid amount.", "warn"); 
      return; 
    }
    populateReview();
  }
  
  document.querySelectorAll('.w-step').forEach((el, i) => {
    if (i < step) el.classList.add('active'); else el.classList.remove('active');
  });
  document.querySelectorAll('.w-panel').forEach(el => el.classList.remove('active'));
  $(`panel-${step}`).classList.add('active');
}

function resetWizard() {
  wizardNext(1);
  $('confirm-check').checked = false;
  $('btn-submit').disabled = true;
  $('c-ref').innerText = '--';
  $('c-amount').innerText = '--';
  $('c-payout-ref').innerText = '--';
}

// Quote Fetching with Binding Quote & Countdown
let quoteCountdownInterval = null;

async function fetchQuote() {
  $('quote-data').style.display = 'none';
  $('quote-loader').style.display = 'block';
  $('btn-to-review').disabled = true;
  if (quoteCountdownInterval) clearInterval(quoteCountdownInterval);
  
  try {
    const ccyNode = $('corridor').options[$('corridor').selectedIndex];
    const dec = parseInt(ccyNode.dataset.dec);
    const amtMinor = parseFloat($('amount').value) * Math.pow(10, dec);
    
    // Obtain binding quote
    currentQuote = await api("/api/quotes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corridor: $('corridor').value, amountMinor: Math.round(amtMinor) })
    });
    
    $('q-send').innerText = `${formatAmt(currentQuote.sendAmountMinor, dec)} ${currentQuote.sendCurrency}`;
    $('q-fee').innerText = `${formatAmt(currentQuote.feeTotalMinor, dec)} ${currentQuote.sendCurrency}`;
    $('q-fund').innerText = `${formatAmt(currentQuote.sendAmountMinor + currentQuote.feeTotalMinor, dec)} ${currentQuote.sendCurrency}`;
    $('q-rate').innerText = `1 ${currentQuote.sendCurrency} = ${(currentQuote.effectiveRateMicro / 1e6).toFixed(4)} INR`;
    $('q-recv').innerText = formatInr(currentQuote.receivePaise);
    
    // Countdown
    let remaining = Math.max(0, Math.floor(currentQuote.expiresAt - (Date.now() / 1000)));
    const timerEl = $('q-lock-timer');
    if (timerEl) {
      timerEl.innerText = `Locked for ${remaining}s`;
      quoteCountdownInterval = setInterval(() => {
        remaining--;
        if (remaining > 0) {
          timerEl.innerText = `Locked for ${remaining}s`;
        } else {
          timerEl.innerText = "Quote expired (refreshing...)";
          clearInterval(quoteCountdownInterval);
          fetchQuote();
        }
      }, 1000);
    }
    
    $('quote-loader').style.display = 'none';
    $('quote-data').style.display = 'block';
    $('btn-to-review').disabled = false;
  } catch (e) {
    $('quote-loader').innerText = `Error: ${e.message}`;
    showToast(`Error fetching quote: ${e.message}`, "error");
  }
}

function populateReview() {
  $('r-sender').innerText = $('sender').value;
  $('r-purpose').innerText = $('purpose').options[$('purpose').selectedIndex].text;
  $('r-benName').innerText = $('benName').value;
  $('r-vpa').innerText = $('vpa').value;
  $('r-corridor').innerText = $('corridor').value;
  
  $('r-financials').innerHTML = $('quote-data').innerHTML;
}

$('confirm-check').addEventListener('change', (e) => {
  $('btn-submit').disabled = !e.target.checked;
});

function updateConfirmationView(result) {
  const status = result.status;
  const iconWrapper = $('c-icon-wrapper');
  const title = $('c-title');
  const desc = $('c-desc');
  const badge = $('c-badge');
  
  badge.className = `badge ${getStatusClass(status)}`;
  badge.innerText = status;
  $('c-ref').innerText = result.id;
  $('c-corridor').innerText = result.corridor || $('corridor').value;
  $('c-amount').innerText = result.quote ? formatInr(result.quote.receivePaise) : '--';
  $('c-payout-ref').innerText = result.payoutReference || 'N/A';
  
  if (status === 'SETTLED') {
    iconWrapper.innerHTML = `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#15803D" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><path d="M22 4L12 14.01l-3-3"></path></svg>`;
    title.innerText = 'Transfer Settled Successfully';
    desc.innerText = 'Funds have been credited instantly to the beneficiary UPI account.';
    showToast(`Transfer ${result.id} settled successfully!`, 'success');
  } else if (status === 'HELD') {
    iconWrapper.innerHTML = `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#B45309" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    title.innerText = 'Transfer Flagged for Compliance Review';
    desc.innerText = 'Compliance hold triggered (risk threshold or corridor daily cap exceeded). Transfer is in HELD state pending Maker-Checker review.';
    showToast(`Transfer ${result.id} is HELD for review`, 'warn');
  } else if (status === 'BLOCKED') {
    iconWrapper.innerHTML = `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#B91C1C" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
    title.innerText = 'Transfer Blocked by Policy';
    desc.innerText = 'Transaction was blocked due to sanctions policy or terminal compliance rules.';
    showToast(`Transfer ${result.id} was BLOCKED`, 'error');
  } else if (status === 'REFUNDED') {
    iconWrapper.innerHTML = `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#B45309" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>`;
    title.innerText = 'Transfer Refunded';
    desc.innerText = 'Beneficiary rejected or payout rail unavailable. Funds reversed back to remitter.';
    showToast(`Transfer ${result.id} refunded to remitter`, 'warn');
  } else {
    iconWrapper.innerHTML = `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>`;
    title.innerText = `Transfer Status: ${status}`;
    desc.innerText = 'Transfer has progressed through the RemitChain state machine.';
    showToast(`Transfer status: ${status}`, 'info');
  }
}

// Submit Transfer
$('btn-submit').addEventListener('click', async () => {
  $('btn-submit').disabled = true;
  $('btn-submit').innerText = 'Processing...';
  
  try {
    const ccyNode = $('corridor').options[$('corridor').selectedIndex];
    const dec = parseInt(ccyNode.dataset.dec);
    const payload = {
      corridor: $('corridor').value,
      senderName: $('sender').value,
      beneficiaryName: $('benName').value,
      beneficiaryVpa: $('vpa').value,
      purpose: $('purpose').value,
      amountMinor: Math.round(parseFloat($('amount').value) * Math.pow(10, dec)),
      scenario: $('scenario').value,
      quoteId: currentQuote ? currentQuote.quoteId : undefined
    };
    
    const res = await api("/api/remittances", { 
      method: "POST", 
      headers: { "Content-Type": "application/json" }, 
      body: JSON.stringify(payload) 
    });
    const rid = res.id;
    $('c-ref').innerText = rid;
    
    // Auto-run steps
    const runRes = await api(`/api/remittances/${rid}/run`, { method: "POST" });
    
    updateConfirmationView(runRes);
    wizardNext(4);
  } catch (e) {
    showToast(`Transfer failed: ${e.message}`, "error");
  } finally {
    $('btn-submit').innerText = 'Submit Transfer';
  }
});

// Tracking
let transferCache = [];

function renderTransferRows(items) {
  const tbody = $('tx-table-body');
  if (!items || !items.length) {
    const q = ($('search-tx') ? $('search-tx').value : '').trim();
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${q ? "No transfers match your search query." : "No transfers found."}</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(r => `
    <tr>
      <td class="mono">${r.id}</td>
      <td>${r.corridor}</td>
      <td><span class="badge ${getStatusClass(r.status)}">${r.status}</span></td>
      <td>${new Date(r.updatedAt * 1000).toLocaleString()}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="openDetail('${r.id}')">View</button></td>
    </tr>
  `).join("");
}

function filterTransfers() {
  const searchInput = $('search-tx');
  const q = (searchInput ? searchInput.value : '').trim().toLowerCase();
  if (!q) {
    renderTransferRows(transferCache);
    return;
  }
  const filtered = transferCache.filter(r =>
    (r.id && r.id.toLowerCase().includes(q)) ||
    (r.status && r.status.toLowerCase().includes(q)) ||
    (r.corridor && r.corridor.toLowerCase().includes(q))
  );
  renderTransferRows(filtered);
}

// Wire up search input listener
if ($('search-tx')) {
  $('search-tx').addEventListener('input', filterTransfers);
}

async function loadTransferList() {
  $('track-list-view').style.display = 'block';
  $('track-detail-view').style.display = 'none';
  const tbody = $('tx-table-body');
  try {
    const list = await api("/api/remittances");
    transferCache = list || [];
    filterTransfers();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Error loading transfers.</td></tr>`;
  }
}

function getStatusClass(status) {
  if (status === 'SETTLED') return 'b-success';
  if (['REFUNDED', 'BLOCKED', 'FAILED', 'BENEFICIARY_REJECTED', 'EXPIRED'].includes(status)) return 'b-err';
  if (status === 'HELD') return 'b-warn';
  return 'b-info';
}

function viewTransferDetail() {
  const rid = $('c-ref').innerText;
  document.querySelector('[data-tab="track"]').click();
  openDetail(rid);
}

async function openDetail(rid) {
  $('track-list-view').style.display = 'none';
  $('track-detail-view').style.display = 'block';
  $('dt-ref').innerText = rid;
  
  try {
    const r = await api(`/api/remittances/${rid}`);
    $('dt-status').innerText = r.status;
    $('dt-status').className = `badge ${getStatusClass(r.status)}`;
    
    // Render timeline
    const allSteps = [
      {id: "CREATE", label: "Remittance Created", org: "Remitting bank"},
      {id: "LOCK_QUOTE", label: "Exchange Rate Locked", org: "Remitting bank"},
      {id: "SCREEN", label: "Compliance Screening", org: "Remitting bank"},
      {id: "VERIFY_BENEFICIARY", label: "Beneficiary Verification", org: "Payout rail"},
      {id: "CONFIRM_FUNDING", label: "Funding Confirmed", org: "Remitting bank"},
      {id: "SUBMIT_PAYOUT", label: "Payout Submitted", org: "Payout rail"},
      {id: "SETTLE_PAYOUT", label: "Settlement Complete", org: "Payout rail"}
    ];
    
    const trailMap = {};
    r.trail.forEach(t => trailMap[t.step] = t);
    
    let html = '';
    for (let s of allSteps) {
      const done = !!trailMap[s.id];
      html += `
        <div class="tl-item ${done ? 'done' : ''}">
          <div class="tl-dot"></div>
          <div class="tl-content">
            <div class="tl-title">${s.label} ${done ? '✓' : ''}</div>
            <div class="tl-meta">
              ${done ? new Date(trailMap[s.id].ts * 1000).toLocaleTimeString() : 'Pending'}
              <span class="tl-org">${s.org}</span>
            </div>
          </div>
        </div>
      `;
    }
    
    // Check terminal exceptions
    const exc = r.trail.find(t => ['BLOCKED', 'HELD', 'REFUND', 'FAIL_PAYOUT'].includes(t.step));
    
    if (r.status === 'HELD') {
      html += `
        <div class="tl-item done">
          <div class="tl-dot" style="background:var(--warn-txt); border-color:var(--warn-txt);"></div>
          <div class="tl-content">
            <div class="tl-title" style="color:var(--warn-txt);">Transfer Held for Review</div>
            <div class="tl-meta">Action Required in Compliance Desk</div>
          </div>
        </div>
      `;
    } else if (exc) {
      html += `
        <div class="tl-item done">
          <div class="tl-dot" style="background:var(--err-txt); border-color:var(--err-txt);"></div>
          <div class="tl-content">
            <div class="tl-title" style="color:var(--err-txt);">${exc.step}</div>
            <div class="tl-meta">${new Date(exc.ts * 1000).toLocaleTimeString()}</div>
          </div>
        </div>
      `;
    }
    
    $('dt-timeline').innerHTML = html;
    
    if (r.failReason) {
      $('dt-error').style.display = 'block';
      $('dt-error').innerText = `Exception: ${r.failReason}`;
    } else {
      $('dt-error').style.display = 'none';
    }
    
    // Render proofs
    $('dt-proofs').innerHTML = r.trail.map(t => `
      <div class="proof-item">
        <b>${t.step}</b><br/>
        TxID: ${t.txId}
      </div>
    `).join("");
    
  } catch (e) {
    showToast("Error loading details: " + e.message, "error");
    closeDetail();
  }
}

function closeDetail() {
  $('track-list-view').style.display = 'block';
  $('track-detail-view').style.display = 'none';
}

// Compliance Desk
async function loadComplianceDesk() {
  const tbody = $('comp-table-body');
  try {
    const list = await api("/api/remittances");
    const held = list.filter(r => r.status === 'HELD');
    if (!held.length) { tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No transfers pending review.</td></tr>`; return; }
    
    tbody.innerHTML = held.map(r => `
      <tr>
        <td class="mono">${r.id}</td>
        <td><b style="color:var(--warn-txt)">${r.riskScore}</b>/100</td>
        <td>${(r.reasonCodes || []).join(", ") || "Manual review"}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="reviewHold('${r.id}', true)">Approve</button>
          <button class="btn btn-secondary btn-sm" style="color:var(--err-txt); border-color:var(--err-txt);" onclick="reviewHold('${r.id}', false)">Reject</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Error loading compliance data.</td></tr>`;
  }
}

async function reviewHold(rid, approve) {
  if (!confirm(`Are you sure you want to ${approve ? 'approve' : 'reject'} transfer ${rid}?`)) return;
  try {
    await api(`/api/remittances/${rid}/review`, { method: "POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({approve}) });
    if (approve) await api(`/api/remittances/${rid}/run`, { method: "POST" });
    showToast(`Transfer ${rid} ${approve ? 'approved and resumed' : 'rejected'}`, approve ? 'success' : 'warn');
    loadComplianceDesk();
  } catch(e) {
    showToast(e.message, "error");
  }
}

// Insights
async function loadInsights() {
  try {
    const s = await api("/api/stats");
    $('kpi-total').innerText = s.total;
    $('kpi-settled').innerText = s.settled;
    $('kpi-held').innerText = s.held;
    $('kpi-time').innerText = s.avgSettleSeconds ? `${s.avgSettleSeconds}s` : '--';
    
    if (s.avgCostBps) {
      const pct = s.avgCostBps / 100;
      $('val-rc').innerText = `${pct.toFixed(2)}%`;
      $('bar-rc').style.width = `${Math.min(100, (pct / 6.5) * 100)}%`;
    }
  } catch(e) {
    console.error(e);
  }
}

init();

let ws;
let wsRetryDelay = 1000;
const MAX_WS_RETRY_DELAY = 30000;

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  try {
    ws = new WebSocket(`${protocol}//${location.host}/ws/events`);
  } catch (err) {
    console.warn("WebSocket initialization error:", err);
    scheduleWsReconnect();
    return;
  }

  ws.onopen = () => {
    wsRetryDelay = 1000;
    console.info("WebSocket connected to event stream");
  };

  ws.onmessage = (msg) => {
    try {
      const e = JSON.parse(msg.data);
      if (e.type === 'state_change') {
        const detailView = document.getElementById('track-detail-view');
        if (detailView && detailView.style.display === 'block' && document.getElementById('dt-ref').innerText === e.remittanceId) {
          openDetail(e.remittanceId);
        }
        // If track list is open, refresh or update cache
        const listView = document.getElementById('track-list-view');
        if (listView && listView.style.display !== 'none') {
          const item = transferCache.find(r => r.id === e.remittanceId);
          if (item) {
            item.status = e.status;
            item.updatedAt = Math.floor(Date.now() / 1000);
            filterTransfers();
          }
        }
      }
    } catch(err) {
      console.warn("Error parsing WebSocket message:", err);
    }
  };

  ws.onerror = (err) => {
    console.warn("WebSocket stream error:", err);
  };

  ws.onclose = () => {
    scheduleWsReconnect();
  };
}

function scheduleWsReconnect() {
  const jitter = Math.random() * 500;
  const delay = Math.min(wsRetryDelay + jitter, MAX_WS_RETRY_DELAY);
  wsRetryDelay = Math.min(wsRetryDelay * 1.5, MAX_WS_RETRY_DELAY);
  setTimeout(connectWS, delay);
}

connectWS();

