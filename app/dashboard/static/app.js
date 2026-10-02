/* ===== VIP Admin Dashboard — vanilla JS SPA ===== */
(() => {
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

/* ---------- i18n ---------- */
const I18N = {
  fa: {
    login_title: 'پنل مدیریت VIP', login_sub: 'توکن API مدیر را وارد کنید', login_btn: 'ورود',
    nav_overview: 'نمای کلی', nav_channels: 'کانال‌ها', nav_plans: 'پلن‌ها',
    nav_subs: 'اشتراک‌ها', nav_broadcast: 'پیام همگانی', logout: 'خروج',
    kpi_revenue_usd: 'درآمد (دلار)', kpi_revenue_xtr: 'درآمد (ستاره)', kpi_subs: 'اشتراک‌های فعال',
    kpi_channels: 'کانال‌ها', kpi_users: 'کاربران', kpi_plans: 'پلن‌ها',
    revenue_30d: 'درآمد ۳۰ روز اخیر', by_provider: 'پرداخت‌ها بر اساس درگاه',
    recent_payments: 'پرداخت‌های اخیر', add_channel: '+ افزودن کانال', add_plan: '+ افزودن پلن',
    export_csv: '⬇ خروجی CSV', broadcast_text: 'متن پیام', broadcast_channel: 'کانال (اختیاری)',
    send: 'ارسال', table_title: 'عنوان', table_chat_id: 'شناسه چت', table_active_subs: 'اشتراک فعال',
    table_revenue: 'درآمد', table_active: 'فعال', table_actions: 'عملیات', table_plan: 'پلن',
    table_days: 'روزها', table_price: 'قیمت', table_duration: 'مدت (روز)', table_channel: 'کانال',
    table_user: 'کاربر', table_status: 'وضعیت', table_created: 'تاریخ',
    edit: 'ویرایش', delete: 'حذف', save: 'ذخیره', cancel: 'انصراف',
    confirm_delete: 'مطمئن هستید؟', no_data: 'داده‌ای یافت نشد',
    page: 'صفحه', all_channels: 'همه کانال‌ها', days_left: 'روز باقی‌مانده',
    edit_channel: 'ویرایش کانال', edit_plan: 'ویرایش پلن', new_channel: 'کانال جدید', new_plan: 'پلن جدید',
    toast_saved: 'ذخیره شد ✓', toast_deleted: 'حذف شد ✓', toast_sent: 'ارسال شد ✓',
    toast_error: 'خطا رخ داد', title: 'عنوان', chat_id: 'شناسه عددی چت',
    price_usd: 'قیمت دلار', price_stars: 'قیمت ستاره', duration: 'مدت (روز)',
  },
  en: {
    login_title: 'VIP Admin Panel', login_sub: 'Enter your admin API token', login_btn: 'Sign in',
    nav_overview: 'Overview', nav_channels: 'Channels', nav_plans: 'Plans',
    nav_subs: 'Subscriptions', nav_broadcast: 'Broadcast', logout: 'Logout',
    kpi_revenue_usd: 'Revenue (USD)', kpi_revenue_xtr: 'Revenue (Stars)', kpi_subs: 'Active Subs',
    kpi_channels: 'Channels', kpi_users: 'Users', kpi_plans: 'Plans',
    revenue_30d: 'Revenue — last 30 days', by_provider: 'Payments by provider',
    recent_payments: 'Recent payments', add_channel: '+ Add channel', add_plan: '+ Add plan',
    export_csv: '⬇ Export CSV', broadcast_text: 'Message text', broadcast_channel: 'Channel (optional)',
    send: 'Send', table_title: 'Title', table_chat_id: 'Chat ID', table_active_subs: 'Active subs',
    table_revenue: 'Revenue', table_active: 'Active', table_actions: 'Actions', table_plan: 'Plan',
    table_days: 'Days', table_price: 'Price', table_duration: 'Duration (days)', table_channel: 'Channel',
    table_user: 'User', table_status: 'Status', table_created: 'Created',
    edit: 'Edit', delete: 'Delete', save: 'Save', cancel: 'Cancel',
    confirm_delete: 'Are you sure?', no_data: 'No data found',
    page: 'Page', all_channels: 'All channels', days_left: 'days left',
    edit_channel: 'Edit channel', edit_plan: 'Edit plan', new_channel: 'New channel', new_plan: 'New plan',
    toast_saved: 'Saved ✓', toast_deleted: 'Deleted ✓', toast_sent: 'Sent ✓',
    toast_error: 'An error occurred', title: 'Title', chat_id: 'Numeric chat ID',
    price_usd: 'Price USD', price_stars: 'Price Stars', duration: 'Duration (days)',
  },
};
let lang = localStorage.getItem('dash_lang') || 'fa';
const t = (k) => (I18N[lang] && I18N[lang][k]) || I18N.fa[k] || k;

function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr';
  $$('[data-i18n]').forEach((el) => { const k = el.dataset.i18n; if (I18N[lang][k]) el.textContent = I18N[lang][k]; });
  $('#login-title').textContent = t('login_title');
  $('#login-sub').textContent = t('login_sub');
  $('#login-btn').textContent = t('login_btn');
  $('#brand-name').textContent = 'VIP Admin';
  $('#lang-toggle').textContent = lang === 'fa' ? 'EN' : 'فا';
  $('#csv-export').textContent = t('export_csv');
  localStorage.setItem('dash_lang', lang);
  if (token) refreshCurrent();
}

/* ---------- API client ---------- */
let token = localStorage.getItem('admin_api_token') || '';

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-API-Token': token, ...(opts.headers || {}) },
  });
  if (res.status === 401) { doLogout(); throw new Error('unauthorized'); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}
