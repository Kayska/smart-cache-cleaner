/* 智能缓存清理器 - 前端逻辑 */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const el = {
    rows: $('#rows'), table: $('#table'), tableWrap: $('#tableWrap'), empty: $('#empty'),
    emptyTitle: $('#emptyTitle'), emptyText: $('#emptyText'), emptyScan: $('#emptyScan'),
    resCount: $('#resCount'), q: $('#q'), headCheck: $('#headCheck'),
    statTotal: $('#statTotal'), statCount: $('#statCount'), statSel: $('#statSel'), statSelN: $('#statSelN'),
    statFreed: $('#statFreed'), statDisk: $('#statDisk'), meterBar: $('#meterBar'),
    presets: $('#presets'), customList: $('#customList'), customEmpty: $('#customEmpty'),
    days: $('#days'), daysInput: $('#daysInput'), prune: $('#prune'),
    scanBtn: $('#scanBtn'), cleanBtn: $('#cleanBtn'), binBtn: $('#binBtn'), addFolder: $('#addFolder'),
    results: $('.results'), tickerDot: $('#tickerDot'), tickerText: $('#tickerText'),
    logPanel: $('#logPanel'), logList: $('#logList'), logToggle: $('#logToggle'), logClear: $('#logClear'), logCount: $('#logCount'),
    toasts: $('#toasts'), modal: $('#modal'), modalTitle: $('#modalTitle'), modalBody: $('#modalBody'),
    modalOk: $('#modalOk'), modalCancel: $('#modalCancel'),
    bgBtn: $('#bgBtn'), bgClear: $('#bgClear'), bgImg: $('#bgImg'), drives: $('#drives'), swatches: $('#swatches'),
  };

  const S = {
    api: null,
    files: new Map(),
    checked: new Set(),
    sort: { key: 'size', dir: -1 },
    query: '',
    scanning: false,
    cleaning: false,
    autoCheck: true,
    idleDays: 7,
    theme: 'aurora',
    prune: true,
    presets: [],
    custom: [],
    freed: 0,
    logs: [],
    animations: {},
  };

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const LV = { 2: '高', 1: '中', 0: '低' };

  function human(n) {
    n = Number(n) || 0;
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? `${n.toFixed(0)} B` : `${n.toFixed(n >= 100 ? 0 : 1)} ${units[i]}`);
  }
  const fmtDate = (ts) => {
    const d = new Date(ts * 1000);
    const p = (x) => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  // 数字滚动：把节点上的数值平滑过渡到目标值
  function countTo(node, target, fmt = human) {
    const from = S.animations[node.id]?.value ?? 0;
    cancelAnimationFrame(S.animations[node.id]?.raf);
    const t0 = performance.now(), dur = 700;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      const v = from + (target - from) * e;
      node.textContent = fmt(v);
      if (k < 1) S.animations[node.id] = { value: v, raf: requestAnimationFrame(step) };
      else S.animations[node.id] = { value: target };
    };
    S.animations[node.id] = { value: from, raf: requestAnimationFrame(step) };
  }

  // ---------- API 桥 ----------
  async function bridge() {
    // api 对象会先于方法出现，必须等到具体方法挂上才算就绪
    for (let i = 0; i < 600; i++) {
      const api = window.pywebview && window.pywebview.api;
      if (api && typeof api.get_state === 'function') return api;
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error('无法连接到本地后端');
  }
  const call = (name, ...args) => {
    const fn = S.api && S.api[name];
    if (typeof fn !== 'function') return Promise.reject(new Error(`后端方法不可用：${name}`));
    return fn(...args);
  };

  window.__push = (batch) => {
    if (!batch) return;
    if (batch.files) addFiles(batch.files);
    if (batch.log) batch.log.forEach(addLog);
    if (batch.error) { toast('err', '扫描出错', batch.error); setTicker('err', batch.error); }
    if (batch.done) onDone(batch.done);
  };

  // ---------- 日志 / 状态 ----------
  function addLog(entry) {
    S.logs.push(entry);
    if (S.logs.length > 500) S.logs.splice(0, S.logs.length - 500);
    const li = document.createElement('li');
    const d = new Date(entry.t * 1000);
    li.innerHTML = `<time>${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}</time><span>${esc(entry.text)}</span>`;
    el.logList.appendChild(li);
    el.logList.scrollTop = el.logList.scrollHeight;
    el.logCount.textContent = S.logs.length;
    el.tickerText.textContent = entry.text;
    el.tickerText.title = entry.text;
  }
  const setTicker = (state, text) => { el.tickerDot.className = `dot ${state}`; el.tickerText.textContent = text; el.tickerText.title = text; };

  function toast(kind, title, msg, action) {
    const t = document.createElement('div');
    t.className = `toast ${kind}`;
    t.innerHTML = `<div class="ico">${{ ok: '✓', warn: '!', err: '×' }[kind] || 'i'}</div><div class="msg"><b>${esc(title)}</b>${msg ? `<div style="color:var(--muted);margin-top:2px">${esc(msg)}</div>` : ''}</div>`;
    if (action) {
      const b = document.createElement('button');
      b.className = 'btn sm ghost act';
      b.textContent = action.label;
      b.onclick = () => { action.run(); dismiss(); };
      t.appendChild(b);
    }
    const dismiss = () => { t.classList.add('out'); setTimeout(() => t.remove(), 320); };
    t.addEventListener('click', (e) => { if (!e.target.closest('.act')) dismiss(); });
    el.toasts.appendChild(t);
    setTimeout(dismiss, 5000);
  }

  function confirmDialog({ title, bodyHtml, okText }) {
    return new Promise((resolve) => {
      el.modalTitle.textContent = title;
      el.modalBody.innerHTML = bodyHtml;
      el.modalOk.textContent = okText || '确定';
      el.modal.hidden = false;
      const done = (v) => { el.modal.hidden = true; el.modalOk.onclick = el.modalCancel.onclick = el.modal.onclick = document.onkeydown = null; resolve(v); };
      el.modalOk.onclick = () => done(true);
      el.modalCancel.onclick = () => done(false);
      el.modal.onclick = (e) => { if (e.target === el.modal) done(false); };
      document.onkeydown = (e) => { if (e.key === 'Escape') done(false); };
      el.modalOk.focus();
    });
  }

  // ---------- 表格 ----------
  const ICON_LOCATE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l18-8-8 18-2.5-7.5z"/><path d="M10.5 13.5L21 3"/></svg>';
  const splitPath = (p) => {
    const i = Math.max(p.lastIndexOf('\\'), p.lastIndexOf('/'));
    return i < 0 ? ['', p] : [p.slice(0, i).replace(/[\\/]+$/, ''), p.slice(i + 1)];
  };

  function rowHtml(f) {
    const [dir, name] = splitPath(f.path);
    return `<td class="c-check"><label class="cb"><input type="checkbox" aria-label="选择 ${esc(name)}"><i></i></label></td>` +
      `<td class="c-file"><div class="name" title="${esc(f.path)}">${esc(name)}</div><div class="dir" title="${esc(dir)}">${esc(dir)}</div></td>` +
      `<td class="c-level"><span class="chip-lv lv${f.level}">${LV[f.level]}</span></td>` +
      `<td class="c-cat">${esc(f.category)}</td>` +
      `<td class="c-size">${human(f.size)}</td>` +
      `<td class="c-time">${fmtDate(f.mtime)}</td>` +
      `<td class="c-go"><button class="icon-btn" title="在资源管理器中定位" data-locate="${f.id}">${ICON_LOCATE}</button></td>`;
  }

  function addFiles(list) {
    const frag = document.createDocumentFragment();
    for (const f of list) {
      S.files.set(f.id, f);
      const tr = document.createElement('tr');
      tr.dataset.id = f.id;
      tr.innerHTML = rowHtml(f);
      // 入场动画只在首次插入时播一次，排序重排时不再重播
      tr.style.animation = 'rowIn .35s var(--ease) both';
      tr.addEventListener('animationend', () => { tr.style.animation = ''; }, { once: true });
      if (S.autoCheck && f.level >= 1) { S.checked.add(f.id); tr.classList.add('checked'); tr.querySelector('input').checked = true; }
      frag.appendChild(tr);
    }
    el.rows.appendChild(frag);
    scheduleSort();
    refreshStats();
  }

  let sortTimer = 0;
  function scheduleSort() { clearTimeout(sortTimer); sortTimer = setTimeout(applyOrder, 120); }

  function applyOrder() {
    const { key, dir } = S.sort;
    const get = {
      size: (f) => f.size, mtime: (f) => f.mtime, level: (f) => f.level, path: (f) => f.path.toLowerCase(),
    }[key];
    const ids = [...S.files.values()].sort((a, b) => (get(a) > get(b) ? dir : get(a) < get(b) ? -dir : 0)).map((f) => f.id);
    el.rows.append(...ids.map((id) => el.rows.querySelector(`tr[data-id="${id}"]`)));
    document.querySelectorAll('th.sortable').forEach((th) => {
      const active = th.dataset.sort === S.sort.key;
      th.classList.toggle('asc', active && dir === 1);
      th.classList.toggle('desc', active && dir === -1);
    });
  }

  function applyFilter() {
    const q = S.query.trim().toLowerCase();
    let shown = 0;
    for (const tr of el.rows.children) {
      const f = S.files.get(Number(tr.dataset.id));
      const hit = !q || f.path.toLowerCase().includes(q);
      tr.hidden = !hit;
      if (hit) shown++;
    }
    el.resCount.textContent = q ? `${shown} / ${S.files.size}` : String(S.files.size);
  }

  function setChecked(id, on) {
    const tr = el.rows.querySelector(`tr[data-id="${id}"]`);
    if (!tr) return;
    if (on) S.checked.add(id); else S.checked.delete(id);
    tr.classList.toggle('checked', on);
    tr.querySelector('input').checked = on;
  }

  function visibleIds() {
    return [...el.rows.children].filter((tr) => !tr.hidden).map((tr) => Number(tr.dataset.id));
  }

  function bulk(kind) {
    S.autoCheck = false;
    const ids = S.query ? visibleIds() : [...S.files.keys()];
    for (const id of ids) {
      const on = kind === 'all' || (kind === 'invert' && !S.checked.has(id)) || (kind === 'high' && S.files.get(id).level === 2);
      setChecked(id, on);
    }
    refreshStats();
  }

  function refreshStats() {
    const list = [...S.files.values()];
    const total = list.reduce((a, f) => a + f.size, 0);
    const selList = [...S.checked].filter((id) => S.files.has(id));
    const sel = selList.reduce((a, id) => a + S.files.get(id).size, 0);
    countTo(el.statTotal, total);
    countTo(el.statSel, sel);
    countTo(el.statFreed, S.freed);
    el.statCount.textContent = S.files.size ? `${S.files.size} 个候选文件，${S.query ? `筛选出 ${visibleIds().length} 个` : '高 / 中建议已默认勾选'}` : (S.scanning ? '正在扫描…' : '还没有扫描结果');
    el.statSelN.textContent = `${selList.length} 个文件`;
    el.meterBar.style.width = `${total ? Math.min(100, (sel / total) * 100) : 0}%`;
    $('#selSize').textContent = human(sel);
    $('#selN').textContent = `已勾选 ${selList.length} 个文件`;
    el.cleanBtn.disabled = !selList.length || S.cleaning || S.scanning;
    if (!S.query) el.resCount.textContent = String(S.files.size);
    const has = list.length > 0;
    el.empty.classList.toggle('hide', has);
    el.empty.classList.toggle('show-btn', !has && !S.scanning);
    if (!has) {
      el.emptyTitle.textContent = S.query ? '没有匹配的文件' : (S.scanning ? '正在扫描…' : '还没有扫描结果');
      el.emptyText.textContent = S.query ? '换一个关键词试试。' : '点击「开始扫描」，列出超过闲置天数没再使用的缓存文件。';
      el.emptyScan.style.display = S.scanning ? 'none' : '';
    }
    const all = list.length && selList.length === list.length;
    el.headCheck.checked = all;
    el.headCheck.indeterminate = selList.length > 0 && !all;
  }

  function renderDrives(list) {
    el.drives.innerHTML = (list || []).slice(0, 4).map((d) => {
      const p = d.total ? (d.used / d.total) * 100 : 0;
      return `<div class="drive ${d.free / Math.max(d.total, 1) < 0.12 ? 'warn' : ''}" title="${d.drive}: 已用 ${human(d.used)} / 共 ${human(d.total)}"><span class="ring" style="--p:${p.toFixed(0)}"></span><b>${d.drive}:</b><span>可用 ${human(d.free)}</span></div>`;
    }).join('');
    const c = (list || []).find((d) => d.drive === 'C') || (list || [])[0];
    if (c) el.statDisk.textContent = `${c.drive}: 盘当前可用 ${human(c.free)}，清空回收站后才会增加`;
  }

  // ---------- 设置区 ----------
  function renderDays() {
    const preset = [3, 7, 14, 30].includes(S.idleDays);
    el.days.querySelectorAll('button').forEach((b) => b.classList.toggle('on', Number(b.dataset.days) === S.idleDays));
    el.daysInput.classList.toggle('on', !preset);
    // 预设值由按钮高亮表示，输入框只在自己填了数值时才显示
    el.daysInput.value = preset ? '' : S.idleDays;
  }

  async function setDays(n) {
    n = Math.max(1, Math.min(365, Math.round(Number(n))));
    if (!n) { renderDays(); return; }
    S.idleDays = n;
    renderDays();
    await call('save_settings', { idle_days: n });
    if (S.files.size) toast('warn', '闲置天数已改为 ' + n + ' 天', '需要重新扫描才会生效');
  }

  const ICON_CHECK = '<svg viewBox="0 0 16 16"><path d="M3 8.5l3.2 3.2L13 5"/></svg>';
  const ICON_FOLDER = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';

  function renderPresets() {
    el.presets.innerHTML = S.presets.map((p) => `<li><button class="chip ${p.on ? 'on' : ''} ${p.missing ? 'missing' : ''}" data-key="${p.key}" title="${esc(p.path)}"><span class="box">${ICON_CHECK}</span><span>${esc(p.label)}<small>${esc(p.hint)}</small></span>${p.risk ? '<span class="tag">重建慢</span>' : ''}</button></li>`).join('');
  }

  function renderCustom() {
    el.customList.innerHTML = S.custom.map((p, i) => `<li>${ICON_FOLDER}<span>${esc(p)}</span><button class="icon-btn" data-rm="${i}" title="移除">${'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'}</button></li>`).join('');
    el.customEmpty.style.display = S.custom.length ? 'none' : '';
  }

  async function persist() {
    await call('save_settings', {
      idle_days: S.idleDays, prune_empty: S.prune, custom: S.custom, theme: S.theme,
      presets: Object.fromEntries(S.presets.map((p) => [p.key, p.on])),
    });
  }

  // ---------- 主题 ----------
  const THEMES = [
    { id: 'aurora', name: '极光 · 荧光绿', color: '#c8ff4d', bg: '#141a10' },
    { id: 'violet', name: '紫罗兰 · 幻夜紫', color: '#c4a5ff', bg: '#171226' },
    { id: 'glacier', name: '雾蓝 · 冰川青', color: '#6ee7ff', bg: '#0b1b23' },
    { id: 'ember', name: '暖阳 · 落日橙', color: '#ffb37b', bg: '#221510' },
    { id: 'daylight', name: '晨曦 · 浅色', color: '#7cb518', bg: '#eef1f4' },
  ];

  function applyTheme(id) {
    if (!THEMES.some((t) => t.id === id)) id = 'aurora';
    S.theme = id;
    document.body.classList.add('theming');
    document.body.dataset.theme = id;
    clearTimeout(applyTheme._t);
    applyTheme._t = setTimeout(() => document.body.classList.remove('theming'), 420);
    document.querySelectorAll('.swatch').forEach((b) => {
      const on = b.dataset.theme === id;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    });
  }

  function renderSwatches() {
    el.swatches.innerHTML = THEMES.map((t) =>
      `<button class="swatch" data-theme="${t.id}" title="${t.name}" aria-label="${t.name}" aria-pressed="false" style="background:${t.bg}"><i style="background:linear-gradient(145deg, ${t.color}, ${t.bg})"></i></button>`).join('');
  }

  el.swatches.onclick = async (e) => {
    const b = e.target.closest('.swatch');
    if (!b || b.dataset.theme === S.theme) return;
    applyTheme(b.dataset.theme);
    await call('save_settings', { theme: S.theme });
  };

  // ---------- 扫描 / 清理 ----------
  function setScanning(on) {
    S.scanning = on;
    el.results.classList.toggle('scanning', on);
    el.scanBtn.disabled = S.cleaning;
    el.scanBtn.classList.toggle('stop', on);
    el.scanBtn.querySelector('.btn-text').textContent = on ? '停止扫描' : '开始扫描';
    el.cleanBtn.disabled = true;
    el.emptyScan.disabled = on;
    refreshStats();
  }

  async function stopScan() {
    if (!S.scanning) return;
    setTicker('busy', '正在停止扫描…');
    await call('stop_scan');
  }

  async function startScan() {
    if (S.cleaning) return;
    if (S.scanning) return stopScan();
    const any = S.presets.some((p) => p.on) || S.custom.length;
    if (!any) return toast('warn', '还没有选择扫描位置', '至少勾选一个预设位置，或添加自定义文件夹');
    const r = await call('start_scan');
    if (!r.ok) {
      if (r.error === 'noroots') toast('warn', '勾选的位置都不存在', '这些缓存目录在本机上还没有生成，换一个位置试试');
      return;
    }
    S.files.clear(); S.checked.clear(); S.autoCheck = true;
    el.rows.innerHTML = ''; el.q.value = ''; S.query = '';
    setScanning(true);
    setTicker('busy', `正在扫描 ${r.roots} 个位置…`);
    refreshStats();
    try { await call('refresh_disk'); } catch (e) { /* 磁盘信息不影响扫描 */ }
  }

  function onDone(d) {
    setScanning(false);
    if (d.stopped) { setTicker('ok', `已停止，共找到 ${d.count} 个文件`); toast('warn', '扫描已停止', `已列出 ${d.count} 个文件，共 ${human(d.bytes)}`); }
    else { setTicker('ok', `扫描完成，${d.count} 个文件，共 ${human(d.bytes)}`); toast('ok', '扫描完成', `${d.count} 个文件，共 ${human(d.bytes)}${d.capped ? '（已达显示上限）' : ''}`); }
    refreshStats();
  }

  async function cleanSelected() {
    if (S.cleaning || S.scanning) return;
    const ids = [...S.checked].filter((id) => S.files.has(id));
    if (!ids.length) return;
    const byLv = { 2: 0, 1: 0, 0: 0 };
    let size = 0, max = 0;
    for (const id of ids) { const f = S.files.get(id); byLv[f.level]++; size += f.size; if (f.size > max) max = f.size; }
    const ok = await confirmDialog({
      title: '把这些文件移入回收站？',
      okText: `移入回收站（${human(size)}）`,
      bodyHtml: `<div class="big"><div><strong>${human(size)}</strong><span>共 ${ids.length} 个文件</span></div><div><strong>${byLv[2]}</strong><span>高建议</span></div><div><strong>${byLv[1] + byLv[0]}</strong><span>中 / 低建议</span></div></div>` +
        `<ul><li>每批 10 个处理，逐个核对；遇到被占用的文件会立即停下</li><li>只处理文件本身，不会删除源码、依赖或项目目录</li>${S.prune ? '<li>清理后被清空的空文件夹会一并移除</li>' : ''}</ul>` +
        `<div class="callout">进回收站的文件仍占用磁盘空间。确认没有需要找回的文件后，清空回收站才会真正释放空间。</div>`,
    });
    if (!ok) return;

    S.cleaning = true;
    S.autoCheck = false;
    el.cleanBtn.disabled = true; el.scanBtn.disabled = true;
    el.cleanBtn.classList.add('busy');
    setTicker('busy', '正在分批移入回收站…');
    try {
      const r = await call('clean', ids);
      for (const id of r.ok || []) { S.files.delete(id); S.checked.delete(id); const tr = el.rows.querySelector(`tr[data-id="${id}"]`); if (tr) tr.remove(); }
      for (const f of r.failed || []) S.checked.delete(f.id);
      S.freed += r.freed || 0;
      const failed = (r.failed || []).length;
      if ((r.ok || []).length) toast('ok', `已移入回收站 ${human(r.freed || 0)}`, `${(r.ok || []).length} 个文件${r.dirs_removed ? `，另移除 ${r.dirs_removed} 个空文件夹` : ''}`, { label: '打开回收站', run: () => call('open_recycle_bin') });
      if (failed) toast('err', `${failed} 个文件未能移入`, '通常是被程序占用，关闭对应程序后再试');
      setTicker(failed ? 'err' : 'ok', `本次移入回收站 ${human(r.freed || 0)}，失败 ${failed} 个`);
    } catch (e) {
      toast('err', '清理失败', String(e && e.message || e));
      setTicker('err', '清理失败');
    } finally {
      S.cleaning = false;
      el.cleanBtn.classList.remove('busy');
      el.scanBtn.disabled = false;
      refreshStats();
      renderDrives(await call('refresh_disk'));
    }
  }

  // ---------- 背景 ----------
  function applyBg(dataUrl) {
    if (dataUrl) { el.bgImg.src = dataUrl; $('.bg').classList.add('has-img'); }
    else { el.bgImg.removeAttribute('src'); $('.bg').classList.remove('has-img'); }
  }

  async function chooseBg() {
    const r = await call('choose_background');
    if (r.ok) { applyBg(r.bg); toast('ok', '背景已更换', r.name); }
    else if (r.reason === 'type') toast('warn', '不支持的图片格式', '请选择 jpg / png / webp / bmp / gif');
    else if (r.reason === 'error') toast('err', '设置背景失败', r.error);
  }

  // ---------- 事件 ----------
  el.scanBtn.onclick = startScan;
  el.emptyScan.onclick = startScan;
  el.cleanBtn.onclick = cleanSelected;
  el.binBtn.onclick = () => call('open_recycle_bin');
  el.bgBtn.onclick = chooseBg;
  el.bgClear.onclick = async () => { await call('clear_background'); applyBg(''); toast('ok', '已恢复默认极光背景'); };
  el.addFolder.onclick = async () => {
    const r = await call('add_folder');
    if (r.ok && r.path) {
      if (S.custom.includes(r.path)) return toast('warn', '这个文件夹已经在列表里');
      S.custom.push(r.path); renderCustom(); await persist();
      toast('ok', '已添加文件夹', r.path);
    }
  };
  el.q.oninput = () => { S.query = el.q.value; applyFilter(); refreshStats(); };
  document.querySelector('.btn-group').onclick = (e) => { const b = e.target.closest('button'); if (b) bulk(b.dataset.sel); };
  document.querySelectorAll('th.sortable').forEach((th) => th.onclick = () => {
    const k = th.dataset.sort;
    S.sort = { key: k, dir: S.sort.key === k ? -S.sort.dir : (k === 'path' ? 1 : -1) };
    applyOrder();
  });
  el.headCheck.onchange = () => bulk(el.headCheck.checked ? 'all' : 'none');
  el.days.onclick = (e) => { const b = e.target.closest('button'); if (b) setDays(Number(b.dataset.days)); };
  el.daysInput.onchange = () => setDays(el.daysInput.value);
  el.daysInput.onkeydown = (e) => { if (e.key === 'Enter') el.daysInput.blur(); };
  el.presets.onclick = async (e) => {
    const b = e.target.closest('.chip'); if (!b) return;
    const p = S.presets.find((x) => x.key === b.dataset.key); if (!p) return;
    p.on = !p.on; b.classList.toggle('on', p.on); await persist();
  };
  el.customList.onclick = async (e) => {
    const b = e.target.closest('[data-rm]'); if (!b) return;
    S.custom.splice(Number(b.dataset.rm), 1); renderCustom(); await persist();
  };
  el.prune.onchange = async () => { S.prune = el.prune.checked; await persist(); };
  el.logToggle.onclick = () => { const open = el.logPanel.hidden; el.logPanel.hidden = !open; el.logToggle.setAttribute('aria-expanded', String(open)); };
  el.logClear.onclick = () => { S.logs = []; el.logList.innerHTML = ''; el.logCount.textContent = '0'; };
  el.rows.addEventListener('change', (e) => {
    const input = e.target.closest('input[type=checkbox]'); if (!input) return;
    const tr = input.closest('tr'); S.autoCheck = false;
    setChecked(Number(tr.dataset.id), input.checked); refreshStats();
  });
  el.rows.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-locate]');
    if (b) { const r = await call('reveal', Number(b.dataset.locate)); if (!r.ok) toast('warn', '文件已不在原位置'); }
  });
  el.tickerText.parentElement.addEventListener('click', (e) => { if (e.target === el.tickerText || e.target === el.tickerDot) el.logToggle.click(); });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { el.q.value = ''; S.query = ''; applyFilter(); refreshStats(); el.q.blur(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); el.q.focus(); el.q.select(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a' && document.activeElement !== el.q) { e.preventDefault(); bulk('all'); }
  });

  // 光标光晕
  let mx = 0;
  document.addEventListener('pointermove', (e) => {
    if (mx) return;
    mx = requestAnimationFrame(() => { document.body.style.setProperty('--mx', `${e.clientX}px`); document.body.style.setProperty('--my', `${e.clientY}px`); mx = 0; });
  });

  // 启动
  (async () => {
    try {
      S.api = await bridge();
      const st = await call('get_state');
      S.presets = st.presets || [];
      S.presets.forEach((p) => { p.missing = !p.exists; });
      S.custom = st.custom || [];
      S.idleDays = st.idle_days || 7;
      S.prune = !!st.prune_empty;
      S.theme = st.theme || 'aurora';
      renderSwatches();
      applyTheme(S.theme);
      el.prune.checked = S.prune;
      renderDays(); renderPresets(); renderCustom(); renderDrives(st.disk); applyBg(st.bg);
      refreshStats();
      setTicker('ok', `就绪 · 闲置阈值 ${S.idleDays} 天 · 清理一律进回收站`);
      addLog({ t: Math.floor(Date.now() / 1000), text: `就绪。默认只列超过 ${S.idleDays} 天没使用的缓存文件，高 / 中建议已默认勾选。` });
    } catch (e) {
      setTicker('err', '启动失败：' + (e.message || e));
      toast('err', '后端没有连上', String(e.message || e));
    }
  })();
})();
