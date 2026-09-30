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
      $('btn-submit').disabled = true;
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
    const nav = document.querySelector('.primary-nav');
    if (nav) nav.classList.remove('open');
  });
});

const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
if (mobileMenuBtn) {
  mobileMenuBtn.addEventListener('click', () => {
    document.querySelector('.primary-nav').classList.toggle('open');
  });
}

// Utility
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const text = await r.text();
  const j = text ? JSON.parse(text) : {};
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

function debounce(f, ms) { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => f(...args), ms); }; }

$('amount').addEventListener('input', debounce(() => {
  if (document.getElementById('panel-2').classList.contains('active')) {
    fetchQuote();
  }
}, 500));

// Wizard Logic
function wizardNext(step) {
  if (step === 2) {
    if (!$('corridor').checkValidity() || !$('sender').checkValidity() || !$('benName').checkValidity() || !$('vpa').checkValidity() || !$('purpose').checkValidity()) {
      alert("Please fill all mandatory fields.");
      return;
    }
    fetchQuote();
  }
  if (step === 3) {
    if (!$('amount').checkValidity()) { alert("Please enter a valid amount."); return; }
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
  $('amount').value = '1000';
  $('confirm-check').checked = false;
  $('btn-submit').disabled = true;
  $('c-ref').innerText = '--';
}

// Quote Fetching
async function fetchQuote() {
  // Validate input before calling API
  if (!$('amount').value || isNaN($('amount').value)) return;

  $('quote-loader').innerText = 'Calculating live quote...';
  $('quote-data').style.display = 'none';
  $('quote-loader').style.display = 'block';
  $('btn-to-review').disabled = true;
  
  try {
    const ccyNode = $('corridor').options[$('corridor').selectedIndex];
    const dec = parseInt(ccyNode.dataset.dec);
    const amtMinor = parseFloat($('amount').value) * Math.pow(10, dec);
    
    currentQuote = await api(`/api/quote?corridor=${$('corridor').value}&amountMinor=${Math.round(amtMinor)}`);
    
    $('q-send').innerText = `${formatAmt(currentQuote.sendAmountMinor, dec)} ${currentQuote.sendCurrency}`;
    $('q-fee').innerText = `${formatAmt(currentQuote.feeTotalMinor, dec)} ${currentQuote.sendCurrency}`;
    $('q-fund').innerText = `${formatAmt(currentQuote.sendAmountMinor, dec)} ${currentQuote.sendCurrency}`;
    $('q-rate').innerText = `1 ${currentQuote.sendCurrency} = ${(currentQuote.effectiveRateMicro / 1e6).toFixed(4)} INR`;
    $('q-recv').innerText = formatInr(currentQuote.receivePaise);
    
    $('quote-loader').style.display = 'none';
    $('quote-data').style.display = 'block';
    $('btn-to-review').disabled = false;
  } catch (e) {
    $('quote-loader').innerText = `Error: ${e.message}`;
  }
}

function populateReview() {
  $('r-sender').innerText = $('sender').value;
  $('r-purpose').innerText = $('purpose').options[$('purpose').selectedIndex].text;
  $('r-benName').innerText = $('benName').value;
  $('r-vpa').innerText = $('vpa').value;
  $('r-corridor').innerText = $('corridor').value;
  
  // Clone quote data without duplicating IDs
  const quoteClone = $('quote-data').cloneNode(true);
  quoteClone.removeAttribute('id');
  quoteClone.querySelectorAll('[id]').forEach(el => el.removeAttribute('id'));
  quoteClone.style.display = 'block';
  $('r-financials').innerHTML = '';
  $('r-financials').appendChild(quoteClone);
}

$('confirm-check').addEventListener('change', (e) => {
  $('btn-submit').disabled = !e.target.checked;
});

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
      scenario: $('scenario').value
    };
    
    const res = await api("/api/remittances", { method: "POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
    const rid = res.id;
    $('c-ref').innerText = rid;
    
    // Auto-run steps
    await api(`/api/remittances/${rid}/run`, { method: "POST" });
    
    wizardNext(4);
  } catch (e) {
    alert(`Transfer failed: ${e.message}`);
    $('btn-submit').disabled = false;
  } finally {
    $('btn-submit').innerText = 'Submit Transfer';
  }
});

// Tracking
async function loadTransferList() {
  // Don't load list if detail view is already showing
  if ($('track-detail-view').style.display === 'block') return;
  
  $('track-list-view').style.display = 'block';
  $('track-detail-view').style.display = 'none';
  const tbody = $('tx-table-body');
  try {
    const list = await api("/api/remittances");
    if (!list.length) { tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No transfers found.</td></tr>`; return; }
    
    window._transferList = list;
    renderTransferTable(list);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Error loading transfers.</td></tr>`;
  }
}

function renderTransferTable(list) {
  const tbody = $('tx-table-body');
  tbody.innerHTML = list.map(r => `
    <tr>
      <td class="mono">${r.id}</td>
      <td>${r.corridor}</td>
      <td><span class="badge ${getStatusClass(r.status)}">${r.status}</span></td>
      <td>${new Date(r.updatedAt * 1000).toLocaleString()}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="openDetail('${r.id}')">View</button></td>
    </tr>
  `).join("");
}

// Search functionality for transfer list
$('search-tx').addEventListener('input', debounce(() => {
  const q = $('search-tx').value.toLowerCase().trim();
  if (!window._transferList) return;
  if (!q) { renderTransferTable(window._transferList); return; }
  const filtered = window._transferList.filter(r =>
    r.id.toLowerCase().includes(q) ||
    r.corridor.toLowerCase().includes(q) ||
    r.status.toLowerCase().includes(q)
  );
  renderTransferTable(filtered);
}, 300));

function getStatusClass(status) {
  if (status === 'SETTLED') return 'b-success';
  if (['REFUNDED', 'BLOCKED', 'FAILED', 'BENEFICIARY_REJECTED', 'EXPIRED'].includes(status)) return 'b-err';
  if (status === 'HELD') return 'b-warn';
  return 'b-info';
}

function viewTransferDetail() {
  const rid = $('c-ref').innerText;
  // Switch to track tab without triggering list load
  document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector('[data-tab="track"]').classList.add('active');
  $('tab-track').classList.add('active');
  $('breadcrumb').innerText = 'Home / Track transfer';
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
    alert("Error loading details");
    closeDetail();
  }
}

function closeDetail() {
  $('track-list-view').style.display = 'block';
  $('track-detail-view').style.display = 'none';
  loadTransferList();
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
    loadComplianceDesk();
  } catch(e) {
    alert(e.message);
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
function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${location.host}/ws/events`);
  ws.onmessage = (msg) => {
    try {
      const e = JSON.parse(msg.data);
      if (e.type === 'state_change') {
        if (document.getElementById('track-detail-view').style.display === 'block' && document.getElementById('dt-ref').innerText === e.remittanceId) {
          openDetail(e.remittanceId);
        }
      }
    } catch(err){}
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}
connectWS();