const get = (p) => api(p);
const post = (p, b) => api(p, { method: 'POST', body: JSON.stringify(b || {}) });
const patch = (p, b) => api(p, { method: 'PATCH', body: JSON.stringify(b || {}) });
const del = (p) => api(p, { method: 'DELETE' });

/* ---------- toasts ---------- */
function toast(msg, kind = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
const errToast = (e) => toast(e.message || t('toast_error'), 'error');

/* ---------- modal ---------- */
function openModal(html) {
  $('#modal').innerHTML = html;
  $('#modal-backdrop').classList.remove('hidden');
}
function closeModal() { $('#modal-backdrop').classList.add('hidden'); }
$('#modal-backdrop').addEventListener('click', (e) => { if (e.target.id === 'modal-backdrop') closeModal(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('#modal-backdrop').classList.contains('hidden')) closeModal();
});

/* ---------- helpers ---------- */
const fmt = (n) => Number(n || 0).toLocaleString(lang === 'fa' ? 'fa-IR' : 'en-US');
const numFmt = () => new Intl.NumberFormat(lang === 'fa' ? 'fa-IR' : 'en-US');
const fmtNum = (n, dec = 0) => new Intl.NumberFormat(lang === 'fa' ? 'fa-IR' : 'en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(Number(n || 0));
// Gregorian calendar everywhere; numerals follow UI locale
const fmtDate = (s, withTime = false) => {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d)) return esc(s);
  return new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR-u-ca-gregory' : 'en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(d);
};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const skeletonRows = (cols = 4, rows = 4) =>
  `<tbody>${Array.from({ length: rows }, () => `<tr>${Array.from({ length: cols }, () => `<td><span class="skel"></span></td>`).join('')}</tr>`).join('')}</tbody>`;

function emptyState(cols, msg) {
  const label = msg || t('no_data');
  return `<tbody><tr><td colspan="${cols}" class="empty-cell">${EMPTY_SVG}
    <div class="empty-msg">${esc(label)}</div></td></tr></tbody>`;
}
const EMPTY_SVG = `<svg class="empty-ill" viewBox="0 0 200 120" fill="none" aria-hidden="true">
  <ellipse cx="100" cy="104" rx="62" ry="8" fill="rgba(124,92,255,.12)"/>
  <rect x="46" y="28" width="108" height="66" rx="10" stroke="rgba(124,92,255,.45)" stroke-width="2.5" fill="rgba(124,92,255,.06)"/>
  <line x1="60" y1="46" x2="118" y2="46" stroke="rgba(139,147,173,.55)" stroke-width="4" stroke-linecap="round"/>
  <line x1="60" y1="60" x2="140" y2="60" stroke="rgba(139,147,173,.4)" stroke-width="4" stroke-linecap="round"/>
  <line x1="60" y1="74" x2="100" y2="74" stroke="rgba(139,147,173,.3)" stroke-width="4" stroke-linecap="round"/>
  <circle cx="146" cy="34" r="18" fill="#0b1020" stroke="rgba(34,211,238,.6)" stroke-width="2.5"/>
  <path d="M139 34l5 5 9-10" stroke="#22d3ee" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

function countUp(el, target, decimals = 0) {
  const dur = 900, start = performance.now();
  const step = (now) => {
    const p = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (target * eased).toLocaleString(lang === 'fa' ? 'fa-IR' : 'en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ---------- SVG icon set ---------- */
const ICONS = {
  grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  megaphone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11v3a1 1 0 0 0 1 1h3l6 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M17.5 8.5a5 5 0 0 1 0 7"/><path d="M20.5 5.5a9 9 0 0 1 0 13"/></svg>',
  gem: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12l4 6-10 12L2 9z"/><path d="M2 9h20"/><path d="M12 21 8 9l4-6 4 6z"/></svg>',
  users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  rocket: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>',
  dollar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
  layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
};
const icon = (name) => `<span class="ico ico-svg" aria-hidden="true">${ICONS[name] || ''}</span>`;

/* Install inline SVG icons into static nav markup */
function installNavIcons() {
  const map = { overview: 'grid', channels: 'megaphone', plans: 'gem', subscriptions: 'users', broadcast: 'rocket' };
  $$('#nav .nav-item').forEach((btn) => {
    const name = map[btn.dataset.view];
    if (name) btn.querySelector('.ico').outerHTML = icon(name);
  });
}

/* ---------- Chart.js defaults ---------- */
function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.font.family = "'Vazirmatn', 'Inter', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = '#8b93ad';
}

function chartLocale() { return lang === 'fa' ? 'fa-IR' : 'en-US'; }

/* ---------- state ---------- */
let channels = [], plans = [], currentView = 'overview';
const subsState = { page: 1, status: '', channel: '' };
let revenueChart = null, providerChart = null;

/* ---------- login ---------- */
async function tryLogin(tok) {
  const res = await fetch('/api/v1/stats/summary', { headers: { 'X-API-Token': tok } });
  if (!res.ok) throw new Error('401');
  return res.json();
}

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const tok = $('#token-input').value.trim();
  const btn = $('#login-btn');
  btn.disabled = true; btn.textContent = '...';
  try {
    await tryLogin(tok);
    token = tok;
    localStorage.setItem('admin_api_token', tok);
    enterApp();
  } catch (_) {
    const el = $('#login-error');
    el.textContent = lang === 'fa' ? 'توکن نامعتبر است' : 'Invalid token';
    el.classList.remove('hidden');
  } finally {
    btn.disabled = false; btn.textContent = t('login_btn');
  }
});
$('#login-lang-toggle').addEventListener('click', () => { lang = lang === 'fa' ? 'en' : 'fa'; applyLang(); });
$('#lang-toggle').addEventListener('click', () => { lang = lang === 'fa' ? 'en' : 'fa'; applyLang(); });
$('#logout-btn').addEventListener('click', doLogout);
function doLogout() {
  token = ''; localStorage.removeItem('admin_api_token');
  $('#app').classList.add('hidden');
  $('#login-screen').classList.remove('hidden');
}
function enterApp() {
  $('#login-screen').classList.add('hidden');
  $('#app').classList.remove('hidden');
  refreshCurrent();
}

/* ---------- router ---------- */
$$('#nav .nav-item').forEach((btn) => btn.addEventListener('click', () => {
  if (btn.dataset.view === currentView) return;
  $$('#nav .nav-item').forEach((b) => b.classList.remove('active'));
  btn.classList.add('active');
  currentView = btn.dataset.view;
  const target = $(`#view-${currentView}`);
  $$('.view').forEach((v) => { if (v !== target) v.classList.add('hidden'); });
  // smooth fade/slide transition
  target.classList.remove('hidden');
  target.classList.remove('view-enter'); void target.offsetWidth;
  target.classList.add('view-enter');
  refreshCurrent();
}));

function refreshCurrent() {
  ({ overview: loadOverview, channels: loadChannels, plans: loadPlans, subscriptions: loadSubs, broadcast: loadBroadcastView }[currentView] || loadOverview)();
}

/* ================= OVERVIEW ================= */
async function loadOverview() {
  const kpis = $('#kpis');
  kpis.innerHTML = Array.from({ length: 4 }, (_, i) => `<div class="glass kpi"><div class="kpi-label"><span class="skel"></span></div><div class="kpi-value"><span class="skel"></span></div><span class="kpi-icon">•</span></div>`).join('');
  try {
    const s = await get('/api/v1/stats/summary');
    let users = '?';
    try { users = fmt((await get('/api/v1/admin/users/count')).count); } catch (_) {}
    const cards = [
      { label: t('kpi_revenue_usd'), val: s.revenue_usd, dec: 2, ico: 'dollar' },
      { label: t('kpi_revenue_xtr'), val: s.revenue_xtr, dec: 0, ico: 'star' },
      { label: t('kpi_subs'), val: s.active_subscriptions, dec: 0, ico: 'users' },
      { label: t('kpi_channels'), val: s.channels, dec: 0, ico: 'megaphone' },
      { label: t('kpi_users'), val: typeof users === 'number' ? users : users, dec: 0, ico: 'user', raw: users },
      { label: t('kpi_plans'), val: s.plans, dec: 0, ico: 'layers' },
    ];
    kpis.innerHTML = cards.map((c, i) => `
      <div class="glass kpi"><div class="kpi-label">${esc(c.label)}</div>
      <div class="kpi-value" id="kpi-${i}">0</div>${icon(c.ico)}</div>`).join('');
    cards.forEach((c, i) => { if (typeof c.val === 'number') countUp($(`#kpi-${i}`), c.val, c.dec); else $(`#kpi-${i}`).textContent = c.val; });
    kpiLabelFix(kpis, cards);
  } catch (e) { errToast(e); }

  loadRevenueChart();
  loadProviderChart();
  loadRecentPayments();
  const lu = $('#last-updated');
  if (lu) {
    const now = new Date();
    lu.textContent = (lang === 'fa' ? 'آخرین به‌روزرسانی: ' : 'Last updated: ') +
      now.toLocaleTimeString(chartLocale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
}
function kpiLabelFix() {}

async function loadRevenueChart() {
  try {
    const data = await get('/api/v1/admin/revenue/daily?days=30');
    const rows = Array.isArray(data) ? data : (data.items || data.daily || []);
    const labels = rows.map((r) => fmtDate(r.date || r.day));
    const vals = rows.map((r) => r.total_usd ?? r.revenue_usd ?? r.amount ?? 0);
    if (revenueChart) revenueChart.destroy();
    revenueChart = new Chart($('#revenueChart'), {
      type: 'line',
      data: { labels, datasets: [{ label: 'USD', data: vals, borderColor: '#7c5cff', backgroundColor: 'rgba(124,92,255,.18)', fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2.5 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        locale: chartLocale(),
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 6, autoSkip: true, maxRotation: 0, minRotation: 0 }, grid: { color: 'rgba(255,255,255,.04)' } },
          y: { ticks: { callback: (v) => fmtNum(v, 0) }, grid: { color: 'rgba(255,255,255,.04)' } },
        },
      },
    });
  } catch (e) { /* endpoint may not exist yet */ }
}

async function loadProviderChart() {
  try {
    const data = await get('/api/v1/admin/payments/by-provider');
    const rows = Array.isArray(data) ? data : (data.items || []);
    const labels = rows.map((r) => r.provider || r.name);
    const vals = rows.map((r) => r.count ?? r.total ?? 0);
    if (providerChart) providerChart.destroy();
    providerChart = new Chart($('#providerChart'), {
      type: 'doughnut',
      data: { labels, datasets: [{ data: vals, backgroundColor: ['#7c5cff', '#22d3ee', '#34d399', '#fbbf24', '#f87171'], borderWidth: 0, hoverOffset: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false, locale: chartLocale(),
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12, padding: 14, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const total = (ctx.dataset.data || []).reduce((a, b) => a + Number(b || 0), 0);
                const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : '0';
                const row = rows[ctx.dataIndex] || {};
                const cur = row.total_amount != null
                  ? ` — ${fmtNum(row.total_amount, 2)} ${row.currency || ''}` : '';
                return ` ${ctx.label}: ${fmt(ctx.parsed)} (${fmtNum(pct, 1)}%)${cur}`;
              },
            },
          },
        },
        cutout: '62%',
      },
    });
  } catch (e) { /* endpoint may not exist yet */ }
}

async function loadRecentPayments() {
  const tbl = $('#recent-payments-table');
  const head = `<thead><tr><th>${t('table_user')}</th><th>${t('table_price')}</th><th>${t('table_status')}</th><th>${t('table_created')}</th></tr></thead>`;
  tbl.innerHTML = head + skeletonRows(4, 4);
  try {
    const data = await get('/api/v1/admin/payments?limit=10');
    const rows = Array.isArray(data) ? data : (data.items || []);
    if (!rows.length) { tbl.innerHTML = head + emptyState(4); return; }
    tbl.innerHTML = head + `<tbody>${rows.map((p) => `<tr>
      <td>${esc(p.user_title || p.username || p.user_telegram_id || '—')}</td>
      <td>${fmt(p.amount)} ${esc(p.currency || '')}</td>
      <td><span class="badge ${p.status === 'paid' ? 'green' : 'gray'}">${esc(p.status)}</span></td>
      <td class="muted">${fmtDate(p.created_at, true)}</td></tr>`).join('')}</tbody>`;
  } catch (_) {
    tbl.innerHTML = head + emptyState(4);
  }
}

/* ================= CHANNELS ================= */
async function loadChannels() {
  const tbl = $('#channels-table');
  tbl.innerHTML = `<thead><tr><th>${t('table_title')}</th><th>${t('table_chat_id')}</th><th>${t('table_active_subs')}</th><th>${t('table_revenue')}</th><th>${t('table_active')}</th><th>${t('table_actions')}</th></tr></thead>${skeletonRows(6, 3)}`;
  try {
    const data = await get('/api/v1/admin/channels');
    channels = Array.isArray(data) ? data : (data.items || []);
    if (!channels.length) { tbl.innerHTML += emptyState(6); return; }
    tbl.innerHTML += `<tbody>${channels.map((c) => {
      const st = c.stats || {};
      return `<tr>
        <td>${esc(c.title)}</td>
        <td class="muted">${esc(c.telegram_chat_id ?? c.chat_id)}</td>
        <td>${fmt(st.active_subscriptions ?? c.active_subscriptions ?? 0)}</td>
        <td>$${fmt(st.revenue_usd ?? c.revenue_usd ?? 0)}</td>
        <td><button class="toggle ${c.is_active ? 'on' : ''}" data-toggle="${c.id}" aria-label="toggle"></button></td>
        <td>
          <button class="btn small-btn" data-edit-ch="${c.id}">${t('edit')}</button>
          <button class="btn small-btn btn-danger" data-del-ch="${c.id}">${t('delete')}</button>
        </td></tr>`;
    }).join('')}</tbody>`;
    $$('[data-toggle]', tbl).forEach((b) => b.addEventListener('click', async () => {
      const id = b.dataset.toggle;
      const ch = channels.find((c) => String(c.id) === id);
      try { await patch(`/api/v1/admin/channels/${id}`, { is_active: !ch.is_active }); ch.is_active = !ch.is_active; b.classList.toggle('on'); toast(t('toast_saved')); }
      catch (e) { errToast(e); }
    }));
    $$('[data-del-ch]', tbl).forEach((b) => b.addEventListener('click', async () => {
      if (!confirm(t('confirm_delete'))) return;
      try { await del(`/api/v1/admin/channels/${b.dataset.delCh}`); toast(t('toast_deleted')); loadChannels(); }
      catch (e) { errToast(e); }
    }));
    $$('[data-edit-ch]', tbl).forEach((b) => b.addEventListener('click', () => {
      const ch = channels.find((c) => String(c.id) === b.dataset.editCh);
      openModal(`<h3>${t('edit_channel')}</h3>
        <label>${t('table_title')}</label><input id="m-title" value="${esc(ch.title)}">
        <div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-backdrop').classList.add('hidden')">${t('cancel')}</button>
        <button class="btn btn-primary" id="m-save">${t('save')}</button></div>`);
      $('#m-save').addEventListener('click', async () => {
        try { await patch(`/api/v1/admin/channels/${ch.id}`, { title: $('#m-title').value }); closeModal(); toast(t('toast_saved')); loadChannels(); }
        catch (e) { errToast(e); }
      });
    }));
  } catch (e) {
    tbl.innerHTML += emptyState(6);
  }
}

$('#add-channel-btn').addEventListener('click', () => {
  openModal(`<h3>${t('new_channel')}</h3>
    <label>${t('table_title')}</label><input id="m-title" placeholder="@mychannel">
    <label>${t('chat_id')}</label><input id="m-chat" placeholder="-1001234567890">
    <div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-backdrop').classList.add('hidden')">${t('cancel')}</button>
    <button class="btn btn-primary" id="m-save">${t('save')}</button></div>`);
  $('#m-save').addEventListener('click', async () => {
    try {
      await post('/api/v1/channels', { title: $('#m-title').value, telegram_chat_id: $('#m-chat').value });
      closeModal(); toast(t('toast_saved')); loadChannels();
    } catch (e) { errToast(e); }
  });
});

/* ================= PLANS ================= */
async function loadPlans() {
  const wrap = $('#plans-groups');
  wrap.innerHTML = `<div class="glass card">${skeletonRows(5, 3)}</div>`;
  try {
    const [pData] = await Promise.all([get('/api/v1/admin/plans')]);
    plans = Array.isArray(pData) ? pData : (pData.items || []);
    try { const c = await get('/api/v1/admin/channels'); channels = Array.isArray(c) ? c : (c.items || []); } catch (_) {}
    if (!plans.length) { wrap.innerHTML = `<div class="glass card">${emptyState(1)}</div>`; return; }
    const byCh = {};
    plans.forEach((p) => { (byCh[p.channel_id] ||= []).push(p); });
    wrap.innerHTML = Object.entries(byCh).map(([cid, list]) => {
      const ch = channels.find((c) => String(c.id) === String(cid));
      return `<div class="group-title">${icon('megaphone')} ${esc(ch ? ch.title : `#${cid}`)}</div>
      <div class="glass card"><div class="table-scroll"><table>
        <thead><tr><th>${t('table_plan')}</th><th>${t('table_duration')}</th><th>${t('table_price')}</th><th>${t('table_active')}</th><th>${t('table_actions')}</th></tr></thead>
        <tbody>${list.map((p) => `<tr>
          <td>${esc(p.title)}</td>
          <td>${fmt(p.duration_days)}</td>
          <td>$${fmt(p.price_usd)} / ⭐${fmt(p.price_stars)}</td>
          <td><span class="badge ${p.is_active ? 'green' : 'gray'}">${p.is_active ? '✓' : '—'}</span></td>
          <td>
            <button class="btn small-btn" data-edit-pl="${p.id}">${t('edit')}</button>
            <button class="btn small-btn btn-danger" data-del-pl="${p.id}">${t('delete')}</button>
          </td></tr>`).join('')}</tbody></table></div></div>`;
    }).join('');
    $$('[data-del-pl]', wrap).forEach((b) => b.addEventListener('click', async () => {
      if (!confirm(t('confirm_delete'))) return;
      try { await del(`/api/v1/admin/plans/${b.dataset.delPl}`); toast(t('toast_deleted')); loadPlans(); }
      catch (e) { errToast(e); }
    }));
    $$('[data-edit-pl]', wrap).forEach((b) => b.addEventListener('click', () => planModal(plans.find((p) => String(p.id) === b.dataset.editPl))));
  } catch (e) {
    wrap.innerHTML = `<div class="glass card">${emptyState(1)}</div>`;
  }
}

function planModal(p) {
  const isNew = !p;
  openModal(`<h3>${isNew ? t('new_plan') : t('edit_plan')}</h3>
    <label>${t('table_channel')}</label>
    <select id="m-ch">${channels.map((c) => `<option value="${c.id}" ${p && p.channel_id === c.id ? 'selected' : ''}>${esc(c.title)}</option>`).join('')}</select>
    <label>${t('table_title')}</label><input id="m-title" value="${esc(p ? p.title : '')}">
    <label>${t('duration')}</label><input id="m-dur" type="number" value="${p ? p.duration_days : 30}">
    <label>${t('price_usd')}</label><input id="m-usd" type="number" step="0.01" value="${p ? p.price_usd : 0}">
    <label>${t('price_stars')}</label><input id="m-xtr" type="number" value="${p ? p.price_stars : 0}">
    <div class="modal-actions"><button class="btn" onclick="document.getElementById('modal-backdrop').classList.add('hidden')">${t('cancel')}</button>
    <button class="btn btn-primary" id="m-save">${t('save')}</button></div>`);
  $('#m-save').addEventListener('click', async () => {
    const body = {
      channel_id: Number($('#m-ch').value), title: $('#m-title').value,
      duration_days: Number($('#m-dur').value), price_usd: Number($('#m-usd').value), price_stars: Number($('#m-xtr').value),
    };
    try {
      if (isNew) await post('/api/v1/channels/plans', body);
      else await patch(`/api/v1/admin/plans/${p.id}`, body);
      closeModal(); toast(t('toast_saved')); loadPlans();
    } catch (e) { errToast(e); }
  });
}
$('#add-plan-btn').addEventListener('click', () => { if (!channels.length) get('/api/v1/admin/channels').then((d) => { channels = Array.isArray(d) ? d : (d.items || []); }).catch(() => {}).finally(planModal); else planModal(); });

/* ================= SUBSCRIPTIONS ================= */
function daysBadge(d) {
  if (d == null) return '<span class="badge gray">—</span>';
  if (d <= 3) return `<span class="badge red">${d}</span>`;
  if (d <= 7) return `<span class="badge yellow">${d}</span>`;
  return `<span class="badge green">${d}</span>`;
}

async function loadSubs() {
  const tbl = $('#subs-table');
  tbl.innerHTML = `<thead><tr><th>#</th><th>${t('table_user')}</th><th>${t('table_channel')}</th><th>${t('table_plan')}</th><th>${t('table_status')}</th><th>${t('days_left')}</th><th>${t('table_created')}</th></tr></thead>${skeletonRows(7, 6)}`;
  const q = new URLSearchParams({ page: subsState.page, page_size: 15 });
  if (subsState.status) q.set('status', subsState.status);
  if (subsState.channel) q.set('channel_id', subsState.channel);
  try {
    const data = await get(`/api/v1/admin/subscriptions?${q}`);
    const items = data.items || data.subscriptions || [];
    const total = data.total ?? items.length;
    const pages = Math.max(1, Math.ceil(total / 15));
    $('#subs-page-info').textContent = `${t('page')} ${subsState.page} / ${pages} — ${fmt(total)}`;
    if (!items.length) { tbl.innerHTML += emptyState(7); return; }
    tbl.innerHTML += `<tbody>${items.map((s) => `<tr>
      <td class="muted">${s.id}</td>
      <td>${esc(s.user_title || s.username || s.telegram_user_id || '—')}</td>
      <td>${esc(s.channel_title || s.channel_id || '—')}</td>
      <td>${esc(s.plan_title || s.plan_id || '—')}</td>
      <td><span class="badge ${s.status === 'active' ? 'green' : s.status === 'expired' ? 'red' : 'gray'}">${esc(s.status)}</span></td>
      <td>${daysBadge(s.days_remaining)}</td>
      <td class="muted">${fmtDate(s.starts_at || s.created_at)}</td>
    </tr>`).join('')}</tbody>`;
  } catch (e) {
    tbl.innerHTML += emptyState(7);
  }
  loadChannelFilter();
}

async function loadChannelFilter() {
  const sel = $('#channel-filter');
  if (sel.options.length) return;
  try {
    const d = await get('/api/v1/admin/channels');
    channels = Array.isArray(d) ? d : (d.items || []);
    sel.innerHTML = `<option value="">${t('all_channels')}</option>` + channels.map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join('');
    $('#broadcast-channel').innerHTML = `<option value="">${t('all_channels')}</option>` + channels.map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join('');
  } catch (_) {}
}

$('#channel-filter').addEventListener('change', (e) => { subsState.channel = e.target.value; subsState.page = 1; loadSubs(); });
$$('#status-chips .chip').forEach((c) => c.addEventListener('click', () => {
  $$('#status-chips .chip').forEach((x) => x.classList.remove('active'));
  c.classList.add('active');
  subsState.status = c.dataset.status; subsState.page = 1;
  loadSubs();
}));
$('#subs-refresh').addEventListener('click', loadSubs);
$('#subs-prev').addEventListener('click', () => { if (subsState.page > 1) { subsState.page--; loadSubs(); } });
$('#subs-next').addEventListener('click', () => { subsState.page++; loadSubs(); });

/* ================= BROADCAST ================= */
function loadBroadcastView() { loadChannelFilter(); }
$('#broadcast-send').addEventListener('click', async () => {
  const text = $('#broadcast-text').value.trim();
  if (!text) return toast(lang === 'fa' ? 'متن پیام خالی است' : 'Message is empty', 'error');
  const ch = $('#broadcast-channel').value;
  const body = { text };
  if (ch) body.channel_id = Number(ch);
  // confirmation dialog before sending
  const chTitle = ch ? ($('#broadcast-channel').selectedOptions[0]?.textContent || ch) : t('all_channels');
  const confirmMsg = lang === 'fa'
    ? `ارسال پیام همگانی به «${chTitle}»؟

${text}`
    : `Send broadcast to "${chTitle}"?

${text}`;
  if (!confirm(confirmMsg)) return;
  let logId = null;
  try {
    const created = await post('/api/v1/admin/broadcast', body);
    logId = created && (created.id ?? created.broadcast_id ?? created.log_id) || null;
    if (logId != null) {
      // confirm-send via botadmin endpoint; response carries sent/failed counts
      const res = await post(`/api/v1/botadmin/broadcast/${logId}/send`);
      const sent = res?.sent ?? res?.success_count ?? '?';
      const failed = res?.failed ?? res?.fail_count ?? 0;
      toast(lang === 'fa' ? `ارسال شد: ${fmt(sent)} موفق، ${fmt(failed)} ناموفق ✓` : `Sent: ${fmt(sent)} ok, ${fmt(failed)} failed ✓`);
    } else {
      toast(t('toast_sent'));
    }
    $('#broadcast-text').value = '';
  } catch (e) { errToast(e); }
});

/* ---------- auto refresh (60s, only when tab visible) ---------- */
setInterval(() => {
  if (document.visibilityState !== 'visible' || !token) return;
  if (currentView === 'overview') {
    loadOverview();
  } else if (currentView === 'subscriptions') {
    loadSubs();
  }
}, 60000);

/* ---------- boot ---------- */
installNavIcons();
applyChartDefaults();
applyLang();
if (token) {
  tryLogin(token).then(enterApp).catch(doLogout);
}
})();
